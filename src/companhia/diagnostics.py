"""Diagnóstico de uma única amostra de voz, sem retry e sem conservar áudio/texto em logs."""

import io
import time
from pathlib import Path

import soundfile as sf

from .providers import ProviderError, Roteia
from .roteia_speech import RoteiaSpeech


async def speech_sample(
    engine, text: str, *, probe=False, play=True, emit=lambda value: None, generation=1
) -> dict:
    provider = Roteia(engine.settings, engine.llm.key)
    speech = RoteiaSpeech(provider, Path(engine.folder), probing=probe)
    if not probe and not speech.validated():
        raise ProviderError(
            "Compatibilidade ainda não validada. Use --probe-audio para uma amostra upstream explícita."
        )
    begin = time.monotonic()
    try:
        result = await engine.call(
            generation, "speech", engine.settings.speech_model, lambda: speech.synthesize(text)
        )
    except ProviderError as error:
        emit(
            {
                "kind": "metrics",
                "values": {
                    "synthesis_attempt_s": time.monotonic() - begin,
                    "requested_model": engine.settings.speech_model,
                    "state": "error",
                    "http_status": error.status,
                    "rejected_field": error.field,
                    "gateway_detail": error.detail or "não informado pelo gateway",
                    "usage": "não informado",
                    "cost": "desconhecido",
                },
            }
        )
        raise
    metrics = {"synthesis_s": time.monotonic() - begin}
    with sf.SoundFile(io.BytesIO(result.audio)) as wav:
        duration = wav.frames / wav.samplerate
    if probe:
        speech.record_validation(result)
    # Texto apenas na saída interativa da amostra, nunca no ledger de diagnóstico.
    emit({"kind": "transcript", "text": result.text})
    metrics.update(
        {
            "requested_model": engine.settings.speech_model,
            "returned_model": result.model,
            "format": "wav",
            "audio_duration_s": duration,
            "usage": result.usage,
        }
    )
    if play:
        ready = time.monotonic()

        def started():
            metrics["synthesis_end_to_playback_s"] = time.monotonic() - ready
            metrics["sample_to_playback_s"] = time.monotonic() - begin

        try:
            await engine.audio.play(
                result.audio, engine.settings, started, valid=lambda: engine.current(generation)
            )
        finally:
            emit({"kind": "metrics", "values": metrics})
    else:
        metrics["playback"] = "não executada (--no-play)"
        emit({"kind": "metrics", "values": metrics})
    return metrics
