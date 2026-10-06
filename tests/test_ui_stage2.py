import asyncio
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_ui import spin

from companhia.config import Settings
from companhia.providers import Chunk
from companhia.ui import MainWindow


def test_idle_empty_editor_draft_config_pause_and_tone_controls(tmp_path, monkeypatch):
    monkeypatch.setattr("companhia.ui.devices", lambda: [])
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, Settings(provider="mock"))
    window.show()
    try:
        app.processEvents()
        spin(app, lambda: "Sem chamadas" in window.diagnostic.toPlainText())
        window.mode.setCurrentIndex(1)
        window.input.setFocus()
        window.update_editing()
        assert not window.tasks.editing.is_set()  # foco vazio sem digitação
        QTest.keyClicks(window.input, "rascunho")
        window.update_editing()
        assert window.tasks.editing.is_set()
        window.input.clear()
        window.update_editing()
        assert window.tasks.editing.is_set()  # carência após digitação, mesmo depois de apagar
        window.edit_activity.last_typing = time.monotonic() - 6
        window.update_editing()
        assert not window.tasks.editing.is_set()
        window.tabs.setCurrentIndex(2)
        window.update_editing()
        assert window.tasks.editing.is_set()
        window.store.set_meta("gentle", "1")
        window.tone_mode.setCurrentIndex(0)
        window.save_settings()
        assert not window.store.get_meta("gentle")
        window.tabs.setCurrentIndex(0)
        window.pause()
        assert not window.talk_button.isEnabled()
        assert window.mode.currentData() == "paused"
    finally:
        window.close()


def test_mock_gui_company_silence_retry_cancel_and_user_priority(tmp_path, monkeypatch):
    monkeypatch.setattr("companhia.ui.devices", lambda: [])
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, Settings(provider="mock"))
    window.show()

    class ControlledLLM:
        def __init__(self):
            self.reply = "<SILENCIO>"
            self.wait = False
            self.entered = False

        async def stream(self, messages):
            self.entered = True
            if self.wait:
                await asyncio.Event().wait()
            yield Chunk(self.reply, "mock/stage2")

    llm = ControlledLLM()
    try:
        app.processEvents()
        spin(app, lambda: "Sem chamadas" in window.diagnostic.toPlainText())
        window.store.message("seed", "user", "vamos continuar a história dos dragões")
        window.store.message("seed", "assistant", "a história continua")
        window.mode.setCurrentIndex(1)
        window.tasks.loop.call_soon_threadsafe(lambda: setattr(window.tasks.engine, "llm", llm))
        spin(app, lambda: window.tasks.engine.proactivity.mode == "company")

        def initiative(gen):
            return window.tasks.engine.turn(gen, proactive=True, editing=window.tasks.editing.is_set)

        window.tasks.start(initiative, proactive=True)
        spin(
            app, lambda: llm.entered and window.state == "disponível" and not window.tasks.pending_or_running
        )
        assert not window.tasks.engine.proactivity.waiting_reply
        assert len(window.tasks.engine.proactivity.initiatives) == 1
        assert len(window.store.recent()) == 2
        llm.entered = False
        llm.wait = True
        window.tasks.start(initiative, proactive=True)
        spin(app, lambda: llm.entered and window.state == "respondendo")
        previous = window.tasks.generation
        QTest.keyClicks(window.input, "Minha pergunta tem prioridade")
        assert window.tasks.generation > previous
        llm.wait = False
        llm.reply = "[SIMULADO] resposta ao novo turno"
        window.send_text()
        spin(app, lambda: window.store.recent()[-1]["content"] == llm.reply and window.state == "disponível")
        assert not window.tasks.engine.proactivity.waiting_reply
        assert "Minha pergunta tem prioridade" in window.history.toPlainText()
        window.pause()
        assert window.mode.currentData() == "paused"
    finally:
        window.close()
