"""The models the app can use (speech-to-text, AI writing, read-aloud voices, and models the
user adds), and downloading/removing them."""
import ctypes
import json
import logging
import re
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger("bark.models")
ROOT = Path(__file__).resolve().parent.parent

# Revisions are pinned: bark_loader.py is code the app runs, and pinned files never change under us.
CATALOG = [
    {
        "id": "bark-3.0", "name": "Bark 3.0", "family": "Parakeet", "engine": "bark",
        "repo": "ConwayResearch/Underdog-Bark-3.0", "revision": "85db2ad18ab41e534a222ee253c29191d77ed919",
        "files": {"model.bark": 163398645, "bark_loader.py": 5820, "NOTICE": 603},
        "languages": "English", "ram_gb": 3.2, "accuracy": 4, "speed": 4, "license": "CC-BY-4.0",
        "blurb": "Recommended. Very accurate English dictation with punctuation, in a small download.",
    },
    {
        "id": "bark-3.0-plus", "name": "Bark 3.0 Plus", "family": "Parakeet", "engine": "bark",
        "repo": "ConwayResearch/Underdog-Bark-3.0-Plus", "revision": "d4fab2f8b95681e5ad3cfb4e8c5f4e0c009b3deb",
        "files": {"model.bark": 179535872, "bark_loader.py": 5820, "NOTICE": 603},
        "languages": "English", "ram_gb": 3.3, "accuracy": 5, "speed": 4, "license": "CC-BY-4.0",
        "blurb": "A little more accurate than Bark 3.0 for a slightly bigger download.",
    },
    {
        "id": "whisper-base.en", "name": "Whisper Base", "family": "Whisper", "engine": "whisper",
        "repo": "Systran/faster-whisper-base.en", "revision": "3d3d5dee26484f91867d81cb899cfcf72b96be6c",
        "files": {"model.bin": 145262807, "config.json": 2000, "tokenizer.json": 2132000, "vocabulary.txt": 460000},
        "languages": "English", "ram_gb": 1.2, "accuracy": 2, "speed": 5, "license": "MIT", "multilingual": False,
        "blurb": "Small and very fast, with good punctuation. Best for low-memory PCs; makes more mistakes.",
    },
    {
        "id": "whisper-small.en", "name": "Whisper Small", "family": "Whisper", "engine": "whisper",
        "repo": "Systran/faster-whisper-small.en", "revision": "d1d751a5f8271d482d14ca55d9e2deeebbae577f",
        "files": {"model.bin": 483508000, "config.json": 2000, "tokenizer.json": 2132000, "vocabulary.txt": 460000},
        "languages": "English", "ram_gb": 1.6, "accuracy": 3, "speed": 3, "license": "MIT", "multilingual": False,
        "blurb": "A middle ground: light on memory, decent accuracy.",
    },
    {
        "id": "whisper-large-v3-turbo", "name": "Whisper Large v3 Turbo", "family": "Whisper", "engine": "whisper",
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "revision": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        "files": {"model.bin": 1617825000, "config.json": 2400, "preprocessor_config.json": 400,
                  "tokenizer.json": 2726000, "vocabulary.json": 1068000},
        "languages": "99 languages", "ram_gb": 2.6, "accuracy": 4, "speed": 2, "license": "MIT", "multilingual": True,
        "blurb": "The one to pick for languages other than English. Slower on CPU.",
    },
]
# Local AI writing models for AI modes (llama.cpp GGUF files). Timings measured on a 6-core
# i5-8500 without a graphics card for a 1-2 sentence clean-up; the 4B figures are estimates.
LLM_CATALOG = [
    {
        "id": "qwen2.5-1.5b", "name": "Qwen2.5 1.5B", "family": "Qwen", "engine": "llm",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "revision": "91cad51170dc346986eccefdc2dd33a9da36ead9",
        "files": {"qwen2.5-1.5b-instruct-q4_k_m.gguf": 1117320736},
        "ram_gb": 1.7, "accuracy": 3, "speed": 5, "license": "Apache-2.0", "secs": "1-2 s",
        "blurb": "Recommended. Fast on any everyday PC; good clean-ups and bullet lists.",
    },
    {
        "id": "qwen3-1.7b", "name": "Qwen3 1.7B", "family": "Qwen", "engine": "llm",
        "repo": "Qwen/Qwen3-1.7B-GGUF", "revision": "90862c4b9d2787eaed51d12237eafdfe7c5f6077",
        "files": {"Qwen3-1.7B-Q8_0.gguf": 1834426016},
        "ram_gb": 2.0, "accuracy": 4, "speed": 3, "license": "Apache-2.0", "secs": "3-4 s",
        "blurb": "Sticks most closely to your own words. A little slower.",
    },
    {
        "id": "qwen3-4b", "name": "Qwen3 4B", "family": "Qwen", "engine": "llm",
        "repo": "Qwen/Qwen3-4B-GGUF", "revision": "bc640142c66e1fdd12af0bd68f40445458f3869b",
        "files": {"Qwen3-4B-Q4_K_M.gguf": 2497280256},
        "ram_gb": 3.5, "accuracy": 5, "speed": 2, "license": "Apache-2.0", "secs": "~8 s",
        "blurb": "Best writing quality, for rewrites like emails. Needs a stronger PC with 16 GB RAM.",
    },
]
# Natural read-aloud voices (Kokoro-82M, Apache-2.0) in the ONNX build kokoro-onnx expects.
# The files live in GitHub releases, so they have direct URLs instead of a Hugging Face repo.
KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
TTS_CATALOG = [
    {
        "id": "kokoro", "name": "Kokoro natural voices", "family": "Kokoro", "engine": "tts",
        "files": {"kokoro-v1.0.int8.onnx": 92361271, "voices-v1.0.bin": 28214398},
        "urls": {f: KOKORO_RELEASE + f for f in ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")},
        "ram_gb": 0.6, "license": "Apache-2.0",
        "blurb": "54 lifelike voices that run on this PC, about twice as fast as real time on a CPU.",
    },
]

# Models the user added themselves (their own GGUF files, or Hugging Face repos), stored in
# data/custom_models.json and merged into the catalogs above.
CUSTOM_FILE = ROOT / "data" / "custom_models.json"
BY_ID = {}


def _rebuild():
    BY_ID.clear()
    BY_ID.update({m["id"]: m for m in CATALOG + LLM_CATALOG + TTS_CATALOG})


def load_custom():
    try:
        entries = json.loads(CUSTOM_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        entries = []
    for e in entries:
        target = LLM_CATALOG if e["engine"] == "llm" else CATALOG
        if not any(m["id"] == e["id"] for m in target):
            target.append(e)
    _rebuild()


def _save_custom():
    custom = [m for m in CATALOG + LLM_CATALOG if m.get("custom")]
    CUSTOM_FILE.parent.mkdir(exist_ok=True)
    CUSTOM_FILE.write_text(json.dumps(custom, indent=2), "utf-8")


def add_custom(entry):
    entry["custom"] = True
    (LLM_CATALOG if entry["engine"] == "llm" else CATALOG).append(entry)
    _rebuild()
    _save_custom()
    return entry


def remove_custom(model_id):
    for cat in (CATALOG, LLM_CATALOG):
        cat[:] = [m for m in cat if m["id"] != model_id]
    _rebuild()
    _save_custom()


DEFAULT_MODEL = "bark-3.0"
DEFAULT_LLM = "qwen2.5-1.5b"


def llm_path(model_id):
    m = BY_ID[model_id]
    if m.get("path"):  # a GGUF file the user picked on their own PC: used where it is
        return Path(m["path"])
    return model_dir(model_id) / next(iter(m["files"]))


def model_dir(model_id):
    # Bark 3.0 lives in model/ because the first version of the app put it there
    return ROOT / "model" if model_id == "bark-3.0" else ROOT / "models" / model_id


def is_installed(model_id):
    m = BY_ID[model_id]
    if m.get("path"):
        return Path(m["path"]).is_file()
    d = model_dir(model_id)
    return all((d / name).is_file() for name in m["files"])


# ---- adding your own models -------------------------------------------------------------
def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def parse_repo(text):
    """'https://huggingface.co/Org/Name/tree/main' or 'Org/Name' -> 'Org/Name'."""
    text = text.strip()
    m = re.search(r"huggingface\.co/([\w.-]+/[\w.-]+)", text) or re.fullmatch(r"([\w.-]+/[\w.-]+)", text)
    if not m:
        raise ValueError("Enter a Hugging Face model like Org/Model-Name or paste its link.")
    return m.group(1)


def _hf_json(path):
    req = urllib.request.Request(f"https://huggingface.co/api/models/{path}", headers={"User-Agent": "Parlo/2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def inspect_repo(text, kind):
    """Look a Hugging Face repo up and say what can be used from it.
    kind 'llm': its .gguf files; kind 'whisper': a faster-whisper (CTranslate2) model."""
    repo = parse_repo(text)
    try:
        info = _hf_json(repo)
        tree = _hf_json(f"{repo}/tree/{info['sha']}")
    except urllib.error.HTTPError as e:
        raise ValueError("That model was not found, or it needs a Hugging Face login." if e.code in (401, 403, 404)
                         else f"Hugging Face answered {e.code}.")
    if info.get("gated"):
        raise ValueError("This model needs you to accept its terms on Hugging Face, so Parlo can't download it.")
    files = {f["path"]: f["size"] for f in tree if f.get("type") == "file"}
    license_ = next((t.split(":", 1)[1] for t in info.get("tags", []) if t.startswith("license:")), "see model page")
    out = {"repo": repo, "revision": info["sha"], "license": license_}
    if kind == "llm":
        ggufs = sorted(((p, s) for p, s in files.items() if p.lower().endswith(".gguf") and "/" not in p
                        and "mmproj" not in p.lower()), key=lambda x: x[1])
        if not ggufs:
            raise ValueError("No .gguf files in that repo. Look for a repo whose name ends in -GGUF.")
        out["choices"] = [{"file": p, "mb": round(s / 2**20)} for p, s in ggufs]
    else:
        if "model.bin" not in files or "config.json" not in files:
            raise ValueError("That isn't a faster-whisper model (it needs model.bin). "
                             "Look for repos named like Systran/faster-whisper-...")
        keep = {p: s for p, s in files.items() if "/" not in p and not p.lower().endswith((".md", ".png", ".jpg"))
                and not p.startswith(".")}
        out["files"] = keep
        out["mb"] = round(sum(keep.values()) / 2**20)
    return out


def custom_llm_from_repo(info, filename):
    size = next(c["mb"] for c in info["choices"] if c["file"] == filename) * 2**20
    name = re.sub(r"(?i)\.gguf$", "", filename)
    return {"id": "custom-" + _slug(name), "name": name, "family": info["repo"].split("/")[0], "engine": "llm",
            "repo": info["repo"], "revision": info["revision"], "files": {filename: size},
            "ram_gb": round(size / 2**30 * 1.2 + 0.4, 1), "accuracy": 0, "speed": 0, "license": info["license"],
            "secs": "untested", "blurb": f"Your own model from {info['repo']}. Untested by Parlo."}


def custom_llm_from_file(path):
    p = Path(path)
    size = p.stat().st_size
    return {"id": "custom-" + _slug(p.stem), "name": p.stem, "family": "Your file", "engine": "llm", "path": str(p),
            "files": {p.name: size}, "ram_gb": round(size / 2**30 * 1.2 + 0.4, 1), "accuracy": 0, "speed": 0,
            "license": "your file", "secs": "untested", "blurb": f"Your own model file: {p}. Untested by Parlo."}


def custom_whisper_from_repo(info):
    repo = info["repo"]
    size = info["files"].get("model.bin", 0)
    return {"id": "custom-" + _slug(repo.split("/")[-1]), "name": repo.split("/")[-1], "family": "Whisper",
            "engine": "whisper", "repo": repo, "revision": info["revision"], "files": info["files"],
            "languages": "English" if ".en" in repo.lower() else "Multilingual", "multilingual": ".en" not in repo.lower(),
            "ram_gb": round(size / 2**30 * 0.8 + 0.6, 1), "accuracy": 0, "speed": 0, "license": info["license"],
            "blurb": f"Your own faster-whisper model from {repo}. Untested by Parlo."}


# ---- memory --------------------------------------------------------------------------------
def available_gb():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                                              "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]

    s = MemoryStatus()
    s.dwLength = ctypes.sizeof(s)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.ullAvailPhys / 2**30, s.ullTotalPhys / 2**30


def memory_check(model_id, freed_gb=0.0):
    """None if the model should fit in free memory, else a plain-English warning.
    freed_gb: memory that will be released first (the model being replaced)."""
    need = BY_ID[model_id].get("ram_gb", 1)
    free, total = available_gb()
    if need > total * 0.8:
        return f"This model needs about {need:.1f} GB of memory but this PC has {total:.0f} GB in total, so it will not run well."
    if need > free + freed_gb - 0.5:
        return (f"This model needs about {need:.1f} GB of memory and only {free + freed_gb:.1f} GB is free right now. "
                "Close other apps first, or it may be very slow.")
    return None


def download_mb(model_id):
    return round(sum(BY_ID[model_id]["files"].values()) / 2**20)


class Downloader:
    """One background download at a time; progress goes to on_progress(model_id, fraction, state, message)."""

    def __init__(self, on_progress):
        self.on_progress = on_progress
        self.current = None
        self.cancel = threading.Event()

    def start(self, model_id):
        if self.current:
            return False
        self.current = model_id
        self.cancel.clear()
        threading.Thread(target=self._run, args=(model_id,), daemon=True, name="download").start()
        return True

    def stop(self):
        self.cancel.set()

    def _run(self, model_id):
        m = BY_ID[model_id]
        d = model_dir(model_id)
        d.mkdir(parents=True, exist_ok=True)
        total = sum(m["files"].values())
        done = 0
        try:
            for name, expected in sorted(m["files"].items(), key=lambda kv: kv[1]):
                target = d / name
                if target.is_file():
                    done += expected
                    continue
                url = m.get("urls", {}).get(name) or f"https://huggingface.co/{m['repo']}/resolve/{m['revision']}/{name}"
                part = target.with_name(name + ".part")
                req = urllib.request.Request(url, headers={"User-Agent": "Parlo/2"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(part, "wb") as out:
                    while True:
                        if self.cancel.is_set():
                            raise InterruptedError
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        self.on_progress(model_id, min(done / total, 0.999), "downloading", "")
                part.replace(target)
            self.on_progress(model_id, 1.0, "done", "")
        except InterruptedError:
            self.on_progress(model_id, 0.0, "cancelled", "Download cancelled")
        except Exception as e:
            log.exception("download of %s failed", model_id)
            self.on_progress(model_id, 0.0, "error", f"Download failed: {e}")
        finally:
            for p in d.glob("*.part"):
                p.unlink(missing_ok=True)
            self.current = None


def delete(model_id):
    m = BY_ID[model_id]
    d = model_dir(model_id)
    if model_id == "bark-3.0":  # model/ also holds the HF cache folder; remove only our files
        for name in list(m["files"]) + ["bark-unpacked.safetensors"]:
            (d / name).unlink(missing_ok=True)
    elif not m.get("path"):  # never delete a file the user picked from their own folders
        shutil.rmtree(d, ignore_errors=True)
    if m.get("custom"):
        remove_custom(model_id)


load_custom()
