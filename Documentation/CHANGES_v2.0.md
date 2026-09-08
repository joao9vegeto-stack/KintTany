# KintTany / KINTARABOT v2.0

## Motivo da versão

v2.0 consolida a sequência v1.1.x depois do teste geral de Tree, Coal, Stone, Fishing e Chicken em iPhone real.

## Alterações desta entrega

- UI da Galinha mostra `Hit 1`, `Hit 2`, ... durante o combate, com estado de confirmação por golpe;
- alvo da Galinha atualiza HP exibido a partir do estado vivo disponível;
- após kill, o card muda para estado de conclusão/cooldown antes de buscar o próximo alvo;
- versão do aplicativo elevada para **2.0** (build **20**);
- badge visual `v2.0` no cabeçalho, lido de `CFBundleShortVersionString`;
- documentação consolidada para v2.0;
- adicionado `KINTARABOT_V2_KNOWLEDGE_HANDOFF.txt` para continuidade em outro chat/agente/desenvolvedor.

## Comportamentos preservados

- seleção automática de servidor NA s2-s7;
- queue keepalive e `queue_ready`;
- encerramento automático em perda fatal de Presence;
- encerramento automático ao atingir meta;
- meta digitável e ajuste ±1;
- exportação de log TXT;
- Fishing por `fish_spots` autoritativo;
- catálogo v5.2 para gathering;
- separação Coal/Stone por `hasCoal`;
- confirmação autoritativa de hit/kill da Galinha.

## Limite conhecido

Zombie/Dragon continuam fora da declaração de “100% final” até regressão ao vivo com a estratégia de poções/sobrevivência.
