from __future__ import annotations

import asyncio
import re
import threading
import time
import uuid
from pathlib import Path

from .audio import Audio, AudioError
from .config import Settings, api_key, elevenlabs_key
from .elevenlabs_speech import ElevenLabs
from .memory import Store
from .personality import context
from .proactivity import Proactivity
from .providers import ContractSpeech, MockProvider, ProviderError, Roteia, WindowsSpeech
from .roteia_speech import RoteiaSpeech
from .tone import apply_tone, tone_request


class Conversation:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        folder: Path,
        emit,
        current,
        llm=None,
        transcription=None,
        speech=None,
        audio=None,
    ):
        self.settings, self.store, self.folder = settings, store, folder
        self.emit, self.current = emit, current
        self.audio = audio or Audio()
        provider = MockProvider() if settings.provider == "mock" else Roteia(settings, api_key(folder))
        self.llm = llm or provider
        self.transcription = transcription or provider
        if speech:
            self.speech = speech
        elif settings.speech == "windows":
            self.speech = WindowsSpeech(settings.voice, settings.timeout)
        elif settings.speech == "contract":
            self.speech = MockProvider() if settings.provider == "mock" else ContractSpeech(provider)
        elif settings.speech == "roteia":
            self.speech = MockProvider() if settings.provider == "mock" else RoteiaSpeech(provider, folder)
        elif settings.speech == "eleven":
            # Provedor próprio: independe da Roteia, inclusive no modo simulado de chat.
            self.speech = (
                MockProvider()
                if settings.provider == "mock"
                else ElevenLabs(settings, elevenlabs_key(folder))
            )
        else:
            self.speech = None
        self.proactivity = Proactivity(
            settings.idle_seconds,
            settings.initiative_interval,
            settings.initiatives_hour,
            last_activity=time.monotonic(),
        )

    def send(self, generation: int, kind: str, **payload):
        if self.current(generation):
            self.emit({"generation": generation, "kind": kind, **payload})

    def check(self, generation: int):
        if not self.current(generation):
            raise asyncio.CancelledError()

    async def call(self, generation: int, modality: str, model: str, operation):
        self.check(generation)
        # Provedor simulado e SAPI local não são consumo da Roteia.
        effective = "mock/no-api" if self.settings.provider == "mock" else model
        id = self.store.start_call(
            str(generation), modality, effective, self.settings.max_calls_day, self.settings.max_tokens_day
        )
        begin = time.monotonic()
        result = None
        state = "error"
        try:
            result = await operation()
            self.check(generation)
            state = "complete"
            return result
        except asyncio.CancelledError:
            state = "interrupted"
            raise
        finally:
            self.store.finish_call(
                id,
                state,
                getattr(result, "model", ""),
                getattr(result, "usage", {}),
                time.monotonic() - begin,
            )

    async def turn(
        self,
        generation: int,
        text: str | None = None,
        stop: threading.Event | None = None,
        proactive=False,
        editing=lambda: False,
    ):
        turn = uuid.uuid4().hex
        response_id = None
        answer = ""
        message_state = "error"
        capture_end = None
        metrics = {}
        current_message_id = None
        turn_begin = time.monotonic()
        try:
            if self.proactivity.mode == "paused":
                return
            if proactive and (self.proactivity.mode != "company" or editing()):
                return
            self.check(generation)
            if stop is not None:
                self.proactivity.activity(time.monotonic())
                self.send(generation, "state", value="ouvindo")
                wav = await self.audio.record(
                    self.settings, stop, lambda value: self.send(generation, "level", value=value)
                )
                self.check(generation)
                capture_end = time.monotonic()
                self.send(generation, "state", value="transcrevendo")
                begin = time.monotonic()
                transcript = await self.call(
                    generation,
                    "transcription",
                    self.settings.transcription_model,
                    lambda: self.transcription.transcribe(wav),
                )
                metrics["transcription_s"] = time.monotonic() - begin
                text = transcript.text
            if not proactive:
                if not text or not text.strip():
                    return
                if len(text) > self.settings.max_message_chars:
                    raise ValueError(f"Use até {self.settings.max_message_chars} caracteres por mensagem.")
                self.check(generation)
                self.proactivity.activity(time.monotonic())
                id = self.store.message(turn, "user", text)
                current_message_id = id
                self.send(generation, "refresh")
                tone = tone_request(text)
                if tone:
                    apply_tone(self.store, tone)
                    self.send(generation, "tone", value=tone)
                silence = re.fullmatch(
                    r"(?:fica em sil[eê]ncio|sil[eê]ncio|n[aã]o puxe assunto|modo foco)[.!]?",
                    text.strip(),
                    re.I,
                )
                local = self.store.memory_command(text, id)
                if silence:
                    self.proactivity.mode = "focus"
                    local = "Tudo bem. Ativei Foco e vou responder quando você me chamar."
                    self.send(generation, "mode", value="focus")
                if local:
                    self.store.message(turn, "assistant", local)
                    self.send(generation, "refresh")
                    message_state = "complete"
                    return
            else:
                text = (
                    "INICIATIVA: faça um comentário curto sobre o contexto recente, sem cobrar resposta. "
                    "Se não há algo pertinente, responda exatamente <SILENCIO>. Não infira atividade pelo silêncio."
                )
            # Resumo extrativo local: nenhuma chamada adicional nem promoção a memória.
            recent = self.store.recent(40, for_context=True)
            if len(recent) > self.settings.recent_messages:
                older = recent[: -self.settings.recent_messages]
                excerpt = "\n".join(f"{row['role']}: {row['content'][:180]}" for row in older)[-2000:]
                self.store.set_meta("summary", excerpt)
            messages = context(
                self.store,
                self.settings,
                self.folder,
                text,
                current_message_id=current_message_id,
                proactive=proactive,
            )
            self.send(generation, "state", value="respondendo")
            returned, usage = "", {}
            call_id = self.store.start_call(
                turn,
                "chat",
                self.settings.chat_model if self.settings.provider != "mock" else "mock/no-api",
                self.settings.max_calls_day,
                self.settings.max_tokens_day,
            )
            begin = time.monotonic()
            if proactive:
                self.proactivity.attempted(begin)
            call_state = "error"
            if not proactive:
                response_id = self.store.message(turn, "assistant", "", "pending")
            try:
                async for chunk in self.llm.stream(messages):
                    self.check(generation)
                    if proactive and (self.proactivity.mode != "company" or editing()):
                        raise asyncio.CancelledError()
                    returned = chunk.model or returned
                    usage = chunk.usage or usage
                    if chunk.text:
                        if not answer:
                            metrics["first_text_s"] = time.monotonic() - begin
                        answer += chunk.text
                        if len(answer) > 12000:
                            raise ProviderError(
                                "Resposta excedeu o limite local. Interrompida para evitar saída excessiva."
                            )
                        if response_id:
                            self.store.update_message(response_id, answer, "pending")
                            self.send(generation, "delta", id=response_id, text=answer)
                self.check(generation)
                if not answer.strip():
                    raise ProviderError("O provedor encerrou sem uma resposta textual.")
                call_state = "complete"
            except asyncio.CancelledError:
                call_state = "interrupted"
                raise
            finally:
                metrics["generation_s"] = time.monotonic() - begin
                self.store.finish_call(call_id, call_state, returned, usage, metrics["generation_s"])
            if proactive:
                if self.proactivity.mode != "company" or editing():
                    raise asyncio.CancelledError()
                if answer.strip() == "<SILENCIO>":
                    message_state = "complete"
                    return
                response_id = self.store.message(turn, "assistant", answer, "pending")
                self.proactivity.delivered()
                self.send(generation, "refresh")
            if self.speech:
                try:
                    self.send(generation, "state", value="preparando voz")
                    model = {
                        "windows": "windows/System.Speech",
                        "eleven": f"elevenlabs/{self.settings.eleven_model}",
                    }.get(self.settings.speech, self.settings.speech_model)
                    synthesis_begin = time.monotonic()
                    try:
                        spoken = await self.call(
                            generation, "speech", model, lambda: self.speech.synthesize(answer)
                        )
                    finally:
                        synthesis_end = time.monotonic()
                        metrics["synthesis_s"] = synthesis_end - synthesis_begin
                    self.check(generation)
                    if proactive and (self.proactivity.mode != "company" or editing()):
                        raise asyncio.CancelledError()
                    answer = spoken.text
                    self.store.update_message(response_id, answer, "pending")
                    self.send(generation, "refresh")
                    self.send(generation, "state", value="falando")

                    def started():
                        metrics["turn_to_playback_s"] = time.monotonic() - turn_begin
                        metrics["synthesis_end_to_playback_s"] = time.monotonic() - synthesis_end
                        if capture_end:
                            metrics["recording_to_voice_s"] = time.monotonic() - capture_end

                    await self.audio.play(
                        spoken.audio, self.settings, started, valid=lambda: self.current(generation)
                    )
                    self.check(generation)
                except (ProviderError, AudioError, TimeoutError, OSError) as error:
                    self.send(
                        generation,
                        "error",
                        message=(
                            str(error)
                            if isinstance(error, (ProviderError, AudioError))
                            else "Não foi possível produzir ou tocar a voz."
                        )
                        + " O texto está disponível.",
                    )
            message_state = "complete"
        except asyncio.CancelledError:
            message_state = "interrupted"
            raise
        except (ProviderError, AudioError, ValueError, OSError) as error:
            self.send(generation, "error", message=str(error))
        except Exception:
            # Erros inesperados não expõem request, chave ou base64.
            self.send(generation, "error", message="Falha interna. Confira o diagnóstico e reinicie o turno.")
        finally:
            if response_id:
                self.store.update_message(response_id, answer, message_state)
            if self.current(generation) and not proactive:
                self.proactivity.last_activity = time.monotonic()
            self.send(generation, "metrics", values=metrics)
            self.send(generation, "refresh")
            self.send(
                generation, "state", value="disponível" if self.proactivity.mode != "paused" else "pausado"
            )
