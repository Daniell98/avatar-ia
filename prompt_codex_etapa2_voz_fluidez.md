# Companhia — etapa 2: voz real e conversa mais natural

Você está trabalhando no projeto Companhia, em Windows nativo, no repositório https://github.com/Daniell98/avatar-ia. O caminho informado pelo usuário é C:\Users\danie\avatar-ia; confirme o diretório atual antes de agir.

Continue a implementação existente. Leia as instruções aplicáveis, examine o estado do Git e preserve alterações locais. A revisão abaixo se refere ao commit bd7e700dab551b15c49bf90fecd8b4e5c6e385e0, da branch main, em 06/10/2026. Se houver mudanças posteriores, verifique quais problemas ainda existem; não reverta o projeto para esse commit.

## Objetivo da entrega

Quero conversar por voz com uma personagem em português brasileiro, com personalidade equilibrada entre espontaneidade, carinho, opiniões próprias e provocações leves, memória persistente e proatividade moderada. Primeiro precisamos tornar essa experiência confiável e natural.

A aplicação atual usa Python 3.12, PySide6, SQLite e adaptadores HTTP da Roteia. A execução é Windows nativo. Já existe uma interface funcionando. A chave deve continuar apenas na configuração local; nunca imprima seu valor.

Leia README.md, docs/contratos.md, docs/validacao.md e os módulos de conversa, personalidade, memória, proatividade, tarefas, áudio, provedores e interface. Implemente as correções aplicáveis e valide o resultado, além de explicar as decisões.

## Evidência da revisão anterior

Na cópia do commit revisado, em Linux com Python 3.12.14:

- Passaram 18 testes existentes: test_memory.py, test_proactivity.py, test_providers.py e test_tasks.py.
- Ruff passou.
- A suíte completa não pôde ser coletada porque o ambiente não tinha a biblioteca nativa PortAudio. Isso é uma limitação do ambiente de revisão, não uma falha demonstrada do aplicativo no Windows.
- Reproduções adicionais confirmaram perda da pergunta atual em contexto cheio, reutilização de IDs e descarte de contexto após correção.
- Reproduções de Conversation e da interface confirmaram os problemas de silêncio proativo, foco no editor e ajuste indevido de tom. Nesses casos, apenas o módulo do driver de áudio ausente foi substituído; não houve captura nem reprodução física. Modelos foram simulados e nenhuma chamada autenticada foi feita.
- A execução real da voz no PC do usuário e a qualidade subjetiva da personalidade ainda precisam ser verificadas.

Use esses resultados como ponto de partida; execute os testes no ambiente atual após suas mudanças.

## 1. Corrigir a proatividade

Arquivos principais: src/companhia/proactivity.py, tasks.py, conversation.py e ui.py.

Hoje Proactivity.started() define waiting_reply=True antes da geração. Quando o modelo retorna <SILENCIO>, Conversation.turn() termina sem desfazer esse estado. Assim, nenhuma mensagem foi enviada, mas o agendador passa a esperar uma resposta do usuário indefinidamente.

Separe tentativa de iniciativa de iniciativa efetivamente entregue:

- Tentativas que chegam à API devem continuar contando para intervalo e limite por hora.
- <SILENCIO>, falha e cancelamento antes da publicação não devem criar uma espera por resposta.
- Marque a espera quando uma iniciativa realmente for publicada. Uma falha de áudio após a publicação do texto não transforma a mensagem em silêncio.
- Preserve o limite de uma iniciativa entregue sem resposta, a prioridade do usuário e o descarte de resultados de gerações antigas.
- Faça as transições no componente/thread apropriado, sem liberar iniciativas concorrentes por acidente.

Outro problema: MainWindow.update_editing() considera qualquer foco em QLineEdit ou QPlainTextEdit como edição contínua. Um campo vazio com foco pode bloquear iniciativas indefinidamente, mesmo sem digitação.

Use sinais de digitação/atividade recentes e presença de rascunho para decidir quando bloquear. Preserve bloqueio durante gravação, geração, reprodução, edição de memória/configurações e diálogos relevantes. O mero foco parado em um editor vazio não deve impedir companhia para sempre.

Teste silêncio, erro, cancelamento, publicação efetiva, cooldown, limite por hora, rascunho, editor vazio parado e prioridade de uma mensagem do usuário.

