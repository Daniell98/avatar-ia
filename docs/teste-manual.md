# Roteiro manual no Windows

Registre data, modelos, modalidade, voz e resultado como **verificado**,
**não verificado** ou **pendente de configuração**. Não registre a chave.

## Fluxo

1. Abra `uv run companhia`. Confirme Foco e nenhuma chamada nova no diagnóstico.
2. Configure a chave localmente e os modelos na interface, sem alterar o código.
3. Atualize dispositivos, salve e teste microfone e tom de saída. Confirme audição.
4. Envie uma pergunta curta. Confira primeiro texto progressivo, conclusão e
   modelo retornado. Uma resposta HTTP válida não basta para avaliar qualidade.
5. Escolha Windows explicitamente para testar a alternativa local. Para validar
   voz API, confirme primeiro o contrato em `docs/contratos.md` e selecione API.
6. Grave uma fala curta usando Falar/Parar. Confira transcrição, texto associado
   à fala, pronúncia pt-BR e medições. Repita por vários turnos.
7. Durante resposta/fala, aperte Falar e faça nova pergunta. O áudio antigo deve
   parar; nenhum resultado atrasado deve aparecer ou tocar.
8. Envie `lembra que prefiro chá`. Feche/reabra e pergunte sobre sua preferência.
9. Corrija pela aba Memórias ou `corrige memória #ID: prefiro café`. Confira uma
   única versão ativa, reinicie e verifique. Exclua e confira ausência posterior.
10. Ative Companhia, tire foco dos editores e aguarde pelo menos 90 s. A iniciativa
    deve ser contextual, curta e pode optar pelo silêncio. Ignore uma iniciativa:
    não pode haver outra antes de você retomar. Foco deve impedir novas iniciativas.
11. Ative Pausado: entrada de voz e novas chamadas devem ficar suspensas.
12. Teste chave inválida, dispositivo indisponível e timeout. A janela continua
    utilizável, e o erro aparece sem segredos. Não provoque erros pagos em série.

## Personalidade (avaliação humana, provedor real)

| Cenário | Entrada sugerida | Avaliar |
|---|---|---|
| Saudação casual | Oi, como vai? | Informal, breve, sem bordão de atendimento |
| Brincadeira recíproca | Fiz uma escolha horrível no jogo | Provocação leve e contextual |
| Opinião divergente | Você concorda que todo jogo difícil é ruim? | Opinião fundamentada, sem concordância automática |
| Dia difícil | Hoje foi um dia péssimo | Atenção, sem piada obrigatória |
| Conversa técnica | Explica o que é SQLite em duas frases | Resposta correta, clara e curta |
| Correção de memória | corrige memória #ID: prefiro chá | Confirmação e consulta coerentes após reiniciar |
| Falta de assunto | Estou sem assunto | Sem cobrar atenção nem inferir atividade |
| Resposta curta | Responde em uma frase | Respeitar a extensão pedida |
| Ajuste de tom | Pega mais leve na zoeira | Redução imediata, preservada em sessões posteriores |

Avalie o conjunto, sem exigir os quatro traços em cada fala. Ajuste as quatro
intensidades e o arquivo de personalidade sem mudar código. Respostas simuladas
não medem personalidade.
