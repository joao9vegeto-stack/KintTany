# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** `41560816` · **Branch:** `XOWUE` · **Backend gráfico:** KosmicKrisp (Vulkan → Metal)

## Estado comprovado

- A Action #22, no commit `5bde4c1`, concluiu e publicou o IPA Build 8. O artifact contém executável arm64, `libvulkan_kosmickrisp.dylib` arm64, e seu IPA tem SHA-256 `8946aae7c1443c91223a03e78adb7f1959dec053a0ca11f7e00b6afcfee974ad`.
- O engine AOT compilou com 344 unidades e o gerador criou adapters para os 261 imports do executável. A Action confirmou compilação, ligação e empacotamento do app.
- O Build 8 inclui o handler `KeEnterCriticalRegion` e a correção dos acessos PPC que precisavam de `base`. O relatório de aparelho mais recente continua sendo do Build 7: 24 opcodes draw e 5 buffers indiretos observados, 0 swaps guest e 0 frames decodificados; parou em `KeEnterCriticalRegion`. Ainda não há log de execução do Build 8.
- KosmicKrisp continua como backend Vulkan → Metal e foi compilado para iOS arm64 na Action. Isso confirma a camada de apresentação do app, não a execução dos shaders Xenos do jogo.

O frontend Xenos atual registra pacotes, draws e buffers indiretos, mas ainda não executa o pipeline completo de shaders, render targets/EDRAM e resolves do jogo. Portanto, os dados disponíveis ainda não comprovam uma imagem do jogo apresentada no iPhone. O app exibe as contagens guest do último diagnóstico em vez de declarar frames de jogo sem evidência.

## App e arquivos do jogo

Coloque a pasta do jogo em **Arquivos → No Meu iPhone → XOWUE → Jogos** ou importe uma pasta/`default.xex` pelo app. Os diagnósticos `diagnostico-build-N.txt` e `crash-build-N.txt` ficam acessíveis pelo app Arquivos. O jogo, saves, DLC e title updates não são incluídos na branch nem no IPA.

O IPA da Action é arm64 e sem assinatura. A instalação exige assinatura Apple compatível.

## Árvore da branch

Os diretórios `Runtime/`, `iOS/`, `generated/`, `dist/`, `patches/`, `tools/` e `upload/` ficam diretamente na raiz desta branch. `.github/workflows/xowue-ios.yml` constrói o IPA. A árvore versionada contém apenas arquivos do XOWUE e o workflow; o conteúdo de `main` não faz parte da árvore atual.

Leia [HANDOFF-XOWUE.md](HANDOFF-XOWUE.md) para arquitetura, validações e comandos. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de redistribuir.
