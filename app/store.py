"""Settings, dictation history and notes, saved as plain JSON files.

Everything lives in data/ unless the user picks a sync folder (e.g. inside OneDrive): then the
shareable settings, history and notes live there and every PC pointing at it sees the same data.
Per-PC settings (microphone, model, API key...) always stay in data/settings.json.
"""
import copy
import json
import shutil
import time
import uuid
from pathlib import Path

from ai import BUILTIN_MODES, CLEAN_INSTRUCTIONS, OLD_CLEAN_INSTRUCTIONS

DEFAULTS = {
    "model": "bark-3.0",
    "dictate_hotkey": "ctrl+win",
    "activation": "automatic",
    "auto_stop": "3",  # tap-to-talk stops after this many seconds of silence ("0" = off)
    "action": "autoInsert",
    "insert_method": "paste",
    "microphone": None,
    "sounds": True,
    "trailing_space": True,
    "tidy": True,
    "replacements": "",
    "read_hotkey": "ctrl+alt+r",
    "voice": None,
    "rate": 0,
    "tts_engine": "windows",  # windows | kokoro (natural voices, downloaded on demand)
    "kokoro_voice": "af_heart",
    "theme": "dark",
    "device": "auto",
    "tray_hint_shown": False,
    # AI text modes
    "modes": copy.deepcopy(BUILTIN_MODES),
    "active_mode": "plain",
    "ai_provider": "local",
    "llm_model": "qwen2.5-1.5b",  # the on-PC model used when ai_provider is "local"
    "ai_model": "",
    "ai_base_url": "",
    "ai_key": "",  # DPAPI-encrypted, see secrets_store.py
    # recording look
    "overlay_style": "pill",  # pill | capsule | dot | off
    "live_preview": True,
    # sync
    "sync_folder": "",
    # words the speech model should get right: names, products, jargon (one per line)
    "dictionary": "",
    "voice_actions": True,  # "send it", "undo that", "scratch that"...
    "language": "auto",  # for multilingual Whisper models: auto-detect or a language code
    "edit_hotkey": "ctrl+alt+space",  # select text, press, say how to change it
    "widget": False,  # small floating mic button
    "widget_pos": None,
    "start_with_windows": False,
    "onboarded": False,
}
# Settings that describe this PC rather than the person; never synced.
LOCAL_KEYS = {"model", "microphone", "voice", "rate", "device", "tray_hint_shown", "ai_key", "sync_folder",
              "live_preview", "llm_model", "tts_engine", "widget", "widget_pos", "start_with_windows", "onboarded"}
SYNC_DIRNAME = "Parlo Sync"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), "utf-8")
    tmp.replace(path)


class Settings(dict):
    def __init__(self, path):
        super().__init__(copy.deepcopy(DEFAULTS))
        self.path = path
        self.update({k: v for k, v in _read_json(path).items() if k in DEFAULTS})
        self.shared_mtime = 0
        self.load_shared()
        for m in self["modes"]:  # the Clean up mode got better instructions; keep any the user wrote
            if m.get("id") == "clean" and m.get("instructions") == OLD_CLEAN_INSTRUCTIONS:
                m["instructions"] = CLEAN_INSTRUCTIONS

    @property
    def sync_dir(self):
        d = self.get("sync_folder")
        return Path(d) if d and Path(d).is_dir() else None

    @property
    def shared_path(self):
        return self.sync_dir / "settings.json" if self.sync_dir else None

    def load_shared(self):
        p = self.shared_path
        if p and p.exists():
            self.shared_mtime = p.stat().st_mtime
            self.update({k: v for k, v in _read_json(p).items() if k in DEFAULTS and k not in LOCAL_KEYS})

    def shared_changed(self):
        p = self.shared_path
        return bool(p and p.exists() and p.stat().st_mtime > self.shared_mtime + 0.5)

    def save(self):
        if self.sync_dir:
            _write_json(self.path, {k: v for k, v in self.items() if k in LOCAL_KEYS})
            _write_json(self.shared_path, {k: v for k, v in self.items() if k not in LOCAL_KEYS})
            self.shared_mtime = self.shared_path.stat().st_mtime
        else:
            _write_json(self.path, dict(self))


def start_sync(data_dir, chosen):
    """Point this PC at <chosen>/Parlo Sync. If that folder already has Parlo data (another PC set it
    up), keep it and merge this PC's notes and history in; otherwise copy this PC's data there."""
    target = Path(chosen) / SYNC_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    (target / "notes").mkdir(exist_ok=True)
    existing = (target / "settings.json").exists()
    local = _read_json(data_dir / "settings.json")
    if not existing:
        _write_json(target / "settings.json", {k: v for k, v in local.items() if k not in LOCAL_KEYS})
    for note in (data_dir / "notes").glob("*.json"):
        dest = target / "notes" / note.name
        if not dest.exists() or note.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(note, dest)
    merge_history(data_dir / "history.jsonl", target / "history.jsonl")
    return target, existing


def stop_sync(data_dir, sync_dir):
    """Copy the synced data back into data/ so this PC keeps everything after leaving sync."""
    shared = _read_json(sync_dir / "settings.json")
    local = _read_json(data_dir / "settings.json")
    local.update({k: v for k, v in shared.items() if k not in LOCAL_KEYS})
    local["sync_folder"] = ""
    _write_json(data_dir / "settings.json", local)
    (data_dir / "notes").mkdir(exist_ok=True)
    for note in (sync_dir / "notes").glob("*.json"):
        shutil.copy2(note, data_dir / "notes" / note.name)
    merge_history(sync_dir / "history.jsonl", data_dir / "history.jsonl")


