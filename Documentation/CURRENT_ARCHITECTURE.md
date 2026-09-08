# Arquitetura atual — v2.0

KintTany/KINTARABOT é um aplicativo iOS nativo Swift/SwiftUI que executa a engine de automação diretamente no iPhone. A fonte funcional continua sendo o Kintarabot Node v5.2; nenhuma mensagem de protocolo deve ser inventada quando o comportamento não estiver documentado no código/log real.

## Fluxo principal

`RootView` → `AppStore` → `RealtimeSocket` → `AutomationEngine` → `RealtimeProtocol` → Kintara.

- `RootView`: dashboard, meta manual, botões ±1, estatísticas, telemetria, log completo e exportação TXT.
- `AppStore`: coordenador global; garante uma atividade por vez, STOP, encerramento automático por meta, encerramento automático em falha fatal e estado apresentado na UI.
- `RealtimeSocket`: `actor` de conexão. Consulta servidores NA, classifica disponibilidade/carga/fila, faz gate-check, abre queue, mantém `q_ping`, espera `queue_ready`, abre Presence e fecha/faz failover com segurança.
- `RealtimeProtocol`: serialização/parsing dos frames usados pela baseline observada.
- `AutomationEngine`: movimento, região, gathering, fishing e combat.
- `SessionManager`/`KeychainStore`: sessão persistida localmente.

## Seleção automática de servidor NA

Candidatos: Server 2, 3, 4, 5, 6 e 7 (`s2...s7`).

Fluxo:

1. `GET /api/servers`;
2. ordenar priorizando não-FULL, menor fila e menor carga;
3. gate-check da conta para o shard;
4. tentar o melhor disponível;
5. se falhar, tentar os demais sem exigir novo toque;
6. fallback seguro quando `/api/servers` estiver indisponível.

## Gathering

Tree, Coal e Stone usam o catálogo conhecido da baseline v5.2. Coal e Stone usam `kind=rock` no wire protocol e são separados por `hasCoal`.

Uma coleta só é sucesso quando o estado autoritativo alcança `h >= hm`. `harv_hit` por si só não conta como sucesso. Alvos que falham entram em retry cooldown local antes de serem tentados novamente.

## Fishing

- entra em World e depois The Pond;
- usa `fish_spots` do servidor como fonte autoritativa;
- não reutiliza coordenadas antigas como alvo de pesca;
- preserva ação de pesca no heartbeat;
- acompanha TTL/rotação do spot;
- registra cada tentativa como `Peixe #N`, incluindo falha/fisgada/spot/confirmação;
- conclusão somente após confirmação usada pela baseline v5.2.

## Chicken

- procura galinha autoritativa;
- move adjacente;
- equipa `wild_sword`;
- envia `am_ev` de hit;
- separa hit enviado, hit confirmado e kill confirmado;
- morte/desaparecimento só conta após hit aceito;
- v2.0 atualiza o card em tempo real com `Hit 1`, `Hit 2`, ... por alvo, em vez de permanecer visualmente em “Movendo até o alvo”.

## Zombie/Dragon

O núcleo foi portado (`wm_ev`, movimentação Wild, seleção, hit, confirmação de kill e limites de segurança de HP/Shield), mas as rotinas avançadas de sobrevivência/poções/banco/loot ainda não foram fechadas em regressão ao vivo. Não marcar 7/7 como 100% até esses testes existirem.

## Logs

A UI não espelha payloads brutos de DevTools/WebSocket. Mantém informações úteis de autenticação, conexão, servidor, HTTP de negociação, queue/presence, warnings, erros e eventos de bot. Tokens/cookies/chaves/action proofs permanecem ocultos. O log completo pode ser exportado em `.txt`.

## Distribuição

O projeto continua preparado para GitHub Actions e Codemagic em runner macOS, sem exigir Mac/Xcode local. O fluxo sem assinatura produz `.app`/IPA não assinado para sideload; assinatura deve usar Secrets.
