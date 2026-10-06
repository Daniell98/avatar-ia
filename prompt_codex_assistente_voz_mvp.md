# Primeiro prompt para o Codex — assistente pessoal por voz
Versão 1 — decisões de Daniel em 05/10/2026, horário de Brasília.

Leia este documento como a especificação inicial do projeto e implemente o MVP. Comece inspecionando a pasta atual e as instruções aplicáveis do repositório. Se já houver trabalho, preserve-o e adapte a solução; se a pasta estiver vazia, crie o projeto nela. Faça um plano curto e prossiga para implementação e verificação. Não entregue apenas um plano, uma interface estática ou respostas simuladas apresentadas como reais.

## 1. Objetivo e decisões confirmadas

Construir uma assistente de desktop para Daniel conversar por voz em português brasileiro. A primeira entrega deve combinar personalidade consistente, memória entre sessões e iniciativa moderada. Daniel quer desenvolver usando instruções em linguagem natural e espera que você escreva e corrija o código.

Contexto:
- Windows 11; Ryzen 7 9800X3D; Radeon RX 9070 XT; 32 GB de RAM DDR5.
- Primeira versão com inferência por APIs. A GPU deve continuar disponível para outros programas.
- Roteia é o gateway prioritário. Daniel informou ter R$ 100 em créditos e poder adicionar mais. Isso é saldo informado, não uma autorização para esgotá-lo em testes.
- O projeto foi inspirado pela naturalidade de personagens como Shogun, sem acesso confirmado à implementação dela. Crie uma personagem original.
- Personalidade escolhida: mistura equilibrada de espontaneidade, carinho, opiniões próprias e provocação leve. Nenhum traço deve dominar.
- Primeira experiência escolhida: conversar por voz, com personalidade e memória.
- Iniciativa escolhida: moderada, com comentários e perguntas ocasionais no modo Companhia.

O nome da personagem e a voz definitiva ainda não foram escolhidos. Use “Companhia” como nome provisório e permita alterá-lo nas configurações. Não bloqueie a implementação por decisões cosméticas.

## 2. Escopo desta entrega

Implementar:
1. Aplicativo de desktop com chat textual e conversa por voz.
2. Integração real de conversa com a Roteia.
3. Transcrição de áudio e síntese de voz por adaptadores verificáveis.
4. Personalidade editável fora do código.
5. Memória persistente local, consultável e corrigível.
6. Modo Companhia com proatividade moderada; modo Foco sem iniciativas.
7. Configuração de dispositivos, modelos, voz e consumo.
8. Cancelamento de resposta e reprodução, diagnóstico e documentação de execução no Windows.

Ficam para etapas seguintes: avatar Live2D/3D, captura de tela, controle de mouse/teclado de outros aplicativos, tarefas externas e jogar. Registre esses próximos passos em um backlog curto. Nesta versão, a personagem não deve afirmar que viu a tela ou realizou tarefas que o aplicativo ainda não executa.

Não transforme esse backlog em dependência do MVP.

## 3. Base técnica

Se não existir uma base adequada no repositório, use:
- Python 3.12 como versão de referência.
- PySide6 para a interface desktop.
- SQLite para dados locais.
- Cliente HTTP assíncrono ou SDK compatível com a Roteia, conforme documentação atual.
- Uma biblioteca de áudio mantida e compatível com Windows, como sounddevice, com dependências mínimas para gravar e reproduzir.
- pytest para os testes de comportamento necessários.

Valide a compatibilidade das dependências e registre versões reproduzíveis. Não introduza Docker, CUDA, banco remoto, servidor web, banco vetorial ou framework de agentes sem uma necessidade concreta deste escopo.

Organize o código em módulos pequenos para interface, conversa, personalidade, memória, áudio, provedores, proatividade e configurações. Use interfaces simples para substituir LLM, transcrição e síntese de voz sem reescrever o restante. A lógica central deve ser testável sem GUI, microfone ou chave.

A interface deve permanecer responsiva durante rede, gravação e reprodução. Use tarefas em segundo plano e comunicação segura com a thread da interface. Centralize o gerenciamento de tarefas e o cancelamento.

