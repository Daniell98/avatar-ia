# Companhia

Assistente desktop para Windows, em português brasileiro, criada a partir de
`prompt_codex_assistente_voz_mvp.md`. Chat com streaming pela Roteia, memória local
SQLite, gravação por turnos, transcrição por API, cancelamento e modo Companhia.

**Estado da entrega:** núcleo e interface verificados com testes simulados.
Chat e transcrição têm adaptadores HTTP reais, mas ainda não houve chamada
autenticada de validação. A saída de voz da Roteia está **pendente de confirmação
do contrato**: o catálogo informa a modalidade, mas não publica o schema completo
consultado. A voz do Windows é uma alternativa local explícita. A experiência
completa de voz por API ainda não está validada. Veja [contratos](docs/contratos.md)
e [validação](docs/validacao.md).

![Interface em modo simulado](docs/interface.png)

## Instalar e iniciar no PowerShell

O ambiente deste projeto já tem `uv`, Python 3.12.13 e as dependências instaladas.
Para reproduzir a instalação, use o `uv` da [documentação oficial](https://docs.astral.sh/uv/getting-started/installation/):

```powershell
Set-Location C:\Users\danie\avatar-ia
uv python install 3.12
uv sync --locked
uv run companhia
```

O aplicativo começa em **Foco**, com voz desligada. Não faz chamadas de API ao
abrir. Para testar sem API, independentemente da chave configurada:

```powershell
uv run companhia --mock
```

As respostas desse modo são marcadas **SIMULADO**, não avaliam personalidade nem
qualidade dos modelos. Se ativar voz API simulada, o som é um tom de teste, não fala.

Sem `uv` após a instalação, o executável também pode ser iniciado diretamente:

```powershell
.\.venv\Scripts\companhia.exe
```

## Chave e configuração

A chave solicitada foi salva no `.env` da raiz, ignorado pelo Git. Não copie o
arquivo para documentação ou commits. Em uma nova instalação, crie-o somente se
ainda não existir:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
notepad .env
```

Preencha `ROTEIA_API_KEY` localmente. A prioridade é: variável de ambiente,
`.env` na raiz do projeto, chave salva pela interface em `api-key.txt` na pasta
de dados. A chave salva pela interface só é usada se ambiente/`.env` estiverem
vazios. O `.env` é encontrado pelo caminho do projeto, não pelo diretório atual
do terminal. O empacotamento em executável fica no backlog.

Na aba **Configurações**, escolha modelos, nome, personalidade, timeout,
microfone/saída, taxa, duração máxima, atalho e limites. Salve antes de testar;
interrompa um turno em andamento antes de salvar. O padrão de chat é
`deepseek/deepseek-v4-flash`, selecionado pela disponibilidade e streaming
declarados, como ponto inicial para diálogo curto, sem alegação de melhor qualidade.

Dados ficam em `%LOCALAPPDATA%\Companhia`, neste ambiente:
`C:\Users\danie\AppData\Local\Companhia`. Contém `config.json`,
`personality.md`, `companhia.sqlite3` e, se informada pela GUI, `api-key.txt`.
Personalidade pode ser alterada diretamente no arquivo, sem mudar código.
O modelo lê esse arquivo a cada turno. O SQLite contém conteúdo pessoal em texto
local; não há banco remoto, embeddings, captura de tela nem processamento na GPU.

Para isolar uma instalação de teste, defina um caminho absoluto antes de iniciar:

```powershell
$env:COMPANHIA_DATA_DIR = 'C:\Users\danie\AppData\Local\Companhia-Teste'
uv run companhia --mock
```

## Conversar e usar voz

1. Envie texto para conversar, mesmo sem áudio disponível.
2. Em Configurações, atualize dispositivos e selecione microfone e saída. Evite
   **Mixagem estéreo** como entrada. Teste captura e saída localmente; são testes
   sem API. O teste de microfone captura três segundos e descarta a gravação.
3. Para experimentar voz local, selecione **Windows · local / alternativa** e
   salve. É necessária uma voz pt-BR instalada compatível com `System.Speech`.
   Nome vazio tenta selecionar pt-BR; pode informar um nome exato instalado.
4. Clique **Falar** ou `Ctrl+Space` com a janela ativa. Clique outra vez para
   parar; a gravação também termina no limite configurado. A transcrição aparece
   como mensagem, seguida da resposta e, se habilitada, da voz.
5. Use **Interromper**/`Esc`, ou **Falar** durante uma resposta, para cancelá-la.
   Não há interrupção automática pela voz. O microfone não fica aberto durante
   a reprodução. Uma requisição já aceita ainda pode gerar cobrança.

A gravação é WAV PCM16 mono, com 16 kHz por padrão. Captura vazia, muito curta
ou com RMS abaixo de 0,002 é rejeitada antes do upload. É uma proteção simples,
não detecção automática de fala; fale perto do microfone ou ajuste o dispositivo.
Áudio fica em memória e é descartado. A alternativa do Windows usa arquivos
temporários removidos ao concluir/cancelar. Não há histórico de áudio bruto.

**Voz por API:** escolha a opção somente após confirmar o contrato descrito em
[docs/contratos.md](docs/contratos.md). O aplicativo não supõe `/audio/speech`
nem envia parâmetros de áudio por analogia com outro serviço. Sem contrato, há
aviso e a resposta textual é mantida; não ocorre troca automática para voz local.
Quando a rota retorna texto e fala juntos, o texto associado à fala substitui a
prévia no chat e no banco, preservando a correspondência.

## Memórias

Registro explícito, sem extração automática de fatos:

```text
lembra que prefiro respostas curtas
corrige memória #1: prefiro respostas curtas só quando estou jogando
esquece memória #2
```

Consulte os IDs, conteúdo, origem e data na aba **Memórias**. Também é possível
adicionar, corrigir e excluir pela interface. Busca textual ambígua para esquecer
não exclui nada; use o ID.

Correção desativa a versão anterior e cria uma ativa. Exclusão remove o registro
selecionado. Ambas invalidam o resumo e estabelecem uma barreira: mensagens
anteriores à alteração permanecem consultáveis, mas não são reenviadas ao modelo.
Não existe extração automática que possa recriar memórias a partir delas.
**Apagar histórico** remove mensagens e resumo, mantendo memórias duradouras e
seus registros de origem. Se a mensagem original for apagada, o ID de origem
continua sendo uma referência histórica, não uma mensagem ainda consultável.

O contexto usa personalidade, até cinco memórias, trecho extrativo de até 2.000
caracteres e até 12 mensagens recentes completas, com teto inicial de 18.000
caracteres. Respostas interrompidas/incompletas ficam no histórico, mas não entram
como respostas completas no contexto.

## Companhia, Foco e Pausado

**Foco** responde quando chamado. **Companhia** precisa ser ativado na janela;
espera 90 segundos após atividade, ao menos cinco minutos entre iniciativas,
no máximo quatro solicitações por hora e uma sem resposta. A decisão de ficar
em silêncio também ocupa essa tentativa para evitar sondagens pagas repetidas.
Só funciona com assunto registrado, sem gravação, geração, reprodução ou edição.
A prioridade é sempre do usuário, com revalidação antes de publicar/falar.

**Pausado** interrompe o turno e impede novas gravações e chamadas. Ao reabrir,
o aplicativo volta a Foco. O comando textual `fica em silêncio` muda para Foco
localmente. Proatividade funciona somente enquanto a janela estiver aberta.

## Diagnóstico e testes

Diagnóstico local, sem chamadas ao gateway:

```powershell
uv run companhia diagnostico
uv run pytest -q
uv run ruff check src tests
uv lock --check
```

Testes bloqueiam HTTP real mesmo com uma chave no `.env`.
A aba Diagnóstico mostra modelos solicitado/retornado, estado, uso informado e
tempos medidos de transcrição, primeiro texto, geração e fim da gravação até voz.
Ausência de medição significa que aquela etapa não foi medida. Não há promessa
de latência. Erros são apresentados sem corpo bruto do provedor ou autorização.

Para realizar uma chamada real curta, escolha a amostra explicitamente. Pode
gerar cobrança. Estes comandos **não foram executados automaticamente**:

```powershell
uv run companhia diagnostico --real --text 'Responda em uma frase: olá, Companhia.'
uv run companhia diagnostico --real --wav 'C:\caminho\amostra-curta.wav'
# Apenas após confirmar e configurar o contrato de voz API:
uv run companhia diagnostico --real --speech-text 'Olá, Daniel.'
```

O diagnóstico de chat desliga voz para consumir só uma chamada. A amostra WAV
deve conter fala, ter até 30 segundos e até 25 MB. Na interface, o teste real de
texto usa a configuração de voz selecionada e poderá gerar também síntese.

Os limites diários (dia UTC) contam tentativas de API, inclusive erros e
cancelamentos, e tokens informados. Voz Windows e modo simulado não consomem a
cota do gateway. O limite de tokens bloqueia **a próxima chamada** após atingir
o valor; não limita tokens de uma resposta em andamento, nem mede uso ausente.
Não há teto financeiro exato ou recarga automática. Custo desconhecido aparece
como desconhecido, nunca zero. Não há retry automático nem troca de modelo.

## Problemas comuns

- **Python abre a Microsoft Store:** use `uv run` ou o executável da `.venv`.
- **Microfone falha:** Windows → Privacidade e segurança → Microfone → permita
  aplicativos desktop; escolha outro dispositivo/taxa e salve. A janela e chat
  textual continuam disponíveis.
- **Não há voz:** a opção inicial é Desligada. Para a alternativa Windows,
  instale uma voz pt-BR compatível com a síntese desktop; vozes OneCore nem
  sempre aparecem em `System.Speech`. Não há fallback silencioso.
- **401 / 402 / 429:** revise chave, saldo ou limite no painel da Roteia.
  O app não faz novas tentativas por conta própria.
- **Modelo incompatível/sem streaming:** copie um ID atual do catálogo e confira
  capacidades. Nenhum modelo é substituído automaticamente.
- **Configuração inválida:** a janela carrega padrões e avisa; o arquivo é
  preservado até você salvar. Falha de rede não impede abertura.

Siga o [roteiro manual](docs/teste-manual.md) antes de considerar a experiência de
voz validada. Próximas etapas estão no [backlog](docs/backlog.md).
