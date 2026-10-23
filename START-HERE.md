# XOWUE — início rápido

Branch: `XOWUE` no repositório [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany). O projeto fica na raiz da branch, sem uma pasta externa envolvendo os arquivos.

A Action #20 (`98e54e2`) concluiu o IPA Build 7. KosmicKrisp está ativo na cadeia Vulkan → Metal. O último relatório disponível do aparelho registrou 24 opcodes draw, 5 buffers indiretos, nenhum swap guest, nenhum frame guest decodificado e parou em `KeEnterCriticalRegion`. O Build 7 ainda não tinha essa rota; o commit `d547096` implementa o handler APC. A Action #21 gerou os 261 adapters e falhou ao compilar o engine por acessos PPC sem o ponteiro `base`; o código local já corrige isso e aguarda nova Action. Ainda não há relatório de aparelho com a correção.

O painel do app mostra os contadores do último boot. Contagem de draw indica que o pacote foi observado; não significa que shaders/render targets do Xenos foram executados. Use o [handoff](HANDOFF-XOWUE.md) para os detalhes do runtime e os procedimentos de build. O `default.xex` e os assets do jogo ficam fora do Git e do IPA.
