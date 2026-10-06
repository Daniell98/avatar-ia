import base64
import io
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from companhia.config import Settings
from companhia.providers import ProviderError, Roteia, Speech
from companhia.roteia_speech import PCM_RATE, RoteiaSpeech


def pcm16(samples=4800) -> bytes:
    """Bloco cru de pcm16, como o stream entrega: sem header."""
    wave = np.sin(np.linspace(0, 40, samples)) * 8000
    return wave.astype("<i2").tobytes()


def sse(*events) -> dict:
    body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)
    return {
        "headers": {"content-type": "text/event-stream"},
        "content": body + "data: [DONE]\n\n",
    }


def voice_stream(audio: bytes | None = None, *, transcript="fala realmente associada", finish="stop"):
    audio = pcm16() if audio is None else audio
    half = len(audio) // 2
    return sse(
        {"model": "openai/gpt-audio-mini", "choices": [{"delta": {"role": "assistant"}}]},
        {
            "model": "openai/gpt-audio-mini",
            "choices": [{"delta": {"audio": {"data": base64.b64encode(audio[:half]).decode()}}}],
        },
        {
            "model": "openai/gpt-audio-mini",
            "choices": [
                {"delta": {"audio": {"data": base64.b64encode(audio[half:]).decode()}}},
            ],
        },
        {
            "model": "openai/gpt-audio-mini",
            "choices": [{"delta": {"audio": {"transcript": transcript}}, "finish_reason": finish}],
            "usage": {"total_tokens": 8},
        },
    )


async def test_probe_streams_pcm16_once_and_builds_wav_locally(tmp_path):
    calls = []
    audio = pcm16()

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert set(body) == {"model", "messages", "modalities", "audio", "stream"}
        # O gateway exige stream para saída de áudio, e em stream o formato de fio é pcm16.
        assert body["stream"] is True
        assert body["audio"] == {"voice": "alloy", "format": "pcm16"}
        assert body["modalities"] == ["text", "audio"]
        return httpx.Response(200, **voice_stream(audio))

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    speech = RoteiaSpeech(provider, tmp_path, probing=True)
    result = await speech.synthesize("Olá, Daniel.")
    assert result.text == "fala realmente associada"
    assert len(calls) == 1
    # O WAV é montado aqui: header local, amostras idênticas ao pcm recebido.
    assert result.audio.startswith(b"RIFF")
    with sf.SoundFile(io.BytesIO(result.audio)) as built:
        assert built.samplerate == PCM_RATE
        assert built.channels == 1
        assert built.frames == len(audio) // 2
    assert sf.read(io.BytesIO(result.audio), dtype="int16")[0].tobytes() == audio
    with pytest.raises(ProviderError, match="Simulações"):
        speech.record_validation(result)
    assert not (tmp_path / "audio-validation.json").exists()


async def test_normal_use_is_blocked_without_real_validation(tmp_path):
    called = []
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: called.append(req)))
    with pytest.raises(ProviderError, match="não validada"):
        await RoteiaSpeech(provider, tmp_path).synthesize("olá")
    assert not called


@pytest.mark.parametrize(
    "problem", ["different_model", "missing_transcript", "no_audio", "truncated", "odd_pcm"]
)
async def test_invalid_voice_stream_never_produces_playable_result(tmp_path, problem):
    if problem == "different_model":
        stream = voice_stream()
        stream["content"] = stream["content"].replace("openai/gpt-audio-mini", "other/model")
    elif problem == "missing_transcript":
        stream = voice_stream(transcript="   ")
    elif problem == "no_audio":
        stream = sse(
            {
                "model": "openai/gpt-audio-mini",
                "choices": [{"delta": {"content": "só texto"}, "finish_reason": "stop"}],
            }
        )
    elif problem == "truncated":
        stream = voice_stream(finish="length")
    else:
        stream = voice_stream(pcm16()[:-1])
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: httpx.Response(200, **stream)))
    with pytest.raises(ProviderError):
        await RoteiaSpeech(provider, tmp_path, probing=True).synthesize("olá")


async def test_gateway_rejection_explains_the_field_without_leaking_and_does_not_retry(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            400,
            json={
                "error": {
                    "param": "modalities",
                    "code": "unsupported_value",
                    "message": "modalities 'audio' is not enabled for sk-live-abcdefgh1234 on 'olá'",
                }
            },
        )

    speech = RoteiaSpeech(Roteia(Settings(), "fake", httpx.MockTransport(handler)), tmp_path, probing=True)
    with pytest.raises(ProviderError) as error:
        await speech.synthesize("olá")
    text = str(error.value)
    # A explicação do gateway é a única pista do campo recusado, então precisa chegar ao operador.
    assert "modalities" in text and "unsupported_value" in text and "is not enabled" in text
    assert error.value.field == "modalities"
    # Chave e texto da amostra não são repassados.
    assert "sk-live-abcdefgh1234" not in text and "'olá'" not in text
    assert len(calls) == 1


