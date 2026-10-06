import pytest

from companhia.config import Settings
from companhia.conversation import Conversation
from companhia.diagnostics import speech_sample
from companhia.providers import ProviderError, Roteia


async def test_failed_sample_records_one_attempt_and_safe_timing_without_sensitive_text(
    store, tmp_path, monkeypatch
):
    class RejectedSpeech:
        def __init__(self, *args, **kwargs):
            pass

        async def synthesize(self, text):
            raise ProviderError("Pedido recusado", status=400, field="modalities")

    monkeypatch.setattr("companhia.diagnostics.RoteiaSpeech", RejectedSpeech)
    settings = Settings(provider="roteia")
    engine = Conversation(
        settings, store, tmp_path, lambda event: None, lambda g: True, llm=Roteia(settings, "fake-secret-key")
    )
    events = []
    with pytest.raises(ProviderError):
        await speech_sample(engine, "conteúdo pessoal", probe=True, play=False, emit=events.append)
    rows = store.rows("SELECT * FROM calls")
    assert len(rows) == 1
    assert rows[0]["state"] == "error"
    values = events[0]["values"]
    assert values["http_status"] == 400
    assert values["synthesis_attempt_s"] >= 0
    assert values["cost"] == "desconhecido"
    assert "conteúdo pessoal" not in str(events) + str(rows)
    assert "fake-secret-key" not in str(events) + str(rows)
    assert not (tmp_path / "audio-validation.json").exists()
