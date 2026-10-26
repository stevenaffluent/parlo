"""Speech engine process: loads one model and transcribes the audio the app sends it.

Running the model in its own process means switching models really frees the memory
(PyTorch on Windows keeps freed memory for itself), and heavy inference cannot starve the
app's microphone or keyboard threads.
Usage (started by engine_client.py):  engine_worker.py <port> <authkey-hex> <model-id>
"""
import logging
import os
import sys
import time
from multiprocessing.connection import Client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
os.environ.setdefault("HF_HOME", str(DATA / "hf"))
if (DATA / "hf" / ".prefetched").exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.basicConfig(filename=DATA / "engine.log", level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bark.worker")
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(DATA / "console.log", "a", encoding="utf-8", buffering=1)
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402

import models  # noqa: E402


class WhisperEngine:
    """Whisper through faster-whisper (CTranslate2), int8 on the CPU."""

    def __init__(self, model_dir, multilingual):
        self.model_dir = Path(model_dir)
        self.multilingual = multilingual
        self.model = None
        self.device = "cpu"

    def load(self):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(str(self.model_dir), device="cpu", compute_type="int8",
                                  cpu_threads=max(1, os.cpu_count() or 1))
        self.transcribe(np.zeros(16000, np.float32) + 1e-2 * np.random.randn(16000).astype(np.float32))

    def transcribe(self, wave, language=None):
        wave = np.asarray(wave, np.float32)
        if len(wave) < 4800 or float(np.abs(wave).max(initial=0.0)) < 1e-3:
            return ""
        segments, _ = self.model.transcribe(
            wave, language=None if self.multilingual and not language else (language or "en"),
            beam_size=1, vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()


def make_engine(model_id):
    m = models.BY_ID[model_id]
    if not models.is_installed(model_id):
        raise FileNotFoundError(f"{m['name']} is not downloaded yet.")
    if m["engine"] == "bark":
        from engine import BarkEngine

        return BarkEngine(models.model_dir(model_id))
    return WhisperEngine(models.model_dir(model_id), m.get("multilingual", False))


def main():
    port, key, model_id = int(sys.argv[1]), bytes.fromhex(sys.argv[2]), sys.argv[3]
    conn = Client(("127.0.0.1", port), authkey=key)
    t0 = time.time()
    try:
        engine = make_engine(model_id)
        engine.load()
    except Exception as e:
        log.exception("loading %s failed", model_id)
        conn.send(("error", str(e)))
        return
    log.info("%s ready in %.1fs on %s", model_id, time.time() - t0, engine.device)
    conn.send(("ready", {"device": engine.device, "load_s": round(time.time() - t0, 1), "pid": os.getpid()}))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break  # the app went away
        if msg[0] == "quit":
            break
        if msg[0] == "transcribe":
            t0 = time.time()
            try:
                text = engine.transcribe(msg[1])
                conn.send(("result", text, round(time.time() - t0, 2)))
            except Exception as e:
                log.exception("transcription failed")
                conn.send(("failed", str(e)))


if __name__ == "__main__":
    main()
