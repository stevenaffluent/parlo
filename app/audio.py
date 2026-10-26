"""Microphone capture and the start/stop cue sounds."""
import logging

import numpy as np

log = logging.getLogger("bark.audio")
SR = 16000


def list_microphones():
    """Input device names on the default host API (avoids listing each mic 3-4 times)."""
    import sounddevice as sd

    try:
        api = sd.query_devices(kind="input")["hostapi"]
    except Exception:
        api = None
    names = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and (api is None or d["hostapi"] == api) and d["name"] not in names:
            names.append(d["name"])
    return names


def _device_index(name):
    import sounddevice as sd

    if not name:
        return None
    api = sd.query_devices(kind="input")["hostapi"]
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0 and d["hostapi"] == api:
            return i
    return None


class Recorder:
    def __init__(self):
        self.stream = None
        self.chunks = []
        self.level = 0.0
        self.rate = SR

    def start(self, mic_name=None):
        import sounddevice as sd

        self.chunks, self.level, self.problems = [], 0.0, set()
        device = _device_index(mic_name)

        def callback(indata, frames, t, status):
            if status:
                self.problems.add(str(status))
            x = indata[:, 0].copy()
            self.chunks.append(x)
            self.level = float(np.sqrt(np.mean(x * x)))

        opts = dict(channels=1, dtype="float32", device=device, callback=callback)
        try:
            self.rate = SR
            self.stream = sd.InputStream(samplerate=SR, **opts)
        except Exception:
            self.rate = int(sd.query_devices(device, "input")["default_samplerate"])
            log.info("mic does not take 16 kHz, recording at %d and resampling", self.rate)
            self.stream = sd.InputStream(samplerate=self.rate, **opts)
        self.stream.start()

    def snapshot(self, seconds):
        """The last `seconds` of audio recorded so far, at 16 kHz, without stopping (for live text)."""
        chunks, need, got = list(self.chunks), int(seconds * self.rate), 0
        tail = []
        for c in reversed(chunks):
            tail.append(c)
            got += len(c)
            if got >= need:
                break
        if not tail:
            return np.zeros(0, np.float32)
        wave = np.concatenate(tail[::-1])[-need:]
        if self.rate != SR:
            import soxr

            wave = soxr.resample(wave, self.rate, SR).astype(np.float32)
        return wave

    def drain(self):
        """Everything recorded since the last drain, at 16 kHz; recording carries on (meeting recorder)."""
        chunks, self.chunks = self.chunks, []
        wave = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
        if self.rate != SR and len(wave):
            import soxr

            wave = soxr.resample(wave, self.rate, SR).astype(np.float32)
        return wave

    def stop(self):
        if self.stream is None:
            return np.zeros(0, np.float32)
        try:
            self.stream.stop()
            self.stream.close()
        finally:
            self.stream = None
        wave = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
        log.info("mic: %d blocks%s", len(self.chunks), f", problems: {sorted(self.problems)}" if self.problems else "")
        self.chunks = []
        if self.rate != SR and len(wave):
            import soxr

            wave = soxr.resample(wave, self.rate, SR).astype(np.float32)
        return wave


def _chirp(f0, f1, dur=0.09, rate=44100, vol=0.18):
    t = np.arange(int(dur * rate)) / rate
    freq = np.linspace(f0, f1, len(t))
    env = np.minimum(1, np.minimum(t / 0.01, (dur - t) / 0.03))
    return (vol * env * np.sin(2 * np.pi * np.cumsum(freq) / rate)).astype(np.float32)


_CUES = {"start": _chirp(660, 990), "stop": _chirp(880, 560), "error": _chirp(300, 220, 0.18)}


def play_cue(name):
    try:
        import sounddevice as sd

        sd.play(_CUES[name], 44100)
    except Exception as e:  # a missing speaker must never break dictation
        log.debug("cue failed: %s", e)