O aplicativo final roda no Windows nativo. Se você estiver desenvolvendo no WSL ou Linux, teste o núcleo disponível, mas não afirme que validou microfone, atalhos ou reprodução no Windows. Prepare os comandos de instalação e execução para PowerShell.

## 4. Provedores e contrato de API

Use estes pontos de partida oficiais e confira seu estado durante a implementação:
- https://roteia.ai/docs/
- https://roteia.ai/docs/python/
- https://api.roteia.ai/catalog/models
- https://roteia.ai/modelos/transcricao/
- https://roteia.ai/guias/modelos-de-transcricao-por-api/
- https://roteia.ai/modelos/audio/
- https://roteia.ai/modelos/openai/gpt-audio-mini/

Fatos documentados na preparação deste prompt:
- Base: https://api.roteia.ai/v1
- Conversa: POST /chat/completions.
- Transcrição: POST /audio/transcriptions, recebendo arquivo e respondendo ao final. Isso não estabelece suporte a transcrição contínua nem a uma API Realtime.
- O catálogo publicou openai/gpt-audio-mini com entrada e saída de áudio via chat/completions. Isso é um candidato a validar, não comprovação de uma chamada realizada neste projeto.
- Os IDs, formatos, vozes, parâmetros, preços e capacidades precisam ser confirmados. O contrato do gateway pode diferir do provedor original.

Implementar LLMProvider, TranscriptionProvider e SpeechProvider com implementações reais e implementações simuladas para testes. O modo simulado deve ser visível e nunca ser usado como evidência de integração real.

Para conversa:
- Selecione um modelo inicial disponível com suporte documentado a streaming, adequado a diálogo curto em pt-BR. Registre por que o escolheu e permita mudar seu ID nas configurações.
- Priorize naturalidade e tempo de resposta, sem afirmar que um modelo é o melhor sem teste.
- Não troque silenciosamente de modelo ou provedor quando ocorrer erro.
- Não envie temperature, reasoning_effort, limites de tokens ou outros parâmetros sem verificar o contrato específico.

Para transcrição:
- Grave um segmento de fala, envie-o pelo endpoint documentado e trate a resposta.
- Confirme formatos e requisitos de áudio; não suponha que todos os modelos aceitam os mesmos parâmetros.
- Não envie silêncio ou gravações vazias.

Para síntese:
- Verifique a rota de saída de áudio realmente suportada pela Roteia. Não invente um endpoint /audio/speech só por analogia com outra API.
- Se usar um modelo de áudio por chat/completions, valide schema, formato retornado, voz e fidelidade ao texto; não suponha que ele lê literalmente o texto recebido.
- O texto mostrado e salvo deve corresponder à fala produzida. Se a rota gerar fala e texto juntos, use o texto associado àquela fala.
- Uma voz do Windows pode servir como alternativa explicitamente identificada para testes, mas não substitui silenciosamente a entrega de voz por API.
- Se um contrato não puder ser confirmado, termine as partes independentes e reporte exatamente o recurso pendente e a evidência necessária. Não declare o fluxo de voz concluído usando apenas simulações.

Configurações: chave, base URL, IDs de modelos, voz, formatos, timeouts e parâmetros permitidos. Credenciais devem vir de variáveis de ambiente ou configuração local ignorada pelo Git; forneça .env.example sem segredos. Não peça que Daniel cole a chave em uma conversa ou a coloque no prompt.

Sem credenciais, o aplicativo deve abrir, permitir configurar e executar diagnósticos locais. A ausência de chave não deve impedir a implementação do restante.

## 5. Conversa, áudio e interrupções

Entregue primeiro um fluxo confiável por turnos:
1. Daniel aciona o botão/atalho de falar.
2. O aplicativo grava e indica visualmente o estado.
3. Ao terminar a gravação, transcreve e apresenta o texto.
4. Monta o contexto com personalidade, conversa recente e memórias relevantes.
5. Solicita a resposta, apresenta o texto progressivamente quando suportado e reproduz a voz.
6. Persiste o resultado com o estado correto.