def merge_history(src, dest):
    def load(p):
        try:
            return [json.loads(x) for x in Path(p).read_text("utf-8").splitlines() if x.strip()]
        except (OSError, ValueError):
            return []

    merged = {e["t"]: e for e in load(dest) + load(src)}
    items = sorted(merged.values(), key=lambda e: e["t"])[-History.LIMIT:]
    Path(dest).write_text("".join(json.dumps(e) + "\n" for e in items), "utf-8")


class History:
    LIMIT = 500

    def __init__(self, path):
        self.path = path
        self.items = []
        self.mtime = 0
        self.refresh(force=True)

    def refresh(self, force=False):
        """Reload if another PC changed the (synced) file. Returns True when the items changed."""
        try:
            m = self.path.stat().st_mtime
        except OSError:
            return False
        if not force and m <= self.mtime + 0.5:
            return False
        try:
            self.items = [json.loads(line) for line in self.path.read_text("utf-8").splitlines() if line.strip()]
            self.mtime = m
        except (OSError, ValueError):
            return False
        return True

    def add(self, text, secs, model, raw=None, mode=None, app=None):
        self.refresh()  # pick up entries a synced PC added meanwhile, so they are not overwritten
        entry = {"t": time.time(), "text": text, "secs": round(secs, 1), "model": model}
        if app:
            entry["app"] = app
        if raw and raw != text:
            entry.update(raw=raw, mode=mode)  # the transcript before the AI mode rewrote it
        self.items.append(entry)
        self.items = self.items[-self.LIMIT:]
        self._write()

    def delete(self, t):
        self.items = [e for e in self.items if e["t"] != t]
        self._write()

    def clear(self):
        self.items = []
        self._write()

    def stats(self):
        midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        words = lambda es: sum(len(e["text"].split()) for e in es)
        today = [e for e in self.items if e["t"] >= midnight]
        total_words = words(self.items)
        spoken_s = sum(e.get("secs", 0) for e in self.items)
        # typing at ~40 wpm versus the time actually spent talking
        saved_min = max(0, total_words / 40 - spoken_s / 60)
        # last 14 days, oldest first, and the streak of days in a row (up to today or yesterday)
        day = 86400
        days = []
        for back in range(13, -1, -1):
            start = midnight - back * day
            es = [e for e in self.items if start <= e["t"] < start + day]
            days.append({"date": time.strftime("%a %d %b", time.localtime(start + 3600)), "words": words(es)})
        active = {time.strftime("%Y%m%d", time.localtime(e["t"])) for e in self.items}
        streak, d = 0, midnight
        if time.strftime("%Y%m%d", time.localtime(d)) not in active:
            d -= day  # no dictation yet today: the streak can still be alive from yesterday
        while time.strftime("%Y%m%d", time.localtime(d)) in active:
            streak, d = streak + 1, d - day
        apps = {}
        for e in self.items:
            if e.get("app") and e["app"] != "file":
                apps[e["app"]] = apps.get(e["app"], 0) + len(e["text"].split())
        top_apps = sorted(apps.items(), key=lambda kv: -kv[1])[:5]
        wpm = round(total_words / (spoken_s / 60)) if spoken_s > 30 else 0
        best = max(days, key=lambda x: x["words"]) if days else None
        return {"today_words": words(today), "total_words": total_words, "count": len(self.items),
                "saved_min": round(saved_min), "days": days, "streak": streak, "wpm": wpm,
                "top_apps": [{"app": a, "words": w} for a, w in top_apps],
                "week_words": sum(x["words"] for x in days[-7:]), "best_day": best if best and best["words"] else None}

    def _write(self):
        self.path.write_text("".join(json.dumps(e) + "\n" for e in self.items), "utf-8")
        self.mtime = self.path.stat().st_mtime


class Notes:
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(exist_ok=True)

    def list(self):
        out = []
        for p in self.folder.glob("*.json"):
            try:
                n = json.loads(p.read_text("utf-8"))
                out.append({k: n[k] for k in ("id", "title", "updated", "preview")})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(out, key=lambda n: -n["updated"])

    def get(self, note_id):
        return json.loads((self.folder / f"{note_id}.json").read_text("utf-8"))

    def new(self):
        now = time.time()
        n = {"id": uuid.uuid4().hex[:12], "title": "", "html": "", "preview": "", "created": now, "updated": now}
        self._write(n)
        return n

    def save(self, note_id, title, html, preview):
        try:
            n = self.get(note_id)
        except (OSError, ValueError):
            n = {"id": note_id, "created": time.time()}
        n.update(title=title, html=html, preview=preview[:160], updated=time.time())
        self._write(n)
        return n["updated"]

    def delete(self, note_id):
        (self.folder / f"{note_id}.json").unlink(missing_ok=True)

    def _write(self, n):
        tmp = self.folder / f"{n['id']}.json.tmp"
        tmp.write_text(json.dumps(n), "utf-8")
        tmp.replace(self.folder / f"{n['id']}.json")
