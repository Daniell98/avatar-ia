# Próximas etapas

- **Entrada de voz com áudio real:** microfone -> `openai/whisper-1` nunca foi
  exercitado de ponta a ponta. Usa o endpoint `transcriptions`, não `chat`, então
  a indisponibilidade do gpt-audio-mini não diz nada sobre ela.
- **Revogar a chave da ElevenLabs** usada no desenvolvimento: ficou exposta em
  texto na sessão.
- **Fluidez:** reprodução por segmentos de frase para reduzir o tempo até a
  primeira fala. Hoje a síntese inteira precede a reprodução. Só vale com
  medição comparativa; preserve ordem, interrupção e descarte de áudio antigo.
- Avaliar a personalidade ao longo de vários turnos, com voz ativa. A audição
  confirmou pronúncia e naturalidade da voz, não o equilíbrio de humor,
  acolhimento, repetição e excesso de perguntas.
- Evoluir a barreira conservadora para seleção por dependências e revisões;
  proposta em `memoria-revisoes.md`, com fallback para mensagens legadas.
- Escolher nome definitivo e ajustar os quatro traços da persona com feedback.
- Reavaliar provedor de voz **se** a rota de áudio da Roteia voltar a funcionar.
  A decisão atual é por capacidade, não por preço; ver `voz-elevenlabs.md`.
- Detecção simples de fim de fala, após validar o fluxo por botão.
- Empacotar instalador Windows e melhorar acessibilidade/atalhos.
- Avatar Live2D/3D ligado aos estados e áudio.
- Captura de tela com ativação explícita e indicações claras de uso.
- Ações em outros aplicativos com permissões e resultados verificáveis.
- Integrações para jogos, com limites próprios e testes antes de executar ações.

Avatar, tela, ações e jogos não são dependências do MVP atual.
