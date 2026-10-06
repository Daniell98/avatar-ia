# Entrega da etapa 2 — 06/10/2026

Base preservada: commit `bd7e700`; Windows nativo, Python 3.12.13.
O prompt de etapa 2 foi preservado. Nenhuma chave aparece no código/documentação.

- Tentativa proativa conta para cooldown e máximo/hora ao despachar o chat;
  só a publicação de texto marca espera por resposta. Silêncio/erro/cancelamento
  anterior à publicação não deixam espera indefinida. Prioridade e gerações continuam.
- Edição usa rascunho/atividade dos últimos cinco segundos. Foco vazio parado é
  permitido; configurações, memórias, diálogos e tarefas em curso mantêm proteção.
- Pedidos locais de tom são específicos, persistentes e reversíveis, sem chamadas
  para classificação. Opiniões sobre filmes não ativam suavização. Configuração
  e pedido explícito restauram normalidade sem alterar as quatro intensidades.
- Pergunta atual reservada antes de dados auxiliares, sem duplicação. Contexto
  fica limitado e seleciona pares de turnos, excluindo respostas incompletas.
- Migração segura para IDs não reutilizados, backup v1 e identificação de origem
  removida. A barreira antiga fica conservadora; proposta de evolução separada.
- Novo padrão de personalidade com exemplos contrastantes; instalações existentes
  e rascunhos são preservados. Aplicação do novo padrão é explícita na interface.
- Voz específica Roteia usa uma hipótese upstream documentada, com uma amostra
  invocada manualmente; valida modelo/WAV/transcript e guarda só evidência técnica.
  Não há JSON interno para o usuário preencher nem retry/fallback.
- Métricas incluem síntese e início da reprodução. Não se alterou número de
  chamadas para otimizar latência sem dados reais.

Testes automatizados simulam modelos, HTTP, áudio e GUI; o fixture proíbe rede
real com a chave existente. Eles não certificam personalidade ou voz natural.
O diagnóstico pago requer invocação explícita e uma amostra curta autorizada.

Foi autorizada e executada uma única amostra com `openai/gpt-audio-mini`, alloy
e WAV, sem reprodução. Resultado: HTTP 400 em 4,235 s. A confirmação técnica não
foi criada, e não houve nova tentativa. Falta exemplo/contrato compatível do
gateway para os campos de saída de áudio; detalhes em `validacao.md`.

Para feedback, faça uma brincadeira, relate frustração, peça uma opinião divergente
e uma resposta prática. Avalie humor adequado, acolhimento sem exagero, repetição,
perguntas em excesso e tempo até ouvir. Alterne os controles e compare vários
turnos; uma resposta isolada não determina o equilíbrio da personalidade.
