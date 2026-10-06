from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def data_dir() -> Path:
    override = os.getenv("COMPANHIA_DATA_DIR")
    path = Path(override).expanduser() if override else user_data_path("Companhia", appauthor=False)
    if not path.is_absolute():
        raise ValueError("COMPANHIA_DATA_DIR deve ser um caminho absoluto.")
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    name: str = "Companhia"
    provider: str = "roteia"
    base_url: str = "https://api.roteia.ai/v1"
    chat_model: str = "deepseek/deepseek-v4-flash"
    transcription_model: str = "openai/whisper-1"
    speech_model: str = "openai/gpt-audio-mini"
    speech: str = "off"
    voice: str = ""
    audio_format: str = "wav"
    speech_contract: str = ""
    timeout: int = 60
    input_device: int | None = None
    output_device: int | None = None
    sample_rate: int = 16000
    recording_seconds: int = 30
    shortcut: str = "Ctrl+Space"
    max_calls_day: int = 100
    max_tokens_day: int = 100000
    idle_seconds: int = 90
    initiative_interval: int = 300
    initiatives_hour: int = 4
    spontaneity: int = 50
    affection: int = 50
    opinions: int = 50
    teasing: int = 50
    recent_messages: int = 12
    context_chars: int = 18000
    max_message_chars: int = 4000

    def validate(self) -> None:
        if self.provider not in {"roteia", "mock"} or self.speech not in {"off", "windows", "contract"}:
            raise ValueError("Provedor ou voz inválidos.")
        if not self.base_url.startswith("https://"):
            raise ValueError("A URL da API deve usar HTTPS.")
        for key, low, high in [
            ("timeout", 5, 300),
            ("recording_seconds", 1, 120),
            ("max_calls_day", 1, 10000),
            ("max_tokens_day", 1, 10000000),
            ("idle_seconds", 10, 3600),
            ("initiative_interval", 30, 86400),
            ("initiatives_hour", 1, 20),
            ("recent_messages", 2, 40),
            ("context_chars", 18000, 50000),
            ("max_message_chars", 100, 4000),
        ]:
            if not low <= getattr(self, key) <= high:
                raise ValueError(f"{key}: use um valor entre {low} e {high}.")
        if self.sample_rate not in {16000, 24000, 44100, 48000}:
            raise ValueError("Taxa de áudio não suportada.")
        if not self.name.strip() or len(self.name) > 80:
            raise ValueError("O nome deve ter entre 1 e 80 caracteres.")
        for key in ("spontaneity", "affection", "opinions", "teasing"):
            if not 0 <= getattr(self, key) <= 100:
                raise ValueError(f"{key}: use uma intensidade de 0 a 100.")

    @classmethod
    def load(cls, folder: Path) -> Settings:
        file = folder / "config.json"
        values = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
        allowed = {f.name for f in fields(cls)}
        result = cls(**{k: v for k, v in values.items() if k in allowed})
        result.validate()
        return result

    def save(self, folder: Path) -> None:
        self.validate()
        temp = folder / "config.json.tmp"
        temp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(folder / "config.json")


def api_key(folder: Path) -> str:
    return os.getenv("ROTEIA_API_KEY", "").strip() or (
        (folder / "api-key.txt").read_text(encoding="utf-8").strip()
        if (folder / "api-key.txt").exists()
        else ""
    )


def personality_file(folder: Path) -> Path:
    target = folder / "personality.md"
    if not target.exists():
        target.write_text(
            (Path(__file__).parent / "resources/personality.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
    return target
