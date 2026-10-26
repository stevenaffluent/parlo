"""Runs a worker (engine_worker.py for speech, llm_worker.py for local AI) in a child process and
talks to it over an authenticated local socket."""
import logging
import os
import subprocess
import sys
import threading
from multiprocessing.connection import Listener
from pathlib import Path

log = logging.getLogger("bark.client")
WORKER = Path(__file__).with_name("engine_worker.py")


class EngineClient:
    def __init__(self, on_event, worker=WORKER):
        """on_event(kind, generation, payload): kind is 'ready' or 'error'; called from a helper thread."""
        self.on_event = on_event
        self.worker = Path(worker)
        self.loaded = threading.Event()  # set once the worker answered ready or error
        self.load_error = None
        self.proc = None
        self.conn = None
        self.worker_pid = None
        self.model_id = None
        self.generation = 0
        self.lock = threading.Lock()

    @property
    def ready(self):
        return self.conn is not None

    def start(self, model_id):
        self.stop()
        self.generation += 1
        gen, self.model_id = self.generation, model_id
        self.loaded.clear()
        self.load_error = None
        key = os.urandom(16)
        listener = Listener(("127.0.0.1", 0), authkey=key)
        self.proc = proc = subprocess.Popen(
            [sys.executable, str(self.worker), str(listener.address[1]), key.hex(), model_id],
            cwd=str(self.worker.parent.parent), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.info("%s process %d starting %s", self.worker.stem, proc.pid, model_id)

        connected = threading.Event()

        def watchdog():  # if the worker dies before connecting, unblock accept()
            proc.wait()
            if not connected.is_set():
                listener.close()

        def connect():
            try:
                conn = listener.accept()
                connected.set()
                kind, payload = conn.recv()
            except Exception as e:
                code = proc.poll()
                self.load_error = (f"The {self.worker.stem.replace('_', ' ')} stopped while loading (exit code {code}). "
                                   f"See data\\engine.log. {e}")
                self.loaded.set()
                self.on_event("error", gen, self.load_error)
                return
            finally:
                try:
                    listener.close()
                except OSError:
                    pass
            if gen != self.generation:  # a newer model was chosen meanwhile
                conn.close()
                return
            if kind == "ready":
                self.conn = conn
                self.worker_pid = payload.get("pid")  # the venv launcher's child, where the model lives
            else:
                self.load_error = str(payload)
            self.loaded.set()
            self.on_event(kind, gen, payload)

        threading.Thread(target=watchdog, daemon=True).start()
        threading.Thread(target=connect, daemon=True).start()

    def try_transcribe(self, wave):
        """For live previews: transcribe only if the engine is idle right now; returns text or None."""
        if not self.lock.acquire(blocking=False):
            return None
        self.lock.release()  # transcribe() takes it again; a final transcription may slip in first, which is fine
        try:
            return self.transcribe(wave)[0]
        except RuntimeError:
            return None

    def transcribe(self, wave):
        """Returns (text, seconds). Raises RuntimeError if the engine is not available."""
        return self.call("transcribe", wave)

    def call(self, *msg):
        """Send one request to the worker and wait for its ("result", value, seconds) reply."""
        with self.lock:
            if self.conn is None:
                raise RuntimeError("The model is not loaded.")
            try:
                self.conn.send(msg)
                reply = self.conn.recv()
            except (EOFError, OSError) as e:
                self.conn = None
                raise RuntimeError(f"The {self.worker.stem.replace('_', ' ')} stopped unexpectedly ({e}).")
        if reply[0] == "result":
            return reply[1], reply[2]
        raise RuntimeError(reply[1])

    def stop(self):
        conn, proc = self.conn, self.proc
        self.conn = self.proc = self.worker_pid = None
        self.generation += 1
        if conn is not None:
            try:
                conn.send(("quit",))
                conn.close()
            except OSError:
                pass
        if proc is not None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def memory_mb(self):
        """Private memory of the engine process, for the Models page."""
        if self.proc is None or self.proc.poll() is not None or not self.worker_pid:
            return 0
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                   "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                                   "PrivateUsage")]

            k = ctypes.windll.kernel32
            k.OpenProcess.restype = wintypes.HANDLE
            k.CloseHandle.argtypes = [wintypes.HANDLE]
            k.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
            h = k.OpenProcess(0x1000, False, self.worker_pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            c = PMC()
            c.cb = ctypes.sizeof(c)
            k.K32GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
            k.CloseHandle(h)
            return int(c.PrivateUsage / 2**20)
        except Exception:
            return 0
