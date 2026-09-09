# KintTany v3.0 — RC1 stabilization

Data: 2026-09-08
Bundle: 3.0 (build 30)

## Evidência real usada

O log v2.4 de 313 linhas validou: reposição automática 0/0/0 → 6/6/6, Zumbi XP +50, Dragão XP +75, strength/shield, duas metas completas com saída segura 10s→World, e seleção/combate autoritativos.

Também mostrou três pontos a corrigir antes de congelar v3.0:

1. Um Zumbi parcialmente ferido desapareceu antes do primeiro hit, mas foi tratado como `sem kill autoritativa` e consumiu Strength.
2. Uma queda de Presence gerou mensagens fatais duplicadas por corrida entre heartbeat/receiver/engine.
3. BGContinuedProcessingTask nunca iniciou; `.queue` ficava sem handler e nem aparecia entre requests pendentes. Após a ponte UIKit expirar, o processo foi suspenso e o WebSocket morreu.

## Alterações RC1

- Revalidação do mob após movimento e antes do combate.
- Target que desaparece sem kill atribuível não conta como falha.
- Strength não é consumida quando o target já desapareceu antes da preparação.
- Deduplicação terminal de falha de conexão.
- Deduplicação das mensagens repetidas de scenePhase.
- Combat timer final informa quanto resta antes do deslocamento e deixa explícito que o deslocamento seguro conta na janela.
- Continued Processing usa `.fail`, pois uma sessão WebSocket precisa da proteção imediatamente.
- Até 3 submissões com identificadores únicos quando o SDK 26 aceita `submit(_:)` mas o handler não aparece e o request não é listado como pendente.
- Diagnóstico de Background App Refresh, Low Power Mode e wildcard do Info.plist.
- Progresso do BGContinuedProcessing usa 100 subunidades por sucesso para permitir progresso intermediário real em movimento/tentativas/hits.

## Não declarar 100% sem teste final

Ainda faltam evidências ao vivo para:

- `[BG] ✅ Continued Processing INICIADA` e atividade avançando por minutos em outro app;
- recovery de emergência especificamente em HP <= 50 E shield == 0 retornando ao mesmo alvo;
- drop bancável real → banco → retorno à Wilderness;
- mount/pet real provando que não é enviado ao banco.

Todo o core foreground (Tree, Coal, Stone, Fishing, Chicken, Zombie, Dragon) já possui evidência funcional real.
