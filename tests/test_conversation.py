import asyncio

from companhia.config import Settings
from companhia.conversation import Conversation
from companhia.providers import Chunk, MockProvider, ProviderError, Speech


class AudioSpy:
    def __init__(self):
        self.played = []

    async def play(self, audio, settings, started=lambda: None, valid=lambda: True):
        self.played.append(audio)
        started()


def engine(store, tmp_path, **kwargs):
    events = []
    current = kwargs.pop("current", lambda g: True)
    obj = Conversation(
        Settings(provider="mock", speech="contract"), store, tmp_path, events.append, current, **kwargs
    )
    return obj, events


async def test_late_uncancellable_result_never_plays_or_persists(store, tmp_path):
    gate = asyncio.Event()
    began = asyncio.Event()

    class LateSpeech:
        async def synthesize(self, text):
            began.set()
            try:
                await gate.wait()
            except asyncio.CancelledError:
                await gate.wait()  # simula um upstream que já aceitou a chamada
            return Speech(b"old audio", "resultado atrasado")

    generation = [1]
    audio = AudioSpy()
    obj, events = engine(
        store, tmp_path, speech=LateSpeech(), audio=audio, current=lambda g: generation[0] == g
    )
    task = asyncio.create_task(obj.turn(1, text="olá"))
    await asyncio.wait_for(began.wait(), 3)
    generation[0] = 2
    count = len(events)
    task.cancel()
    gate.set()
    await asyncio.gather(task, return_exceptions=True)
    assert not audio.played
    assert all("resultado atrasado" not in r["content"] for r in store.recent())
    assert len(events) == count
    assert store.recent()[-1]["state"] == "interrupted"


async def test_cancel_partial_stream_marks_interrupted(store, tmp_path):
    began = asyncio.Event()

    class SlowLLM:
        async def stream(self, messages):
            yield Chunk("parcial")
            began.set()
            await asyncio.Event().wait()

    audio = AudioSpy()
    obj, events = engine(store, tmp_path, llm=SlowLLM(), audio=audio)
    task = asyncio.create_task(obj.turn(1, text="oi"))
    await began.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert store.recent()[-1]["state"] == "interrupted"
    assert store.recent()[-1]["content"] == "parcial"
    assert not audio.played


async def test_speech_associated_transcript_matches_saved_text(store, tmp_path):
    class DifferentSpeech:
        async def synthesize(self, text):
            return Speech(b"audio", "fala associada retornada", "audio/model")

    audio = AudioSpy()
    obj, events = engine(store, tmp_path, speech=DifferentSpeech(), audio=audio)
    await obj.turn(1, text="oi")
    assert audio.played == [b"audio"]
    assert store.recent()[-1]["content"] == "fala associada retornada"
    assert store.recent()[-1]["state"] == "complete"


async def test_api_failure_retains_partial_text_and_ends_idle(store, tmp_path):
    class BrokenLLM:
        async def stream(self, messages):
            yield Chunk("texto parcial")
            raise ProviderError("Erro de teste")

    obj, events = engine(store, tmp_path, llm=BrokenLLM(), audio=AudioSpy())
    await obj.turn(1, text="oi")
    assert store.recent()[-1]["state"] == "error"
    assert any(e["kind"] == "error" for e in events)
    assert events[-1]["value"] == "disponível"


async def test_proactive_revalidation_suppresses_response_after_editing(store, tmp_path):
    began = asyncio.Event()
    go = asyncio.Event()
    editing = [False]

    class SlowLLM:
        async def stream(self, messages):
            began.set()
            await go.wait()
            yield Chunk("iniciativa")

    audio = AudioSpy()
    obj, events = engine(store, tmp_path, llm=SlowLLM(), audio=audio)
    obj.proactivity.mode = "company"
    task = asyncio.create_task(obj.turn(1, proactive=True, editing=lambda: editing[0]))
    await began.wait()
    editing[0] = True
    go.set()
    await asyncio.gather(task, return_exceptions=True)
    assert not store.recent()
    assert not audio.played


async def test_paused_makes_no_calls_and_explicit_memory_is_local(store, tmp_path):
    obj, events = engine(store, tmp_path, llm=MockProvider(), audio=AudioSpy())
    obj.proactivity.mode = "paused"
    await obj.turn(1, text="oi")
    assert not store.rows("SELECT * FROM calls")
    assert not store.recent()
    obj.proactivity.mode = "focus"
    await obj.turn(1, text="lembra que gosto de chá")
    assert store.memories()[0]["content"] == "gosto de chá"
    assert not store.rows("SELECT * FROM calls")
