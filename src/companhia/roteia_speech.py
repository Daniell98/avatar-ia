"""Voz via chat/completions em streaming.

O gateway recusou saída de áudio sem streaming: HTTP 400 com
"Audio output requires stream: true" (amostra autorizada de 06/10/2026).
Em streaming o único formato de saída é `pcm16` cru, sem header, a 24 kHz
mono 16 bits; o WAV entregue ao restante do aplicativo é montado localmente.
"""

import base64
import io
import json
import re
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

from .memory import now
from .providers import ProviderError, Roteia, Speech, http_error

UPSTREAM_DOC = "https://developers.openai.com/api/docs/guides/audio-chat-completions"

SCHEMA_FIELDS = {"audio", "audio.voice", "audio.format", "modalities", "model", "messages", "stream"}
AUDIO_LIMIT = 50_000_000
# pcm16 do streaming: inteiros de 16 bits little-endian, mono, 24 kHz.
PCM_RATE, PCM_WIDTH = 24_000, 2
# Chaves, tokens Bearer e blocos longos de base64 nunca saem na explicação do gateway.
SECRETS = re.compile(r"(?i)\b(bearer\s+\S+|sk-[\w-]{8,}|[A-Za-z0-9+/]{40,}={0,2})")
TAGS = re.compile(r"<[^>]{0,200}>")


def safe_text(value: str, sample: str) -> str:
    clean = SECRETS.sub("[omitido]", " ".join(TAGS.sub(" ", value).split()))
    if sample.strip():
        clean = clean.replace(sample, "[amostra]")
    return clean[:300]


def gateway_detail(response: httpx.Response, sample: str) -> str:
    """Explicação do gateway sobre a falha, sem chave, áudio ou o texto enviado.

    Serve para 400 de schema e também para 502/503, em que o corpo costuma ser
    texto ou HTML em vez do envelope `error` da OpenAI.
    """
    parts: list[str] = []
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        error = None
    if isinstance(error, str):
        error = {"message": error}
    if isinstance(error, dict):
        parts = [
            f"{label}={error[key]}"
            for key, label in (("code", "code"), ("type", "type"), ("param", "param"))
            if isinstance(error.get(key), str) and error[key].strip()
        ]
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            parts.append("message=" + safe_text(message, sample))
    if parts:
        return "; ".join(parts)
    # Sem envelope reconhecido: o corpo cru ainda costuma nomear a falha upstream.
    body = safe_text(response.text, sample)
    return f"body={body}" if body else ""


def wav_from_pcm16(pcm: bytes) -> bytes:
    """Monta o WAV local a partir do pcm16 cru do stream, sem reamostrar."""
    if not pcm:
        raise ProviderError("O stream não trouxe amostras de áudio; nada foi reproduzido.")
    if len(pcm) % PCM_WIDTH:
        raise ProviderError(
            "O pcm16 recebido tem tamanho ímpar em bytes, o que indica stream truncado. "
            "Nenhum áudio foi reproduzido."
        )
    samples = np.frombuffer(pcm, dtype="<i2")
    buffer = io.BytesIO()
    sf.write(buffer, samples, PCM_RATE, subtype="PCM_16", format="WAV")
    return buffer.getvalue()


