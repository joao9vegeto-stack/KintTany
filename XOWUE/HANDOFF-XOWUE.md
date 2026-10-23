# Handoff técnico — XOWUE

**Data:** 23/10/2026
**Jogo:** X-Men Origins: Wolverine — Uncaged Edition (Xbox 360)
**Title ID:** `41560816`
**Repositório:** `joao9vegeto-stack/KintTany`
**Branch:** `XOWUE` (derivada de `main`)
**Destino:** runner iOS arm64 que prepara o caminho para uma recompilação estática PPC.

## Estado atual

### Recompilação AOT

- Entrada analisada localmente: `default.xex`, 23.052.288 bytes.
- SHA-256: `b5afa6ff191194e5cc0a29302878b154baccfa7073868108c5e7416d08b3aa9a`.
- XEX2, Title ID `41560816`, Media ID `09FF5403`, base `0x82000000`, entry point `0x82C3CAA8`, imagem carregada de 23.986.176 bytes, 12 seções e 261 imports resolvidos.
- Código gerado pelo XenonRecomp: 344 unidades `ppc_recomp.*.cpp` + `ppc_func_mapping.cpp` = 345 fontes C++ geradas. As fontes estão compactadas em `dist/XOWUE-AOT-source.partNN` (partes de até 4 MiB); o SHA-256 do archive montado fica em `dist/SHA256SUMS`.
- O log `generated/config/XOWUE-recompile.log` é versionado junto ao projeto porque o gerador de adapters usa as 161 instruções que o XenonRecomp não decodificou para manter falhas explícitas.
- As 345 unidades passaram por `clang++-18 -fsyntax-only`; o engine com as 345 unidades AOT, os adapters e o mapa também compilou e ligou no host com Clang 18.
- O patch do XenonRecomp está fixado ao upstream `ddd128bcca99fe8bfbb99bea583c972351fa6ace` e adiciona as instruções necessárias para esta entrada, além de retirar o alias não portável em Clang não-Apple.

### Runtime e app iOS adicionados

`Runtime/XOWUEEngine.cpp` usa o parser XEX2/LZX de XenonUtils e implementa a fundação do runner:

1. Lê e valida o XEX2 selecionado.
2. Confere a base do executável contra a configuração AOT (`0x82000000`).
3. Reserva uma janela de memória PPC de 4 GiB e copia as seções carregadas para os endereços guest.
4. Preenche a tabela de despacho `PPCFuncMappings`, incluindo as entradas de import geradas.
5. Inicializa o contexto PPC com uma pilha provisória e chama o entry point recompilado (`_xstart`, `0x82C3CAA8`).

`Runtime/generate_runtime_stubs.py` gera um adapter para cada uma das 261 APIs importadas. Há suporte básico para `NtAllocateVirtualMemory` e `NtFreeVirtualMemory` no heap guest de memória uniforme, e `HalReturnToFirmware` vira uma parada controlada do runner. As outras 258 APIs encerram o boot com nome e LR PPC. O script também transforma as 160 palavras indecodificadas que têm entrada no mapa de funções em falhas explícitas; uma das 161 palavras reportadas não possui entrada própria no mapa. Nenhuma delas é apresentada como código resolvido.

### Validações concluídas no host

- O parser leu o XEX2: base `0x82000000`, entry point `0x82C3CAA8`, imagem carregada de 23.986.176 bytes, 12 seções e 261 imports.
- O engine e todo o código AOT ligaram em `XOWUEHostSmoke`.
- A chamada ao entry point passou por alocação e liberação de memória; o caminho termina em `HalReturnToFirmware(routine=1)`. O runner relata a parada como estado de firmware, sem alegar que o título chegou ao menu ou renderizou um frame.
- O workflow GitHub Actions `XOWUE iOS IPA` concluiu com sucesso no run #4 (ID `39888098218`), validando o commit de código `c784c75c3c770ffcf3cebca3dd21ed926f1cc779`. O runner macOS compilou o engine e o app para arm64, empacotou o IPA e passou pelas verificações do workflow. [Run do Actions](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39888098218).
- O run #6 (ID `39890657352`, commit `9f32c367b378721cc1887a2136c5801ed26e1ac7`) recompilou o engine arm64 com sucesso, mas o XcodeGen recusou o spec por falta de `info.path`; o app não foi compilado nem houve artefato IPA. O spec corrigido gera o Info.plist em `XOWUE-Info.plist`; o próximo run passa a ser **Build 1**. [Run com a falha de configuração](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39890657352).
- IPA entregue: `XOWUE-unsigned.ipa`, 20.024.250 bytes, SHA-256 `ed2d567b87a278317c2d2c61097ec6b1e2502b6ca22e9864620aaa17fe2e791d`. O ZIP do artifact da CI tem SHA-256 `b897a5ce17bc60dd81e4031debfa5a71fd5c46c7515aaba5e763db914bd2e0f9`.
- A inspeção local confirmou um ZIP IPA íntegro, executável Mach-O de 64 bits arm64, bundle `com.joaopedro.xowue` e versão mínima iOS 17.0. O pacote não contém assinatura Apple.

`iOS/` contém o app SwiftUI de diagnóstico, ícone próprio e biblioteca local do jogo. O app expõe `Documents` no Arquivos, cria `Jogos` e detecta `default.xex` no nível da raiz ou em uma pasta de jogo dentro dela. O seletor aceita uma pasta completa ou o `default.xex`; ao receber a pasta externa, o app copia os itens com progresso para a área local e tenta iniciar o diagnóstico. O tipo de documento `.xex` também é registrado para abertura pelo iOS.

