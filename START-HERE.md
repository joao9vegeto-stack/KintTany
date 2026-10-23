# XOWUE — início rápido

Branch: `XOWUE` no repositório [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany). O projeto fica diretamente na raiz.

O [Build 10](https://github.com/joao9vegeto-stack/KintTany/actions/runs/40011161715), Action #24 no commit `75cab56`, passou pela compilação, empacotamento e validação dos símbolos AOT no executável final. O Build 8 caía em `PC=0` porque 87.736 aliases PPC estavam weak e viravam weak dyld lookups. O Build 9 ainda continha esses aliases; o Build 10 os liga como símbolos fortes. A inspeção do IPA achou 133.351 definições AOT fortes, zero weak lookups e confirmou `sub_8237CA18` como símbolo forte. O log nativo persistente do boot grava os eventos iniciais em `crash-build-N.txt`.

KosmicKrisp continua sendo o backend Vulkan → Metal. O Build 10 ainda aguarda validação de execução no aparelho: esta Action não confirma frames guest nem imagem do jogo. O IPA CI é arm64, sem assinatura e não inclui `default.xex` ou assets do jogo.

Consulte [README.md](README.md) para o estado breve, [HANDOFF-XOWUE.md](HANDOFF-XOWUE.md) para a auditoria técnica e [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de redistribuir.
