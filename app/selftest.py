"""Self-test: a Windows voice speaks a sentence into a WAV file, then Bark 3.0 transcribes it.

Run:  .venv\\Scripts\\python.exe app\\selftest.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "data" / "hf"))
if (ROOT / "data" / "hf" / ".prefetched").exists():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(Path(__file__).parent))

SENTENCE = "Hello from Parlo. The quick brown fox jumps over the lazy dog, and it costs twenty five dollars."


def synthesize(path):
    import comtypes.client

    voice = comtypes.client.CreateObject("SAPI.SpVoice", dynamic=True)
    stream = comtypes.client.CreateObject("SAPI.SpFileStream", dynamic=True)
    stream.Open(str(path), 3)  # SSFMCreateForWrite
    voice.AudioOutputStream = stream
    voice.Speak(SENTENCE)
    stream.Close()


def main():
    from engine import BarkEngine, read_audio_file, tidy

    wav = Path(tempfile.gettempdir()) / "bark_selftest.wav"
    synthesize(wav)
    wave = read_audio_file(wav)
    print(f"spoken: {SENTENCE}\naudio: {len(wave) / 16000:.1f}s")
    eng = BarkEngine(ROOT / "model")
    t0 = time.time()
    eng.load()
    print(f"model load + warm-up: {time.time() - t0:.1f}s on {eng.device}")
    t0 = time.time()
    text = eng.transcribe(wave)
    print(f"heard:  {text}\ntidied: {tidy(text)}\ntranscribe time: {time.time() - t0:.2f}s")
    sys.exit(0 if "fox" in text.lower() else 1)


if __name__ == "__main__":
    main()
