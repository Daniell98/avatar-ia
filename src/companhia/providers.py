from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx
import numpy as np
import soundfile as sf

from .config import Settings


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        field: str | None = None,
        detail: str | None = None,
    ):
        super().__init__(message)
        self.status, self.field, self.detail = status, field, detail


@dataclass
class Chunk:
    text: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class Transcript:
    text: str
    model: str = ""
    usage: dict = field(default_factory=dict)


@dataclass
class Speech:
    audio: bytes
    text: str
    model: str = ""
    usage: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    def stream(self, messages: list[dict]) -> AsyncIterator[Chunk]: ...


class TranscriptionProvider(Protocol):
    async def transcribe(self, audio: bytes) -> Transcript: ...


class SpeechProvider(Protocol):
    async def synthesize(self, text: str) -> Speech: ...


def http_error(status: int) -> ProviderError:
    messages = {
        401: "Chave recusada. Confira a configuração local da Roteia.",
        402: "Saldo insuficiente. Confira o painel da Roteia.",
        403: "A chave não tem acesso a esse recurso ou modelo.",
        413: "Arquivo de áudio excede o limite do provedor.",
        429: "Limite de requisições atingido. Aguarde e tente manualmente.",
    }
    return ProviderError(
        messages.get(status, f"O provedor retornou HTTP {status}. Confira modelo e contrato."), status=status
    )


