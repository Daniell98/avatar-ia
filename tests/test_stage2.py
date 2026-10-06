import asyncio
import sqlite3

import pytest

from companhia.config import Settings, apply_default_personality, default_personality, personality_file
from companhia.conversation import Conversation
from companhia.memory import Store
from companhia.personality import context
from companhia.proactivity import EditingActivity
from companhia.providers import Chunk, ProviderError
from companhia.tone import apply_tone, tone_request


def test_current_question_reserved_under_maximum_auxiliary_context(store, tmp_path):
    personality_file(tmp_path).write_text("p" * 5000, encoding="utf-8")
    for i in range(5):
        store.remember(str(i) + "m" * 1999, "ui:manual")
    store.set_meta("summary", "s" * 2000)
    store.message("old", "user", "outro assunto")
    store.message("old", "assistant", "resposta completa")
    question = "q" * 4000
    id = store.message("current", "user", question)
    messages = context(store, Settings(), tmp_path, question, current_message_id=id)
    assert messages[-1] == {"role": "user", "content": question}
    assert sum(m["content"] == question for m in messages) == 1
    assert sum(len(m["content"]) for m in messages) <= 18000
    assert any(m["content"] == "outro assunto" for m in messages)


def test_normal_context_has_whole_turns_and_never_incomplete_answer(store, tmp_path):
    store.message("a", "user", "vamos falar de dragões")
    store.message("a", "assistant", "dragões voam")
    store.message("b", "user", "pergunta interrompida")
    store.message("b", "assistant", "NÃO COMPLETA", "interrupted")
    id = store.message("c", "user", "continuar a história")
    messages = context(store, Settings(), tmp_path, "continuar a história", current_message_id=id)
    contents = [m["content"] for m in messages]
    assert contents.count("continuar a história") == 1
    assert "NÃO COMPLETA" not in contents
    assert contents.index("dragões voam") == contents.index("vamos falar de dragões") + 1
    proactive = "INICIATIVA: comente a história"
    assert context(store, Settings(), tmp_path, proactive, proactive=True)[-1]["content"] == proactive


def test_context_window_never_starts_with_orphan_answer(store, tmp_path):
    for i in range(8):
        store.message(str(i), "user", f"pergunta {i}")
        store.message(str(i), "assistant", f"resposta {i}")
    id = store.message("new", "user", "pergunta atual")
    messages = context(store, Settings(), tmp_path, "pergunta atual", current_message_id=id)
    history = messages[2:-1]
    assert history[0]["role"] == "user"
    for i in range(0, len(history), 2):
        assert history[i]["role"] == "user"
        assert history[i + 1]["role"] == "assistant"


@pytest.mark.parametrize(
    "text", ["Não gostei desse filme.", "Não gostei dessa cor", "No filme ele disse: menos zoeira"]
)
def test_opinion_is_not_tone_feedback(text):
    assert tone_request(text) is None


@pytest.mark.parametrize(
    "text", ["menos zoeira", "Pega mais leve nas piadas.", "não gostei dessa provocação"]
)
def test_direct_tone_feedback(text):
    assert tone_request(text) == "gentle"


def test_tone_persists_and_is_reversible_without_touching_controls(tmp_path):
    path = tmp_path / "tone.sqlite3"
    db = Store(path)
    apply_tone(db, tone_request("menos zoeira"))
    db.close()
    db = Store(path)
    assert "Seja mais suave" in context(db, Settings(), tmp_path, "olá")[0]["content"]
    apply_tone(db, tone_request("Pode voltar a me zoar."))
    assert "Seja mais suave" not in context(db, Settings(), tmp_path, "olá")[0]["content"]
    db.close()
    db = Store(path)
    assert db.get_meta("gentle") == ""
    db.close()


def test_personality_update_preserves_custom_file_and_unsaved_draft(tmp_path):
    file = personality_file(tmp_path)
    file.write_text("minha personagem personalizada", encoding="utf-8")
    assert personality_file(tmp_path).read_text(encoding="utf-8") == "minha personagem personalizada"
    backup = apply_default_personality(tmp_path, draft="rascunho personalizado")
    assert backup.read_text(encoding="utf-8") == "minha personagem personalizada"
    assert any(
        p.read_text(encoding="utf-8") == "rascunho personalizado" for p in tmp_path.glob("*.draft.bak.md")
    )
    assert file.read_text(encoding="utf-8") == default_personality()