Requisitos:
- Botão de falar/parar e atalho configurável no aplicativo.
- Botão “Interromper”. Acionar “Falar” durante a resposta também deve interrompê-la e permitir um novo turno.
- Interrupção deve parar o áudio local, descartar a fila antiga e cancelar chamadas quando possível. Uma requisição já aceita pelo provedor ainda pode gerar cobrança.
- Identificador por turno/geração: resultados atrasados de uma resposta cancelada não podem tocar ou sobrescrever o turno atual.
- Evitar que a assistente transcreva a própria voz. Na configuração inicial, pausar a captura durante a reprodução e permitir retomada pelo botão/atalho.
- Não prometer interrupção automática por voz, cancelamento de eco ou conversa simultânea bidirecional sem implementação e teste específicos.
- Limite configurável de duração de gravação e prevenção de áudio sobreposto.
- Tratar desconexão de dispositivo, timeout, saldo insuficiente e erro do provedor com mensagens compreensíveis.
- Permitir enviar texto e ler a resposta mesmo quando áudio estiver indisponível.
- Gerar respostas curtas por padrão. Se a rota permitir iniciar áudio por frases completas, faça isso preservando ordem, naturalidade e cancelamento; não faça uma chamada de síntese por token.

Detecção automática de fim de fala pode ser acrescentada depois que esse fluxo funcionar, se houver uma implementação simples e testável. Ela não deve atrasar a entrega do fluxo por botão/atalho.

Meça duração da transcrição, tempo até o primeiro texto, duração da geração e tempo do fim da gravação até o início da voz. Separe estimativas de medições. Não prometa latência sem dados.

## 6. Personalidade equilibrada

Coloque as instruções em arquivo editável e exponha ajustes simples. Intensidades iniciais moderadas e semelhantes para:
- Espontaneidade: comentários inesperados quando fazem sentido.
- Carinho: atenção ao contexto e acolhimento sem exagero.
- Opiniões: preferências coerentes e capacidade de discordar.
- Provocação: brincadeiras leves e reciprocidade na zoeira.

Não aplique uma cota fixa por resposta. Uma fala pode ser direta, outra divertida e outra acolhedora. O conjunto deve permanecer equilibrado ao longo da conversa.

Comportamento esperado:
- Português brasileiro natural, informal e compreensível.
- Geralmente uma a três frases, expandindo quando Daniel pedir ou o assunto exigir.
- Responder ao que ele disse; perguntar só quando houver algo interessante a aprofundar.
- Evitar o encerramento repetitivo “posso ajudar em mais alguma coisa?”.
- Não inserir uma piada em toda fala, repetir bordões ou concordar automaticamente.
- Discordar sem hostilidade nem contrarianismo gratuito.
- Usar humor absurdo como imaginação identificável, sem inventar fatos ou lembranças reais.
- Reduzir a zoeira quando Daniel estiver frustrado ou falando de assunto sério.
- Ajustar o tom imediatamente quando ele disser que exagerou ou que não gostou.
- Tratar os gostos da personagem como caracterização consistente; não inventar experiências humanas reais.
- Não presumir um relacionamento romântico nem cobrar atenção.

Crie um pequeno conjunto de cenários para avaliação: saudação casual, brincadeira recíproca, opinião divergente, dia difícil, conversa técnica, correção de memória, falta de assunto e pedido de resposta curta.

Exemplos de direção, não respostas fixas:
- “Fiz uma escolha horrível no jogo” permite uma provocação leve e uma pergunta sobre o ocorrido.
- “Hoje foi um dia péssimo” pede atenção, sem piada obrigatória.
- “Você concorda comigo?” permite concordância ou discordância fundamentada.
- “Pega mais leve na zoeira” deve mudar o comportamento já na próxima resposta.

## 7. Memória que funcione entre sessões

