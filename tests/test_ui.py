import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from companhia.config import Settings
from companhia.ui import MainWindow


def spin(app, condition, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("GUI não completou a operação no prazo")


def test_window_mock_chat_memory_and_pause_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr("companhia.ui.devices", lambda: [])
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, Settings(provider="mock"))
    window.show()
    try:
        app.processEvents()
        spin(app, lambda: "Sem chamadas" in window.diagnostic.toPlainText())
        window.input.setPlainText("lembra que gosto de chá")
        window.send_text()
        spin(app, lambda: window.memory_table.rowCount() == 1)
        window.input.setPlainText("olá")
        window.send_text()
        spin(app, lambda: "SIMULADO" in window.history.toPlainText() and window.state == "disponível")
        window.pause()
        app.processEvents()
        assert not window.send_button.isEnabled()
        assert window.mode.currentData() == "paused"
        assert window.tasks.thread.is_alive()
    finally:
        window.close()
    assert not window.tasks.thread.is_alive()
