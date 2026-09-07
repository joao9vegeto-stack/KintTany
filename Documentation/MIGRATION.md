# Migração v5.2 → iOS

O projeto mantém o protocolo em uma camada única. O transporte executa a sequência observada na v5.2: sessão → `connect-token` de queue → `q_ping`/`queue_ready` → `connect-token` de presence → `pos`.

As sete atividades permanecem distintas: Tree, Coal, Stone, Fishing, Chicken, Zombie e Dragon. A UI não fabrica loot, XP, hits ou kills. Esses contadores devem ser incrementados apenas depois dos eventos de confirmação equivalentes aos usados pela v5.2.

O iOS não mantém processo 24h garantido em background; a execução confiável é em foreground, conforme as restrições do sistema.
