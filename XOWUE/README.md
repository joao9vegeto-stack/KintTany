# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** `41560816`
**Branch:** `XOWUE`
**Estado:** recompilação AOT ligada a um runner iOS de diagnóstico; o boot jogável ainda não foi concluído.

## O que está neste branch

- Fontes C++ AOT compactadas e divididas em partes de até 4 MiB em `dist/`; a CI recompõe o archive para compilar sem armazenar o `default.xex`.
- Runtime inicial em `Runtime/`: parser XEX2/LZX de XenonUtils, mapeamento das seções, memória PPC de 32 bits, tabela de despacho e chamada ao entry point `0x82C3CAA8`.
- Adaptadores explícitos para as 261 importações conhecidas: `NtAllocateVirtualMemory` e `NtFreeVirtualMemory` operam no heap guest limitado; `HalReturnToFirmware` encerra o diagnóstico com o código da rotina. As outras 258 APIs param com erro identificável.
- App SwiftUI com ícone próprio, abertura direta de `.xex`, seletor de pasta, detecção no Documents exposto em Arquivos > No Meu iPhone > XOWUE > Jogos, e número de Build visível.
- `.github/workflows/xowue-ios.yml`, que compila o engine arm64, valida o Info.plist/ícone e empacota `XOWUE-Build-N.ipa` unsigned.

O smoke test do host parseia e liga o XEX, executa o entry point e chega a `HalReturnToFirmware(routine=1)`. Isso é uma parada de firmware, não prova de boot jogável. O IPA é um runner de desenvolvimento; ainda faltam implementações de Xbox kernel/XAM, memória e threads completas, Xenos/D3D, XMA/áudio, leitura dos assets do jogo e validação em aparelho. O app não inclui o XEX nem assets.

## Comece por aqui

1. Leia `HANDOFF-XOWUE.md` para arquitetura, validações e limitações.
2. Coloque a pasta completa do jogo em `Arquivos > No Meu iPhone > XOWUE > Jogos`; o app procura `default.xex` na raiz ou uma pasta abaixo.
3. Abra o app e toque **Abrir jogo**. Também é possível selecionar uma pasta ou abrir `default.xex` pelo iOS.
4. A versão aparece como **Build 1**, **Build 2** e assim por diante. As IPAs da CI são unsigned e exigem assinatura Apple para instalação.
5. Para repetir localmente, siga “Build local” no handoff.

## Identificação da entrada usada para a recompilação

O `default.xex` analisado tinha SHA-256 `b5afa6ff191194e5cc0a29302878b154baccfa7073868108c5e7416d08b3aa9a`, Title ID `41560816`, Media ID `09FF5403`, entry point `0x82C3CAA8`, base `0x82000000`, 12 seções e 261 imports reconhecidos. O arquivo original não está neste repositório.
