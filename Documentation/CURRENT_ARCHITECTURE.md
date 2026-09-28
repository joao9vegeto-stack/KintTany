# Arquitetura atual — v4.0 (build 1)

KintTany/KINTARABOT é um aplicativo iOS nativo Swift/SwiftUI que executa a engine diretamente no iPhone. A baseline funcional continua baseada em protocolo e capturas reais do Kintara; estados autoritativos têm prioridade sobre inferências locais.

## Continuidade e background

- O runtime de áudio real (`AVAudioSession.playback` + `AVAudioEngine`) é a autoridade de continuidade observada em background.
- `BGContinuedProcessingTask` fornece integração/progresso do sistema e pode ser rearmado no foreground sem reiniciar a sessão.
- Expiração do Continued Processing não encerra uma atividade se o runtime de áudio continuar ativo.
- Atividades seguras usam BG Headless: SwiftUI/SceneKit/WebKit e eventos puramente visuais ficam congelados, enquanto engine, socket, HTTP e progresso autoritativo continuam.
- Dunes/Wilderness preservam telemetria necessária à segurança.

## Realtime recovery v4.0

A queda de Presence deixou de ser uma política específica de Gathering.

- Gathering seguro: reconecta no mesmo shard e preserva meta/progresso autoritativo.
- Fishing, Roast Pit, Frostmere Smith e Chicken: recriam a Presence no mesmo shard e retomam somente o restante da meta.
- Smith/Roast/Fishing mantêm âncoras autoritativas de inventário para reconciliar uma operação que o servidor possa ter processado durante a queda.
- Wild e Dunes continuam conservadores: queda em região de risco prioriza saída segura antes de qualquer retomada.

## STOP transacional

Fishing, Roast Pit e Frostmere Smith usam STOP cooperativo: uma operação já em voo termina/reconcilia antes do teardown; nenhuma nova operação é iniciada depois do STOP.

## Dunes

- BANK-FIRST obrigatório.
- Health Potion+ 0/6 continua permitido; sua ausência não bloqueia coleta.
- Ferramentas com durabilidade <=100 não entram em full-loot.
- Antes de iniciar novo alvo, a engine reserva desgaste suficiente para não cruzar o piso de 100 (Cacti: 6; Silver: 10 conservador).
- No banco, ferramentas compatíveis seguras são escolhidas por menor durabilidade primeiro, preservando as melhores para depois.
- Ferramenta gasta é bancadas e outra cópia segura é carregada; a meta da sessão continua.
- Ausência da ferramenta em The Shores não é prova isolada de morte. Morte exige lifeEpoch/HP autoritativo; sem evidência suficiente o resultado é inconclusivo.
- Respawn confirmado nas Dunes não encerra automaticamente a meta: até 3 vezes por sessão o progresso é preservado, o bot reconstrói BANK-FIRST/loadout no World e retorna às Dunes. Sem ferramenta >100 ele permanece seguro e encerra com progresso preservado.
- Checkpoints, HP 100 no World, dano externo, calor, saída The Shores e proteção de recursos permanecem ativos.

## Fluxo

`RootView/ReplicaUI → AppStore → RealtimeSocket → AutomationEngine → RealtimeProtocol → Kintara`.

A suíte XCTest cobre contratos de protocolo, gathering/proof/wear, Dunes, banco, combate, background, Trout e as políticas v4.0 de recovery/rotação.

## Distribuição

GitHub Actions em `macos-26` executa XCTest, build `iphoneos`, valida configuração de background e publica o IPA não assinado. A versão visível no canto superior direito vem de `CFBundleShortVersionString(CFBundleVersion)`, por exemplo `v4.0(1)`.


## v4.0 Build 2 — correção do loop Dunes observado em log

- A ferramenta escolhida para reentrada precisa sobreviver ao próximo alvo inteiro: Silver exige durabilidade mínima 111 e Cacti 107.
- A iid que acabou de disparar rotação preventiva é excluída explicitamente daquela seleção.
- A cópia carregada é validada pela iid realmente retirada, sem ser confundida com uma cópia de menor durabilidade ainda no banco.
- STOP é autoridade global da sessão Dunes. Em World/Bank/The Shores nenhum novo `desert` pode ser aberto após STOP; se o toque competir com uma reconexão, a nova Presence é fechada antes de qualquer coleta.


## v4.0 Build 3 — autoridade de HP nas Dunes

- Engines novas podem herdar o último HP realtime conhecido para não voltar visualmente a 100 por default, mas herança não conta como confirmação fresca.
- A reentrada nas Dunes só é liberada após uma vital realtime nova da Presence World, posterior à transição bank_shop→World.
- `/api/auth/me` continua útil para playerId e para corroborar um drop suspeito, mas seu HP isolado não satisfaz o gate realtime de reentrada.
- Drops inesperados de HP vindos de `pvit` próprio passam pela mesma confirmação HTTP já usada por snapshots suspeitos; divergência é registrada e o drop baixo não dispara fuga.
- Logs de HP agora registram fonte e revisão autoritativa para diagnosticar futuras divergências sem adivinhar.