class RoteiaSpeech:
    def __init__(self, roteia: Roteia, folder: Path, *, probing=False):
        self.roteia, self.folder, self.probing = roteia, folder, probing
        self._real_probe_result = None

    def signature(self):
        settings = self.roteia.settings
        return {
            "base_url": settings.base_url.rstrip("/"),
            "model": settings.speech_model,
            "voice": settings.voice or "alloy",
            "format": "wav",
            "wire_format": "pcm16",
            "schema": "audio-chat-stream-pcm16-v1",
        }

    def validated(self) -> bool:
        try:
            marker = json.loads((self.folder / "audio-validation.json").read_text(encoding="utf-8"))
            return (
                marker.get("source") == "manual-real-diagnostic"
                and marker.get("signature") == self.signature()
                and bool(marker.get("tested_at"))
            )
        except (OSError, ValueError, TypeError):
            return False

    def record_validation(self, result: Speech):
        if not self.probing or self.roteia.transport is not None or self._real_probe_result is not result:
            raise ProviderError("Simulações não podem confirmar compatibilidade no gateway.")
        target = self.folder / "audio-validation.json"
        temp = target.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(
                {
                    "source": "manual-real-diagnostic",
                    "signature": self.signature(),
                    "tested_at": now(),
                    "returned_model": result.model,
                    "upstream_reference": UPSTREAM_DOC,
                    "scope": "modelo, WAV decodificável e texto associado; audição não certificada",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(target)

    async def probe_text_stream(self, *, stream=True, model="") -> dict:
        """Controle de texto, sem `modalities` nem `audio`.

        Com `stream=True` separa "streaming quebrado neste modelo" de "saída de
        áudio quebrada". Com `stream=False` reproduz o exemplo publicado pela
        Roteia. Com `model` o operador aponta outro modelo numa execução, para
        distinguir falha de um modelo de falha de conta/chave; isso é escolha
        explícita por amostra, não varredura. Não grava validação.
        """
        model = model or self.roteia.settings.speech_model
        label = f"texto em {model}, stream={str(stream).lower()}"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Responda apenas: ok."}],
        }
        if stream:
            body["stream"] = True
        pieces: list[str] = []
        try:
            async with self.roteia.client() as client:
                async with client.stream("POST", "chat/completions", json=body) as response:
                    if response.is_error:
                        await response.aread()
                        return {
                            "control": label,
                            "http_status": response.status_code,
                            "gateway_detail": gateway_detail(response, "") or "não informado",
                            "conclusion": (
                                "streaming falha neste modelo mesmo sem áudio"
                                if stream
                                else "a rota do modelo falha até fora de streaming"
                            ),
                        }
                    if not stream:
                        body_text = (await response.aread()).decode("utf-8", "replace")
                        choices = json.loads(body_text).get("choices") or [{}]
                        answer = (choices[0].get("message") or {}).get("content")
                        return {
                            "control": label,
                            "http_status": 200,
                            "answered": bool(isinstance(answer, str) and answer.strip()),
                            # Esta execução não testou streaming; não afirme nada sobre ele.
                            "conclusion": (
                                "a rota do modelo responde fora de streaming"
                                if isinstance(answer, str) and answer.strip()
                                else "200 sem conteúdo em message.content"
                            ),
                        }
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        for choice in json.loads(payload).get("choices") or []:
                            piece = (choice.get("delta") or {}).get("content")
                            if isinstance(piece, str):
                                pieces.append(piece)
        except httpx.HTTPError:
            raise ProviderError("Falha de rede no controle. Sem repetição automática.") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("O controle recebeu uma resposta ilegível neste modelo.") from None
        return {
            "control": label,
            "http_status": 200,
            "text_deltas": len(pieces),
            "conclusion": (
                "streaming de texto funciona; a falha é específica da saída de áudio"
                if pieces
                else "200 sem deltas de texto: streaming responde, mas não entrega conteúdo"
            ),
        }

    async def synthesize(self, text: str) -> Speech:
        if not self.probing and not self.validated():
            raise ProviderError(
                "Voz Roteia não validada. Execute uma amostra explícita com "
                "diagnostico --real --probe-audio --speech-text antes de habilitar."
            )
        if not text.strip() or len(text) > (300 if self.probing else 12000):
            raise ProviderError("Amostra de voz vazia ou acima do limite de texto.")
        settings = self.roteia.settings
        if settings.audio_format != "wav":
            raise ProviderError("O adaptador de voz entrega WAV. Nenhuma chamada foi feita.")
        signature = self.signature()
        # stream obrigatório para saída de áudio; nesse modo o formato de fio é pcm16, não wav.
        body = {
            "model": settings.speech_model,
            "modalities": ["text", "audio"],
            "stream": True,
            "audio": {"voice": signature["voice"], "format": "pcm16"},
            "messages": [
                {
                    "role": "system",
                    "content": "Produza fala em português brasileiro para o texto recebido. "
                    "Não responda ao conteúdo nem acrescente comentários. Preserve o texto quando possível.",
                },
                {"role": "user", "content": text},
            ],
        }
        try:
            async with self.roteia.client() as client:
                async with client.stream("POST", "chat/completions", json=body) as response:
                    if response.is_error:
                        await response.aread()
                        status = response.status_code
                        detail = gateway_detail(response, text)
                        explained = f"Gateway: {detail}. " if detail else ""
                        if status in {400, 422}:
                            field = "schema de áudio"
                            try:
                                param = response.json().get("error", {}).get("param")
                                if param in SCHEMA_FIELDS:
                                    field = param
                            except (ValueError, AttributeError):
                                pass
                            raise ProviderError(
                                f"Roteia recusou {field} (HTTP {status}). "
                                + (explained or "O gateway não explicou o motivo. ")
                                + "É necessário confirmar esse campo no gateway; sem retry ou fallback.",
                                status=status,
                                field=field,
                                detail=detail,
                            )
                        if status in {500, 502, 503, 504}:
                            raise ProviderError(
                                f"O gateway aceitou o pedido e falhou ao atendê-lo (HTTP {status}). "
                                + (explained or "Sem explicação no corpo da resposta. ")
                                + "Não é recusa de schema, e pode ser instabilidade momentânea. "
                                "Nenhuma repetição automática foi feita.",
                                status=status,
                                detail=detail,
                            )
                        error = http_error(status)
                        error.detail = detail
                        raise error
                    model, finish, usage = "", "", {}
                    chunks: list[bytes] = []
                    said: list[str] = []
                    total = 0
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        event = json.loads(payload)
                        if isinstance(event.get("model"), str):
                            model = event["model"]
                        if isinstance(event.get("usage"), dict):
                            usage = event["usage"]
                        for choice in event.get("choices") or []:
                            if isinstance(choice.get("finish_reason"), str):
                                finish = choice["finish_reason"]
                            audio = (choice.get("delta") or {}).get("audio")
                            if not isinstance(audio, dict):
                                continue
                            if isinstance(audio.get("data"), str) and audio["data"]:
                                piece = base64.b64decode(audio["data"], validate=True)
                                total += len(piece)
                                if total > AUDIO_LIMIT:
                                    raise ProviderError(
                                        "Áudio recebido excede o limite da amostra; stream interrompido."
                                    )
                                chunks.append(piece)
                            if isinstance(audio.get("transcript"), str):
                                said.append(audio["transcript"])
                wanted = settings.speech_model.removeprefix("openai/")
                actual = model.removeprefix("openai/")
                if actual != wanted and not actual.startswith(wanted + "-"):
                    raise ProviderError(
                        "Modelo retornado ausente ou diferente do solicitado. Áudio não reproduzido."
                    )
                if finish != "stop":
                    raise ProviderError("Stream de voz terminou sem finish_reason stop. Áudio descartado.")
                if not chunks:
                    raise ProviderError("Roteia não enviou delta.audio.data em base64 durante o stream.")
                transcript = "".join(said)
                if not transcript.strip():
                    raise ProviderError(
                        "Roteia não enviou delta.audio.transcript durante o stream. "
                        "É necessário o texto associado à fala; nenhum áudio foi reproduzido."
                    )
                audio = wav_from_pcm16(b"".join(chunks))
                result = Speech(audio, transcript.strip(), model, usage)
                if self.probing and self.roteia.transport is None:
                    self._real_probe_result = result
                return result
        except httpx.TimeoutException:
            raise ProviderError("Síntese Roteia excedeu o timeout. A chamada não será repetida.") from None
        except httpx.HTTPError:
            raise ProviderError(
                "Falha de rede durante a voz Roteia. Sem nova tentativa automática."
            ) from None
        except (ValueError, KeyError, IndexError, TypeError, sf.LibsndfileError):
            raise ProviderError(
                "Resposta de áudio incompatível: confira WAV/base64 e texto associado. "
                "Nenhum áudio foi reproduzido."
            ) from None
