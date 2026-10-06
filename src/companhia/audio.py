from __future__ import annotations

import asyncio
import io
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioError(Exception):
    pass


def devices() -> list[dict]:
    try:
        return [
            {"id": i, "name": d["name"], "input": d["max_input_channels"], "output": d["max_output_channels"]}
            for i, d in enumerate(sd.query_devices())
        ]
    except sd.PortAudioError:
        raise AudioError("Não foi possível listar os dispositivos de áudio.") from None


class Audio:
    async def record(self, settings, stop: threading.Event, level=lambda x: None) -> bytes:
        blocks = []
        failure = []

        def callback(data, frames, timing, status):
            if status:
                failure.append(str(status))
            blocks.append(data.copy())

        stream = None
        try:
            stream = sd.InputStream(
                samplerate=settings.sample_rate,
                channels=1,
                dtype="float32",
                device=settings.input_device,
                callback=callback,
            )
            stream.start()
            deadline = time.monotonic() + settings.recording_seconds
            while not stop.is_set() and time.monotonic() < deadline:
                if not stream.active:
                    raise AudioError("O microfone foi desconectado ou parou de gravar.")
                if blocks:
                    level(float(np.max(np.abs(blocks[-1]))))
                await asyncio.sleep(0.05)
        except sd.PortAudioError:
            raise AudioError(
                "Falha no microfone. Confira dispositivo, taxa e permissão do Windows."
            ) from None
        finally:
            if stream is not None:
                stream.abort()
                stream.close()
        if failure:
            raise AudioError("A captura perdeu áudio. Tente outro dispositivo ou taxa nas configurações.")
        if not blocks:
            raise AudioError("Gravação vazia; nenhum áudio foi enviado.")
        samples = np.concatenate(blocks)
        if len(samples) < settings.sample_rate * 0.2 or np.sqrt(np.mean(samples**2)) < 0.002:
            raise AudioError("Gravação curta demais ou silêncio; nenhum áudio foi enviado.")
        wav = io.BytesIO()
        sf.write(wav, samples, settings.sample_rate, format="WAV", subtype="PCM_16")
        return wav.getvalue()

    async def play(self, audio: bytes, settings, started=lambda: None, valid=lambda: True):
        stream = None
        try:
            samples, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
            if not len(samples):
                raise AudioError("O áudio recebido está vazio.")
            position = 0

            def callback(out, frames, timing, status):
                nonlocal position
                out.fill(0)
                if not valid():
                    raise sd.CallbackStop()
                available = min(frames, len(samples) - position)
                out[:available] = samples[position : position + available]
                position += available
                if available < frames:
                    raise sd.CallbackStop()

            stream = sd.OutputStream(
                samplerate=rate,
                channels=samples.shape[1],
                dtype="float32",
                device=settings.output_device,
                callback=callback,
            )
            if not valid():
                raise asyncio.CancelledError()
            stream.start()
            started()
            while stream.active:
                await asyncio.sleep(0.03)
        except (sd.PortAudioError, sf.LibsndfileError, ValueError):
            raise AudioError(
                "Falha na reprodução. Confira o dispositivo de saída; o texto continua disponível."
            ) from None
        finally:
            if stream is not None:
                stream.abort()
                stream.close()

    async def test_output(self, settings):
        wav = io.BytesIO()
        wave = np.sin(np.arange(8000) * 2 * np.pi * 440 / 16000).astype("float32") * 0.08
        sf.write(wav, wave, 16000, format="WAV", subtype="PCM_16")
        await self.play(wav.getvalue(), settings)
