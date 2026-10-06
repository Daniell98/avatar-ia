# Decisões e contratos de provedores

Consulta: 05–06/10/2026, ambiente Windows nativo, sem requisições autenticadas.
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

## Síntese por API — pendência concreta

O catálogo e a [página de GPT Audio Mini](https://roteia.ai/modelos/openai/gpt-audio-mini/)
declaram `text,audio → text,audio` em `chat/completions`. A
[categoria de áudio](https://roteia.ai/modelos/audio/) também o lista.
As páginas consultadas não especificam o pedido de saída falada, vozes aceitas,
formato binário/base64 ou caminhos de áudio e transcrição no JSON. As rotas
públicas `/openapi.json` e `/docs` da API não puderam ser consultadas. Portanto,
**não foi inventado `/audio/speech` nem ativado um schema de outro provedor**.

Evidência necessária para concluir:

1. Exemplo oficial da Roteia, ou confirmação do suporte, do corpo aceito por
   `chat/completions` para produzir áudio de `openai/gpt-audio-mini`.
2. Nome de voz válido e formato WAV, com resposta de exemplo mostrando áudio
   base64 e o texto correspondente àquela fala; unidade de cobrança de áudio.
3. Uma chamada autenticada curta escolhida pelo operador, com audição e comparação
   da fala ao texto retornado. Naturalidade/fidelidade não são garantidas pelo ID.

O adaptador `ContractSpeech` está implementado para esse contrato: não roda sem
arquivo local com `confirmed: true`, `evidence`, `endpoint: "chat/completions"`,
`format: "wav"`, `request`, `audio_path` e `transcript_path`. Copie
`contrato-voz.template.json` para a pasta local de dados, preencha **com o contrato
confirmado**, configure seu caminho absoluto e escolha Voz API na interface.

`request` é o corpo JSON confirmado. Substituições disponíveis em valores string:
`{text}`, `{model}`, `{voice}`, `{format}`. Deve haver `{text}` no pedido.
`audio_path` e `transcript_path` são caminhos de propriedades separados por pontos;
índices numéricos navegam listas. O adaptador exige áudio base64, WAV decodificável
e texto associado não vazio. Ele exibe/salva esse texto, mesmo que o modelo tenha
parafraseado a prévia. Não promete leitura literal. Nunca registre o base64.

O template é intencionalmente vazio e bloqueado. Testes cobrem o adaptador por
HTTP simulado e não constituem integração de voz real.

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
roteamento interno. Nenhuma chamada paga foi feita durante a implementação.
