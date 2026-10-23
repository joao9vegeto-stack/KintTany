# XOWUE — início rápido

Branch: `XOWUE` no repositório [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany). O projeto fica na raiz da branch, sem uma pasta externa envolvendo os arquivos.

A Action #22, commit `5bde4c1`, concluiu e publicou o IPA Build 8. O engine arm64, o app iOS e o backend KosmicKrisp Vulkan → Metal compilaram; o pacote foi validado como IPA sem assinatura. O Build 8 inclui o handler `KeEnterCriticalRegion` e a correção do ponteiro guest `base`.

O último relatório do aparelho ainda é do Build 7: 24 opcodes draw e 5 buffers indiretos, nenhum swap guest, nenhum frame decodificado, parada em `KeEnterCriticalRegion`. O Build 8 ainda não tem relatório de execução em aparelho. A compilação verde não demonstra renderização do jogo: o frontend Xenos ainda não executa por completo shaders, render targets/EDRAM e resolves. KosmicKrisp permanece como backend gráfico; não confunda o clear/present host com frame guest.

O painel do app mostra os contadores do último boot. Contagem de draw indica que o pacote foi observado; não significa que shaders/render targets do Xenos foram executados. Use o [handoff](HANDOFF-XOWUE.md) para os detalhes do runtime e os procedimentos de build. O `default.xex` e os assets do jogo ficam fora do Git e do IPA.