def test_migration_preserves_data_seeds_missing_references_and_never_reuses_ids(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
          CREATE TABLE messages (id INTEGER PRIMARY KEY, turn TEXT, role TEXT, content TEXT, state TEXT, created TEXT);
          CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT, kind TEXT, source TEXT,
                                 created TEXT, updated TEXT, active INTEGER DEFAULT 1);
          CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
          INSERT INTO messages VALUES(5,'a','user','história de dragões','complete','date');
          INSERT INTO memories VALUES(7,'gosto de chá','explicit','message:49','date','date',1);
        """)
    db = Store(path)
    assert db.recent()[0]["id"] == 5
    assert db.memories()[0]["id"] == 7
    assert db.get_meta("schema_version") == "2"
    assert "removida" in db.source_label("message:49")
    new_message = db.message("b", "user", "mensagem nova")
    assert new_message > 49
    new_memory = db.remember("gosto de café", f"message:{new_message}")
    db.clear_history()
    assert len(db.memories()) == 2
    assert "removida" in db.source_label(f"message:{new_message}")
    assert db.message("c", "user", "outra pergunta") > new_message
    db.forget(new_memory)
    assert db.remember("gosto de água", "ui:manual") > new_memory
    db.close()
    db = Store(path)
    assert "removida" in db.source_label("message:49")
    assert db.rows("SELECT id FROM deleted_messages WHERE id=49")
    db.close()
    assert path.with_name(path.name + ".before-v2.bak").exists()


def test_empty_editor_expires_but_draft_and_dialog_never_do():
    activity = EditingActivity()
    assert not activity.blocked(100, False, False)
    activity.typed(100)
    assert activity.blocked(103, False, False)
    assert not activity.blocked(106, False, False)
    assert activity.blocked(1000, True, False)
    assert activity.blocked(1000, False, True)


class ScriptedLLM:
    def __init__(self, reply="<SILENCIO>", failure=False):
        self.reply, self.failure = reply, failure
        self.entered = asyncio.Event()
        self.hold = None

    async def stream(self, messages):
        self.entered.set()
        if self.hold:
            await self.hold.wait()
        if self.failure:
            raise ProviderError("falha simulada")
        yield Chunk(self.reply, "mock/model")


def proactive_engine(store, tmp_path, llm):
    events = []
    obj = Conversation(Settings(provider="mock"), store, tmp_path, events.append, lambda g: True, llm=llm)
    obj.proactivity.mode = "company"
    return obj, events


@pytest.mark.parametrize("failure", [False, True])
async def test_silence_or_error_counts_attempt_without_waiting_for_reply(store, tmp_path, failure):
    obj, events = proactive_engine(store, tmp_path, ScriptedLLM(failure=failure))
    await obj.turn(1, proactive=True)
    assert not obj.proactivity.waiting_reply
    assert not store.recent()
    assert len(obj.proactivity.initiatives) == 1
    attempt = obj.proactivity.initiatives[-1]
    assert not obj.proactivity.eligible(attempt + 299, False, False, True)
    assert obj.proactivity.eligible(attempt + 301, False, False, True)
    assert all(e.get("kind") != "delta" for e in events)


async def test_cancel_before_publication_counts_attempt_without_waiting_reply(store, tmp_path):
    llm = ScriptedLLM("iniciativa")
    llm.hold = asyncio.Event()
    obj, _ = proactive_engine(store, tmp_path, llm)
    task = asyncio.create_task(obj.turn(1, proactive=True))
    await llm.entered.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(obj.proactivity.initiatives) == 1
    assert not obj.proactivity.waiting_reply
    assert not store.recent()


async def test_published_initiative_waits_even_if_synthesis_fails(store, tmp_path):
    obj, events = proactive_engine(store, tmp_path, ScriptedLLM("comentário contextual"))

    class BrokenSpeech:
        async def synthesize(self, text):
            raise ProviderError("voz indisponível")

    obj.speech = BrokenSpeech()
    await obj.turn(1, proactive=True)
    assert obj.proactivity.waiting_reply
    assert store.recent()[0]["content"] == "comentário contextual"
    assert store.recent()[0]["state"] == "complete"
    assert not obj.proactivity.eligible(obj.proactivity.initiatives[-1] + 1000, False, False, True)
    assert "synthesis_s" in next(e["values"] for e in events if e["kind"] == "metrics")


async def test_tone_pipeline_ignores_film_opinion_and_resets(store, tmp_path):
    obj, _ = proactive_engine(store, tmp_path, ScriptedLLM("resposta"))
    obj.proactivity.mode = "focus"
    await obj.turn(1, text="Não gostei desse filme.")
    assert not store.get_meta("gentle")
    await obj.turn(1, text="não gostei dessa provocação")
    assert store.get_meta("gentle") == "1"
    await obj.turn(1, text="Pode voltar a me zoar.")
    assert not store.get_meta("gentle")
