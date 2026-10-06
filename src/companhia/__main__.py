from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

from .audio import AudioError, devices
from .config import Settings, api_key, data_dir, personality_file
from .conversation import Conversation
from .memory import Store
from .providers import Roteia
from .roteia_speech import RoteiaSpeech


def local_diagnostic(folder: Path, settings: Settings) -> dict:
    try:
        available = devices()
        audio_status = "dispositivos enumerados; captura/reprodução ainda exigem teste local"
    except AudioError as error:
        available, audio_status = [], str(error)
    return {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "data_dir": str(folder),
        "key_present": bool(api_key(folder)),
        "provider": settings.provider,
        "chat_model": settings.chat_model,
        "transcription_model": settings.transcription_model,
        "speech": settings.speech,
        "audio_status": audio_status,
        "devices": available,
        "personality": str(personality_file(folder)),
        "api_calls": 0,
        "voice_api_validation": (
            "schema observado em diagnóstico real; audição/conversa requerem teste manual"
            if RoteiaSpeech(Roteia(settings, ""), folder).validated()
            else "não testado: execute uma amostra explícita --real --probe-audio --speech-text"
        ),
    }


async def real_diagnostic(folder: Path, settings: Settings, args):
    if not api_key(folder):
        print("Configure a chave localmente antes do diagnóstico real.", file=sys.stderr)
        return 1
    store = Store(folder / "companhia.sqlite3")
    errors = []

    def emit(event):
        if event["kind"] == "error":
            errors.append(event["message"])
            print(event["message"], file=sys.stderr)
        elif event["kind"] == "metrics":
            print(json.dumps(event["values"], ensure_ascii=False))

    # Real é sempre Roteia, mesmo se a configuração da GUI estiver em Simulado.
    settings = replace(settings, provider="roteia", speech="off" if args.text else settings.speech)
    engine = Conversation(settings, store, folder, emit, lambda gen: True)
    try:
        if args.text:
            await engine.turn(1, text=args.text)
            for row in store.recent(2):
                print(f"{row['role']}: {row['content']}")
        elif args.wav:
            import numpy as np
            import soundfile as sf

            from .providers import ProviderError

            file = Path(args.wav)
            if file.stat().st_size > 25_000_000:
                raise ProviderError("Amostra acima de 25 MB.")
            samples, rate = sf.read(file, dtype="float32")
            if not len(samples) or len(samples) / rate > 30 or np.sqrt(np.mean(samples**2)) < 0.002:
                raise ProviderError("Use uma amostra WAV com fala, de até 30 segundos, sem silêncio.")
            transcript = await engine.call(
                1,
                "transcription",
                settings.transcription_model,
                lambda: engine.transcription.transcribe(file.read_bytes()),
            )
            print(transcript.text)
        elif args.probe_stream_text:
            speech = RoteiaSpeech(Roteia(settings, engine.llm.key), folder, probing=True)
            control = await speech.probe_text_stream(
                stream=not args.no_stream, model=args.probe_model or ""
            )
            print(json.dumps(control, ensure_ascii=False))
        elif args.speech_text:
            from .diagnostics import speech_sample

            settings = replace(
                settings, speech="roteia", voice=args.voice if args.voice is not None else settings.voice
            )
            engine = Conversation(settings, store, folder, emit, lambda gen: True)

            def report(event):
                if event["kind"] == "transcript":
                    print("Texto associado à fala (para comparação):", event["text"])
                else:
                    print(json.dumps(event["values"], ensure_ascii=False))

            await speech_sample(
                engine, args.speech_text, probe=args.probe_audio, play=not args.no_play, emit=report
            )
        else:
            print(
                "Escolha --text, --wav, --speech-text ou --probe-stream-text para uma amostra real.",
                file=sys.stderr,
            )
            return 1
        return 1 if errors else 0
    except Exception as error:
        from .providers import ProviderError

        print(
            str(error)
            if isinstance(error, (ProviderError, AudioError))
            else "Falha no diagnóstico; confira arquivo, contrato e configurações.",
            file=sys.stderr,
        )
        return 1
    finally:
        store.close()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Companhia · assistente desktop em pt-BR")
    parser.add_argument("--mock", action="store_true", help="Modo simulado explícito; não chama APIs")
    sub = parser.add_subparsers(dest="command")
    diagnostic = sub.add_parser("diagnostico", help="Diagnóstico local sem chamadas pagas por padrão")
    diagnostic.add_argument(
        "--real", action="store_true", help="Envia uma amostra escolhida; pode gerar cobrança"
    )
    samples = diagnostic.add_mutually_exclusive_group()
    samples.add_argument("--text", help="Texto curto para uma chamada real de chat")
    samples.add_argument("--wav", help="Amostra WAV, até 30 s, para transcrição real")
    samples.add_argument("--speech-text", help="Uma amostra de voz Roteia com texto curto, sem retry")
    samples.add_argument(
        "--probe-stream-text",
        action="store_true",
        help="Controle: stream de texto no modelo de voz, sem áudio, para isolar a falha",
    )
    diagnostic.add_argument(
        "--probe-audio",
        action="store_true",
        help="Testa explicitamente a hipótese de schema upstream no gateway",
    )
    diagnostic.add_argument("--voice", help="Voz da amostra (vazio/configuração: alloy)")
    diagnostic.add_argument(
        "--no-play", action="store_true", help="Valida a amostra sem reproduzir; áudio descartado"
    )
    diagnostic.add_argument(
        "--no-stream",
        action="store_true",
        help="No controle de texto, repete o exemplo publicado pela Roteia, sem stream",
    )
    diagnostic.add_argument(
        "--probe-model",
        help="Modelo do controle de texto, uma amostra por execução (padrão: o de voz)",
    )
    args = parser.parse_args()
    folder = data_dir()
    startup_error = ""
    try:
        settings = Settings.load(folder)
    except (ValueError, TypeError, OSError):
        settings = Settings()
        startup_error = (
            "Configuração local inválida. Valores padrão carregados; arquivo preservado até você salvar."
        )
    if args.mock:
        settings = replace(settings, provider="mock", speech="off")
    if args.command == "diagnostico":
        if (args.probe_audio or args.voice is not None or args.no_play) and not (
            args.real and args.speech_text
        ):
            parser.error("--probe-audio, --voice e --no-play exigem --real e --speech-text.")
        if (args.no_stream or args.probe_model) and not (args.real and args.probe_stream_text):
            parser.error("--no-stream e --probe-model exigem --real e --probe-stream-text.")
        if args.real:
            if args.mock:
                parser.error("--mock e --real não podem ser combinados.")
            if args.text and len(args.text) > 500:
                parser.error("Use até 500 caracteres no diagnóstico.")
            if args.speech_text and len(args.speech_text) > 300:
                parser.error("Use até 300 caracteres na amostra de voz.")
            sys.exit(asyncio.run(real_diagnostic(folder, settings, args)))
        if args.text or args.wav or args.speech_text or args.probe_stream_text:
            parser.error("Amostras exigem --real; sem essa opção o diagnóstico é apenas local.")
        print(json.dumps(local_diagnostic(folder, settings), ensure_ascii=False, indent=2))
        return
    from PySide6.QtWidgets import QApplication

    from .ui import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Companhia")
    window = MainWindow(folder, settings, startup_error)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
