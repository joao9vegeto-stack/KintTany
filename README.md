# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** `41560816` · **Branch:** `XOWUE` · **Backend gráfico:** KosmicKrisp (Vulkan → Metal)

## Estado comprovado

- A Action #20, no commit `98e54e2`, concluiu e publicou o IPA Build 7.
- O runtime valida o XEX2 do jogo, compila 344 unidades PPC AOT e gera adapters para os 261 imports encontrados no executável. O gerador falha quando há import sem rota classificada.
- Os adapters incluem handlers de kernel/XAM e políticas locais para serviços que não existem no iPhone. Cobertura de imports não significa equivalência completa do kernel Xbox.
- O diagnóstico de aparelho mais recente registrado alcançou o ring Xenos: 24 opcodes draw e 5 buffers indiretos foram observados; o relatório registrou 0 swaps guest e 0 frames decodificados. O Build 7 parou em `KeEnterCriticalRegion`, que ainda não tinha uma rota naquele pacote. O commit `d547096` implementa o handler; a Action #21 gerou os 261 adapters, mas encontrou erro de compilação por acessos PPC sem o ponteiro de memória guest. A correção já está no código local e aguarda nova Action; ainda falta relatório de aparelho.
- KosmicKrisp validou instância, surface, device, swapchain Metal e presents do host. O runtime decodifica e encaminha frames guest nos formatos Xenos 6 e 54 quando `VdSwap` fornece um framebuffer válido.

O frontend Xenos atual registra pacotes, draws e buffers indiretos, mas ainda não executa o pipeline de shaders, render targets/EDRAM e resolves do jogo. Portanto, os dados disponíveis ainda não comprovam uma imagem do jogo apresentada no iPhone. O app agora exibe as contagens guest do último diagnóstico em vez de declarar frames de jogo sem evidência.

## App e arquivos do jogo

Coloque a pasta do jogo em **Arquivos → No Meu iPhone → XOWUE → Jogos** ou importe uma pasta/`default.xex` pelo app. Os diagnósticos `diagnostico-build-N.txt` e `crash-build-N.txt` ficam acessíveis pelo app Arquivos. O jogo, saves, DLC e title updates não são incluídos na branch nem no IPA.

O IPA da Action é arm64 e sem assinatura. A instalação exige assinatura Apple compatível.

## Árvore da branch

Os diretórios `Runtime/`, `iOS/`, `generated/`, `dist/`, `patches/`, `tools/` e `upload/` ficam diretamente na raiz desta branch. `.github/workflows/xowue-ios.yml` constrói o IPA. A árvore versionada contém apenas arquivos do XOWUE e o workflow; o conteúdo de `main` não faz parte da árvore atual.

Leia [HANDOFF-XOWUE.md](HANDOFF-XOWUE.md) para arquitetura, validações e comandos. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de redistribuir.
