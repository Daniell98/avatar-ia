import base64
import io
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from companhia.config import Settings
from companhia.providers import ContractSpeech, ProviderError, Roteia


def wav():
    file = io.BytesIO()
    sf.write(file, np.ones(1600, dtype="float32") * 0.1, 16000, format="WAV", subtype="PCM_16")
    return file.getvalue()


async def test_stream_contract_no_unconfirmed_parameters():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"model":"actual/model","choices":[{"delta":{"content":"Olá"}}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"total_tokens":8}}\n\n'
                "data: [DONE]\n\n"
            ).encode(),
        )

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    chunks = [c async for c in provider.stream([{"role": "user", "content": "oi"}])]
    assert "".join(c.text for c in chunks) == "Olá"
    assert chunks[-1].usage == {"total_tokens": 8}
    assert set(requests[0]) == {"model", "messages", "stream"}


@pytest.mark.parametrize("status", [401, 402, 429, 500])
async def test_http_error_is_sanitized_and_never_retried(status):
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(status, json={"error": "fake-secret-must-not-be-shown"})

    provider = Roteia(Settings(), "fake-secret", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        _ = [c async for c in provider.stream([])]
    assert "fake-secret" not in str(error.value)
    assert len(called) == 1


async def test_truncated_stream_is_incomplete():
    provider = Roteia(
        Settings(),
        "fake",
        httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
            )
        ),
    )
    with pytest.raises(ProviderError, match="conclusão"):
        _ = [c async for c in provider.stream([])]


async def test_transcription_multipart_and_empty_file():
    captured = []

    def handler(request):
        captured.append(request)
        assert "multipart/form-data" in request.headers["content-type"]
        assert b'filename="fala.wav"' in request.content
        assert b'name="model"' in request.content
        return httpx.Response(200, json={"text": "fala em português"})

    provider = Roteia(Settings(), "fake", httpx.MockTransport(handler))
    assert (await provider.transcribe(wav())).text == "fala em português"
    with pytest.raises(ProviderError, match="vazio"):
        await provider.transcribe(b"")
    assert len(captured) == 1


async def test_unconfirmed_audio_contract_never_calls_api(tmp_path):
    file = tmp_path / "contract.json"
    file.write_text('{"confirmed":false}', encoding="utf-8")
    called = []
    provider = Roteia(
        Settings(speech_contract=str(file)),
        "fake",
        httpx.MockTransport(lambda request: called.append(request)),
    )
    with pytest.raises(ProviderError, match="contrato"):
        await ContractSpeech(provider).synthesize("oi")
    assert not called


@pytest.mark.parametrize("has_transcript", [True, False])
async def test_confirmed_contract_validates_audio_and_associated_text(tmp_path, has_transcript):
    # Schema inventado SOMENTE para o transporte falso de teste; não é contrato da Roteia.
    file = tmp_path / "confirmed-test.json"
    file.write_text(
        json.dumps(
            {
                "confirmed": True,
                "evidence": "fixture:fake-gateway",
                "endpoint": "chat/completions",
                "format": "wav",
                "request": {"model": "{model}", "say": "{text}", "voice": "{voice}"},
                "audio_path": "result.0.wav",
                "transcript_path": "result.0.words",
            }
        ),
        encoding="utf-8",
    )

    def handler(request):
        body = json.loads(request.content)
        assert body["say"] == 'Olá "Daniel"'
        item = {"wav": base64.b64encode(wav()).decode()}
        if has_transcript:
            item["words"] = "Texto associado à fala"
        return httpx.Response(200, json={"result": [item], "model": "fake/audio"})

    provider = Roteia(Settings(speech_contract=str(file)), "fake", httpx.MockTransport(handler))
    speech = ContractSpeech(provider)
    if has_transcript:
        result = await speech.synthesize('Olá "Daniel"')
        assert result.text == "Texto associado à fala"
        assert result.audio.startswith(b"RIFF")
    else:
        with pytest.raises(ProviderError, match="incompatível"):
            await speech.synthesize('Olá "Daniel"')
