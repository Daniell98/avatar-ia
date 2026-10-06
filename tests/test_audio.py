import threading

import numpy as np
import pytest

from companhia.audio import Audio, AudioError
from companhia.config import Settings


class SilentStream:
    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.active = False
        self.closed = False

    def start(self):
        self.active = True
        self.callback(np.zeros((16000, 1), dtype="float32"), 16000, None, None)

    def abort(self):
        self.active = False

    def close(self):
        self.closed = True


async def test_silence_is_rejected_before_transcription(monkeypatch):
    instances = []

    def factory(**kwargs):
        stream = SilentStream(**kwargs)
        instances.append(stream)
        return stream

    monkeypatch.setattr("companhia.audio.sd.InputStream", factory)
    stop = threading.Event()
    stop.set()
    with pytest.raises(AudioError, match="silêncio"):
        await Audio().record(Settings(), stop)
    assert instances[0].closed


async def test_device_failure_is_readable(monkeypatch):
    import sounddevice as sd

    def fail(**kwargs):
        raise sd.PortAudioError("device disappeared")

    monkeypatch.setattr("companhia.audio.sd.InputStream", fail)
    with pytest.raises(AudioError, match="microfone"):
        await Audio().record(Settings(), threading.Event())