class Roteia:
    def __init__(self, settings: Settings, key: str, transport=None):
        self.settings, self.key, self.transport = settings, key, transport

    def client(self):
        if not self.key:
            raise ProviderError("Configure a chave da Roteia ou selecione o modo Simulado nas configurações.")
        return httpx.AsyncClient(
            base_url=self.settings.base_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + self.key},
            timeout=self.settings.timeout,
            transport=self.transport,
            follow_redirects=False,
        )

    async def stream(self, messages: list[dict]) -> AsyncIterator[Chunk]:
        try:
            async with self.client() as client:
                async with client.stream(
                    "POST",
                    "chat/completions",
                    json={
                        "model": self.settings.chat_model,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    if response.is_error:
                        raise http_error(response.status_code)
                    if "text/event-stream" not in response.headers.get("content-type", ""):
                        raise ProviderError("Resposta sem SSE. Confirme streaming do modelo configurado.")
                    data = []
                    finished = False
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data.append(line[5:].lstrip())
                        elif not line and data:
                            payload = "\n".join(data)
                            data = []
                            if payload == "[DONE]":
                                finished = True
                                break
                            event = json.loads(payload)
                            if event.get("error"):
                                raise ProviderError(
                                    "O provedor interrompeu o fluxo. A resposta está incompleta."
                                )
                            choices = event.get("choices") or []
                            text = (choices[0].get("delta", {}).get("content") or "") if choices else ""
                            if not isinstance(text, str):
                                raise ProviderError("Delta de texto incompatível com o contrato.")
                            if choices and choices[0].get("finish_reason"):
                                finished = True
                                if choices[0]["finish_reason"] not in {"stop"}:
                                    raise ProviderError(
                                        "Geração terminou incompleta ou com recurso não suportado."
                                    )
                            yield Chunk(text, event.get("model", ""), event.get("usage") or {})
                    if not finished:
                        raise ProviderError(
                            "Conexão terminou antes da conclusão. Não houve repetição automática."
                        )
        except httpx.TimeoutException:
            raise ProviderError("A Roteia excedeu o tempo limite. Tente novamente manualmente.") from None
        except httpx.HTTPError:
            raise ProviderError("Falha de rede ao acessar a Roteia. Confira sua conexão.") from None
        except (json.JSONDecodeError, KeyError, TypeError):
            raise ProviderError("A resposta da Roteia não corresponde ao contrato esperado.") from None

    async def transcribe(self, audio: bytes) -> Transcript:
        if not audio or len(audio) > 25_000_000:
            raise ProviderError("Áudio vazio ou acima de 25 MB.")
        try:
            async with self.client() as client:
                response = await client.post(
                    "audio/transcriptions",
                    data={"model": self.settings.transcription_model},
                    files={"file": ("fala.wav", audio, "audio/wav")},
                )
                if response.is_error:
                    raise http_error(response.status_code)
                result = response.json()
                text = result.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ProviderError("A transcrição não retornou texto utilizável.")
                return Transcript(text.strip(), result.get("model", ""), result.get("usage") or {})
        except httpx.TimeoutException:
            raise ProviderError("A transcrição excedeu o tempo limite.") from None
        except httpx.HTTPError:
            raise ProviderError("Falha de rede durante a transcrição.") from None
        except (ValueError, TypeError):
            raise ProviderError("Formato da transcrição incompatível.") from None


class ContractSpeech:
    """Adaptador real, habilitado apenas com contrato do gateway confirmado localmente.

    Não incorpora um schema OpenAI por analogia. O operador fornece o contrato,
    sua referência e os caminhos de áudio/transcrição de uma resposta confirmada.
    """

    def __init__(self, roteia: Roteia):
        self.roteia = roteia

    def contract(self) -> dict:
        try:
            value = json.loads(Path(self.roteia.settings.speech_contract).read_text(encoding="utf-8"))
            if (
                value.get("confirmed") is not True
                or not value.get("evidence")
                or value.get("endpoint") != "chat/completions"
                or value.get("format") != "wav"
                or not isinstance(value.get("request"), dict)
                or not value.get("audio_path")
                or not value.get("transcript_path")
            ):
                raise ValueError()
            if "{text}" not in json.dumps(value["request"]):
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError):
            raise ProviderError(
                "Voz por API pendente: informe um contrato confirmado. Consulte docs/contratos.md."
            ) from None

    async def synthesize(self, text: str) -> Speech:
        contract = self.contract()
        settings = self.roteia.settings
        replacements = {
            "{text}": text,
            "{model}": settings.speech_model,
            "{voice}": settings.voice,
            "{format}": settings.audio_format,
        }

        def expand(obj):
            if isinstance(obj, str):
                for key, value in replacements.items():
                    obj = obj.replace(key, value)
                return obj
            if isinstance(obj, dict):
                return {k: expand(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [expand(v) for v in obj]
            return obj

        def at(obj, path):
            for item in path.split("."):
                obj = obj[int(item)] if isinstance(obj, list) else obj[item]
            return obj

        try:
            async with self.roteia.client() as client:
                response = await client.post(contract["endpoint"], json=expand(contract["request"]))
                if response.is_error:
                    raise http_error(response.status_code)
                value = response.json()
                audio = base64.b64decode(at(value, contract["audio_path"]), validate=True)
                transcript = at(value, contract["transcript_path"])
                if not isinstance(transcript, str) or not transcript.strip():
                    raise ValueError()
                # A fala e o texto exibido serão os retornados juntos, mesmo se o modelo parafrasear.
                with sf.SoundFile(io.BytesIO(audio)) as file:
                    if file.format != "WAV" or file.frames < 1:
                        raise ValueError()
                return Speech(audio, transcript.strip(), value.get("model", ""), value.get("usage") or {})
        except httpx.TimeoutException:
            raise ProviderError("A voz por API excedeu o tempo limite.") from None
        except httpx.HTTPError:
            raise ProviderError("Falha de rede durante a síntese de voz.") from None
        except (ValueError, KeyError, IndexError, TypeError, sf.LibsndfileError):
            raise ProviderError(
                "Resposta de voz incompatível com o contrato local; nenhum áudio foi tocado."
            ) from None


class WindowsSpeech:
    def __init__(self, voice="", timeout=60):
        self.voice, self.timeout = voice, timeout

    async def synthesize(self, text: str) -> Speech:
        if sys.platform != "win32":
            raise ProviderError("A alternativa local de voz do Windows só funciona no Windows.")
        with tempfile.TemporaryDirectory(prefix="companhia-") as folder:
            path = Path(folder)
            (path / "text.txt").write_text(text, encoding="utf-8")
            script = Path(__file__).parent / "resources/windows_speech.ps1"
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-TextPath",
                str(path / "text.txt"),
                "-OutputPath",
                str(path / "speech.wav"),
                "-VoiceName",
                self.voice,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=0x08000000,
            )
            try:
                await asyncio.wait_for(proc.communicate(), self.timeout)
                if proc.returncode != 0:
                    raise ProviderError(
                        "Voz do Windows indisponível. Instale uma voz pt-BR ou confira o nome."
                    )
                return Speech((path / "speech.wav").read_bytes(), text, "windows/System.Speech")
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()


class MockProvider:
    """Somente testes e demonstração explicitamente identificada."""

    async def stream(self, messages):
        if messages[-1]["content"].startswith("INICIATIVA"):
            reply = "[SIMULADO] Uma pausa tranquila por aqui."
        else:
            reply = "[SIMULADO] Recebi seu texto. Este modo testa a interface, sem consultar a Roteia."
        for word in reply.split(" "):
            await asyncio.sleep(0.015)
            yield Chunk(word + " ", "mock/no-api", {"total_tokens": 0})

    async def transcribe(self, audio):
        return Transcript("[SIMULADO] Teste de gravação local.", "mock/no-api")

    async def synthesize(self, text):
        wav = io.BytesIO()
        # Tom de teste, não representa fala sintetizada.
        samples = np.sin(np.arange(4800) * 2 * np.pi * 440 / 16000).astype("float32") * 0.05
        sf.write(wav, samples, 16000, format="WAV", subtype="PCM_16")
        return Speech(wav.getvalue(), text, "mock/test-tone")
