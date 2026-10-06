# Memória: migração e continuidade

Etapa 2, 06/10/2026. A migração local de esquema v1 → v2 preserva as linhas e
referências existentes; não apaga nem recria o banco do usuário. Antes da primeira
migração, cria `companhia.sqlite3.before-v2.bak` na mesma pasta local. Cópia de
tabelas, troca de nomes e atualização de sequências são transacionais.

Mensagens e memórias passam a usar `INTEGER PRIMARY KEY AUTOINCREMENT`.
As sequências são inicializadas acima dos IDs presentes e dos IDs referenciados
em origens/barreiras, incluindo referências de mensagens já apagadas. Exclusão
de histórico mantém tombstones dos IDs, sem conservar o texto apagado. A interface
mostra `message:ID (mensagem removida)` para uma origem sem mensagem consultável.
Nenhuma mensagem ou memória nova reutiliza esses IDs depois da migração.

Se um ID já foi reutilizado **antes** dessa migração, não existe evidência suficiente
no esquema antigo para reconstruir a identidade correta. Não tentamos reescrever
referências nem afirmar que ambiguidades históricas foram reparadas retroativamente.

## Limitação conservadora preservada

A correção/exclusão ainda invalida o resumo e retira **todas** as mensagens
anteriores à alteração do contexto enviado ao modelo. O histórico continua
consultável, mas tópicos sem relação, como uma história de dragões, precisarão
ser retomados pelo usuário. Essa limitação foi mantida deliberadamente: não há
proveniência das memórias usadas em cada geração, e o fato corrigido pode ter
aparecido parafraseado em respostas e resumos. Retirar só palavras literais não
é suficiente para evitar reaparecimento.

## Proposta pequena de próxima migração

1. Dar uma revisão monotônica às memórias e registrar `context_revision` por turno.
2. Registrar dependências `turn_memories(turn_id, memory_id, revision)` e
   `turn_messages(turn_id, message_id)` do contexto efetivamente enviado; derivar
   dependências transitivas de respostas e resumos.
3. Registrar `summary_sources(summary_id, message_id)` para cada trecho resumido.
4. Ao corrigir/excluir, invalidar respostas/resumos dependentes, suas descendentes
   e o turno que originou o fato; preservar turnos independentes **com proveniência**.
5. Para mensagens antigas sem proveniência, continuar usando a barreira até um
   reinício explícito de contexto. Informações mencionadas espontaneamente pelo
   usuário exigem vínculo explícito ou a mesma exclusão conservadora.

Não é suficiente registrar apenas a palavra antiga ou o horário de correção.
Os testes da etapa 2 garantem ausência do fato antigo, recuperação após reinício,
IDs não reutilizados e preservação de memórias ao apagar histórico. A seleção
seletiva de tópicos independentes continua no backlog, sem bloquear as demais correções.
