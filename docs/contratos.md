# Decisões e contratos de provedores

Consulta: 05–06/10/2026, ambiente Windows nativo. Uma amostra de áudio autenticada
foi autorizada na etapa 2; resultado HTTP 400, sem repetir a chamada.
O snapshot reduzido do catálogo consultado está em `catalogo-selecionado.json`.
Datas/preços de páginas cacheadas diferiam do catálogo ao vivo; o aplicativo não
usa esses valores para afirmar cobrança nem fixa preços de áudio a partir deles.

## Conversa

Base `https://api.roteia.ai/v1`; `POST chat/completions` com Bearer. Corpo enviado:
`model`, `messages`, `stream: true`. A escolha inicial é
`deepseek/deepseek-v4-flash`, disponível com streaming no catálogo consultado e
usado no exemplo Python oficial. É um ponto de partida para comparar naturalidade
em pt-BR e latência, ainda não medidos neste projeto.

O leitor SSE reúne linhas `data`, concatena deltas de texto, lê `model` e `usage`
quando presentes e exige conclusão. Queda parcial preserva a mensagem como
incompleta. Sem retry automático, troca de modelo ou parâmetros como temperature,
reasoning_effort, stream_options ou limites de tokens não confirmados. O teto de
saída local cancela a leitura ao exceder 12.000 caracteres; não garante custo.