O caminho recomendado é **Arquivos → No Meu iPhone → XOWUE → Jogos**. A configuração inclui `UIFileSharingEnabled`, `LSSupportsOpeningDocumentsInPlace` e o tipo `com.xowue.xex`. A interface mostra o estado observado do runtime, o resultado do boot e a versão da IPA em uso.

O workflow define `CFBundleVersion` como **Build 1, Build 2, Build 3…** e nomeia o arquivo `XOWUE-Build-N.ipa`. O run #6 compilou o engine, mas não gerou IPA porque o spec do XcodeGen estava sem o campo obrigatório `info.path`. A correção restaura esse caminho e reserva o run #7 para o primeiro IPA, **Build 1**.

### Limites atuais

Este IPA é um **runner de desenvolvimento**, não uma versão jogável. O boot ainda pode parar em uma API de kernel/XAM não implementada. Também faltam gerenciamento de heap/threads/handles compatível, MMIO, driver Xenos/D3D para renderizar na GPU Apple, XMA/áudio e integração dos arquivos WGame. Não há frame de jogo comprovado nem teste no iPhone.

O pacote de assets WGame completo não está neste workspace. O repositório não recebe o `default.xex`, assets, DLC, title updates ou arquivos extraídos desses dados. O arquivo AOT contém código derivado do executável fornecido e foi incluído no branch para a CI compilar o engine; não é incluído o executável original.

O IPA empacotado pela CI é unsigned. Para instalar em iPhone, configure assinatura Apple compatível (identificador `com.joaopedro.xowue`, certificado e provisioning profile) ou assine localmente com o método de sideload escolhido.

## Build local (macOS/Linux com Clang 18)

```bash
git clone https://github.com/joao9vegeto-stack/KintTany.git
cd KintTany
git fetch origin
git switch --track origin/XOWUE

git clone --recursive https://github.com/hedge-dev/XenonRecomp.git XOWUE/vendor/XenonRecomp
git -C XOWUE/vendor/XenonRecomp checkout ddd128bcca99fe8bfbb99bea583c972351fa6ace
git -C XOWUE/vendor/XenonRecomp submodule update --init --recursive
git -C XOWUE/vendor/XenonRecomp apply "$PWD/XOWUE/patches/XenonRecomp-XOWUE.patch"

tar -xzf XOWUE/dist/XOWUE-AOT-source.tar.gz -C XOWUE/generated
cmake -S XOWUE/Runtime -B build-runtime \
  -DCMAKE_C_COMPILER=clang-18 \
  -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_BUILD_TYPE=Release \
  -DXENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
  -DXOWUE_BUILD_HOST_SMOKE=ON
cmake --build build-runtime --target XOWUEHostSmoke --parallel 4
./build-runtime/XOWUEHostSmoke /caminho/local/default.xex
```

Para regenerar o AOT, coloque uma cópia autorizada em `XOWUE/upload/default.xex` e rode:

```bash
XENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
XENONRECOMP_BUILD_DIR="$PWD/XOWUE/vendor/XenonRecomp/build-xowue" \
XOWUE_XEX="$PWD/XOWUE/upload/default.xex" \
XOWUE/tools/run_xowue_codegen.sh

XENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
python3 XOWUE/tools/check_generated_cpp_syntax.py
```

Depois de regenerar, atualize o archive AOT e o hash:

```bash
python3 XOWUE/tools/package_xowue_aot.py
```

## IPA pelo GitHub Actions

O workflow `.github/workflows/xowue-ios.yml` roda em push na branch `XOWUE` quando mudam o runtime, o app, as fontes AOT, as ferramentas ou o próprio workflow; mudanças só nos handoffs não recompilam o IPA. Também aceita `workflow_dispatch`. Cada execução define `CFBundleVersion` e gera o artifact `XOWUE-Build-N`, contendo `XOWUE-Build-N.ipa`. O build continua unsigned e não é instalado no telefone.

## Próximas etapas técnicas

1. Instalar o próximo IPA numerado e testar no iPhone: pasta nativa em Arquivos, detecção após retorno ao app, seletor de pasta, abertura de `.xex` pelo iOS e número de Build visível.
2. Instrumentar o boot real no aparelho e identificar o primeiro import que bloqueia além do smoke test, mantendo falhas explícitas para APIs desconhecidas.
3. Integrar a leitura da estrutura WGame e implementar os imports Xbox kernel/XAM observados, memória, threads e handles compatíveis.
4. Implementar MMIO e renderer Xenos/D3D para Metal; depois áudio/XMA e controles.
5. Só declarar boot jogável após capturar um frame real do jogo e validar no dispositivo alvo.

## Arquivos importantes

- `Runtime/`: loader PPC, C API, CMake e gerador de adapters de import.
- `iOS/`: app SwiftUI, bridging header e spec do XcodeGen.
- `dist/XOWUE-AOT-source.partNN`: partes do archive AOT usado pela GitHub Actions.
- `tools/package_xowue_aot.py`: atualiza archive, partes e SHA-256 após nova recompilação.
- `dist/SHA256SUMS`: integridade do archive AOT.
- `generated/config/`: TOML, tabelas, logs e histórico da análise.
- `patches/XenonRecomp-XOWUE.patch`: patch para a revisão upstream pinada.
- `tools/`: auditoria, geração, validação de sintaxe e análise de helpers/tabelas.
