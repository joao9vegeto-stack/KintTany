# Arquitetura atual

- `AppStore`: coordenador global, uma atividade por vez e STOP transacional.
- `RealtimeSocket`: transporte WebSocket nativo, isolado por actor.
- `RealtimeProtocol`: codificação/decodificação dos eventos comprovados na v5.2.
- `SessionManager`/`KeychainStore`: ponto único para sessão.
- `RootView`: dashboard SwiftUI.

As engines específicas devem consumir snapshots e confirmações do protocolo; nenhuma recompensa é contabilizada por ação apenas enviada.
