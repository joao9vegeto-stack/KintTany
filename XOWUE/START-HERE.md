# XOWUE — início rápido

Branch de trabalho: XOWUE, no repositório joao9vegeto-stack/KintTany. Build 3 está sendo validada pela Action XOWUE iOS IPA (execução #12, commit d2cfc714903a1381629c6dce3397f56e63ea8436).

O app mostra o número da build e procura o jogo em Arquivos → No Meu iPhone → XOWUE → Jogos. Coloque a pasta completa do jogo nesse local ou use o seletor de pasta/default.xex. O app detecta o executável e escreve diagnostico-build-N.txt e crash-build-N.txt na raiz Documentos.

A compilação host Clang 18 passou para as 345 unidades AOT e o smoke executable. Build 2 parou em ExCreateThread. Build 3 acrescenta scheduler PPC/thread/TLS; execute no aparelho e envie os relatórios para identificar o próximo bloqueio.

KosmicKrisp/Mesa Metal WSI está ligado a um quadro Vulkan de diagnóstico. Ele não renderiza a cena Xenos. Ainda não foi comprovado menu, frame real ou boot jogável.

Leia HANDOFF-XOWUE.md para os comandos e arquitetura. Leia THIRD_PARTY_NOTICES.md antes de redistribuir. O IPA da CI é unsigned; requer certificado e provisioning profile Apple. O executável do jogo e os assets não entram no branch nem no IPA.