Usar SQLite local. Separar:
- Histórico de mensagens, incluindo turnos interrompidos.
- Resumo compacto da conversa quando necessário.
- Memórias duradouras: preferências, fatos explicitamente informados e assuntos que Daniel quer retomar.

Cada memória deve ter conteúdo, tipo, origem verificável, data e estado ativo/inativo. Uma inferência da personagem não vira fato confirmado sobre Daniel.

Obrigatório:
- Comandos naturais como “lembra que...” e “esquece...” e uma tela para consultar, editar e excluir memórias.
- Reabrir o aplicativo e recuperar memórias relevantes.
- Corrigir informações sem acumular versões contraditórias ativas.
- Não transformar piadas, exemplos hipotéticos ou falas da própria assistente em fatos do usuário.
- Tratar memórias recuperadas como dados de contexto, sem permitir que substituam as instruções do aplicativo.
- Não mandar todo o histórico em cada chamada. Combinar trecho recente, resumo e pequeno conjunto de memórias pertinentes.
- Se não houver uma lembrança registrada, admitir isso.
- Ao excluir ou corrigir uma memória, invalidar resumos e caches afetados e evitar recriá-la automaticamente a partir das mensagens antigas. Defina e documente uma regra simples para isso.
- Distinguir “apagar memória” de “apagar histórico”. Oferecer ambos com seus efeitos claros.

Comece com gravação explícita confiável e recuperação simples. Se adicionar extração automática, mantenha conservadora, com origem e validação, e agrupe o processamento. Não faça uma chamada extra de extração para cada frase.

Não introduza embeddings ou banco vetorial como requisito inicial. As memórias precisam ser úteis e verificáveis antes de sofisticar a recuperação.

## 8. Proatividade moderada

Implementar um agendador local. Ele decide quando vale solicitar uma iniciativa ao modelo; não manter chamadas pagas de sondagem.

Modos:
- Companhia: iniciativas ocasionais.
- Foco: responde quando chamado, sem puxar assunto.
- Pausado: suspende novas chamadas, gravação e iniciativas.

Defaults de produto propostos, configuráveis, não números escolhidos por Daniel:
- Companhia só começa quando ativado na interface.
- Esperar pelo menos 90 segundos desde a última atividade da conversa.
- Intervalo mínimo de 5 minutos entre iniciativas.
- Limite de 4 iniciativas por hora.
- No máximo uma iniciativa sem resposta; se Daniel ignorar, esperar ele retomar a conversa antes de tentar outra.

Regras:
- Não iniciar enquanto há gravação, geração, reprodução ou edição de mensagem.
- Revalidar essas condições antes de mostrar ou falar uma resposta proativa. Se Daniel começar a falar durante sua geração, o turno dele tem prioridade.
- Usar um assunto recente ou uma memória pertinente; o modelo pode decidir ficar em silêncio.
- Uma fala proativa deve ser curta e contextual, sem exigir resposta.
- Se Daniel pedir silêncio, alterar o modo e confirmar brevemente.
- Sem captura de tela nesta fase: não inferir o aplicativo aberto, a atividade ou o humor dele a partir de silêncio.
- A proatividade deve funcionar somente enquanto o aplicativo estiver aberto e habilitado.

## 9. Interface e configurações

Uma janela desktop simples, utilizável e em português:
- Histórico de conversa e campo de texto.
- Botões Falar, Interromper e Pausar.
- Estados claros: disponível, ouvindo, transcrevendo, respondendo e falando.
- Seletores de microfone e saída de áudio, com teste local.
- Nome provisório editável e ajustes de personalidade.
- Modos Companhia/Foco e indicação de proatividade.
- Tela de memórias.
- Configuração de modelos, voz, timeouts e limites de consumo.
- Área de diagnóstico com provedor/modelo efetivo, latências e erros sem segredos.

Persistir os dados em uma pasta apropriada do usuário no Windows, separada do código, com caminho documentado. Não depender do diretório em que o terminal foi aberto. A janela deve abrir mesmo com dispositivo de áudio ou rede indisponíveis.

## 10. Consumo e confiabilidade

