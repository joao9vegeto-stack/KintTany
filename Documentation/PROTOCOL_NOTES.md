# Protocolo observado e portado — v2.0

Fonte de verdade: Kintarabot v5.2 e logs reais. Não substituir confirmação do servidor por timer ou contador local.

## Autenticação/sessão

A sessão autenticada é persistida no Keychain. Valores sensíveis nunca devem ser escritos integralmente no log.

## Servidor/queue/presence

1. consultar `/api/servers` para ranquear NA (`s2...s7`);
2. gate-check do shard;
3. `GET /api/lobby/connect-token?shard=...&purpose=queue`;
4. WebSocket queue;
5. enviar `q_ping` como frame texto e manter keepalive de 5 s;
6. aguardar `queue_ready`;
7. fechar queue;
8. novo connect-token com `purpose=presence`;
9. abrir Presence;
10. enviar posição/bootstrap inicial da atividade.

`queue_evicted` é erro explícito. O encerramento inesperado do receive loop da Presence é tratado como perda fatal de realtime e interrompe a atividade.

## Movimento

Frames `pos` usam `mov=true` durante deslocamento e `mov=false` no final. A engine também atualiza sua posição a partir de snapshots autoritativos do próprio jogador.

## Gathering

Wire kinds:

- Tree: `k=tree`, `hasCoal=false`;
- Stone: `k=rock`, `hasCoal=false`;
- Coal: `k=rock`, `hasCoal=true`.

Sequência observada: posição/ação → `harv_hit` → `action_proof`/`res_evt` → wear fresco. Próximo hit só é considerado confirmado quando proof/wear autoritativos avançam. Conclusão: `h >= hm`.

## Fishing

Eventos principais: `fish_spots`, `fish_spot_moved`, `fish_bite` e `pos` com `act=fish`, `eq=tool_fishing_rod`, `fc`, `fr`, `fph`.

Fases: `0 → bite → 1 → 2`, depois confirmação HTTP da implementação de referência. O heartbeat mantém a ação de pesca ativa durante o cast; um `pos` limpo nessa janela pode cancelar o cast.

## Combat

Chicken:

- evento enviado: `am_ev`, `a=hit`;
- hit só é confirmado pelo eco autoritativo associado ao próprio player/alvo;
- kill só é aceito após hit confirmado + morte/desaparecimento autoritativo.

Zombie/Dragon:

- evento enviado: `wm_ev`, `a=hit`;
- `zm=1` corresponde ao kill de Zombie e `dr=1` ao kill de Dragon no fluxo observado;
- região Wild usa `wblk` conhecido da baseline.

## Logging/sanitização

`[IN ...]`/`[OUT ...]` brutos não aparecem no log de usuário. Mantêm-se apenas etapas úteis de conexão/autenticação/servidor/erros e eventos funcionais do bot. Tokens, cookies, private key e action proofs são ocultados.