Fontes: [documentação](https://roteia.ai/docs/),
[Python](https://roteia.ai/docs/python/),
[modelo inicial](https://roteia.ai/modelos/deepseek/deepseek-v4-flash/),
[streaming](https://roteia.ai/guias/streaming-em-apis-de-ia/).

## Transcrição

`POST audio/transcriptions`, multipart com **somente** `model` e `file`, limite
documentado de 25 MB e resposta ao final. ID inicial `openai/whisper-1`,
disponível no catálogo. Parser exige JSON com texto não vazio em `text`.
A aplicação produz WAV PCM16 mono em segmentos, sem upload de silêncio.

O endpoint e os campos multipart estão confirmados no guia da Roteia; a aceitação
de WAV/16 kHz e o campo `text` pelo gateway/modelo escolhido ainda precisam da
amostra autenticada. Não foram enviados idioma, response_format, prompt ou
timestamps por suposição. Não há Realtime nem transcrição contínua.

Fontes: [catálogo público](https://api.roteia.ai/catalog/models),
[transcrição](https://roteia.ai/modelos/transcricao/),
[contrato multipart e limite](https://roteia.ai/guias/modelos-de-transcricao-por-api/).

## Síntese por API — adaptador específico e hipótese verificável

O catálogo e a [página de GPT Audio Mini](https://roteia.ai/modelos/openai/gpt-audio-mini/)
declaram `text,audio → text,audio` em `chat/completions`. A
[categoria de áudio](https://roteia.ai/modelos/audio/) também o lista.
As páginas consultadas não especificam o pedido de saída falada, vozes aceitas,
formato binário/base64 ou caminhos de áudio e transcrição no JSON. As rotas
públicas `/openapi.json` e `/docs` da API retornaram HTTP 403 sem autenticação
na consulta da etapa 2. Portanto,
**não foi inventado `/audio/speech`**. Na etapa 2, a hipótese upstream é isolada
num diagnóstico explicitamente invocado, antes de habilitar conversa.

O `RoteiaSpeech` usa os campos documentados no
[guia upstream de áudio em Chat Completions](https://developers.openai.com/api/docs/guides/audio-chat-completions):
`model`, `messages`, `modalities: ["text", "audio"]`, `audio.voice` (alloy inicial)
e `audio.format` (wav). A resposta exige `choices[0].message.audio.data` em base64
e `choices[0].message.audio.transcript`, além de modelo coerente e conclusão `stop`.
Esses campos são fundamentados na [referência upstream](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
mas **a aceitação pelo gateway ainda precisa ser observada**. A página upstream
do [modelo solicitado](https://developers.openai.com/api/docs/models/gpt-audio-mini)
não é evidência de streaming ou disponibilidade na Roteia. Não se usa streaming
de áudio nesta implementação.

Diagnóstico, uma amostra por execução:

```powershell
uv run companhia diagnostico --real --probe-audio --voice alloy --speech-text 'Olá, Daniel. Esta é uma amostra curta.'
```

Pode gerar cobrança. A versão inicial não realizou amostras autenticadas.
Na etapa 2, a única amostra autorizada foi recusada com HTTP 400 em 4,235 s;
nenhum parâmetro específico foi informado de forma reconhecida, e não houve
áudio/modelo retornado/uso para validar. **A hipótese não foi confirmada.**
`--no-play` valida sem reprodução; a execução padrão permite ouvir/comparar.
O modelo vem da configuração local, sem varredura de modelos ou tentativas extras.
Sem `--probe-audio`, o adaptador exige uma observação real anterior da mesma
URL/modelo/voz/formato. Uma mudança invalida essa autorização técnica.

Um resultado real válido gera `audio-validation.json` com origem
`manual-real-diagnostic`, data, assinatura de configuração e modelo retornado.
Fixtures com transporte HTTP simulado são impedidas de criar essa confirmação.
Áudio/texto não ficam nesse arquivo nem no ledger de amostra. O transcript aparece
apenas na CLI/interface para comparação. A confirmação é **do schema observado**,
não certificação de naturalidade, idioma, fidelidade literal ou produto completo.

Pendências específicas se o diagnóstico falhar:

1. Em 400/422, confirmar especificamente `modalities`, `audio.voice` ou
   `audio.format` (o parâmetro é mostrado se a Roteia informar um campo seguro).
2. Se só vier texto, confirmar como solicitar `choices[0].message.audio.data`.
3. Se vier áudio sem transcript, obter o campo de texto associado àquela fala.
4. Confirmar a unidade de cobrança de áudio; preços de texto não bastam.

O adaptador genérico `ContractSpeech` continua para configurações legadas já
existentes; ele não é o caminho de configuração da voz Roteia para usuário final.
O template antigo permanece bloqueado e não foi marcado `confirmed=true`.

`request` é o corpo JSON confirmado. Substituições disponíveis em valores string:
`{text}`, `{model}`, `{voice}`, `{format}`. Deve haver `{text}` no pedido.
`audio_path` e `transcript_path` são caminhos de propriedades separados por pontos;
índices numéricos navegam listas. O adaptador exige áudio base64, WAV decodificável
e texto associado não vazio. Ele exibe/salva esse texto, mesmo que o modelo tenha
parafraseado a prévia. Não promete leitura literal. Nunca registre o base64.

O template é intencionalmente vazio e bloqueado. Testes cobrem o adaptador por
HTTP simulado e não constituem integração de voz real.

## Medições e fluidez

O fluxo mantém uma chamada de chat e uma de síntese, quando voz habilitada.
Mede `transcription_s`, `first_text_s`, `generation_s`, `synthesis_s`,
`turn_to_playback_s`, `synthesis_end_to_playback_s` e, em entrada gravada,
`recording_to_voice_s`. Início é o início local do stream de saída, não tempo
perceptual certificado. A amostra isolada mede síntese e início da reprodução.
Ausência de uma etapa não é registrada como zero.

Não segmentamos frases nem aumentamos chamadas silenciosamente. O modelo upstream
solicitado não estabelece streaming de áudio no gateway. Essa otimização exige
contrato e medições reais, incluindo custo e cancelamento, antes de ser adotada.

## Alternativa local identificada

`WindowsSpeech` usa `System.Speech` em processo PowerShell oculto, produz WAV
temporário e lê exatamente o texto mostrado. Voz pt-BR precisa estar instalada.
Cancelamento encerra o processo e remove os temporários. Seleção explícita na
interface, sem substituição automática de voz API. Não usa créditos nem GPU.

## Consumo e segurança operacional

Cada tentativa registra modalidade, estado, modelo solicitado/retornado, tempo
e `usage` informado, sem chave, autorização ou áudio bruto. Não há campo de custo
confirmado documentado na resposta consultada, então o custo permanece
**desconhecido**. Limites de chamadas/tokens não equivalem a orçamento em reais.
Contadores usam dia UTC; chamadas sem usage ainda contam contra o limite de
chamadas. Status 401, 402, 403, 413, 429 e falhas de rede têm mensagens locais.

Nenhum modelo/provedor é trocado pelo cliente. Se o gateway rotear internamente,
o modelo retornado será registrado quando informado; não se promete controle do
roteamento interno. A etapa 2 fez uma chamada autorizada e rejeitada com HTTP 400;
nenhum uso/custo foi informado, portanto não se afirma débito nem custo zero.
