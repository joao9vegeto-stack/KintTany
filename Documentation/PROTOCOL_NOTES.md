# Protocolo portado da v5.2

Esta versão não inventa endpoints ou mensagens. A camada `RealtimeProtocol` usa somente os eventos encontrados na implementação fornecida: `q_ping`, `queue_ready`, `pos`, `region_ack`, `snap`, `res_evt`, `res_snap`, `harv`, `harv_hit`, `wm_ev`, `am_ev` e `wild_mb_ack`.

O transporte ainda deve completar a segunda etapa queue → presence usando o `connect-token` observado em `lib/presenceWs.js`; essa etapa está isolada em `RealtimeSocket` para não espalhar protocolo pela UI.
