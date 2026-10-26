"""Parlo: hold or tap a shortcut, speak, and the words appear where you are typing.

Threads: the main thread runs the window (pywebview), a Tk thread runs the app core and the
recording pill, and the speech model runs in its own process (engine_worker.py).
"""
import ctypes
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
WEB = Path(__file__).resolve().parent / "web"

logging.basicConfig(filename=DATA / "parlo.log", level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bark")
if sys.stdout is None or sys.stderr is None:  # pythonw has no console; libraries still print
    sys.stdout = sys.stderr = open(DATA / "console.log", "a", encoding="utf-8", buffering=1)

import tkinter as tk  # noqa: E402

import webview  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import ai  # noqa: E402
import audio  # noqa: E402
import models  # noqa: E402
import secrets_store  # noqa: E402
import textout  # noqa: E402
from engine_client import EngineClient  # noqa: E402
from hotkeys import HotkeyManager  # noqa: E402
from overlay import Overlay  # noqa: E402
from speech import Speaker  # noqa: E402
from store import DEFAULTS, History, Notes, Settings, start_sync, stop_sync  # noqa: E402
from textfmt import apply_dictionary, dictionary_terms, note_tokens, parse_actions, postprocess  # noqa: E402

HOLD_S = 0.45  # in automatic mode, holding longer than this means push-to-talk
LIVE_EVERY_S = 1.2  # how often the live transcript refreshes while recording
LIVE_WINDOW_S = 10  # it re-transcribes only the last few seconds, so the cost stays flat
LLM_IDLE_S = 300  # unload the local AI model after 5 idle minutes to give the memory back
LLM_WORKER = Path(__file__).with_name("llm_worker.py")
TTS_WORKER = Path(__file__).with_name("tts_worker.py")
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\n+")
MEETING_CHUNK_S = 30  # the meeting recorder transcribes and saves every 30 seconds
ACTION_NAMES = {"undo": "Undo", "delete_last": "Deleted", "select_all": "Select all", "copy": "Copied",
                "enter": "Enter", "tab": "Tab", "escape": "Escape"}


def load_audio_file(path):
    """Any audio or video file as mono 16 kHz float32 (PyAV via faster-whisper, else libsndfile)."""
    try:
        from faster_whisper.audio import decode_audio

        return decode_audio(str(path), sampling_rate=audio.SR)
    except ImportError:
        from engine import read_audio_file

        return read_audio_file(path)


class App:
    def __init__(self):
        self.settings = Settings(DATA / "settings.json")
        self._open_stores()
        self.mode = None  # the AI mode of the dictation in progress
        self.current_app = ""  # exe of the app the dictation goes into
        self.last_inserted = ""  # for "scratch that"
        self.edit_selection = ""
        self.meeting = None
        self.test_rec = None  # microphone check during onboarding
        self.widget = None
        self.live_busy = False
        self.last_live = 0.0
        self.last_sync_check = 0.0
        self.events = queue.Queue()
        self.ui_queue = queue.Queue()
        self.window = None
        self.window_visible = True
        self.ui_ready = False
        self.quitting = False
        self.state = "idle"  # idle | recording | transcribing
        self.target = "insert"  # where the next transcript goes: insert | note
        self.press_t = 0.0
        self.engine_state, self.engine_msg = "loading", ""
        self.downloads = {}  # model id -> {"progress", "state", "message"}
        self.recorder = audio.Recorder()
        self.speaker = Speaker()
        self.engine = EngineClient(lambda kind, gen, payload: self.post("engine", kind, gen, payload))
        self.llm = EngineClient(lambda kind, gen, payload: self.push("llms", self.llm_list()), worker=LLM_WORKER)
        self.llm_lock = threading.Lock()
        self.llm_last = 0.0
        self.tts = EngineClient(lambda kind, gen, payload: None, worker=TTS_WORKER)
        self.tts_lock = threading.Lock()
        self.tts_last = 0.0
        self.read_gen = 0  # bumps on every new read or stop, so stale audio is dropped
        self.reading = False
        if not self.settings["ai_key"] and ai.PROVIDERS.get(self.settings["ai_provider"], {}).get("key_url") \
                and self.settings["ai_provider"] != "ollama":
            self.settings["ai_provider"] = "local"  # no key was ever entered: use the free on-PC model
        self.downloader = models.Downloader(lambda *a: self.post("download", *a))
        self.hotkeys = HotkeyManager(self.post)
        self.apply_settings()
        self.tray = self._make_tray()
        threading.Thread(target=self._ui_sender, daemon=True, name="ui-push").start()
        tk_ready = threading.Event()
        threading.Thread(target=self._tk_main, args=(tk_ready,), daemon=True, name="tk").start()
        tk_ready.wait()
        self.post("start_engine")

    def _open_stores(self):
        base = self.settings.sync_dir or DATA
        self.history = History(base / "history.jsonl")
        self.notes = Notes(base / "notes")
        self.notes_sig = self._notes_signature()

    def _notes_signature(self):
        try:
            return tuple(sorted((p.name, p.stat().st_mtime) for p in self.notes.folder.glob("*.json")))
        except OSError:
            return ()

    # plumbing ---------------------------------------------------------------
    def post(self, *event):
        self.events.put(event)

    def push(self, kind, data=None):
        """Send an event to the window's JavaScript (window.onBark)."""
        self.ui_queue.put((kind, data))

    def _ui_sender(self):
        while True:
            kind, data = self.ui_queue.get()
            if not (self.window and self.ui_ready):
                continue
            try:
                self.window.evaluate_js(f"window.onBark && window.onBark({json.dumps(kind)}, {json.dumps(data)})")
            except Exception:
                log.debug("ui push failed", exc_info=True)

    def _tk_main(self, ready):
        self.root = tk.Tk()
        self.root.withdraw()
        self.overlay = Overlay(self.root)
        self.overlay.style = self.settings["overlay_style"]
        if self.settings["widget"]:
            self._show_widget(True)
        ready.set()
        self.root.after(30, self._pump)
        self.root.mainloop()

    def _pump(self):
        try:
            while True:
                self._handle(*self.events.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            log.exception("event handling failed")
        level = self.recorder.level if self.state == "recording" else 0.0
        self.overlay.tick(level)
        if (self.state == "recording" or self.test_rec) and self.window_visible:  # live waveforms in the window
            self._level_n = getattr(self, "_level_n", 0) + 1
            if self._level_n % 3 == 0:
                self.push("level", round((self.test_rec.level if self.test_rec else level) * 12, 3))
        now = time.time()
        if (self.state == "recording" and self.settings["live_preview"] and not self.live_busy
                and now - self.last_live >= LIVE_EVERY_S and now - self.press_t >= 1.0):
            self.last_live = now
            self.live_busy = True
            threading.Thread(target=self._live_preview, daemon=True).start()
        if now - self.last_sync_check > 5 and self.settings.sync_dir:
            self.last_sync_check = now
            self._check_sync()
        if self.llm.ready and self.llm_last and now - self.llm_last > LLM_IDLE_S and not self.llm_lock.locked():
            self.llm_last = 0
            log.info("unloading the idle local AI model")
            threading.Thread(target=self._unload_llm, daemon=True).start()
        if self.tts.ready and self.tts_last and now - self.tts_last > LLM_IDLE_S and not self.reading:
            self.tts_last = 0
            log.info("unloading the idle voice model")
            threading.Thread(target=self.tts.stop, daemon=True).start()
        self.root.after(30, self._pump)

    # read aloud ----------------------------------------------------------------------
    def neural_voice(self):
        return self.settings["tts_engine"] == "kokoro" and models.is_installed("kokoro")

    def read(self, text):
        """Read text aloud with the chosen engine (natural Kokoro voice, or a Windows voice)."""
        self.stop_reading()
        if not (text or "").strip():
            return
        if self.neural_voice():
            threading.Thread(target=self._neural_read, args=(text, self.read_gen), daemon=True).start()
        else:
            self.speaker.speak(text)

    def stop_reading(self):
        self.read_gen += 1
        self.speaker.stop()
        if self.reading:
            import sounddevice as sd

            sd.stop()

    def toggle_read(self, text):
        if self.reading:
            self.stop_reading()
        elif self.neural_voice():
            self.read(text)
        else:
            self.speaker.toggle(text)

    def _neural_read(self, text, gen):
        """Sentence by sentence: the next one is synthesised while the current one plays."""
        import sounddevice as sd

        self.reading, self.reading_gen = True, gen
        self.push("reading", True)
        parts = [p.strip() for p in SENTENCE_END.split(text) if p.strip()]
        ready = queue.Queue(maxsize=2)
        speed = max(0.5, min(2.0, 1 + self.settings["rate"] / 10))

        def produce():
            try:
                with self.tts_lock:
                    if not self.tts.ready:
                        self.tts.start("kokoro")
                        if not self.tts.loaded.wait(60) or self.tts.load_error:
                            raise RuntimeError(self.tts.load_error or "The voice model took too long to load.")
                for p in parts:
                    if gen != self.read_gen:
                        break
                    (audio, sr), _ = self.tts.call("synth", p[:1000], self.settings["kokoro_voice"], speed)
                    ready.put((audio, sr))
            except Exception as e:
                log.exception("natural voice failed")
                self.push("toast", f"Natural voice failed: {e}")
            finally:
                ready.put(None)

        threading.Thread(target=produce, daemon=True).start()
        try:
            while True:
                item = ready.get()
                if item is None or gen != self.read_gen:
                    break
                sd.play(item[0], item[1])
                sd.wait()
        finally:
            self.tts_last = time.time()
            if self.reading_gen == gen:  # a newer read may already have started
                self.reading = False
                self.push("reading", False)

    def kokoro_voices(self):
        """Voice ids inside the downloaded voices file (an .npz zip: one entry per voice)."""
        if not models.is_installed("kokoro"):
            return []
        import zipfile

        path = models.model_dir("kokoro") / "voices-v1.0.bin"
        try:
            names = [n[:-4] for n in zipfile.ZipFile(path).namelist() if n.endswith(".npy")]
        except (OSError, zipfile.BadZipFile):
            return []
        return sorted(n for n in names if n[:1] in "abefip")

    def tts_state(self):
        return {"installed": models.is_installed("kokoro"), "voices": self.kokoro_voices(),
                "size_mb": models.download_mb("kokoro"), "download": self.downloads.get("kokoro")}

    # local AI model ----------------------------------------------------------------
    def _unload_llm(self):
        with self.llm_lock:
            self.llm.stop()
        self.push("llms", self.llm_list())

    def _ensure_llm(self):
        """Load the chosen on-PC AI model if needed. Caller holds llm_lock."""
        mid = self.settings["llm_model"]
        if mid not in models.BY_ID or not models.is_installed(mid):
            raise ai.AIError("Download a free on-PC AI model in AI modes first (one click).")
        if self.llm.model_id != mid or not self.llm.ready:
            self.llm.start(mid)
            if not self.llm.loaded.wait(120) or self.llm.load_error:
                raise ai.AIError(self.llm.load_error or "The local AI model took too long to load.")
            self.push("llms", self.llm_list())

    def _preload_llm(self):
        """Start loading the local model while the user is still talking, so polishing starts at once."""
        try:
            with self.llm_lock:
                self._ensure_llm()
                self.llm_last = time.time()
        except ai.AIError:
            pass

    def _local_rewrite(self, system, text):
        with self.llm_lock:
            self._ensure_llm()
            try:
                out, _ = self.llm.call("rewrite", system, text)
            except RuntimeError as e:
                raise ai.AIError(str(e))
            self.llm_last = time.time()
        return out

    def llm_list(self):
        out = []
        for m in models.LLM_CATALOG:
            d = {k: m[k] for k in ("id", "name", "family", "ram_gb", "accuracy", "speed", "blurb", "license", "secs")}
            d.update(installed=models.is_installed(m["id"]), active=m["id"] == self.settings["llm_model"],
                     loaded=self.llm.ready and self.llm.model_id == m["id"], custom=bool(m.get("custom")),
                     local_file=bool(m.get("path")),
                     size_mb=models.download_mb(m["id"]), download=self.downloads.get(m["id"]))
            out.append(d)
        return out

    def _live_preview(self):
        try:
            text = self.engine.try_transcribe(self.recorder.snapshot(LIVE_WINDOW_S), self.transcribe_opts())
            if text and self.state == "recording":
                self.post("live", text)
        finally:
            self.live_busy = False

    def _check_sync(self):
        """Pick up changes another PC made in the shared sync folder."""
        if self.settings.shared_changed():
            self.settings.load_shared()
            self.apply_settings()
            self.push("settings", self.public_settings())
        if self.history.refresh():
            self.push("history", {"items": list(reversed(self.history.items))[:200], "stats": self.history.stats()})
        sig = self._notes_signature()
        if sig != self.notes_sig:
            self.notes_sig = sig
            self.push("notes", self.notes.list())

    def apply_settings(self):
        s = self.settings
        bindings = {"dictate": s["dictate_hotkey"], "read": s["read_hotkey"], "edit": s["edit_hotkey"]}
        for m in s["modes"]:
            if m.get("hotkey"):
                bindings["mode:" + m["id"]] = m["hotkey"]
        self.hotkeys.set_bindings(bindings)
        if s["voice"]:
            self.speaker.set_voice(s["voice"])
        self.speaker.set_rate(s["rate"])
        if hasattr(self, "overlay"):
            self.overlay.style = s["overlay_style"]

    def public_settings(self):
        s = {k: v for k, v in self.settings.items() if k != "ai_key"}
        s["ai_key_set"] = bool(self.settings["ai_key"])
        return s

    def mode_by_id(self, mode_id):
        return next((m for m in self.settings["modes"] if m["id"] == mode_id), None)

    def _make_tray(self):
        import pystray
        from icon import make_icon

        menu = pystray.Menu(
            pystray.MenuItem("Open Parlo", lambda: self.post("show"), default=True),
            pystray.MenuItem("New note", lambda: self.post("show", "notes")),
            pystray.MenuItem("Read clipboard aloud", lambda: self.read(textout.get_clipboard_text() or "")),
            pystray.MenuItem("Stop speaking", lambda: self.stop_reading()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.post("quit")),
        )
        tray = pystray.Icon("Parlo", make_icon(64), "Parlo", menu)
        tray.run_detached()
        return tray

    # state the window shows ---------------------------------------------------
    def status(self):
        m = models.BY_ID.get(self.engine.model_id or self.settings["model"], {})
        return {"engine": self.engine_state, "message": self.engine_msg, "model": m.get("name", ""),
                "model_id": m.get("id"), "state": self.state, "target": self.target}

    def model_list(self):
        active = self.settings["model"]
        out = []
        for m in models.CATALOG:
            d = {k: m[k] for k in ("id", "name", "family", "languages", "ram_gb", "accuracy", "speed", "blurb",
                                   "license", "repo")}
            d.update(installed=models.is_installed(m["id"]), active=m["id"] == active, custom=bool(m.get("custom")),
                     size_mb=models.download_mb(m["id"]), download=self.downloads.get(m["id"]))
            out.append(d)
        return out

    def full_state(self):
        self.speaker.ready.wait(3)
        return {
            "settings": self.public_settings(), "status": self.status(), "models": self.model_list(),
            "providers": ai.PROVIDERS, "llms": self.llm_list(), "tts": self.tts_state(),
            "history": list(reversed(self.history.items))[:200], "stats": self.history.stats(),
            "voices": self.speaker.voices, "mics": [m for m in self.microphones() if "Sound Mapper" not in m],
            "notes": self.notes.list(), "engine_mb": self.engine.memory_mb(),
        }

    def microphones(self):
        try:
            return audio.list_microphones()
        except Exception:
            log.exception("listing microphones failed")
            return []

    # events (always on the Tk thread) ------------------------------------------
    def _handle(self, kind, *args):
        if kind.endswith(("_down", "_up")) or kind in ("escape", "note_toggle"):
            log.info("event %s (state %s)", kind, self.state)
        if kind == "dictate_down":
            if self.state == "recording":
                self._stop_recording()
            else:
                self._dictate_down(args[0], "insert", self.mode_for_app())
        elif kind == "widget_click":
            if self.state == "recording":
                self._stop_recording()
            else:
                self._dictate_down(time.time(), "insert", self.mode_for_app())
        elif kind == "edit_down":
            if self.state == "recording" and self.target == "edit":
                self._stop_recording()
            elif self.state == "idle":
                threading.Thread(target=self._edit_begin, daemon=True).start()
        elif kind == "edit_start":
            self.edit_selection = args[0] or ""
            self._dictate_down(time.time(), "edit")
        elif kind == "edited":
            self._finish_edit(*args)
        elif kind == "widget":
            self._show_widget(args[0])
        elif kind.startswith("mode:") and kind.endswith("_down"):  # a mode's own shortcut
            self._dictate_down(args[0], "insert", kind[5:-5])
        elif kind == "dictate_up" or (kind.startswith("mode:") and kind.endswith("_up")):
            self._dictate_up(args[0])
        elif kind == "live" and self.state == "recording":
            self.overlay.set_live(args[0])
            if self.target == "note":
                self.push("live", args[0])
        elif kind == "polished":
            self._finish_insert(*args)
        elif kind == "note_toggle":
            if self.state == "recording":
                self._stop_recording()
            else:
                self._dictate_down(time.time(), "note")
        elif kind == "escape" and self.state == "recording":
            self.recorder.stop()
            self._set_state("idle")
            self.overlay.show("Cancelled", "info", hide_after=0.8)
        elif kind == "read_down":
            threading.Thread(target=self._read_selection, daemon=True).start()
        elif kind == "start_engine":
            self._start_engine()
        elif kind == "engine":
            self._engine_event(*args)
        elif kind == "transcribed":
            self._deliver(*args)
        elif kind == "download":
            self._download_event(*args)
        elif kind == "show":
            if self.window:
                self.window.show()
                self.window.restore()
                self.window_visible = True
                if args:
                    self.push("navigate", args[0])
        elif kind == "quit":
            self.quit()

    def _show_widget(self, on):
        if on and not self.widget:
            from widget import Widget

            def moved(x, y):
                self.settings["widget_pos"] = [x, y]
                self.settings.save()

            def hide():
                self.settings["widget"] = False
                self.settings.save()
                self._show_widget(False)
                self.push("settings", self.public_settings())

            self.widget = Widget(self.root, self.settings["widget_pos"], lambda: self.post("widget_click"),
                                 lambda: self.post("show"), hide, moved)
            self.widget.set_state(self.state)
        elif not on and self.widget:
            self.widget.destroy()
            self.widget = None

    def _set_state(self, state):
        recording_changed = (state == "recording") != (self.state == "recording")
        self.state = state
        self.push("status", self.status())
        if self.widget:
            self.widget.set_state(state)
        if recording_changed:
            from icon import make_icon

            self.tray.icon = make_icon(64, recording=state == "recording")

    def _start_engine(self):
        wanted = self.settings["model"]
        if wanted not in models.BY_ID or not models.is_installed(wanted):
            installed = [m["id"] for m in models.CATALOG if models.is_installed(m["id"])]
            if not installed:
                self.engine_state, self.engine_msg = "missing", "No speech model is downloaded yet."
                self.push("status", self.status())
                return
            wanted = installed[0]
            self.settings["model"] = wanted
            self.settings.save()
        self.engine_state, self.engine_msg = "loading", ""
        self.engine.start(wanted)
        self.push("status", self.status())
        self.push("models", self.model_list())

    def _engine_event(self, kind, gen, payload):
        if gen != self.engine.generation:
            return
        if kind == "ready":
            self.engine_state, self.engine_msg = "ready", f"Loaded in {payload['load_s']:.0f}s"
            log.info("engine %s ready: %s", self.engine.model_id, payload)
        else:
            self.engine_state, self.engine_msg = "error", str(payload)
            log.error("engine error: %s", payload)
        self.push("status", self.status())
        self.push("models", self.model_list())

    def set_model(self, model_id):
        if model_id not in models.BY_ID or not models.is_installed(model_id):
            return
        self.settings["model"] = model_id
        self.settings.save()
        self.post("start_engine")

    def _download_event(self, model_id, progress, state, message):
        self.downloads[model_id] = {"progress": progress, "state": state, "message": message}
        if state != "downloading":
            self.downloads.pop(model_id, None)
            if state == "done" and self.engine_state == "missing":
                self.set_model(model_id)
            if message:
                self.push("toast", message)
        self.push("models", self.model_list())
        self.push("llms", self.llm_list())
        self.push("tts", self.tts_state())

    # dictation -------------------------------------------------------------------
    def mode_for_app(self):
        """The mode to use for the app in front: a mode that lists this app, else the default mode."""
        exe, _ = textout.foreground_app()
        self.current_app = exe
        for m in self.settings["modes"]:
            if exe and exe in [a.lower() for a in m.get("apps", [])]:
                return m["id"]
        return self.settings["active_mode"]

    def transcribe_opts(self):
        """Hints for Whisper models: the language to expect and the user's dictionary words."""
        terms = dictionary_terms(self.settings)
        lang = self.settings["language"]
        return {"language": None if lang == "auto" else lang,
                "prompt": ("Glossary: " + ", ".join(terms) + ".") if terms else None}

    def _dictate_down(self, t, target, mode_id=None):
        """target: insert (type into the app in front), note (the open note) or edit (edit by voice)."""
        if self.state == "idle":
            if self.engine_state != "ready":
                text = {"loading": "Model still loading", "missing": "Download a model first"}.get(
                    self.engine_state, "Speech model error")
                self.overlay.show(text, "info", hide_after=1.8)
                self.push("toast", text)
                return
            try:
                self.recorder.start(self.settings["microphone"])
            except Exception as e:
                log.exception("mic start failed")
                self.overlay.show("Microphone error", "info", hide_after=2)
                self.push("toast", f"Microphone error: {e}")
                return
            self.target = target
            self.press_t = t
            self.last_live = t
            self.mode = self.mode_by_id(mode_id) if target == "insert" else None
            ai_mode = self.mode if self.mode and self.mode.get("instructions", "").strip() else None
            self._set_state("recording")
            log.info("recording at %d Hz for %s (mode %s, app %s)", self.recorder.rate, target, mode_id, self.current_app)
            if self.settings["sounds"]:
                audio.play_cue("start")
            label = "Edit" if target == "edit" else ai_mode["name"] if ai_mode else ""
            self.overlay.show("", "rec", label=label)
            if (ai_mode or target == "edit") and self.settings["ai_provider"] == "local" and not self.llm.ready:
                threading.Thread(target=self._preload_llm, daemon=True).start()
        elif self.state == "recording":  # second tap in toggle / automatic mode
            self._stop_recording()

    def _dictate_up(self, t):
        if self.state != "recording" or self.target != "insert":
            return
        mode = self.settings["activation"]
        held = t - self.press_t
        if mode == "push_to_talk" or (mode == "automatic" and held >= HOLD_S):
            self._stop_recording()

    def _stop_recording(self):
        wave = self.recorder.stop()
        if self.settings["sounds"]:
            audio.play_cue("stop")
        secs = len(wave) / audio.SR
        log.info("stopped after %.1fs, got %.2fs of audio", time.time() - self.press_t, secs)
        if secs < 0.3:
            self._set_state("idle")
            self.overlay.hide()
            return
        self._set_state("transcribing")
        self.overlay.show("Transcribing", "busy")
        target, opts = self.target, self.transcribe_opts()

        def work():
            try:
                text, took = self.engine.transcribe(wave, opts)
                log.info("transcribed %.1fs of audio in %.2fs", secs, took)
            except Exception as e:
                log.exception("transcription failed")
                text = None
                self.push("toast", f"Transcription failed: {e}")
            self.post("transcribed", text, secs, target)

        threading.Thread(target=work, daemon=True).start()

    def _deliver(self, text, secs, target):
        if text is None:
            self._set_state("idle")
            self.overlay.show("Transcription failed", "info", hide_after=2)
            if self.settings["sounds"]:
                audio.play_cue("error")
            return
        if not text.strip():
            self._set_state("idle")
            self.overlay.show("No speech heard", "info", hide_after=1.2)
            return
        text = apply_dictionary(text, dictionary_terms(self.settings))
        if target == "note":
            from engine import tidy

            self._set_state("idle")
            self.overlay.hide()
            text = tidy(text) if self.settings["tidy"] else text
            self.push("note_insert", note_tokens(text))
            return
        if target == "edit":
            self._set_state("polishing")
            self.overlay.show("Editing", "busy")
            threading.Thread(target=self._edit, args=(text, secs), daemon=True).start()
            return
        actions = []
        if self.settings["voice_actions"]:
            text, actions = parse_actions(text)
            if not text:  # the whole dictation was a command such as "undo that"
                self._set_state("idle")
                self.overlay.show(ACTION_NAMES.get(actions[0], "Done"), "info", hide_after=1.0)
                threading.Thread(target=self._run_actions, args=(actions,), daemon=True).start()
                return
        mode = self.mode
        if mode and mode.get("instructions", "").strip():
            self._set_state("polishing")
            self.overlay.show(f"{mode['name']}: polishing", "busy")
            threading.Thread(target=self._polish, args=(text, secs, mode, actions), daemon=True).start()
        else:
            self._finish_insert(text, secs, None, None, None, actions)

    def _polish(self, raw, secs, mode, actions):
        s = self.settings
        t0 = time.time()
        try:
            out = ai.rewrite(raw, mode["instructions"], s["ai_provider"], secrets_store.unprotect(s["ai_key"]),
                             s["ai_model"], s["ai_base_url"], local=self._local_rewrite)
            log.info("AI mode %s took %.1fs", mode["id"], time.time() - t0)
            self.post("polished", out, secs, raw, mode["name"], None, actions)
        except ai.AIError as e:
            log.warning("AI mode %s failed: %s", mode["id"], e)
            self.post("polished", raw, secs, None, mode["name"], str(e), actions)

    def _finish_insert(self, text, secs, raw, mode_name, error, actions=()):
        self._set_state("idle")
        if error:
            self.overlay.show("AI failed: plain text inserted", "info", hide_after=2.5)
            self.push("toast", f"{mode_name}: {error} The plain transcript was inserted instead.")
        else:
            self.overlay.hide()
        # an AI rewrite is already punctuated; replacements and spacing still apply
        if raw and text[:1].islower():
            text = text[0].upper() + text[1:]
        out = postprocess(text, dict(self.settings, tidy=False) if raw else self.settings)
        self.history.add(out.strip(), secs, self.engine.model_id, raw=raw, mode=mode_name, app=self.current_app)
        self.push("history", {"items": list(reversed(self.history.items))[:200], "stats": self.history.stats()})
        action, method = self.settings["action"], self.settings["insert_method"]

        def insert():
            try:
                self.hotkeys.wait_released()
                if action == "copyToClipboard":
                    textout.set_clipboard_text(out.strip())
                elif action in ("autoInsert", "pasteAndSend"):
                    (textout.type_text if method == "type" else textout.paste_text)(out)
                    self.last_inserted = out
                    if action == "pasteAndSend":
                        textout.press_enter()
                    self._run_actions(actions)
            except Exception:
                log.exception("inserting text failed")

        if action != "historyOnly":
            threading.Thread(target=insert, daemon=True).start()

    def _run_actions(self, actions):
        if not actions:
            return
        self.hotkeys.wait_released()
        for a in actions:
            log.info("voice action: %s", a)
            textout.run_action(a, self.last_inserted)
            if a == "delete_last":
                self.last_inserted = ""

    # edit by voice: select text, press the edit shortcut, say what to change ---------------
    def _edit_begin(self):
        self.hotkeys.wait_released()
        self.current_app = textout.foreground_app()[0]
        selection = textout.copy_selection()
        self.post("edit_start", selection)

    def _edit(self, instruction, secs):
        s = self.settings
        sel = self.edit_selection
        prompt = f"INSTRUCTION: {instruction}\n\nTEXT:\n{sel}" if sel.strip() else f"INSTRUCTION: {instruction}"
        try:
            out = ai.rewrite(prompt, "", s["ai_provider"], secrets_store.unprotect(s["ai_key"]), s["ai_model"],
                             s["ai_base_url"], local=self._local_rewrite, system=ai.EDIT_SYSTEM)
            self.post("edited", out, secs, instruction, None)
        except ai.AIError as e:
            log.warning("edit by voice failed: %s", e)
            self.post("edited", None, secs, instruction, str(e))

    def _finish_edit(self, out, secs, instruction, error):
        self._set_state("idle")
        if error:
            self.overlay.show("Edit failed", "info", hide_after=2)
            self.push("toast", f"Edit by voice: {error}")
            return
        self.overlay.hide()
        self.history.add(out, secs, self.engine.model_id, raw=f"Edit: {instruction}", mode="Edit by voice",
                         app=self.current_app)
        self.push("history", {"items": list(reversed(self.history.items))[:200], "stats": self.history.stats()})

        def replace():
            self.hotkeys.wait_released()
            textout.paste_text(out)  # the selection is still active, so pasting replaces it
            self.last_inserted = out

        threading.Thread(target=replace, daemon=True).start()

    def _read_selection(self):
        self.hotkeys.wait_released()
        self.toggle_read(textout.copy_selection() or "")

    def transcribe_file(self, path):
        """Blocking; called from a window API thread."""
        if self.engine_state != "ready":
            raise RuntimeError("The speech model is not ready yet.")
        wave = load_audio_file(path)
        text, took = self.engine.transcribe(wave, self.transcribe_opts())
        from engine import tidy

        text = apply_dictionary(text, dictionary_terms(self.settings))
        text = tidy(text) if self.settings["tidy"] else text
        if text:
            self.history.add(text, len(wave) / audio.SR, self.engine.model_id, app="file")
            self.push("history", {"items": list(reversed(self.history.items))[:200], "stats": self.history.stats()})
        return {"text": text, "secs": round(len(wave) / audio.SR), "took": took, "name": Path(path).name}

    # meeting recorder: long recordings into a note, with an AI summary at the end ------------
    def meeting_start(self):
        if self.meeting:
            return self.meeting["note_id"]
        if self.engine_state != "ready":
            raise RuntimeError("The speech model is not ready yet.")
        note = self.notes.new()
        title = "Meeting " + time.strftime("%d %b %Y, %H:%M")
        self.notes.save(note["id"], title, "<h2>Transcript</h2>", "")
        rec = audio.Recorder()
        rec.start(self.settings["microphone"])
        self.meeting = {"note_id": note["id"], "title": title, "rec": rec, "start": time.time(), "parts": [],
                        "stop": threading.Event()}
        threading.Thread(target=self._meeting_loop, args=(self.meeting,), daemon=True).start()
        self.push("meeting", {"note_id": note["id"], "state": "recording", "start": self.meeting["start"]})
        self.push("notes", self.notes.list())
        return note["id"]

    def meeting_stop(self):
        if self.meeting:
            self.meeting["stop"].set()

    def _meeting_loop(self, m):
        """Every 30 s: transcribe what was said and append it to the note with a timestamp."""
        import numpy as np

        from engine import tidy

        opts = self.transcribe_opts()
        offset, carry = 0.0, np.zeros(0, np.float32)
        while True:
            stopped = m["stop"].wait(MEETING_CHUNK_S)
            wave = np.concatenate([carry, m["rec"].drain()])
            carry = np.zeros(0, np.float32)
            if stopped:
                m["rec"].stop()
            elif len(wave) > 4 * audio.SR:
                # end the chunk at the quietest moment of its last 2 s, so a word is not cut in half
                frame = audio.SR // 20
                tail = wave[-2 * audio.SR:]
                energy = [float(np.mean(tail[i:i + frame] ** 2)) for i in range(0, len(tail) - frame, frame)]
                cut = len(wave) - len(tail) + int(np.argmin(energy)) * frame + frame // 2
                wave, carry = wave[:cut], wave[cut:]
            if len(wave) > audio.SR:
                try:
                    text, _ = self.engine.transcribe(wave, opts)
                except RuntimeError as e:
                    text = ""
                    log.warning("meeting chunk failed: %s", e)
                text = apply_dictionary(text, dictionary_terms(self.settings))
                text = tidy(text) if self.settings["tidy"] else text
                if text.strip():
                    stamp = time.strftime("%H:%M:%S", time.gmtime(offset))
                    m["parts"].append((stamp, text))
                    self._meeting_save(m)
                    self.push("meeting", {"note_id": m["note_id"], "state": "recording", "start": m["start"],
                                          "html": self._meeting_html(m)})
            offset += len(wave) / audio.SR
            if stopped:
                break
        self.push("meeting", {"note_id": m["note_id"], "state": "summarising", "start": m["start"]})
        summary = self._meeting_summary(" ".join(t for _, t in m["parts"]))
        m["summary"] = summary
        self._meeting_save(m)
        self.meeting = None
        self.push("meeting", {"note_id": m["note_id"], "state": "done", "html": self._meeting_html(m)})
        self.push("notes", self.notes.list())

    def _meeting_html(self, m):
        from html import escape

        body = ""
        if m.get("summary"):
            body += m["summary"]
        body += "<h2>Transcript</h2>" + "".join(f"<p><b>[{s}]</b> {escape(t)}</p>" for s, t in m["parts"])
        if not m["parts"]:
            body += "<p><i>Nothing was heard.</i></p>"
        return body

    def _meeting_save(self, m):
        preview = " ".join(t for _, t in m["parts"])[:160]
        self.notes.save(m["note_id"], m["title"], self._meeting_html(m), preview)

    def _meeting_summary(self, transcript):
        """A summary and action items from the AI writing model, as HTML (empty if no AI is available)."""
        from html import escape

        if len(transcript.split()) < 25:
            return ""
        s = self.settings
        ask = lambda text: ai.rewrite(text, "", s["ai_provider"], secrets_store.unprotect(s["ai_key"]), s["ai_model"],
                                      s["ai_base_url"], local=self._local_rewrite, system=ai.SUMMARY_SYSTEM, timeout=120)
        try:
            if len(transcript) > 9000:  # too long for a small model at once: summarise parts, then the parts
                parts = [transcript[i:i + 8000] for i in range(0, len(transcript), 8000)]
                transcript = "\n".join(ask(p) for p in parts)
            out = ask(transcript)
        except ai.AIError as e:
            log.warning("meeting summary failed: %s", e)
            return f"<p><i>No summary: {escape(str(e))}</i></p>"
        html, items = [], []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(("-", "*", "•")):
                item = line.lstrip("-*• ").strip()
                if item.lower().rstrip(".") not in ("none", "n/a"):  # small models add '- None' even after real items
                    items.append(f"<li>{escape(item)}</li>")
                continue
            if items:
                html.append("<ul>" + "".join(items) + "</ul>")
                items = []
            head = line.rstrip(":").strip().lower()
            html.append("<h2>Action items</h2>" if head.startswith("action") else
                        "<h2>Summary</h2>" if head.startswith("summary") else f"<p>{escape(line)}</p>")
        if items:
            html.append("<ul>" + "".join(items) + "</ul>")
        if html and html[-1] == "<h2>Action items</h2>":
            html.pop()  # nobody agreed to do anything
        return "".join(html)

    # window ------------------------------------------------------------------------
    def style_titlebar(self):
        """Colour the native title bar to match the app's theme (Windows 10 dark mode, Windows 11 caption colour)."""
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, "Parlo")
            if not hwnd:
                return
            theme = self.settings["theme"]
            if theme == "system":
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                    theme = "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
            dark = theme != "light"
            dwm = ctypes.windll.dwmapi
            for attr, value in ((20, int(dark)),  # DWMWA_USE_IMMERSIVE_DARK_MODE
                                (35, 0x00161212 if dark else 0x00F2EFEF),  # caption colour #121216 / #efeff2 (0x00BBGGRR)
                                (36, 0x00F1ECEC if dark else 0x001D1818)):  # caption text colour
                v = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(v), 4)
        except Exception:
            log.debug("title bar styling unavailable", exc_info=True)

    def on_shown(self):
        self.window_visible = True
        self.style_titlebar()

    def on_closing(self):
        if self.quitting:
            return True
        self.window_visible = False
        self.window.hide()
        if not self.settings["tray_hint_shown"]:
            self.settings["tray_hint_shown"] = True
            self.settings.save()
            self.tray.notify("Parlo keeps running in the tray. Right-click the icon to quit.", "Parlo")
        return False

    def quit(self):
        self.quitting = True
        try:
            self.tray.stop()
            self.hotkeys.stop()
            self.engine.stop()
            self.llm.stop()
            self.tts.stop()
        finally:
            if self.window:
                self.window.destroy()
            os._exit(0)


