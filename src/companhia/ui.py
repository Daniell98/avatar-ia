from __future__ import annotations

import asyncio
import html
import json
import time
from dataclasses import replace

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioError, devices
from .config import api_key, apply_default_personality, default_personality, personality_file
from .conversation import Conversation
from .memory import Store
from .proactivity import EditingActivity
from .providers import ProviderError, Roteia
from .roteia_speech import RoteiaSpeech
from .tasks import Tasks
from .tone import apply_tone


class Bridge(QObject):
    event = Signal(dict)


class MainWindow(QMainWindow):
    def __init__(self, folder, settings, startup_error=""):
        super().__init__()
        self.folder, self.settings = folder, settings
        self.store = Store(folder / "companhia.sqlite3")
        self.bridge = Bridge()
        self.bridge.event.connect(self.receive)
        self.tasks = Tasks(self.bridge.event.emit)
        self.tasks.engine = Conversation(
            settings, self.store, folder, self.bridge.event.emit, self.tasks.current
        )
        self.state = "disponível"
        self.metrics = {}
        self.devices_cache = []
        self.edit_activity = EditingActivity()
        self.setWindowTitle(f"{settings.name} · assistente pessoal")
        self.resize(1050, 800)
        self.setMinimumSize(760, 600)
        self.setStyleSheet("""
            QWidget { background: #121922; color: #e6ecf4; font-family: Segoe UI; font-size: 14px; }
            QLineEdit, QPlainTextEdit, QTextBrowser, QSpinBox, QComboBox, QTableWidget {
                background: #1c2633; border: 1px solid #344459; border-radius: 6px; padding: 7px;
                selection-background-color: #497a8d; }
            QPushButton { background: #294558; border: 1px solid #46687d; border-radius: 7px;
                          padding: 9px 15px; }
            QPushButton:hover { background: #345b73; }
            QPushButton:disabled { color: #718094; background: #202a35; }
            QTabBar::tab { padding: 12px 20px; background: #1c2633; }
            QTabBar::tab:selected { background: #294558; }
            QHeaderView::section { background: #294558; padding: 6px; }
        """)
        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.title = QLabel(settings.name)
        self.title.setStyleSheet("font-size: 25px; font-weight: 600; padding: 10px 0;")
        top.addWidget(self.title)
        top.addStretch()
        self.mode = QComboBox()
        for name, id in [
            ("Foco — responde quando chamado", "focus"),
            ("Companhia — iniciativas habilitadas", "company"),
            ("Pausado", "paused"),
        ]:
            self.mode.addItem(name, id)
        self.mode.currentIndexChanged.connect(self.change_mode)
        top.addWidget(self.mode)
        layout.addLayout(top)
        self.provider_label = QLabel()
        self.update_provider_label()
        layout.addWidget(self.provider_label)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.chat_tab()
        self.memory_tab()
        self.settings_tab()
        self.diagnostics_tab()
        self.status = QLabel("Disponível · Foco")
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.shortcut = QShortcut(QKeySequence(settings.shortcut), self)
        self.shortcut.activated.connect(self.talk)
        self.escape = QShortcut(QKeySequence("Esc"), self)
        self.escape.activated.connect(self.interrupt)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_editing)
        self.timer.start(300)
        self.refresh()
        if startup_error:
            self.diagnostic.appendPlainText(startup_error)
        QTimer.singleShot(0, self.local_diagnostic)

    def update_provider_label(self):
        if self.settings.provider == "mock":
            value = "SIMULADO · sem API · respostas de teste; áudio simulado é um tom"
        else:
            voice = {
                "off": "voz desligada",
                "windows": "voz local do Windows",
                "contract": "voz por API com contrato local",
                "eleven": f"voz ElevenLabs · {self.settings.eleven_model}",
                "roteia": "voz Roteia · "
                + (
                    "schema observado em diagnóstico real"
                    if RoteiaSpeech(Roteia(self.settings, ""), self.folder).validated()
                    else "amostra ainda não validada"
                ),
            }.get(self.settings.speech, self.settings.speech)
            value = f"Roteia · {self.settings.chat_model} · {voice}"
        self.provider_label.setText(value)

    def chat_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.history = QTextBrowser()
        self.history.setOpenExternalLinks(False)
        box.addWidget(self.history)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Converse ou use: lembra que… / esquece memória #1 / corrige memória #1: …"
        )
        self.input.setMaximumHeight(85)
        self.input.textChanged.connect(self.user_editing)
        self.input.installEventFilter(self)
        box.addWidget(self.input)
        buttons = QHBoxLayout()
        self.send_button = QPushButton("Enviar texto")
        self.send_button.clicked.connect(self.send_text)
        buttons.addWidget(self.send_button)
        self.talk_button = QPushButton("Falar")
        self.talk_button.clicked.connect(self.talk)
        buttons.addWidget(self.talk_button)
        stop = QPushButton("Interromper · Esc")
        stop.clicked.connect(self.interrupt)
        buttons.addWidget(stop)
        self.pause_button = QPushButton("Pausar")
        self.pause_button.clicked.connect(self.pause)
        buttons.addWidget(self.pause_button)
        box.addLayout(buttons)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setMaximumHeight(10)
        self.level.setTextVisible(False)
        box.addWidget(self.level)
        note = QLabel(
            "Falar interrompe a resposta atual. O microfone fica fechado durante a reprodução. "
            "Atalho válido nesta janela: " + self.settings.shortcut
        )
        note.setWordWrap(True)
        self.shortcut_note = note
        box.addWidget(note)
        self.tabs.addTab(page, "Conversa")

    def memory_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.memory_table = QTableWidget(0, 5)
        self.memory_table.setHorizontalHeaderLabels(["ID", "Conteúdo", "Tipo", "Origem", "Atualização"])
        self.memory_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.memory_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.memory_table.horizontalHeader().setStretchLastSection(True)
        self.memory_table.setColumnWidth(1, 360)
        box.addWidget(self.memory_table)
        row = QHBoxLayout()
        for label, callback in [
            ("Adicionar memória", self.add_memory),
            ("Corrigir selecionada", self.edit_memory),
            ("Apagar selecionada", self.delete_memory),
            ("Apagar histórico", self.delete_history),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        note = QLabel(
            "Memórias são registradas explicitamente. Corrigir/apagar retira a conversa anterior do "
            "contexto futuro e invalida o resumo. O histórico continua visível até você apagá-lo."
        )
        note.setWordWrap(True)
        box.addWidget(note)
        self.tabs.addTab(page, "Memórias")

    def settings_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        contents = QWidget()
        form = QFormLayout(contents)
        self.fields = {}

        def text(key, label):
            field = QLineEdit(str(getattr(self.settings, key)))
            self.fields[key] = field
            form.addRow(label, field)

        def number(key, label, low, high):
            field = QSpinBox()
            field.setRange(low, high)
            field.setValue(getattr(self.settings, key))
            self.fields[key] = field
            form.addRow(label, field)

        def decimal(key, label, low, high):
            field = QDoubleSpinBox()
            field.setRange(low, high)
            field.setSingleStep(0.05)
            field.setDecimals(2)
            field.setValue(getattr(self.settings, key))
            self.fields[key] = field
            form.addRow(label, field)

        def combo(key, label, options):
            field = QComboBox()
            for title, value in options:
                field.addItem(title, value)
            field.setCurrentIndex(max(0, field.findData(getattr(self.settings, key))))
            self.fields[key] = field
            form.addRow(label, field)

        text("name", "Nome da personagem")
        combo(
            "provider",
            "Conversa e transcrição",
            [("Roteia · real", "roteia"), ("Simulado · sem API", "mock")],
        )
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText(
            "Chave configurada" if api_key(self.folder) else "Informe a chave localmente"
        )
        form.addRow("Chave (ambiente/.env tem prioridade)", self.key_input)
        for key, label in [
            ("base_url", "URL base HTTPS"),
            ("chat_model", "Modelo de conversa"),
            ("transcription_model", "Modelo de transcrição"),
            ("speech_model", "Modelo de voz API"),
        ]:
            text(key, label)
        combo(
            "speech",
            "Saída de voz",
            [
                ("Desligada", "off"),
                ("ElevenLabs · pt-BR", "eleven"),
                ("Windows · local / alternativa", "windows"),
                ("Roteia · validar amostra antes do uso", "roteia"),
                *([("Contrato externo · legado", "contract")] if self.settings.speech == "contract" else []),
            ],
        )
        text("voice", "Voz (vazio = pt-BR no Windows / alloy na API)")
        if self.settings.speech == "eleven":
            text("eleven_voice", "ID da voz ElevenLabs")
            text("eleven_model", "Modelo ElevenLabs")
            decimal("eleven_stability", "Estabilidade (baixa = mais expressiva)", 0.0, 1.0)
            decimal("eleven_similarity", "Semelhança com a voz original", 0.0, 1.0)
            decimal("eleven_style", "Estilo (exagero da entonação)", 0.0, 1.0)
            decimal("eleven_speed", "Velocidade da fala", 0.7, 1.2)
        combo("audio_format", "Formato de voz", [("WAV", "wav")])
        if self.settings.speech == "contract":
            text("speech_contract", "Contrato legado já configurado")
        number("timeout", "Timeout por requisição (s)", 5, 300)
        combo("input_device", "Microfone", [("Padrão do Windows", None)])
        combo("output_device", "Saída de áudio", [("Padrão do Windows", None)])
        combo("sample_rate", "Taxa de gravação (Hz)", [(str(v), v) for v in [16000, 24000, 44100, 48000]])
        number("recording_seconds", "Duração máxima da gravação (s)", 1, 120)
        text("shortcut", "Atalho Falar/Parar (na janela)")
        for key, label in [
            ("spontaneity", "Espontaneidade"),
            ("affection", "Carinho"),
            ("opinions", "Opiniões"),
            ("teasing", "Provocação"),
        ]:
            number(key, label + " · 0 a 100", 0, 100)
        number("idle_seconds", "Companhia: espera após atividade (s)", 10, 3600)
        number("initiative_interval", "Companhia: intervalo mínimo (s)", 30, 86400)
        number("initiatives_hour", "Companhia: máximo por hora", 1, 20)
        number("max_calls_day", "Limite de chamadas por dia UTC", 1, 10000)
        number("max_tokens_day", "Limite de tokens informados por dia UTC", 1, 10000000)
        number("recent_messages", "Mensagens recentes no contexto", 2, 40)
        number("context_chars", "Limite de caracteres do contexto", 18000, 50000)
        self.persona = QPlainTextEdit(personality_file(self.folder).read_text(encoding="utf-8"))
        self.persona.setMinimumHeight(210)
        form.addRow("Personalidade (também editável em arquivo)", self.persona)
        self.persona.installEventFilter(self)
        self.tone_mode = QComboBox()
        self.tone_mode.addItem("Normal · conforme os quatro controles", "normal")
        self.tone_mode.addItem("Mais suave · pedido de menos zoeira", "gentle")
        self.tone_mode.setCurrentIndex(1 if self.store.get_meta("gentle") == "1" else 0)
        form.addRow("Tom pedido por você", self.tone_mode)
        review = QPushButton("Revisar padrão atualizado de personalidade")
        review.clicked.connect(self.review_personality)
        form.addRow(review)
        form.addRow(
            QLabel(
                "Voz Roteia: execute o diagnóstico de uma amostra para validar compatibilidade. "
                "Limites de chamadas/tokens não garantem um teto financeiro exato."
            )
        )
        scroll.setWidget(contents)
        box.addWidget(scroll)
        row = QHBoxLayout()
        for title, callback in [
            ("Salvar configurações", self.save_settings),
            ("Atualizar dispositivos", self.local_diagnostic),
            ("Testar microfone local", self.test_microphone),
            ("Testar saída local", self.test_output),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        self.tabs.addTab(page, "Configurações")

    def diagnostics_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.diagnostic = QPlainTextEdit()
        self.diagnostic.setReadOnly(True)
        self.diagnostic.setMaximumBlockCount(300)
        box.addWidget(self.diagnostic)
        self.calls = QTableWidget(0, 6)
        self.calls.setHorizontalHeaderLabels(
            ["Modalidade", "Solicitado", "Retornado", "Estado", "Segundos", "Uso"]
        )
        self.calls.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.calls.horizontalHeader().setStretchLastSection(True)
        box.addWidget(self.calls)
        self.cost = QLabel("Custo: desconhecido. Nenhum valor confirmado pelo gateway.")
        self.cost.setWordWrap(True)
        box.addWidget(self.cost)
        self.sample_text = QLabel("Texto associado à amostra de voz aparecerá aqui para comparação.")
        self.sample_text.setWordWrap(True)
        box.addWidget(self.sample_text)
        row = QHBoxLayout()
        for title, callback in [
            ("Diagnóstico local · sem API", self.local_diagnostic),
            ("Teste real · uma amostra de texto", self.real_sample),
            ("Testar voz Roteia · uma amostra", self.real_voice_sample),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        box.addLayout(row)
        self.tabs.addTab(page, "Diagnóstico")

    def update_editing(self):
        # Foco vazio/parado não bloqueia indefinidamente. Abas de edição e diálogos são protegidos.
        editing = self.edit_activity.blocked(
            time.monotonic(),
            bool(self.input.toPlainText().strip()),
            self.tabs.currentIndex() in {1, 2} or QApplication.activeModalWidget() is not None,
        )
        if editing:
            self.tasks.editing.set()
        else:
            self.tasks.editing.clear()

    def user_editing(self):
        self.update_editing()
        # Se uma iniciativa está sendo gerada, editar ganha prioridade imediatamente.
        if self.input.toPlainText().strip() and self.tasks.is_proactive():
            self.interrupt()

    def eventFilter(self, obj, event):
        if event.type() in {QEvent.Type.KeyPress, QEvent.Type.InputMethod}:
            self.edit_activity.typed(time.monotonic())
            self.update_editing()
            if self.tasks.is_proactive():
                self.interrupt()
        return super().eventFilter(obj, event)

    def review_personality(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Revisar personalidade atualizada")
        dialog.setText(
            "O padrão atualizado aparece em Mostrar detalhes. Aplicar preserva a versão "
            "atual e o rascunho em cópias locais. Nome e intensidades continuam configuráveis."
        )
        dialog.setDetailedText(default_personality())
        apply = dialog.addButton("Aplicar padrão com cópia", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Manter minha personalidade", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == apply:
            self.interrupt()
            backup = apply_default_personality(self.folder, draft=self.persona.toPlainText())
            self.persona.setPlainText(default_personality())
            self.diagnostic.appendPlainText("Padrão aplicado. Versão anterior preservada em " + str(backup))

    def change_mode(self):
        value = self.mode.currentData()
        if value == "paused" or self.state != "disponível":
            self.interrupt()
        self.tasks.mode(value)
        self.state = "pausado" if value == "paused" else "disponível"
        self.update_state()

    def pause(self):
        self.mode.setCurrentIndex(0 if self.mode.currentData() == "paused" else 2)

    def update_state(self):
        self.status.setText(self.state.capitalize() + " · " + self.mode.currentText())
        paused = self.mode.currentData() == "paused"
        self.send_button.setEnabled(not paused)
        self.talk_button.setEnabled(not paused)
        self.talk_button.setText("Parar gravação" if self.state == "ouvindo" else "Falar")
        self.pause_button.setText("Retomar em Foco" if paused else "Pausar")
        if self.state != "ouvindo":
            self.level.setValue(0)

    def send_text(self):
        text = self.input.toPlainText().strip()
        if not text or self.mode.currentData() == "paused":
            return
        self.input.clear()
        self.state = "respondendo"
        self.update_state()
        self.tasks.start(lambda gen: self.tasks.engine.turn(gen, text=text))

    def talk(self):
        if self.mode.currentData() == "paused":
            return
        if self.state == "ouvindo":
            self.tasks.stop_recording.set()
            self.state = "transcrevendo"
        else:
            self.state = "ouvindo"
            self.tasks.start(lambda gen: self.tasks.engine.turn(gen, stop=self.tasks.stop_recording))
        self.update_state()

    def interrupt(self):
        self.tasks.interrupt()
        self.state = "pausado" if self.mode.currentData() == "paused" else "disponível"
        self.update_state()

    def receive(self, event):
        if not self.tasks.current(event["generation"]):
            return
        kind = event["kind"]
        if kind in {"refresh", "delta"}:
            self.refresh()
        elif kind == "state":
            self.state = event["value"]
            self.update_state()
        elif kind == "level":
            self.level.setValue(min(100, round(event["value"] * 100)))
        elif kind == "error":
            self.diagnostic.appendPlainText(event["message"])
            self.status.setText(event["message"])
            QMessageBox.warning(self, "Diagnóstico", event["message"])
        elif kind == "metrics":
            self.metrics = event["values"]
            if self.metrics:
                self.diagnostic.appendPlainText(
                    "Medições deste turno: " + json.dumps(self.metrics, ensure_ascii=False)
                )
        elif kind == "mode":
            self.mode.setCurrentIndex(self.mode.findData(event["value"]))
        elif kind == "tone":
            self.tone_mode.setCurrentIndex(self.tone_mode.findData(event["value"]))
        elif kind == "sample_text":
            self.sample_text.setText("Texto associado à fala: " + event["text"])
        elif kind == "voice_validated":
            self.update_provider_label()
        elif kind == "diagnostic":
            self.diagnostic.appendPlainText(event["text"])
            self.devices_cache = event.get("devices", self.devices_cache)
            self.populate_devices()

    def refresh(self):
        parts = []
        for row in self.store.recent(100):
            name = "Daniel" if row["role"] == "user" else self.settings.name
            color = "#9cd4e0" if row["role"] == "assistant" else "#cbb6ee"
            badge = {
                "pending": " · em andamento",
                "interrupted": " · interrompida",
                "error": " · incompleta",
            }.get(row["state"], "")
            value = html.escape(row["content"]).replace("\n", "<br>")
            parts.append(
                f'<p style="color:{color}"><b>{html.escape(name)}{badge}</b></p>'
                f'<p style="margin-bottom:20px">{value}</p>'
            )
        self.history.setHtml("".join(parts) or "<p>Comece por texto ou configure o microfone e a voz.</p>")
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())
        memories = self.store.memories()
        self.memory_table.setRowCount(len(memories))
        for i, memory in enumerate(memories):
            for j, key in enumerate(["id", "content", "kind", "source", "updated"]):
                value = self.store.source_label(memory[key]) if key == "source" else str(memory[key])
                self.memory_table.setItem(i, j, QTableWidgetItem(value))
        calls = self.store.rows("SELECT * FROM calls ORDER BY id DESC LIMIT 50")
        self.calls.setRowCount(len(calls))
        for i, call in enumerate(calls):
            values = [
                call["modality"],
                call["requested"],
                call["returned"] or "não informado",
                call["state"],
                f"{call['elapsed']:.2f}" if call["elapsed"] is not None else "—",
                call["usage"] or "não informado",
            ]
            for j, value in enumerate(values):
                self.calls.setItem(i, j, QTableWidgetItem(str(value)))

    def selected_memory(self):
        row = self.memory_table.currentRow()
        return int(self.memory_table.item(row, 0).text()) if row >= 0 else None

    def add_memory(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "Adicionar memória", "Fato ou preferência explicitamente informado:"
        )
        if ok and text.strip():
            self.interrupt()
            try:
                self.store.remember(text, "ui:manual")
            except ValueError as error:
                QMessageBox.warning(self, "Memória", str(error))
            self.refresh()

    def edit_memory(self):
        id = self.selected_memory()
        if id is None:
            return
        old = self.store.rows("SELECT content FROM memories WHERE id=?", (id,))[0]["content"]
        text, ok = QInputDialog.getMultiLineText(self, "Corrigir memória", "Conteúdo corrigido:", old)
        if ok and text.strip():
            self.interrupt()
            try:
                self.store.remember(text, f"ui:correction:{id}", replace_id=id)
            except ValueError as error:
                QMessageBox.warning(self, "Memória", str(error))
            self.refresh()

    def delete_memory(self):
        id = self.selected_memory()
        if (
            id is not None
            and QMessageBox.question(
                self,
                "Apagar memória",
                "Apagar a memória selecionada? "
                "O histórico será mantido e o contexto anterior será retirado das próximas chamadas.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.interrupt()
            self.store.forget(id)
            self.refresh()

    def delete_history(self):
        if (
            QMessageBox.question(
                self,
                "Apagar histórico",
                "Apagar todas as mensagens e o resumo? As memórias duradouras serão mantidas.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.interrupt()
            self.store.clear_history()
            self.refresh()

    def save_settings(self):
        if self.state not in {"disponível", "pausado"}:
            QMessageBox.information(
                self, "Configurações", "Interrompa o turno antes de salvar configurações."
            )
            return
        values = {}
        for key, field in self.fields.items():
            values[key] = (
                field.currentData()
                if isinstance(field, QComboBox)
                else (
                    field.value()
                    if isinstance(field, (QSpinBox, QDoubleSpinBox))
                    else field.text().strip()
                )
            )
        try:
            settings = replace(self.settings, **values)
            settings.validate()
            shortcut = QKeySequence(settings.shortcut)
            if shortcut.isEmpty():
                raise ValueError("Atalho vazio ou inválido.")
            if not self.persona.toPlainText().strip() or len(self.persona.toPlainText()) > 5000:
                raise ValueError("Personalidade deve ter entre 1 e 5000 caracteres.")
            settings.save(self.folder)
            personality_file(self.folder).write_text(self.persona.toPlainText(), encoding="utf-8")
            if self.key_input.text().strip():
                (self.folder / "api-key.txt").write_text(self.key_input.text().strip(), encoding="utf-8")
                self.key_input.clear()
                self.key_input.setPlaceholderText("Chave local salva; ambiente/.env tem prioridade")
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Configurações", str(error))
            return
        self.interrupt()
        apply_tone(self.store, self.tone_mode.currentData())
        self.settings = settings

        def rebuild():
            old = self.tasks.engine.proactivity
            engine = Conversation(
                settings, self.store, self.folder, self.bridge.event.emit, self.tasks.current
            )
            engine.proactivity.mode = old.mode
            engine.proactivity.last_activity = old.last_activity
            engine.proactivity.waiting_reply = old.waiting_reply
            engine.proactivity.initiatives = old.initiatives
            self.tasks.engine = engine

        self.tasks.loop.call_soon_threadsafe(rebuild)
        self.title.setText(settings.name)
        self.setWindowTitle(f"{settings.name} · assistente pessoal")
        self.shortcut.setKey(QKeySequence(settings.shortcut))
        self.shortcut_note.setText(
            "Falar interrompe a resposta atual. O microfone fica fechado durante a reprodução. "
            "Atalho válido nesta janela: " + settings.shortcut
        )
        self.update_provider_label()
        self.diagnostic.appendPlainText(
            "Configurações salvas. Personalidade: " + str(personality_file(self.folder))
        )
        self.refresh()

    def populate_devices(self):
        for key, capability in [("input_device", "input"), ("output_device", "output")]:
            field = self.fields[key]
            wanted = field.currentData() if field.count() > 1 else getattr(self.settings, key)
            field.clear()
            field.addItem("Padrão do Windows", None)
            for device in self.devices_cache:
                if device[capability]:
                    field.addItem(f"{device['id']}: {device['name']}", device["id"])
            if wanted is not None and field.findData(wanted) < 0:
                field.addItem(f"{wanted}: dispositivo indisponível", wanted)
            field.setCurrentIndex(max(0, field.findData(wanted)))

    def local_diagnostic(self):
        if self.state not in {"disponível", "pausado"}:
            return

        async def run(gen):
            try:
                found = await asyncio.to_thread(devices)
                text = (
                    f"Dados: {self.folder}\nChave presente: {'sim' if api_key(self.folder) else 'não'}\n"
                    f"Dispositivos: {len(found)}. Sem chamadas à API. Voz API não validada."
                )
                self.tasks.engine.send(gen, "diagnostic", text=text, devices=found)
            except AudioError as error:
                self.tasks.engine.send(gen, "diagnostic", text=str(error), devices=[])

        self.tasks.start(run)

    def test_microphone(self):
        if self.mode.currentData() == "paused":
            return
        self.state = "ouvindo"
        self.update_state()

        async def run(gen):
            try:
                wav = await self.tasks.engine.audio.record(
                    replace(self.settings, recording_seconds=3),
                    self.tasks.stop_recording,
                    lambda v: self.tasks.engine.send(gen, "level", value=v),
                )
                self.tasks.engine.send(
                    gen,
                    "diagnostic",
                    text=f"Captura local: {len(wav)} bytes. Nenhuma transcrição/API; gravação descartada.",
                )
            except AudioError as error:
                self.tasks.engine.send(gen, "error", message=str(error))
            finally:
                self.tasks.engine.send(gen, "state", value="disponível")

        self.tasks.start(run)

    def test_output(self):
        if self.mode.currentData() == "paused":
            return
        self.state = "falando"
        self.update_state()

        async def run(gen):
            try:
                await self.tasks.engine.audio.test_output(self.settings)
                self.tasks.engine.send(
                    gen, "diagnostic", text="Tom de saída concluído. Confirme se você ouviu."
                )
            except AudioError as error:
                self.tasks.engine.send(gen, "error", message=str(error))
            finally:
                self.tasks.engine.send(gen, "state", value="disponível")

        self.tasks.start(run)

    def real_sample(self):
        if self.settings.provider != "roteia" or self.mode.currentData() == "paused":
            QMessageBox.information(self, "Teste real", "Selecione Roteia e saia do modo Pausado primeiro.")
            return
        sample, ok = QInputDialog.getText(
            self, "Amostra real · pode gerar cobrança", "Texto curto para enviar à Roteia:"
        )
        if ok and sample.strip():
            self.input.setPlainText(sample)
            self.send_text()

    def real_voice_sample(self):
        if self.settings.provider != "roteia" or self.mode.currentData() == "paused":
            QMessageBox.information(self, "Teste de voz", "Selecione Roteia e saia do modo Pausado primeiro.")
            return
        sample, ok = QInputDialog.getText(
            self,
            "Uma amostra de voz · pode gerar cobrança",
            "Texto curto (até 300 caracteres). Testa o schema upstream, ainda não confirmado no gateway. "
            "Será feita uma única chamada, sem retry. Salve modelo e voz antes de testar:",
        )
        if not ok or not sample.strip():
            return
        if len(sample) > 300:
            QMessageBox.information(self, "Teste de voz", "Use até 300 caracteres na amostra.")
            return
        self.state = "preparando voz"
        self.update_state()

        async def run(gen):
            from .diagnostics import speech_sample

            engine = self.tasks.engine

            def report(event):
                if event["kind"] == "transcript":
                    engine.send(gen, "sample_text", text=event["text"])
                else:
                    engine.send(gen, "metrics", values=event["values"])

            try:
                await speech_sample(engine, sample, probe=True, emit=report, generation=gen)
                engine.send(gen, "voice_validated")
            except (ProviderError, AudioError) as error:
                engine.send(gen, "error", message=str(error))
            finally:
                engine.send(gen, "state", value="disponível")

        self.tasks.start(run)

    def closeEvent(self, event):
        self.timer.stop()
        self.tasks.shutdown()
        self.store.close()
        event.accept()
