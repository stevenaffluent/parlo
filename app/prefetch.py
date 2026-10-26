"""Setup steps that fetch and prepare models, so the app then runs fully offline.

    prefetch.py speech   download Bark 3.0 (pinned) and the small processor files it needs
    prefetch.py unpack   unpack the speech model's weights once (a few minutes on CPU)
    prefetch.py llm      download the free on-PC AI writing model
    prefetch.py          all of the above

For the installer window, progress is printed as machine-readable lines:
"@status <text>" and "@progress <0..1>" (fraction of the current step).
"""
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
os.environ["HF_HOME"] = str(DATA / "hf")
os.environ.pop("HF_HUB_OFFLINE", None)
sys.path.insert(0, str(ROOT / "app"))

import models  # noqa: E402


def say(status=None, progress=None):
    if status is not None:
        print(f"@status {status}", flush=True)
    if progress is not None:
        print(f"@progress {progress:.3f}", flush=True)


def download(model_id):
    """Blocking download through models.Downloader, reporting progress. Returns True on success."""
    if models.is_installed(model_id):
        say(f"{models.BY_ID[model_id]['name']} is already downloaded", 1)
        return True
    m = models.BY_ID[model_id]
    say(f"Downloading {m['name']} ({models.download_mb(model_id)} MB)", 0)
    done, result = threading.Event(), {}

    def progress(_id, frac, state, msg):
        if state == "downloading":
            say(progress=frac)
        else:
            result.update(state=state, msg=msg)
            done.set()

    models.Downloader(progress).start(model_id)
    done.wait()
    if result["state"] != "done":
        say(result["msg"] or "Download failed")
        return False
    say(f"{m['name']} downloaded", 1)
    return True


def speech():
    if not download(models.DEFAULT_MODEL):
        sys.exit(1)
    say("Fetching the speech processor settings", 0.98)
    from transformers import AutoProcessor, GenerationConfig

    from engine import BASE_MODEL

    AutoProcessor.from_pretrained(BASE_MODEL)
    GenerationConfig.from_pretrained(BASE_MODEL)
    (DATA / "hf" / ".prefetched").write_text("ok")
    from icon import save_ico

    save_ico(DATA / "icon.ico")
    say("Speech model ready", 1)


def unpack():
    say("Unpacking the speech model (one time only, can take a few minutes)", 0)
    from engine import BarkEngine

    BarkEngine(models.model_dir(models.DEFAULT_MODEL)).load()
    say("Speech model unpacked", 1)


def llm():
    # not fatal: the model can also be downloaded later from AI modes
    if not download(models.DEFAULT_LLM):
        say("The AI writing model can be downloaded later in AI modes.", 1)


if __name__ == "__main__":
    steps = {"speech": [speech], "unpack": [unpack], "llm": [llm], "all": [speech, unpack, llm]}
    for step in steps[sys.argv[1] if len(sys.argv) > 1 else "all"]:
        step()
