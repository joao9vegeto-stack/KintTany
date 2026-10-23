# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** 41560816
**Branch:** XOWUE
**Build de código:** Build 3 em validação pelo workflow XOWUE iOS IPA.

## Estado do runner

A recompilação AOT contém 344 unidades de funções mais ppc_func_mapping.cpp. O build host completo com Clang 18 compilou e ligou XOWUEEngine e XOWUEHostSmoke. O runtime agora inclui uma base de ciclo de vida de threads PPC (ExCreateThread, XAPI startup, espera/suspensão/retomada, TLS por thread, KPCR e saída) e adapters iniciais para kernel/XAM.

O último log disponível, da Build 2, parou em ExCreateThread (LR 0x82C4C110). O código da Build 3 precisa ser executado no aparelho com a pasta do jogo para confirmar o próximo ponto. Não há prova de menu ou frame real ainda.

## App, arquivos e relatórios

- A pasta local é Arquivos → No Meu iPhone → XOWUE → Jogos.
- O app detecta default.xex na raiz de Jogos ou em uma subpasta. O seletor também aceita pasta ou executável.
- Build aparece no cabeçalho do app e é gravado em CFBundleVersion.
- Diagnósticos ficam na raiz Documentos com os nomes diagnostico-build-N.txt e crash-build-N.txt.
- O IPA não inclui default.xex nem assets do jogo e precisa de assinatura Apple para instalação.

## Gráficos

O workflow compila KosmicKrisp com os patches iOS/Metal WSI preservados da branch PsTJohn e fixa a revisão Mesa usada. O app apresenta um clear de diagnóstico Vulkan sobre CAMetalLayer. Os handlers gráficos Xenos ainda não traduzem o ring buffer real, shaders, textura/tiling ou draw state. O clear de diagnóstico não é um frame do jogo.

## Compile e continuidade

Leia HANDOFF-XOWUE.md para comandos do build host, execução no telefone, diagnóstico e handoff para o próximo agente. Leia THIRD_PARTY_NOTICES.md antes de redistribuir artefatos.

Artifact de Build 3: ação #12 em [GitHub Actions](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml). Confirme a execução e baixe XOWUE-Build-3 somente quando estiver concluída com sucesso.

O jogo, WGame, DLC, title updates e assets derivados permanecem fora do Git.
