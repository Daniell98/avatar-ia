"""Voz pela ElevenLabs: endpoint dedicado de TTS, sem schema de áudio em chat.

O texto enviado é o próprio transcript, então não há texto associado a validar.
A reprodução recebe os bytes como vieram; `audio.play` lê formato e taxa do
arquivo. Consultas de conta, modelos e vozes são metadados e não gastam cota.
"""

from __future__ import annotations

import io

import httpx
import soundfile as sf

from .providers import ProviderError, Speech

# Formatos que o plano gratuito alcança. PCM acima de 44,1 kHz exige Pro.
FREE_FORMATS = {
    "mp3_22050_32",
    "mp3_44100_32",
    "mp3_44100_64",
    "mp3_44100_96",
    "mp3_44100_128",
    "pcm_16000",
    "pcm_22050",
    "pcm_24000",
    "wav_16000",
    "wav_22050",
    "wav_24000",
}
TEXT_LIMIT = 5000


def http_error(status: int) -> ProviderError:
    messages = {
        401: "Chave da ElevenLabs recusada. Confira ELEVENLABS_API_KEY.",
        403: "A chave não tem acesso a esse recurso. Confira o plano.",
        422: "A ElevenLabs recusou os parâmetros do pedido.",
        429: "Limite de requisições ou de cota atingido. Aguarde e tente manualmente.",
    }
    return ProviderError(
        messages.get(status, f"A ElevenLabs retornou HTTP {status}."),
        status=status,
    )


class ElevenLabs:
    def __init__(self, settings, key: str, transport=None):
        self.settings, self.key, self.transport = settings, key, transport

    def client(self):
        if not self.key:
            raise ProviderError("Configure ELEVENLABS_API_KEY no .env antes de usar essa voz.")
        return httpx.AsyncClient(
            base_url=self.settings.eleven_base_url.rstrip("/") + "/",
            headers={"xi-api-key": self.key},
            timeout=self.settings.timeout,
            transport=self.transport,
        )

    async def _json(self, path: str) -> dict:
        try:
            async with self.client() as client:
                response = await client.get(path)
                if response.is_error:
                    raise http_error(response.status_code)
                return response.json()
        except httpx.TimeoutException:
            raise ProviderError(f"A consulta {path} excedeu o timeout.") from None
        except httpx.HTTPError:
            raise ProviderError(f"Falha de rede na consulta {path}.") from None
        except ValueError:
            raise ProviderError(f"A consulta {path} devolveu JSON ilegível.") from None

    async def subscription(self) -> dict:
        """Plano, cota e uso. Confirma acesso de API sem gastar caractere."""
        value = await self._json("user/subscription")
        used = value.get("character_count")
        limit = value.get("character_limit")
        left = limit - used if isinstance(used, int) and isinstance(limit, int) else None
        return {
            "tier": value.get("tier"),
            "status": value.get("status"),
            "characters_used": used,
            "character_limit": limit,
            "characters_left": left,
            "resets_at": value.get("next_character_count_reset_unix"),
            "max_output": value.get("max_character_limit_extension"),
        }

    async def models(self) -> list[dict]:
        value = await self._json("models")
        found = []
        for model in value if isinstance(value, list) else []:
            languages = {
                language.get("language_id")
                for language in model.get("languages") or []
                if isinstance(language, dict)
            }
            found.append(
                {
                    "model_id": model.get("model_id"),
                    "name": model.get("name"),
                    "tts": bool(model.get("can_do_text_to_speech")),
                    "pt": "pt" in languages,
                    "languages": len(languages),
                    "cost_factor": model.get("model_rates", {}).get("character_cost_multiplier"),
                }
            )
        return [model for model in found if model["tts"]]

    async def voices(self) -> list[dict]:
        value = await self._json("voices")
        return [
            {
                "voice_id": voice.get("voice_id"),
                "name": voice.get("name"),
                "labels": voice.get("labels") or {},
            }
            for voice in value.get("voices") or []
        ]

    def voice_settings(self) -> dict:
        """Controles de expressividade.

        O v3 aceita estabilidade só em três degraus (0,0 criativo / 0,5 natural /
        1,0 robusto), então o valor é encaixado no mais próximo para esse modelo.
        """
        settings = self.settings
        stability = settings.eleven_stability
        if "v3" in settings.eleven_model:
            stability = min((0.0, 0.5, 1.0), key=lambda degrau: abs(degrau - stability))
        return {
            "stability": stability,
            "similarity_boost": settings.eleven_similarity,
            "style": settings.eleven_style,
            "use_speaker_boost": settings.eleven_speaker_boost,
            "speed": settings.eleven_speed,
        }

    async def synthesize(self, text: str) -> Speech:
        settings = self.settings
        if not text.strip() or len(text) > TEXT_LIMIT:
            raise ProviderError(f"Texto vazio ou acima de {TEXT_LIMIT} caracteres.")
        if not settings.eleven_voice.strip():
            raise ProviderError("Nenhuma voz escolhida. Liste as vozes e defina eleven_voice.")
        if settings.eleven_format not in FREE_FORMATS:
            raise ProviderError(
                f"Formato {settings.eleven_format} não está na lista conferida para planos baixos."
            )
        body = {"text": text, "voice_settings": self.voice_settings()}
        if settings.eleven_model.strip():
            body["model_id"] = settings.eleven_model.strip()
        try:
            async with self.client() as client:
                response = await client.post(
                    f"text-to-speech/{settings.eleven_voice.strip()}",
                    params={"output_format": settings.eleven_format},
                    json=body,
                )
                if response.is_error:
                    raise http_error(response.status_code)
                audio = response.content
                if not audio:
                    raise ProviderError("A ElevenLabs respondeu sem corpo de áudio.")
                with sf.SoundFile(io.BytesIO(audio)) as sound:
                    if sound.frames < 1:
                        raise ProviderError("O áudio retornado está vazio.")
                # O texto enviado é a fala pedida: serve de transcript sem validação extra.
                return Speech(audio, text.strip(), settings.eleven_model or "eleven-default", {})
        except httpx.TimeoutException:
            raise ProviderError("A síntese excedeu o timeout. A chamada não será repetida.") from None
        except httpx.HTTPError:
            raise ProviderError("Falha de rede durante a síntese. Sem nova tentativa.") from None
        except sf.LibsndfileError:
            raise ProviderError(
                f"O áudio em {settings.eleven_format} não foi decodificável aqui. Nada foi reproduzido."
            ) from None
