# XOWUE — início rápido

Branch: `XOWUE` no repositório [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany). O projeto fica na raiz da branch, sem uma pasta externa envolvendo os arquivos.

A Action #20 (`98e54e2`) concluiu o IPA Build 7. KosmicKrisp está ativo na cadeia Vulkan → Metal. O último relatório disponível do aparelho registrou 24 opcodes draw, 5 buffers indiretos, nenhum swap guest, nenhum frame guest decodificado e parou em `KeEnterCriticalRegion`. Essa chamada agora tem implementação APC no código do Build 7; o relatório após essa correção ainda precisa ser atualizado no aparelho.

O painel do app mostra os contadores do último boot. Contagem de draw indica que o pacote foi observado; não significa que shaders/render targets do Xenos foram executados. Use o [handoff](HANDOFF-XOWUE.md) para os detalhes do runtime e os procedimentos de build. O `default.xex` e os assets do jogo ficam fora do Git e do IPA.