## 2. Corrigir o ajuste de personalidade

Arquivo principal: src/companhia/conversation.py; integração em personality.py e memória/configuração quando necessário.

A expressão atual inclui “não gostei” sem contexto. Foi reproduzido:

1. Enviar “Não gostei desse filme.”
2. O meta gentle passa a "1".
3. Enviar “Pode voltar a me zoar.”
4. gentle continua "1".

Uma opinião sobre um filme não é feedback sobre o comportamento da personagem. Reconheça pedidos dirigidos ao tom, como “menos zoeira”, “pega mais leve nas piadas” e “não gostei dessa provocação”. Evite inferir esse pedido de qualquer frase contendo “não gostei”.

Permita voltar ao tom normal por pedido explícito e pela configuração. Um teste deve verificar persistência entre sessões quando apropriado e reversibilidade. Use regras locais pequenas e claras para comandos diretos; não adicione uma chamada paga a cada mensagem apenas para classificar tom.

Depois, refine resources/personality.md sem transformar a personagem em uma sequência de bordões:

- Responder primeiro ao conteúdo da conversa.
- Alternar humor, acolhimento e opinião conforme o contexto; os quatro controles não são cotas por resposta.
- Perguntas ocasionais, sem terminar todas as falas com uma pergunta.
- Discordância com motivo e zoeira proporcional à intimidade demonstrada.
- Reduzir brincadeiras em assuntos sérios e diante de um pedido real.
- Memórias e exemplos fictícios não devem virar fatos sobre Daniel.
- Preferências da personagem devem ser apresentadas como caracterização, sem inventar experiências vividas.
- Nome e voz continuam configuráveis.

Acrescente poucos exemplos contrastantes de conversa para orientar o estilo. Cubra brincadeira, frustração, discordância e resposta prática. Não me peça um nome definitivo para conseguir concluir as correções.

Considere que o arquivo de personalidade do usuário já foi copiado para a pasta de dados: modificar apenas o recurso padrão não atualiza uma instalação existente. Preserve personalizações e ofereça uma forma clara de revisar/aplicar o novo padrão.

## 3. Garantir que a pergunta atual chegue ao modelo

Arquivo principal: src/companhia/personality.py, com ajuste no chamador se necessário.

Foi reproduzido, dentro dos limites válidos da configuração:

- Personalidade com 5.000 caracteres.
- Cinco memórias de 2.000 caracteres cada.
- Resumo de 2.000 caracteres.
- Pergunta atual com 4.000 caracteres.
- context() produziu somente sistema e dados recuperados: a pergunta atual não entrou.

Reserve espaço para a mensagem atual antes de selecionar resumo, memórias e histórico. Priorize a pergunta e a coerência dos turnos recentes; reduza os dados auxiliares conforme o orçamento. Não duplique a pergunta já persistida. Trate explicitamente o pedido proativo, que é adicionado separadamente hoje.

Garanta o limite total da configuração, a presença da mensagem atual e a exclusão de respostas incompletas. Adicione teste com a configuração acima e com mensagens curtas normais.

## 4. Preservar memória e continuidade

Arquivo principal: src/companhia/memory.py.

Há duas situações distintas:

**IDs reutilizados:** as tabelas usam INTEGER PRIMARY KEY sem política de não reutilização. Após apagar o histórico, uma nova mensagem pode receber o ID 1 enquanto uma memória antiga continua com source="message:1". Isso associa a origem histórica a uma mensagem diferente. IDs de memória apagada também podem ser reaproveitados.

Implemente IDs que não sejam reutilizados nas entidades referenciadas e uma migração segura para bancos existentes. A origem de uma mensagem removida deve continuar identificável como removida, nunca apontar silenciosamente para conteúdo novo. Preserve registros, versões e referências existentes; não recrie o banco do usuário.

**Barreira de contexto:** corrigir “prefiro chá” para “prefiro café” remove do contexto também uma conversa recente sem relação, por exemplo sobre uma história de dragões. O histórico continua no banco e na tela. É uma decisão conservadora implementada, não exclusão física dos dados, mas prejudica a continuidade.

Melhore a invalidação com proveniência/revisões e seleção de contexto quando isso permitir excluir o fato antigo sem descartar tópicos independentes. Não remova simplesmente a barreira nem use somente substituição literal de palavras: o fato antigo pode aparecer parafraseado no resumo ou nas respostas.

