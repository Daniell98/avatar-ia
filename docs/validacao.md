# Validação da entrega

Ambiente: Windows nativo, Python 3.12.13, dependências em `uv.lock`.
Data: 06/10/2026. Etapa 2: uma chamada autenticada de áudio, autorizada pelo usuário,
retornou HTTP 400. Sem retry ou confirmação indevida de compatibilidade.

Resultado da etapa 2: **57 testes passaram**, Ruff sem erros, lockfile conferido.
Na etapa inicial, wheel e distribuição fonte foram gerados com os recursos de personalidade/voz
presentes e sem `.env`, `api-key.txt` ou configuração local secreta.

| Resultado | Classificação | Evidência |
|---|---|---|
| Instalação/importação de PySide6, HTTP e áudio | Verificado | `uv sync`, execução e testes no Windows |
| GUI abre, conversa simulada, memória e pausa | Verificado com simulação | Teste Qt offscreen com loop de eventos e encerramento do worker |
| Reiniciar recupera memória | Verificado | SQLite reaberto no teste |
| Correção/exclusão não reenviam informação antiga | Verificado | Barreira, invalidação do resumo e ausência no contexto |
| Cancelamento bloqueia resultados atrasados e áudio | Verificado com simulação | Upstream falso que ignora cancelamento e retorna tarde |
| Resposta parcial é marcada interrompida/incompleta | Verificado com simulação | Cancelamento/erro durante streaming |
| Proatividade: ativação, edição, cooldown, limite e prioridade | Verificado com simulação | Agendador e revalidação durante geração |
| Silêncio, falha e cancelamento não esperam resposta não entregue | Verificado com simulação | Tentativa contada, espera só após publicação |
| Campo vazio parado, rascunho e digitação recente | Verificado com GUI simulada | Qt: foco vazio libera, rascunho/carência bloqueiam |
| Pedidos de tom específicos, persistentes e reversíveis | Verificado | Filme não altera tom; pedido explícito e configuração restauram normalidade |
| Pergunta atual com personalidade/memórias/resumo máximos | Verificado | Pergunta de 4.000 caracteres aparece uma vez no orçamento de 18.000 |
| Migração de banco e IDs não reutilizados | Verificado | Banco legado, referências removidas, backup e reinício |
| Aplicação do novo padrão preserva personalidade e rascunho | Verificado | Cópias locais; nenhuma substituição automática |
| Erros HTTP e ausência de retry | Verificado com HTTP simulado | 401/402/429/500, fluxo truncado e multipart |
| Bloqueio de API paga nos testes | Verificado | Fixture impede transporte HTTP real |
| Adaptador de voz com contrato externo | Verificado com HTTP simulado | WAV base64 e texto associado; contrato ausente e transcrição ausente bloqueados |
| Contexto permanece limitado, memórias são dados | Verificado | Teste com histórico extenso e conteúdo adversarial |
| Rejeição de silêncio e erro de dispositivo | Verificado com áudio simulado | Fluxo de captura e fechamento de stream |
| Enumeração dos dispositivos Windows | Verificado | Diagnóstico local: 25 entradas/saídas enumeradas |
| Geração de WAV pela voz local pt-BR do Windows | Verificado | `WindowsSpeech` gerou WAV válido de 6,62 s; sem reprodução |
| Captura de fala física, audição e atalho com janela ativa | Não verificado | Exige operador no roteiro manual |
| Integração autenticada de chat/transcrição | Pendente de teste escolhido pelo operador | Comandos `diagnostico --real` no README |
| Adaptador específico de voz Roteia | Verificado com HTTP simulado | Valida modelo, WAV, transcript e rejeita confirmações por fixture |
| Amostra real de voz Roteia | Verificada: rejeitada em toda configuração | Quatro POST autorizados; ver `docs/voz-elevenlabs.md` |
| Rota `openai/gpt-audio-mini` na Roteia | Verificada: indisponível | Falha até no exemplo mínimo da doc deles, sem stream |
| Chave e saldo da Roteia | Verificados | Controle com `deepseek/deepseek-v4-flash`: HTTP 200 |
| Síntese de voz pela ElevenLabs | **Verificada com audição** | Conversa real em pt-BR aprovada pelo usuário |
| Latência de síntese ElevenLabs | Medida | 1,23–1,61 s para 72 caracteres; 2,64 s para 186 no v4 Turbo |
| Vozes pt-BR na conta | Verificado | Quatro adicionadas pela biblioteca pública; `ptbr-Larissa-natural` em uso |
| Adaptador Roteia em streaming | Implementado, não exercitado | `stream: true` + `pcm16`; bloqueado por falta de amostra bem-sucedida |
| Conversa completa de voz API e naturalidade | Verificada por audição (saída) | ElevenLabs em pt-BR; entrada por microfone segue pendente |

