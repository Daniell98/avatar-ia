# Validação da entrega

Ambiente: Windows nativo, Python 3.12.13, dependências em `uv.lock`.
Data: 06/10/2026. Não foram feitas chamadas autenticadas à Roteia.

Resultado final: **27 testes passaram**, Ruff sem erros, lockfile conferido.
Wheel e distribuição fonte foram gerados com os recursos de personalidade/voz
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
| Erros HTTP e ausência de retry | Verificado com HTTP simulado | 401/402/429/500, fluxo truncado e multipart |
| Bloqueio de API paga nos testes | Verificado | Fixture impede transporte HTTP real |
| Adaptador de voz com contrato externo | Verificado com HTTP simulado | WAV base64 e texto associado; contrato ausente e transcrição ausente bloqueados |
| Contexto permanece limitado, memórias são dados | Verificado | Teste com histórico extenso e conteúdo adversarial |
| Rejeição de silêncio e erro de dispositivo | Verificado com áudio simulado | Fluxo de captura e fechamento de stream |
| Enumeração dos dispositivos Windows | Verificado | Diagnóstico local: 25 entradas/saídas enumeradas |
| Geração de WAV pela voz local pt-BR do Windows | Verificado | `WindowsSpeech` gerou WAV válido de 6,62 s; sem reprodução |
| Captura de fala física, audição e atalho com janela ativa | Não verificado | Exige operador no roteiro manual |
| Integração autenticada de chat/transcrição | Pendente de teste escolhido pelo operador | Comandos `diagnostico --real` no README |
| Síntese de voz pela Roteia | Pendente de contrato/configuração | Schema/voz/retorno não confirmados publicamente |
| Conversa completa de voz API e naturalidade | Não verificado | Necessita áudio real e provedores configurados |

As latências exibidas em uso são medições do turno, não estimativas de desempenho
geral. Testes simulados não comprovam latência, qualidade de voz ou personalidade.

Execute novamente `uv run pytest -q` e `uv run ruff check src tests` após mudanças.
Use `docs/teste-manual.md` para fechar a validação de produto.

A captura `interface.png` mostra a interface no modo explicitamente simulado.
O ambiente offscreen do Qt precisou carregar fontes Windows para essa captura;
a plataforma nativa enumerou 199 famílias normalmente. O auxiliar de síntese usa
`-ExecutionPolicy Bypass` somente no processo filho que executa o script local
do projeto, sem alterar a política global do Windows.