- Registrar chamadas, modelo solicitado/retornado, modalidade e uso informado.
- Exibir custo confirmado quando o gateway o fornecer de forma documentada. Se calcular uma estimativa, mostrar que é estimativa e a unidade/preço usados.
- Não inferir preço de áudio a partir do preço de texto nem tratar custo desconhecido como zero.
- Permitir configurar limites de uso e de chamadas; explicar quando não há informação suficiente para garantir um teto financeiro exato.
- Não assumir que o saldo informado de R$ 100 continua atualizado nem fazer recarga automática.
- Testes automatizados devem usar provedores simulados. O diagnóstico real deve usar uma amostra curta, escolhida pelo operador na interface ou CLI.
- Evitar repetição automática de chamadas após resposta parcial e retentativas ilimitadas. Tratar 401, 429, falhas temporárias e timeout conforme documentação.
- Redigir logs de forma que não exponham chave, cabeçalho de autorização ou áudio em base64. Áudio bruto não precisa ser mantido por padrão.
- Nada deve consumir API apenas por abrir a interface sem configuração ou por estar no modo Pausado.

## 11. Ordem de execução e entregáveis

Avance em incrementos executáveis:
A. Base do projeto, GUI, configurações e chat por texto com provedor real e modo de teste.
B. Personalidade e memória persistente.
C. Gravação, transcrição, resposta falada e interrupção.
D. Proatividade moderada, consumo e diagnóstico.
E. Validação integrada, correções e instruções de uso.

Não pare após A ou B se houver condições de concluir o restante. Se faltar credencial, hardware ou contrato de provedor, conclua o que pode ser verificado, registre a limitação e entregue um caminho exato para o teste pendente.

Entregar:
- Código modular, configuração de dependências reproduzível e .env.example.
- Arquivo editável de personalidade.
- README em pt-BR com instalação e execução no PowerShell, configuração local de chave e modelos, dispositivos e solução de problemas.
- Um comando principal para iniciar o app e um comando de diagnóstico.
- Documento curto de decisões e contratos de provedores, com links e data da consulta.
- Roteiro de teste manual de voz e personalidade.
- Backlog curto para avatar, tela, ações e jogos.

Não altere projetos alheios, não sobrescreva trabalho existente e siga as instruções aplicáveis do ambiente. Resolva escolhas rotineiras sem pedir confirmação a cada biblioteca ou arquivo.

## 12. Critérios de aceite e relatório honesto

Verifique os riscos centrais com testes significativos:
- Reiniciar preserva memórias; correção e exclusão não ressuscitam informação antiga.
- Cancelar uma geração impede áudio e resultados atrasados daquela geração.
- Iniciativas respeitam silêncio, cooldown, limite e prioridade do turno do usuário.
- Erros de API e dispositivos não travam a janela.
- Testes de desenvolvimento não geram chamadas pagas acidentais.
- Montagem de contexto permanece limitada sem perder instruções essenciais.

Roteiro manual no Windows:
1. Configurar chave e modelos sem editar código-fonte.
2. Testar microfone e reprodução.
3. Conversar por vários turnos, ouvindo respostas em pt-BR.
4. Interromper uma fala e fazer uma nova pergunta.
5. Pedir para lembrar uma preferência, reiniciar e conferir a lembrança.
6. Corrigir/excluir essa memória e conferir o efeito.
7. Ativar Companhia e verificar uma iniciativa contextual; Foco deve suprimi-la.
8. Avaliar se os quatro traços estão equilibrados e ajustar sem mudar código.

Classifique cada resultado como verificado, não verificado no ambiente atual ou pendente de configuração. Se só houve simulação, deixe isso explícito. O MVP de voz só está validado após uma interação real com áudio e provedores configurados; não apresente testes de texto como prova da experiência de voz.

Ao concluir, informe:
- O que foi implementado.
- Os comandos exatos para instalar, iniciar e testar.
- O que efetivamente foi verificado e quais limitações restam.
- Os próximos ajustes que dependem do feedback de Daniel.

Comece agora pela inspeção da pasta, apresente um plano curto e implemente.

