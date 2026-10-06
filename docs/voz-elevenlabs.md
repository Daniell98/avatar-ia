# Voz: decisão de migrar para a ElevenLabs — 06/10/2026

Registro para quem retomar o projeto. Resume por que a saída de voz pela Roteia
foi abandonada, com a evidência obtida, e como a voz funciona hoje.

## Resultado

**A voz funciona.** Conversa real em pt-BR com a voz `ptbr-Larissa-natural`,
confirmada pelo usuário por audição. A Roteia continua responsável pelo chat de
texto e pela transcrição; só a síntese mudou de provedor.

## Por que a Roteia não serve para áudio

Quatro amostras autenticadas, uma hipótese distinta por execução, sem varredura
de modelos e sem repetição automática:

| Pedido | Resultado |
|---|---|
| `chat/completions` sem stream, `modalities: [text, audio]`, formato wav | HTTP 400 — `Audio output requires stream: true` |
| `stream: true` com `modalities` e `audio.format: pcm16` | HTTP 502 — `a rota do modelo não iniciou uma resposta válida` |
| `stream: true`, texto puro, sem `modalities` nem `audio` | HTTP 400 — `upstream_error`, `Provider returned error` |
| **sem** stream, texto puro (o exemplo publicado pela Roteia) | HTTP 400 — `upstream_error`, `Provider returned error` |
| controle: `deepseek/deepseek-v4-flash`, texto puro, sem stream | **HTTP 200, respondeu** |

A conclusão que essa sequência sustenta: a chave e o saldo funcionam, provado
pelo controle com deepseek. A rota de `openai/gpt-audio-mini` na Roteia falha em
toda configuração, inclusive no exemplo mínimo da documentação deles. Não é o
nosso schema, não é streaming e não é a conta — é o modelo indisponível no
gateway, apesar de o catálogo anunciar `status: available` e saída `text,audio`.

A documentação pública da Roteia (`/docs/`, `/docs/primeira-chamada/`,
`/modelos/audio/` e a página do GPT Audio Mini) não especifica o schema de áudio
em lugar nenhum: declara compatibilidade OpenAI e capacidade de áudio, sem um
exemplo de `modalities`, `audio` ou delta de áudio. A melhor evidência obtida
foi a própria mensagem de erro do gateway, mais específica que a documentação.

## O que o adaptador da Roteia virou

`src/companhia/roteia_speech.py` **não foi apagado** e continua correto conforme
a especificação upstream: `stream: true` com `audio.format: pcm16`, leitura SSE
de `delta.audio.data` e `delta.audio.transcript`, e montagem local do WAV em
`wav_from_pcm16` (pcm16 cru, 24 kHz mono 16 bits — em streaming a OpenAI não
aceita wav). Se a Roteia consertar a rota, ele deve funcionar sem alteração.
Segue bloqueado para conversa real por falta de `audio-validation.json`, que só
uma amostra real bem-sucedida grava.

Correções de diagnóstico que vieram dessa investigação e valem para qualquer
provedor:

- `gateway_detail()` preserva `code`, `type`, `param` e a mensagem do gateway,
  com fallback para o corpo cru quando não há envelope `error` (típico de 502,
  que costuma vir em texto ou HTML). Chaves, tokens Bearer, blocos longos de
  base64 e o texto da amostra são redigidos antes de qualquer saída.
  **Antes dessa correção a causa era indiagnosticável:** o código lia apenas
  `error.param` e descartava `error.message`.
- 500/502/503/504 têm caminho próprio: falha ao atender, não recusa de schema.
- `probe_text_stream(stream=, model=)` é o controle que separa as causas, usado
  pelo diagnóstico `--probe-stream-text`. Uma amostra por execução; `--probe-model`
  é escolha explícita do operador, não varredura.

## Como a voz funciona hoje

`src/companhia/elevenlabs_speech.py`. Endpoint dedicado, sem schema de áudio
dentro de chat:

```
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128
header: xi-api-key
body:   {"text": ..., "model_id": ..., "voice_settings": {...}}
```

Quatro detalhes que custaram verificação e evitam erro em quem mexer depois:

1. `output_format` é **query param**, não campo do corpo.
2. O texto enviado **é** o transcript. Não existe texto associado a validar,
   diferente da Roteia. Uma classe inteira de validação desaparece.
3. PCM só exige plano Pro **acima** de 44,1 kHz. `mp3_44100_128` funciona em
   qualquer plano, e o `soundfile` daqui decodifica MP3 (libsndfile 1.2.2), então
   `audio.play` reproduz sem alteração: ele lê formato e taxa do próprio arquivo.
4. O modelo `eleven_v3` aceita estabilidade só em três degraus (0,0 criativo /
   0,5 natural / 1,0 robusto). `voice_settings()` encaixa no degrau mais próximo
   para esse modelo e mantém o valor contínuo nos outros.

Chave em `ELEVENLABS_API_KEY` (`.env`, ignorado pelo Git) ou
`elevenlabs-key.txt` no diretório de dados, via `elevenlabs_key()` espelhando o
mecanismo da Roteia. `tests/conftest.py` mascara essa variável, senão os testes
leriam a chave real do `.env`.

## Configuração escolhida

| Campo | Valor | Motivo |
|---|---|---|
| `eleven_voice` | `4PNBmCCUBwRktp7B7R1y` | Larissa, pt-BR, sotaque paulistano natural |
| `eleven_model` | `eleven_v4_turbo` | custo 0.5x e menor latência |
| `eleven_stability` | 0.3 | baixa dá variação emocional; alta soa robótica |
| `eleven_style` | 0.4 | entonação mais marcada |
| `eleven_similarity` | 0.8 | fidelidade à voz original |
| `eleven_format` | `mp3_44100_128` | sem exigência de plano |

Quatro vozes pt-BR foram adicionadas à conta via
`POST /v1/voices/add/{public_owner_id}/{voice_id}`, buscadas em
`GET /v1/shared-voices?language=pt&gender=female&use_case=conversational`
(1.991 disponíveis). As outras três ficam como alternativa:
`ptbr-Bea-acolhedora`, `ptbr-Beatriz-calorosa`, `ptbr-Larissa-brincalhona`.

## Medições reais

Síntese completa, não estimativa. Frase de 72 caracteres: 1,23 s a 1,61 s nas
vozes pt-BR. Frase de 186 caracteres: 2,64 s no v4 Turbo, 3,24 s no v4 e 5,01 s
no v3. O v3 é o mais expressivo e foi descartado por isso: 5 s de silêncio
depois de cada fala prejudica a conversa mais do que o timbre melhora.

Plano da conta no momento: `creator`, ativo, 131.000 créditos. O contador
`character_count` da API **tem atraso** e marcou 12 depois de oito sínteses;
o consumo real não foi confirmado por essa via. Para 216 caracteres a 0.5x
seriam ~108 créditos. Quem precisar do custo exato deve conferir o painel.

## Pendências

- Entrada de voz (microfone → `openai/whisper-1` na Roteia) nunca foi exercitada
  com áudio real. Whisper usa o endpoint `transcriptions`, não `chat`, então a
  falha do gpt-audio-mini não diz nada sobre ela.
- Reprodução por segmentos de frase, para reduzir o tempo até a primeira fala,
  segue não implementada. Só vale com medição comparativa; hoje a síntese inteira
  precede a reprodução.
- A chave da ElevenLabs usada nestes testes foi exposta em texto na sessão de
  desenvolvimento e **precisa ser revogada**.
- O áudio da Roteia pode voltar a funcionar sem aviso. Se voltar, a decisão de
  provedor merece reavaliação por custo, não por capacidade.
