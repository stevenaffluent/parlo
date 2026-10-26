"""Read-aloud with the voices built into Windows (SAPI). Bark 3.0 only does speech-to-text."""
import logging
import queue
import threading

log = logging.getLogger("bark.speech")
SVSF_ASYNC, SVSF_PURGE = 1, 2


class Speaker:
    """All SAPI calls happen on one worker thread (COM objects belong to the thread that made them)."""

    def __init__(self):
        self.q = queue.Queue()
        self.voices = []
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="speaker").start()

    def speak(self, text):
        if text and text.strip():
            self.q.put(("speak", text))

    def stop(self):
        self.q.put(("stop",))

    def toggle(self, text):
        self.q.put(("toggle", text))

    def set_voice(self, name):
        self.q.put(("voice", name))

    def set_rate(self, rate):
        self.q.put(("rate", int(rate)))

    def _run(self):
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            voice = comtypes.client.CreateObject("SAPI.SpVoice", dynamic=True)
            tokens = voice.GetVoices()
            self.voices = [tokens.Item(i).GetDescription() for i in range(tokens.Count)]
        except Exception:
            log.exception("Windows speech (SAPI) unavailable")
            self.ready.set()
            return
        self.ready.set()
        while True:
            cmd = self.q.get()
            try:
                if cmd[0] == "speak":
                    voice.Speak(cmd[1], SVSF_ASYNC | SVSF_PURGE)
                elif cmd[0] == "stop":
                    voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                elif cmd[0] == "toggle":
                    if voice.Status.RunningState == 2:  # SRSEIsSpeaking
                        voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                    elif cmd[1] and cmd[1].strip():
                        voice.Speak(cmd[1], SVSF_ASYNC | SVSF_PURGE)
                elif cmd[0] == "voice" and cmd[1] in self.voices:
                    voice.Voice = tokens.Item(self.voices.index(cmd[1]))
                elif cmd[0] == "rate":
                    voice.Rate = max(-10, min(10, cmd[1]))
            except Exception:
                log.exception("speech command %s failed", cmd[0])
