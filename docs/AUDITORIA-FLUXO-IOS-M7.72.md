# Auditoria do launcher e do caminho nativo de Ascension

## O que o vídeo mostrou

O app conseguiu importar a pasta e o ELF. O relatório da execução anterior
mostrou uma chamada, PC `0x00010410` e zero chamadas `cellFsOpen`/`cellFsRead`.
O número 1 não era o total de progresso do jogo: só contava a chamada de
entrada feita pelo host. Por isso, a tela parecia parada mesmo sem medir as
funções AOT chamadas por dentro.

Havia também um erro de contrato no caminho de execução. O host entregava uma
função PS3Recomp completa a `ar_run`, que foi feita para blocos PPC pequenos e
usa LR como próximo PC. No PS3Recomp fixado pelo projeto, `_start` é chamado
como função C nativa completa e as continuações pendentes em
`g_trampoline_fn` são drenadas pelo host. O app ainda percorre uma cadeia M6 de
microprovas antes de “Play”; essas provas não eram requisito do runtime e não
executavam o processo do jogo.

## Alterações desta revisão

- O caminho M7.73 entra diretamente na função da tabela AOT em `0x00010410`,
  com thread principal, TOC, PT_TLS, pilha, `argv[0]` e trampoline configurados
  segundo o `ppu_run()` do commit PS3Recomp que o CI fixa. Quando o guest
  retorna, o host coleta os dados e encerra a sessão; LR não é tratado como
  endereço de continuação.
- O estágio que reconstrói o lift injeta uma contagem no início das 29.849
  funções PPU. O relatório passa a mostrar chamadas AOT reais, último PC,
  chamadas guest de arquivo e bytes lidos. Não estima percentuais e deixa
  explícito que chamadas HLE internas ainda não têm contadores completos.
- O relatório reserva “execução do jogo” para a sessão nativa. Importar ELF,
  indexar arquivos, abrir a bancada gráfica e desenhar quadros sintéticos não
  são apresentados como boot ou gameplay.
- O relatório abre em um toque, mesmo antes da primeira execução. Isso corrige
  o caminho anterior, que recusava visualizar enquanto não existia um resultado
  concluído. A sessão também não relê o manifesto grande na thread da interface.
- A primeira tela virou um launcher de jogo: biblioteca, importação da pasta,
  importação validada do ELF, botão Iniciar condicionado aos dois itens e
  relatório da sessão. A bancada RSX/Metal fica em aba separada e identificada
  como sintética.
- A pasta continua fora do IPA e é aberta por permissão do Files durante a
  sessão. O ELF é validado localmente pelo SHA-256, entry e TOC esperados.

## Comparação com os ports enviados

O port de PC do Ascension documenta boot até o primeiro nível, cerca de 28 FPS
no menu e 9 FPS no primeiro nível no Windows. Ele usa a versão europeia
`BCES-01741` 1.00; este app valida `NPUA80918`. Portanto, os endereços e os
resultados do PC não comprovam que o lift deste ELF esteja correto em iOS.
O repositório do PC também carrega 44 patches de runtime, incluindo SPURS2,
LFQueue, SPU, espera/retomada do GCM e VBlank. Esses subsistemas são referências
concretas para a próxima portabilidade; não são trocas de interface.

O launcher de PC prepara o jogo em background, valida o disco, mantém páginas
de vídeo/controles/jogo/mods, inicia o processo e preserva log de execução. O
launcher SwiftUI do GoW2 mostra outra parte útil: preferências e importações
nativas, preparação fora da interface e entrada no jogo só quando o backend
entrega um quadro real. O runtime e os dados de GoW2 são específicos daquele
jogo; o que pode ser adaptado é o ciclo de vida e o desenho do launcher.

## O que ainda impede chegar ao menu

Esta revisão corrige a chamada de entrada e torna o caminho observável. Ela
não demonstra, por si, que o dispositivo chegou à inicialização de arquivos.
O gate concreto no telefone passa a ser: chamadas AOT aumentando, em seguida
`cellFsOpen`/`cellFsRead` e bytes positivos. O PC mostra que, mesmo depois de
entrar no jogo, SPURS e GCM podem parar a execução silenciosamente; esses são
os subsistemas que precisam ser acompanhados pelos dados reais do próximo run.
As métricas iniciais contam leituras guest no total; ainda não guardam caminho
por arquivo, então não afirmam que um `.psarc` específico foi aberto.

O app ainda não conecta comandos RSX do jogo ao Metal. A aba gráfica é um
laboratório de testes sintéticos. Por isso, primeiro frame original, menu,
gameplay e FPS continuam não comprovados. O fluxo nativo roda fora da thread
da interface e o relatório continua acessível durante a execução, mas o runtime
atual ainda não oferece cancelamento seguro de código guest bloqueado.

## Critérios de passagem

| Marco | Estado verificável nesta revisão |
|---|---|
| M0–M1 | ELF autenticado, loader e integração iOS construídos; teste em aparelho continua necessário |
| M2 | Entrada PS3Recomp completa e hooks nas 29.849 funções preparados; CI ainda precisa compilar este commit |
| M3 | Quatro imagens SPU registradas; execução de tarefas SPURS do título não comprovada |
| M4 | Pasta autorizada e VFS montado; chamadas guest de arquivos dependem do resultado no aparelho |
| M5 | Bancada Metal sintética disponível; renderer RSX do jogo não conectado |
| M6 | Nenhum primeiro frame do jogo medido |
| M7 | Nenhum gameplay estável a 30 FPS medido |
| M8 | Nenhuma validação de fidelidade a 60 FPS ou upscale medida |

`M7.73.0` é a versão de software do próximo artefato; não significa que o
critério de gameplay do marco M7 foi aprovado.
