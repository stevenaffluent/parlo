"""Speech-to-text engine: Underdog Bark 3.0 loaded through its official bark_loader.py."""
import importlib.util
import logging
import os
import warnings
from pathlib import Path

import numpy as np

log = logging.getLogger("bark.engine")
warnings.filterwarnings("ignore", message=".*max_length.*")

BASE_MODEL = "nvidia/parakeet-tdt-0.6b-v3"  # processor + generation config the loader expects
SR = 16000
PAD_S = 0.25  # silence prepended before audio, the setting Bark 3.0 was evaluated with


def split_long(wave, sr=SR, max_s=40, search_s=6):
    """Cut long audio into <= max_s pieces, each cut at the quietest 50 ms in the last search_s seconds."""
    out, i, n, maxn = [], 0, len(wave), max_s * sr
    win = int(0.05 * sr)
    while n - i > maxn:
        lo, hi = i + maxn - search_s * sr, i + maxn
        energy = np.convolve(wave[lo:hi] ** 2, np.ones(win) / win, mode="valid")
        cut = lo + int(np.argmin(energy)) + win // 2
        out.append(wave[i:cut])
        i = cut
    out.append(wave[i:])
    return out


class BarkEngine:
    def __init__(self, model_dir, device="auto"):
        self.model_dir = Path(model_dir)
        self.device_pref = device
        self.model = None
        self.proc = None
        self.device = None

    @property
    def ready(self):
        return self.model is not None

    @property
    def cache_path(self):
        return self.model_dir / "bark-unpacked.safetensors"

    def load(self):
        import torch
        from transformers import AutoProcessor

        bark = self.model_dir / "model.bark"
        for p in (bark, self.model_dir / "bark_loader.py"):
            if not p.is_file():
                raise FileNotFoundError(f"Missing {p}. Run Setup.bat again.")
        if self.device_pref == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = self.device_pref
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        if not cache_is_current(self.model_dir):
            # Unpacking needs several GB of scratch memory that Windows does not hand back,
            # so do it in a short-lived child process and only read the result here.
            import subprocess
            import sys

            log.info("unpacking %s (first run only)", bark)
            subprocess.run([sys.executable, __file__, "--build-cache", str(self.model_dir)], check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.info("loading %s on %s", self.cache_path, self.device)
        self.model = load_from_cache(self.cache_path).to(self.device)
        self.proc = AutoProcessor.from_pretrained(BASE_MODEL)
        self._one(np.zeros(SR, np.float32))  # warm-up so the first dictation is fast
        log.info("model ready")

    def transcribe(self, wave):
        """wave: mono float32 at 16 kHz. Returns the transcript ('' for silence or very short clips)."""
        wave = np.asarray(wave, np.float32)
        if len(wave) < int(0.3 * SR) or float(np.abs(wave).max(initial=0.0)) < 1e-3:
            return ""
        texts = [self._one(part) for part in split_long(wave)]
        return " ".join(t for t in texts if t).strip()

    def _one(self, wave):
        import torch

        w = np.concatenate([np.zeros(int(PAD_S * SR), np.float32), wave])
        inp = self.proc([w], sampling_rate=SR, return_tensors="pt", padding=True)
        p = next(self.model.parameters())
        inp = {k: (v.to(p.device, p.dtype) if v.dtype.is_floating_point else v.to(p.device)) for k, v in inp.items()}
        with torch.inference_mode():
            out = self.model.generate(**inp)
        return self.proc.batch_decode(out.sequences, skip_special_tokens=True)[0].strip()


# Unpacking model.bark (entropy-coded) takes minutes on CPU, so the exact unpacked weights are kept
# next to it in bark-unpacked.safetensors and reused while model.bark is unchanged.
CACHE_LAYOUT = "fp16-where-exact"


def _sha256(path):
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cache_is_current(model_dir):
    from safetensors import safe_open

    cache = Path(model_dir) / "bark-unpacked.safetensors"
    if not cache.is_file():
        return False
    try:
        with safe_open(str(cache), "pt") as f:
            meta = f.metadata() or {}
    except Exception:
        log.exception("weight cache unreadable")
        return False
    return meta.get("layout") == CACHE_LAYOUT and meta.get("source_sha256") == _sha256(Path(model_dir) / "model.bark")


def build_cache(model_dir):
    """Unpack model.bark with the official bark_loader.py and save the weights."""
    import json

    import torch
    from safetensors.torch import save_file

    model_dir = Path(model_dir)
    spec = importlib.util.spec_from_file_location("bark_loader", model_dir / "bark_loader.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    raw, cfg = loader.load_state_dict(str(model_dir / "model.bark"))
    packed = {}
    for k in list(raw):
        v = raw.pop(k).float().contiguous()
        h = v.half()  # most tensors are fp16 levels, so fp16 is lossless for them and halves the file
        packed[k] = h if torch.equal(h.float(), v) else v
    tmp = model_dir / "bark-unpacked.safetensors.tmp"
    save_file(packed, str(tmp), metadata={"source_sha256": _sha256(model_dir / "model.bark"),
                                          "config": json.dumps(cfg), "layout": CACHE_LAYOUT})
    os.replace(tmp, model_dir / "bark-unpacked.safetensors")


def load_from_cache(cache):
    """Same model bark_loader.load_model builds, but created on the meta device and filled one tensor
    at a time, so loading needs about the model's size in RAM instead of four copies of it."""
    import json

    import torch
    from transformers import GenerationConfig, ParakeetForTDT, ParakeetTDTConfig

    # Plain reads instead of safetensors' memory map: on Windows the mapping and its fp16 copies
    # stay committed to the process, which doubled its memory.
    sd = {}
    with open(cache, "rb") as f:
        n = int.from_bytes(f.read(8), "little")
        header = json.loads(f.read(n))
        cfg = json.loads(header.pop("__metadata__")["config"])
        biggest = max(e - s for s, e in (i["data_offsets"] for i in header.values()))
        scratch = np.empty(biggest, np.uint8)  # one reusable read buffer for every tensor
        # All weights live in one block: separate allocations cost ~1.7x their size with
        # PyTorch's Windows allocator. Each tensor starts on a 64-float boundary.
        sizes = {name: int(np.prod(info["shape"])) for name, info in header.items()}
        flat = torch.empty(sum(-(-s // 64) * 64 for s in sizes.values()), dtype=torch.float32)
        flat_np, offset = flat.numpy(), 0
        for name, info in header.items():
            dtype = {"F16": np.float16, "F32": np.float32}[info["dtype"]]
            start, end = info["data_offsets"]
            f.seek(8 + n + start)
            f.readinto(memoryview(scratch)[: end - start])
            size = sizes[name]
            flat_np[offset:offset + size] = scratch[: end - start].view(dtype)
            sd[name] = flat[offset:offset + size].view(info["shape"])
            offset += -(-size // 64) * 64
        del scratch
    with torch.device("meta"):
        model = ParakeetForTDT(ParakeetTDTConfig.from_dict(cfg))
    missing, unexpected = model.load_state_dict(sd, strict=False, assign=True)
    del sd
    assert not unexpected and all("num_batches_tracked" in m for m in missing), (missing[:5], unexpected[:5])
    # buffers the checkpoint does not carry are still placeholders: create them for real
    for mod in model.modules():
        for name, buf in list(mod.named_buffers(recurse=False)):
            if not buf.is_meta:
                continue
            if name == "num_batches_tracked":
                mod.register_buffer(name, torch.zeros((), dtype=torch.long))
            elif name == "inv_freq":
                mod.register_buffer(name, mod.compute_default_relative_positional_parameters(mod.config), persistent=False)
            else:
                raise RuntimeError(f"uninitialised buffer {name} in {type(mod).__name__}")
    assert not any(t.is_meta for t in list(model.parameters()) + list(model.buffers()))
    model.generation_config = GenerationConfig.from_pretrained(BASE_MODEL)
    return model.eval()


def tidy(text):
    """Bark 3.0 tends to output lowercase without punctuation; give dictation a sentence shape."""
    import re

    text = text.strip()
    if not text:
        return text
    text = re.sub(r"\bi\b", "I", text)
    text = re.sub(r"\bi'(m|ll|d|ve)\b", lambda m: "I'" + m.group(1), text)
    text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    text = text[0].upper() + text[1:]
    if text[-1].isalnum():
        text += "."
    return text


def read_audio_file(path):
    """Read any file libsndfile understands (wav, flac, ogg, mp3) as mono 16 kHz float32."""
    import soundfile as sf
    import soxr

    wave, sr = sf.read(str(path), dtype="float32", always_2d=True)
    wave = wave.mean(1)
    if sr != SR:
        wave = soxr.resample(wave, sr, SR).astype(np.float32)
    return wave


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--build-cache":
        build_cache(sys.argv[2])