Se o esquema atual não permitir uma invalidação seletiva confiável nesta entrega, mantenha o comportamento conservador explicitamente documentado e apresente uma proposta técnica pequena para a migração. Conclua as outras correções sem fazer essa evolução bloquear a entrega.

Teste correção/exclusão sem reaparecimento, reinício, exclusão de histórico preservando memórias e criação de novas mensagens/memórias sem confusão de IDs.

## 5. Concluir a saída de voz pela Roteia

A saída por API ainda é um adaptador genérico ContractSpeech com template bloqueado. Isso não constitui integração final validada. WindowsSpeech é uma alternativa local explícita.

Fontes públicas consultadas em 06/10/2026:

- https://roteia.ai/docs/
- https://roteia.ai/modelos/openai/gpt-audio-mini/
- https://api.roteia.ai/catalog/models
- https://roteia.ai/guias/modelos-de-transcricao-por-api/

A página do GPT Audio Mini declara entrada/saída de áudio em chat/completions, mas o exemplo consultado só mostra uma mensagem textual. A declaração geral de compatibilidade OpenAI não comprova por si só cada campo de áudio no gateway.

Pesquise a documentação atual e examine qualquer contrato/evidência já obtido no projeto. Implemente um adaptador específico quando o contrato puder ser fundamentado; não deixe o usuário final responsável por preencher manualmente caminhos internos de JSON.

Caso seja necessário usar a documentação upstream para construir um teste de compatibilidade, trate isso como hipótese explícita até a validação no gateway. Não marque confirmed=true apenas porque uma fixture simulada passou. Nunca invente a rota /audio/speech.

Prepare um diagnóstico manual curto, invocado explicitamente, que:

- Use a chave já configurada localmente.
- Faça uma amostra por execução, com texto curto e sem retry automático.
- Valide modelo, formato, áudio decodificável e texto associado quando o contrato o fornecer.
- Registre tempos, modelo solicitado/retornado e uso quando informado, sem chave, áudio bruto ou conteúdo sensível nos logs.
- Permita ouvir e comparar a fala com o texto.

Mantenha os testes automatizados sem chamadas pagas. Não faça varredura de modelos ou tentativas autenticadas repetidas. Se a autorização existente da sessão local não abranger a amostra paga, deixe o comando pronto e peça somente essa execução concreta. Se faltar informação do provedor, descreva exatamente o campo ou exemplo faltante, em vez de apenas repetir “contrato pendente”.

A falha da voz deve preservar o texto e deixar o aplicativo utilizável. Não mude automaticamente para outro provedor ou para a voz do Windows.

## 6. Medir e melhorar a fluidez

Atualmente o código espera terminar o chat, depois espera terminar a síntese de todo o texto, e então começa a tocar. Identifique o tempo de cada etapa antes de otimizar.

Exiba tempos de transcrição, primeiro texto, geração completa, síntese e início da reprodução. Não prometa latência específica sem medição real.

Depois de estabilizar a voz, avalie reprodução por segmentos de frases ou streaming somente se o contrato suportar e os ganhos justificarem chamadas adicionais. Preserve ordem, interrupção imediata e descarte de áudio antigo. A otimização não pode duplicar texto falado nem aumentar chamadas silenciosamente.

## Critérios de conclusão

Entregue as correções implementáveis, com os testes de regressão dos comportamentos acima e documentação atualizada. Preserve a interface e a organização existente, fazendo mudanças focadas.

Execute no Windows, quando disponível:

- uv run pytest -q
- uv run ruff check src tests
- uv lock --check
- Aplicação em modo simulado para verificar interface, memória, pausa, cancelamento e proatividade.
- Diagnóstico real apenas conforme autorização e configuração disponíveis.

Separe os resultados em testes simulados, verificações reais concluídas e pendências específicas. O teste manual de produto deve incluir conversa de voz, interrupção, correção de memória e um período em modo Companhia.

Ao finalizar, explique em português o que mudou, como foi verificado, o que falta para a voz real e os comandos exatos para eu testar. Não afirme que a personalidade ficou natural apenas porque testes passaram: inclua um roteiro curto para eu dar feedback sobre humor, acolhimento, repetição e tempo de resposta.

