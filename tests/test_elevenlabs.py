import io
import json

import httpx
import numpy as np
import pytest
import soundfile as sf

from companhia.config import Settings, elevenlabs_key
from companhia.elevenlabs_speech import TEXT_LIMIT, ElevenLabs
from companhia.providers import ProviderError


def mp3_like() -> bytes:
    """WAV serve de corpo decodificável: o adaptador aceita o que o soundfile lê."""
    file = io.BytesIO()
    sf.write(file, np.zeros(2400, dtype="float32"), 24000, format="WAV", subtype="PCM_16")
    return file.getvalue()


def settings(**changes):
    base = {
        "speech": "eleven",
        "eleven_voice": "voice-123",
        "eleven_model": "eleven_v4_turbo",
        "eleven_format": "mp3_44100_128",
    }
    return Settings(**{**base, **changes})


async def test_synthesis_sends_key_in_header_and_format_as_query(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=mp3_like())

    client = ElevenLabs(settings(), "secret-key", httpx.MockTransport(handler))
    result = await client.synthesize("Oi, Daniel.")
    request = seen[0]
    assert request.url.path == "/v1/text-to-speech/voice-123"
    # output_format é query param, não campo do corpo.
    assert request.url.params["output_format"] == "mp3_44100_128"
    assert request.headers["xi-api-key"] == "secret-key"
    sent = json.loads(request.content)
    assert sent["text"] == "Oi, Daniel." and sent["model_id"] == "eleven_v4_turbo"
    assert sent["voice_settings"]["stability"] == 0.4
    assert sent["voice_settings"]["similarity_boost"] == 0.8
    # O texto enviado é o transcript: não há texto associado a validar.
    assert result.text == "Oi, Daniel."
    assert result.audio == mp3_like()


async def test_missing_voice_is_refused_before_any_call():
    called = []
    client = ElevenLabs(
        settings(eleven_voice=""), "key", httpx.MockTransport(lambda req: called.append(req))
    )
    with pytest.raises(ProviderError, match="Nenhuma voz escolhida"):
        await client.synthesize("olá")
    assert not called


async def test_format_outside_the_checked_list_is_refused_before_any_call():
    called = []
    client = ElevenLabs(
        settings(eleven_format="pcm_48000"), "key", httpx.MockTransport(lambda req: called.append(req))
    )
    with pytest.raises(ProviderError, match="não está na lista conferida"):
        await client.synthesize("olá")
    assert not called


@pytest.mark.parametrize("text", ["", "   ", "x" * (TEXT_LIMIT + 1)])
async def test_empty_or_oversized_text_never_reaches_the_api(text):
    called = []
    client = ElevenLabs(settings(), "key", httpx.MockTransport(lambda req: called.append(req)))
    with pytest.raises(ProviderError):
        await client.synthesize(text)
    assert not called


async def test_missing_key_is_refused_without_network():
    with pytest.raises(ProviderError, match="ELEVENLABS_API_KEY"):
        await ElevenLabs(settings(), "").synthesize("olá")


@pytest.mark.parametrize(
    ("status", "message"), [(401, "recusada"), (403, "não tem acesso"), (429, "Limite")]
)
async def test_http_errors_are_explained_and_not_retried(status, message):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "qualquer"})

    client = ElevenLabs(settings(), "key", httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match=message) as error:
        await client.synthesize("olá")
    assert error.value.status == status
    assert len(calls) == 1


async def test_undecodable_body_is_not_played():
    client = ElevenLabs(
        settings(), "key", httpx.MockTransport(lambda req: httpx.Response(200, content=b"not audio"))
    )
    with pytest.raises(ProviderError, match="não foi decodificável"):
        await client.synthesize("olá")


async def test_empty_body_is_not_played():
    client = ElevenLabs(
        settings(), "key", httpx.MockTransport(lambda req: httpx.Response(200, content=b""))
    )
    with pytest.raises(ProviderError, match="sem corpo de áudio"):
        await client.synthesize("olá")


async def test_subscription_reports_remaining_quota():
    payload = {
        "tier": "creator",
        "status": "active",
        "character_count": 1200,
        "character_limit": 131000,
        "next_character_count_reset_unix": 1793939302,
    }
    client = ElevenLabs(
        settings(), "key", httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    )
    result = await client.subscription()
    assert result["tier"] == "creator"
    assert result["characters_left"] == 129800


async def test_models_listing_keeps_only_tts_and_flags_portuguese():
    payload = [
        {
            "model_id": "eleven_v4_turbo",
            "name": "V4 Turbo",
            "can_do_text_to_speech": True,
            "languages": [{"language_id": "pt"}, {"language_id": "en"}],
            "model_rates": {"character_cost_multiplier": 0.5},
        },
        {
            "model_id": "scribe_v2",
            "name": "Scribe",
            "can_do_text_to_speech": False,
            "languages": [{"language_id": "pt"}],
        },
    ]
    client = ElevenLabs(
        settings(), "key", httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    )
    found = await client.models()
    assert [model["model_id"] for model in found] == ["eleven_v4_turbo"]
    assert found[0]["pt"] is True and found[0]["cost_factor"] == 0.5


def test_conversation_picks_elevenlabs_and_labels_the_model(tmp_path, store):
    from companhia.conversation import Conversation

    engine = Conversation(settings(), store, tmp_path, lambda event: None, lambda gen: True)
    assert isinstance(engine.speech, ElevenLabs)
    # A voz não depende da Roteia: o rótulo da métrica também não.
    assert engine.speech.settings.eleven_voice == "voice-123"


def test_mock_provider_keeps_elevenlabs_offline(tmp_path, store):
    from companhia.conversation import Conversation
    from companhia.providers import MockProvider

    engine = Conversation(
        settings(provider="mock"), store, tmp_path, lambda event: None, lambda gen: True
    )
    assert isinstance(engine.speech, MockProvider)


def test_settings_require_a_voice_before_enabling_eleven():
    with pytest.raises(ValueError, match="Escolha uma voz"):
        settings(eleven_voice="").validate()
    settings().validate()


def test_v3_snaps_stability_to_its_three_allowed_steps():
    """O v3 só aceita 0,0 / 0,5 / 1,0; outros modelos usam o valor contínuo."""
    for pedido, esperado in [(0.1, 0.0), (0.4, 0.5), (0.9, 1.0)]:
        client = ElevenLabs(settings(eleven_model="eleven_v3", eleven_stability=pedido), "key")
        assert client.voice_settings()["stability"] == esperado
    continuo = ElevenLabs(settings(eleven_model="eleven_v4_turbo", eleven_stability=0.37), "key")
    assert continuo.voice_settings()["stability"] == 0.37


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("eleven_stability", 1.5), ("eleven_similarity", -0.1), ("eleven_style", 2.0), ("eleven_speed", 2.0)],
)
def test_expressivity_values_outside_range_are_refused(campo, valor):
    with pytest.raises(ValueError):
        settings(**{campo: valor}).validate()


def test_eleven_base_url_must_use_https():
    with pytest.raises(ValueError, match="HTTPS"):
        settings(eleven_base_url="http://api.elevenlabs.io/v1").validate()


def test_key_comes_from_environment_without_touching_the_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "from-env")
    assert elevenlabs_key(tmp_path) == "from-env"
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    (tmp_path / "elevenlabs-key.txt").write_text("from-file\n", encoding="utf-8")
    assert elevenlabs_key(tmp_path) == "from-file"