async def test_rejection_body_without_error_envelope_is_still_reported(tmp_path):
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: httpx.Response(400, text="nope")))
    with pytest.raises(ProviderError, match="body=nope"):
        await RoteiaSpeech(provider, tmp_path, probing=True).synthesize("olá")


async def test_rejection_with_empty_body_admits_there_is_no_explanation(tmp_path):
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: httpx.Response(400, text="")))
    with pytest.raises(ProviderError, match="não explicou o motivo"):
        await RoteiaSpeech(provider, tmp_path, probing=True).synthesize("olá")


async def test_upstream_failure_is_not_reported_as_schema_rejection(tmp_path):
    """502 traz o corpo cru: é falha ao atender, não recusa de campo."""
    body = "<html><body>Bad Gateway: upstream connect error</body></html>"
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: httpx.Response(502, text=body)))
    with pytest.raises(ProviderError) as error:
        await RoteiaSpeech(provider, tmp_path, probing=True).synthesize("olá")
    text = str(error.value)
    assert "aceitou o pedido e falhou" in text and "502" in text
    assert "upstream connect error" in text and "<html>" not in text
    assert error.value.status == 502 and error.value.field is None


async def test_text_stream_control_isolates_audio_from_streaming(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, **sse({"choices": [{"delta": {"content": "ok"}}]}))

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    result = await RoteiaSpeech(provider, tmp_path, probing=True).probe_text_stream()
    # O controle usa o modelo de voz em stream, mas sem pedir áudio.
    assert bodies[0]["model"] == Settings().speech_model and bodies[0]["stream"] is True
    assert "modalities" not in bodies[0] and "audio" not in bodies[0]
    assert result["text_deltas"] == 1
    assert "específica da saída de áudio" in result["conclusion"]
    assert not (tmp_path / "audio-validation.json").exists()


async def test_text_stream_control_reports_failure_without_audio(tmp_path):
    provider = Roteia(Settings(), "fake", httpx.MockTransport(lambda req: httpx.Response(502, text="down")))
    result = await RoteiaSpeech(provider, tmp_path, probing=True).probe_text_stream()
    assert result["http_status"] == 502 and "body=down" in result["gateway_detail"]
    assert result["conclusion"] == "streaming falha neste modelo mesmo sem áudio"
    assert result["control"] == f"texto em {Settings().speech_model}, stream=true"


async def test_control_can_point_at_another_model_to_separate_account_from_model(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    result = await RoteiaSpeech(provider, tmp_path, probing=True).probe_text_stream(
        stream=False, model="deepseek/deepseek-v4-flash"
    )
    assert bodies[0]["model"] == "deepseek/deepseek-v4-flash"
    assert result["control"] == "texto em deepseek/deepseek-v4-flash, stream=false"
    assert result["answered"] is True


async def test_plain_control_repeats_the_published_example_without_stream(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    result = await RoteiaSpeech(provider, tmp_path, probing=True).probe_text_stream(stream=False)
    # O exemplo publicado pela Roteia é só model + messages.
    assert set(bodies[0]) == {"model", "messages"}
    assert result["answered"] is True
    # O controle sem stream não testou streaming, então não conclui nada sobre ele.
    assert result["conclusion"] == "a rota do modelo responde fora de streaming"
    assert "streaming falha" not in result["conclusion"]


def test_validation_is_for_exact_configuration(tmp_path):
    speech = RoteiaSpeech(Roteia(Settings(), "fake"), tmp_path)
    (tmp_path / "audio-validation.json").write_text(
        json.dumps(
            {"source": "manual-real-diagnostic", "signature": speech.signature(), "tested_at": "fixture-only"}
        ),
        encoding="utf-8",
    )
    assert speech.validated()
    changed = RoteiaSpeech(Roteia(Settings(voice="different"), "fake"), tmp_path)
    assert not changed.validated()


def test_marker_from_the_pre_stream_schema_does_not_validate(tmp_path):
    """Uma validação gravada antes da exigência de stream não vale para o schema atual."""
    speech = RoteiaSpeech(Roteia(Settings(), "fake"), tmp_path)
    stale = dict(speech.signature(), schema="audio-chat-v1")
    stale.pop("wire_format")
    (tmp_path / "audio-validation.json").write_text(
        json.dumps({"source": "manual-real-diagnostic", "signature": stale, "tested_at": "antigo"}),
        encoding="utf-8",
    )
    assert not speech.validated()


def test_handmade_fixture_without_http_transport_cannot_confirm_gateway(tmp_path):
    speech = RoteiaSpeech(Roteia(Settings(), "fake"), tmp_path, probing=True)
    with pytest.raises(ProviderError, match="Simulações"):
        speech.record_validation(Speech(b"RIFF", "fixture", "openai/gpt-audio-mini"))
    assert not (tmp_path / "audio-validation.json").exists()