As latências exibidas em uso são medições do turno, não estimativas de desempenho
geral. Testes simulados não comprovam latência, qualidade de voz ou personalidade.

Execute novamente `uv run pytest -q` e `uv run ruff check src tests` após mudanças.
Use `docs/teste-manual.md` para fechar a validação de produto.

A captura `interface.png` mostra a interface no modo explicitamente simulado.
O ambiente offscreen do Qt precisou carregar fontes Windows para essa captura;
a plataforma nativa enumerou 199 famílias normalmente. O auxiliar de síntese usa
`-ExecutionPolicy Bypass` somente no processo filho que executa o script local
do projeto, sem alterar a política global do Windows.

## Evidência real da etapa 2

Foi executado exatamente um `POST chat/completions` com o modelo
`openai/gpt-audio-mini`, `modalities: ["text", "audio"]`, voz `alloy`, formato
`wav` e uma amostra curta autorizada. A hipótese fundamentada na documentação
upstream foi recusada com HTTP 400 em **4,235 s**, medidos no ledger local.
Não houve corpo de áudio, modelo retornado ou `usage` aproveitável. O gateway
não informou `error.param` reconhecido pelo diagnóstico; não é possível atribuir
a falha a um campo específico com essa evidência. Custo continua desconhecido.

Essa amostra não rendeu o campo recusado porque o diagnóstico lia somente
`error.param` e descartava `error.message`. Isso foi corrigido: a recusa agora
registra `gateway_detail` com `code`, `type`, `param` e a mensagem do gateway,
com chaves, tokens, blocos base64 longos e o texto da amostra substituídos antes
de qualquer saída.

### Segunda amostra autorizada: motivo identificado

Com a mensagem preservada, uma segunda amostra autorizada retornou em 3,672 s:

```
http_status 400; code=upstream_error; type=upstream_error;
message=Audio output requires stream: true
```

O motivo não era um campo recusado, e sim a ausência de `stream`. O gateway
aceita saída de áudio em `chat/completions`, mas somente em streaming. Não houve
varredura de modelos: duas amostras, cada uma com uma hipótese distinta.

A documentação pública da Roteia não especifica o schema de áudio. As páginas
`/docs/`, `/docs/primeira-chamada/`, `/modelos/audio/` e a do GPT Audio Mini
declaram compatibilidade OpenAI e capacidade de áudio, mas nenhuma traz exemplo
de `modalities`, `audio` ou delta de áudio em streaming. A evidência usada é a
própria mensagem do gateway, que é mais específica que a documentação dele.

Em streaming, o formato de saída documentado upstream é apenas `pcm16`: áudio
cru, sem header, 24 kHz mono 16 bits. Por isso o adaptador pede
`audio.format: "pcm16"` no fio e monta o WAV localmente em `wav_from_pcm16`,
sem reamostrar. O restante do aplicativo continua recebendo WAV, e a reprodução
lê a taxa do próprio arquivo. O `usage` pode não vir em streaming sem
`stream_options.include_usage`; esse campo não foi adicionado para não arriscar
outra recusa na mesma amostra, então o custo pode seguir não informado.

Pendência: a terceira amostra autorizada, que confirma se o gateway entrega
`delta.audio.data` e `delta.audio.transcript` nesse formato. Até ela, não há
`audio-validation.json` e a voz por API segue bloqueada para conversa real;
a alternativa local do Windows e o texto foram preservados.

A suíte inclui abertura da GUI em modo simulado, memória, pausa, tentativa
silenciosa, cancelamento e prioridade do usuário. Não houve captura física nem
comparação auditiva ou avaliação subjetiva de personalidade nesta etapa.

## Mudança de provedor de voz

A saída de voz passou da Roteia para a ElevenLabs em 06/10/2026, após quatro
amostras autenticadas que nunca entregaram áudio. A decisão, a evidência
completa e as pendências estão em `docs/voz-elevenlabs.md`. O chat de texto e a
transcrição continuam na Roteia; o adaptador de voz dela foi preservado e segue
bloqueado por falta de amostra bem-sucedida, não por ter sido abandonado.

A audição foi confirmada pelo usuário em conversa real. Isso valida a saída de
voz e a pronúncia pt-BR, não a personalidade: naturalidade de humor, acolhimento
e repetição continuam dependendo de avaliação ao longo de vários turnos.
