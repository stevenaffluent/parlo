"""Natural read-aloud voice process: loads Kokoro (ONNX) and turns sentences into audio.

Runs apart from the app like the other workers, so its memory is freed when it is unloaded.
Usage (started by engine_client.py):  tts_worker.py <port> <authkey-hex> <model-id>
"""
import logging
import os
import sys
import time
from multiprocessing.connection import Client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
logging.basicConfig(filename=DATA / "engine.log", level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("parlo.tts")
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(DATA / "console.log", "a", encoding="utf-8", buffering=1)
sys.path.insert(0, str(Path(__file__).parent))

import models  # noqa: E402

# Kokoro voice ids start with a language letter: a=US English, b=UK English, e=Spanish, f=French,
# i=Italian, p=Brazilian Portuguese (these work with the bundled espeak-ng phonemiser).
LANGS = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "i": "it", "p": "pt-br"}


def main():
    port, key, model_id = int(sys.argv[1]), bytes.fromhex(sys.argv[2]), sys.argv[3]
    conn = Client(("127.0.0.1", port), authkey=key)
    t0 = time.time()
    try:
        from kokoro_onnx import Kokoro

        d = models.model_dir(model_id)
        files = list(models.BY_ID[model_id]["files"])
        kokoro = Kokoro(str(d / files[0]), str(d / files[1]))
    except Exception as e:
        log.exception("loading %s failed", model_id)
        conn.send(("error", str(e)))
        return
    log.info("%s ready in %.1fs", model_id, time.time() - t0)
    conn.send(("ready", {"device": "cpu", "load_s": round(time.time() - t0, 1), "pid": os.getpid()}))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break
        if msg[0] == "quit":
            break
        if msg[0] == "synth":
            text, voice, speed = msg[1], msg[2], msg[3]
            t0 = time.time()
            try:
                samples, sr = kokoro.create(text, voice=voice, speed=speed, lang=LANGS.get(voice[:1], "en-us"))
                conn.send(("result", (samples.astype("float32"), sr), round(time.time() - t0, 2)))
            except Exception as e:
                log.exception("synthesis failed")
                conn.send(("failed", str(e)))


if __name__ == "__main__":
    main()