class Api:
    """Methods the window's JavaScript calls as window.pywebview.api.<name>(...)."""

    def __init__(self, app):
        self._app = app

    def ui_ready(self):
        self._app.ui_ready = True
        return self._app.full_state()

    def get_state(self):
        return self._app.full_state()

    def save_settings(self, changes):
        app = self._app
        changes = {k: v for k, v in changes.items() if k in DEFAULTS and k not in ("ai_key", "sync_folder")}
        app.settings.update(changes)
        app.settings.save()
        app.apply_settings()
        if "theme" in changes:
            app.style_titlebar()
        if "start_with_windows" in changes:
            set_autostart(bool(changes["start_with_windows"]))
        if "widget" in changes:
            app.post("widget", bool(changes["widget"]))
        return app.public_settings()

    # AI modes
    def save_ai(self, provider, model, base_url, key=None):
        """key=None keeps the stored key; '' removes it. Keys are stored DPAPI-encrypted, never sent back."""
        app = self._app
        app.settings.update(ai_provider=provider, ai_model=model.strip(), ai_base_url=base_url.strip())
        if key is not None:
            app.settings["ai_key"] = secrets_store.protect(key.strip())
        app.settings.save()
        return app.public_settings()

    def open_key_page(self, provider):
        """Opens the provider's API-key page in the normal browser (only the known URLs in ai.PROVIDERS)."""
        url = ai.PROVIDERS.get(provider, {}).get("key_url")
        if url:
            import webbrowser

            webbrowser.open(url)

    def set_llm(self, model_id):
        app = self._app
        if model_id in models.BY_ID and models.is_installed(model_id):
            app.settings.update(llm_model=model_id, ai_provider="local")
            app.settings.save()
            if app.llm.ready and app.llm.model_id != model_id:
                threading.Thread(target=app._unload_llm, daemon=True).start()
        app.push("llms", app.llm_list())
        return {"settings": app.public_settings(), "warn": models.memory_check(model_id)}

    def delete_llm(self, model_id):
        app = self._app
        if app.llm.model_id == model_id:
            app._unload_llm()
        models.delete(model_id)
        app.push("llms", app.llm_list())

    def test_ai(self):
        s = self._app.settings
        sample = "um so I think we should uh meet on tuesday no wait wednesday at like three to go over the the budget"
        t0 = time.time()
        try:
            out = ai.rewrite(sample, ai.BUILTIN_MODES[1]["instructions"], s["ai_provider"],
                             secrets_store.unprotect(s["ai_key"]), s["ai_model"], s["ai_base_url"],
                             local=self._app._local_rewrite)
            return {"ok": True, "before": sample, "after": out, "secs": round(time.time() - t0, 1)}
        except ai.AIError as e:
            return {"ok": False, "error": str(e)}

    def save_modes(self, modes, active):
        app = self._app
        clean = []
        for m in modes:
            clean.append({"id": str(m["id"])[:40], "name": str(m.get("name", "Mode"))[:40] or "Mode",
                          "icon": m.get("icon", "sparkles"), "instructions": str(m.get("instructions", ""))[:4000],
                          "hotkey": str(m.get("hotkey", ""))[:40],
                          "apps": [str(a).lower()[:80] for a in m.get("apps", [])][:30]})
        if not any(m["id"] == "plain" for m in clean):
            clean.insert(0, dict(ai.BUILTIN_MODES[0]))
        app.settings["modes"] = clean
        app.settings["active_mode"] = active if any(m["id"] == active for m in clean) else "plain"
        app.settings.save()
        app.apply_settings()
        return app.public_settings()

    # sync
    def choose_sync_folder(self):
        app = self._app
        kind = getattr(webview, "FileDialog", None)
        picked = app.window.create_file_dialog(kind.FOLDER if kind else webview.FOLDER_DIALOG)
        if not picked:
            return None
        chosen = picked[0] if isinstance(picked, (list, tuple)) else picked
        target, existing = start_sync(DATA, chosen)
        app.settings["sync_folder"] = str(target)
        app.settings.load_shared()
        app.settings.save()
        app._open_stores()
        app.apply_settings()
        log.info("sync on: %s (existing data: %s)", target, existing)
        return {"folder": str(target), "existing": existing, "state": app.full_state()}

    def stop_sync(self):
        app = self._app
        if app.settings.sync_dir:
            stop_sync(DATA, app.settings.sync_dir)
        app.settings["sync_folder"] = ""
        app.settings.save()
        app._open_stores()
        return app.full_state()

    # meeting recorder
    def meeting_start(self):
        try:
            return {"note_id": self._app.meeting_start()}
        except Exception as e:
            log.exception("meeting start failed")
            return {"error": str(e)}

    def meeting_stop(self):
        self._app.meeting_stop()

    def meeting_state(self):
        m = self._app.meeting
        return {"note_id": m["note_id"], "start": m["start"]} if m else None

    # first-run walkthrough: microphone check
    def mic_test(self, on):
        app = self._app
        if on and not app.test_rec:
            app.test_rec = audio.Recorder()
            try:
                app.test_rec.start(app.settings["microphone"])
            except Exception as e:
                app.test_rec = None
                return str(e)
        elif not on and app.test_rec:
            app.test_rec.stop()
            app.test_rec = None
        return None

    def recent_apps(self):
        """Apps recently dictated into, for per-app modes."""
        seen = []
        for e in reversed(self._app.history.items):
            a = e.get("app")
            if a and a != "file" and a not in seen:
                seen.append(a)
        return seen[:20]

    def capture_shortcut(self, on):
        """While the user records a new shortcut, the global hotkeys must not fire."""
        if on:
            self._app.hotkeys.set_bindings({})
        else:
            self._app.apply_settings()

    # models
    def set_model(self, model_id):
        app = self._app
        # the current speech model is unloaded first, so its memory counts as free
        current = models.BY_ID.get(app.engine.model_id or "", {}).get("ram_gb", 0) if app.engine.ready else 0
        warn = models.memory_check(model_id, freed_gb=current) if model_id in models.BY_ID else None
        app.set_model(model_id)
        return warn

    def download_model(self, model_id):
        return self._app.downloader.start(model_id)

    def cancel_download(self):
        self._app.downloader.stop()

    def delete_model(self, model_id):
        app = self._app
        if model_id == app.settings["model"]:
            return False
        models.delete(model_id)
        app.push("models", app.model_list())
        return True

    def engine_memory(self):
        return self._app.engine.memory_mb()

    # history
    def delete_history(self, t):
        self._app.history.delete(t)
        return self._app.history.stats()

    def clear_history(self):
        self._app.history.clear()
        return self._app.history.stats()

    def copy_text(self, text):
        return textout.set_clipboard_text(text)

    # read aloud
    def speak(self, text):
        self._app.read(text)

    def stop_speaking(self):
        self._app.stop_reading()

    def try_voice(self, voice):
        app = self._app
        app.settings["kokoro_voice"] = voice
        app.settings.save()
        app.read("Hi, I'm one of Parlo's natural voices. I run entirely on your own computer.")

    # your own models
    def inspect_hf(self, text, kind):
        try:
            return {"ok": True, **models.inspect_repo(text, kind)}
        except (ValueError, OSError) as e:
            return {"ok": False, "error": str(e)}

    def add_custom_llm(self, info, filename):
        app = self._app
        entry = models.custom_llm_from_repo(info, filename)
        if entry["id"] not in models.BY_ID:
            models.add_custom(entry)
        app.downloader.start(entry["id"])
        app.push("llms", app.llm_list())
        return {"id": entry["id"], "warn": models.memory_check(entry["id"])}

    def add_custom_llm_file(self):
        app = self._app
        kind = getattr(webview, "FileDialog", None)
        picked = app.window.create_file_dialog(kind.OPEN if kind else webview.OPEN_DIALOG,
                                               file_types=("AI models (*.gguf)", "All files (*.*)"))
        if not picked:
            return None
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        if not path.lower().endswith(".gguf"):
            return {"error": "Choose a .gguf model file."}
        entry = models.custom_llm_from_file(path)
        if entry["id"] not in models.BY_ID:
            models.add_custom(entry)
        app.push("llms", app.llm_list())
        return {"id": entry["id"], "warn": models.memory_check(entry["id"])}

    def add_custom_whisper(self, info):
        app = self._app
        entry = models.custom_whisper_from_repo(info)
        if entry["id"] not in models.BY_ID:
            models.add_custom(entry)
        app.downloader.start(entry["id"])
        app.push("models", app.model_list())
        return {"id": entry["id"], "warn": models.memory_check(entry["id"])}

    # notes
    def notes_list(self):
        return self._app.notes.list()

    def note_get(self, note_id):
        return self._app.notes.get(note_id)

    def note_new(self):
        return self._app.notes.new()

    def note_save(self, note_id, title, html, preview):
        return self._app.notes.save(note_id, title, html, preview)

    def note_delete(self, note_id):
        self._app.notes.delete(note_id)

    def note_record(self):
        self._app.post("note_toggle")

    # files
    def pick_and_transcribe(self):
        win = self._app.window
        kind = getattr(webview, "FileDialog", None)
        paths = win.create_file_dialog(kind.OPEN if kind else webview.OPEN_DIALOG, file_types=(
            "Audio and video (*.wav;*.mp3;*.m4a;*.flac;*.ogg;*.opus;*.mp4;*.webm)", "All files (*.*)"))
        if not paths:
            return None
        try:
            return self._app.transcribe_file(paths[0])
        except Exception as e:
            log.exception("file transcription failed")
            return {"error": str(e)}

    def save_text_file(self, filename, content):
        win = self._app.window
        kind = getattr(webview, "FileDialog", None)
        path = win.create_file_dialog(kind.SAVE if kind else webview.SAVE_DIALOG, save_filename=filename)
        if not path:
            return False
        path = path[0] if isinstance(path, (list, tuple)) else path
        Path(path).write_text(content, "utf-8")
        return True


