# KINTARABOT v2.1 — Background Continuity

## Objetivo

Manter a atividade iniciada pelo usuário executando quando o KintTany sai do primeiro plano no iOS 26, evitando que a suspensão normal do app derrube a Presence/WebSocket durante a troca para outros aplicativos.

## Alterações

- integração oficial com `BGContinuedProcessingTask` e `BGContinuedProcessingTaskRequest`;
- progresso do sistema baseado em `sucessos/meta`;
- título/subtítulo da tarefa atualizados com atividade e estado;
- expiração/cancelamento da tarefa contínua é tratado como erro fatal e interrompe a engine;
- fallback curto com `UIApplication.beginBackgroundTask` quando a tarefa contínua não estiver disponível;
- logs `[BG]` adicionados ao diagnóstico útil;
- `RootView` encaminha `scenePhase` para o coordenador;
- `Info.plist` autoriza `$(PRODUCT_BUNDLE_IDENTIFIER).continuedBot`;
- versão atualizada para 2.1 (build 21);
- GitHub Actions migrado para `macos-26` e Xcode 26.x;
- seleção de simulador no CI passou a ser dinâmica para evitar quebra por nome/runtime fixo.

## Limites do iOS

A API é a solução oficial do iOS 26 para trabalho iniciado em primeiro plano que deve continuar no background. Ela permite rede e processamento, mas não transforma o app em daemon: o sistema ainda pode encerrar a tarefa sob pressão de recursos, e fechar manualmente o app no app switcher cancela as tarefas em execução.

## Não alterado

Nenhuma mensagem de protocolo, alvo, gathering, pesca ou combate foi modificada nesta versão. O núcleo funcional da v2.0 permanece intacto.
