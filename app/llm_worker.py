"""Local AI process for AI modes: loads one small language model (llama.cpp) and rewrites text.

It runs separately from the app and the speech model so its memory is freed completely when it is
unloaded, and generating text never stalls the microphone or keyboard.
Usage (started by engine_client.py):  llm_worker.py <port> <authkey-hex> <model-id>
"""
import logging
import os
import re
import sys
import time
from multiprocessing.connection import Client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
logging.basicConfig(filename=DATA / "engine.log", level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("parlo.llm")
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(DATA / "console.log", "a", encoding="utf-8", buffering=1)
sys.path.insert(0, str(Path(__file__).parent))

import models  # noqa: E402

THINK = re.compile(r"<think>.*?</think>", re.S)


def main():
    port, key, model_id = int(sys.argv[1]), bytes.fromhex(sys.argv[2]), sys.argv[3]
    conn = Client(("127.0.0.1", port), authkey=key)
    t0 = time.time()
    try:
        from llama_cpp import Llama

        if not models.is_installed(model_id):
            raise FileNotFoundError(f"{models.BY_ID[model_id]['name']} is not downloaded yet.")
        llm = Llama(model_path=str(models.llm_path(model_id)), n_ctx=4096, n_threads=max(1, os.cpu_count() or 1),
                    verbose=False)
    except Exception as e:
        log.exception("loading %s failed", model_id)
        conn.send(("error", str(e)))
        return
    qwen3 = model_id.startswith("qwen3")
    log.info("%s ready in %.1fs", model_id, time.time() - t0)
    conn.send(("ready", {"device": "cpu", "load_s": round(time.time() - t0, 1), "pid": os.getpid()}))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break
        if msg[0] == "quit":
            break
        if msg[0] == "rewrite":
            system, text = msg[1], msg[2]
            if qwen3:  # answer directly instead of "thinking" first: much faster, same quality for rewrites
                system += " /no_think"
            t0 = time.time()
            try:
                r = llm.create_chat_completion(
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
                    temperature=0.2, max_tokens=max(256, len(text) // 2))
                out = THINK.sub("", r["choices"][0]["message"]["content"]).strip()
                conn.send(("result", out, round(time.time() - t0, 2)))
            except Exception as e:
                log.exception("rewrite failed")
                conn.send(("failed", str(e)))


if __name__ == "__main__":
    main()
