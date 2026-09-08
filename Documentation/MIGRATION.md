# Migração Kintarabot v5.2 → iOS — estado v2.0

## Fechado e verificado em execução real

Com base no teste geral de 08/09/2026:

- Tree/Madeira: meta 10/10 concluída automaticamente sem falha funcional;
- Coal/Carvão: meta 10/10 concluída automaticamente; houve retries recuperáveis de proof/wear em alvos concorridos;
- Stone/Pedra: uma perda real de Presence interrompeu automaticamente a primeira tentativa; nova execução completou 10/10;
- Fishing/Pesca: 5/5, com uma tentativa sem bite registrada e recuperação automática;
- Chicken/Galinha: 10/10, com uma morte não confirmada contabilizada como falha e recuperação para o próximo alvo;
- meta manual + botões ±1;
- STOP;
- auto-stop por meta;
- auto-stop por erro fatal de realtime;
- seleção automática/failover entre servidores NA;
- log filtrado e exportação TXT.

## Ajuste v2.0

A Galinha agora atualiza o estado visível por golpe (`Hit 1`, `Hit 2`, ... e confirmação), mantendo a contagem autoritativa existente. O número reinicia por alvo e não altera o protocolo.

A versão de marketing do app e o `CFBundleShortVersionString` foram elevados para 2.0; build 20. A UI mostra o badge `v2.0` lendo o valor do bundle.

## Ainda não considerar 100% fechado

Zombie/Dragon não participaram do teste geral porque a estratégia de poções/sobrevivência ainda não foi definida/validada. O core existe, mas isso impede afirmar paridade total 7/7.

## Infraestrutura

GitHub Actions é parte obrigatória do fluxo porque o usuário não possui Mac. Cada commit deve continuar compilável remotamente com runner macOS/Xcode, XCTest, build `iphoneos` e artifact `.app`/IPA. Assinatura usa Secrets; sem assinatura, produzir build adequado a sideload posterior.