def set_autostart(on):
    """Start with Windows: a per-user Run entry that opens Parlo quietly in the tray."""
    import winreg

    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            pythonw = Path(sys.executable).with_name("pythonw.exe").resolve()
            winreg.SetValueEx(k, "Parlo", 0, winreg.REG_SZ, f'"{pythonw}" "{Path(__file__).resolve()}" --tray')
        else:
            try:
                winreg.DeleteValue(k, "Parlo")
            except FileNotFoundError:
                pass


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # Our own taskbar identity: without it Windows groups the window under pythonw.exe and shows
    # the Python logo instead of the app's icon.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Parlo.App")
    from icon import save_ico

    save_ico(DATA / "icon.ico")  # redrawn each start so a new logo always reaches the window and tray
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ParloSingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(None, "Parlo is already running (see the tray icon).", "Parlo", 0x40)
        return
    app = App()
    if app.settings["start_with_windows"]:
        set_autostart(True)  # rewrite the entry in case the Parlo folder was moved
    in_tray = "--tray" in sys.argv  # started with Windows: stay in the tray until opened
    window = webview.create_window(
        "Parlo", url=str(WEB / "index.html"), js_api=Api(app), width=1120, height=740, min_size=(880, 580),
        background_color="#0e0e11" if app.settings["theme"] != "light" else "#f6f6f8", hidden=in_tray)
    app.window = window
    app.window_visible = not in_tray
    window.events.closing += app.on_closing
    window.events.shown += app.on_shown
    webview.start(gui="edgechromium", icon=str(DATA / "icon.ico"))
    del mutex
    os._exit(0)


if __name__ == "__main__":
    main()
