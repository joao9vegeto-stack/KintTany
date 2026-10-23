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
- A compilação iOS arm64 e o empacotamento do IPA ainda precisam ser confirmados pelo workflow GitHub Actions `XOWUE iOS IPA`.

`iOS/` contém um app SwiftUI de diagnóstico. Ele importa um `default.xex` (ou uma pasta que o contém), copia o executável para o sandbox e oferece inspeção/tentativa de boot. O workflow cria o projeto Xcode com XcodeGen e empacota `XOWUE-unsigned.ipa`.

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

O workflow `.github/workflows/xowue-ios.yml` roda em push na branch `XOWUE` (quando arquivos `XOWUE/**` mudam) e por `workflow_dispatch`. Ele valida o hash do AOT, baixa XenonRecomp na revisão pinada, compila `XOWUEEngine` para iOS arm64, gera o Xcode project, monta o app sem assinatura e valida o IPA.

No GitHub, abrir **Actions → XOWUE iOS IPA → último run → Artifacts → `XOWUE-iOS-unsigned-<run>`**. A CI não instala o app no telefone nem cria uma assinatura Apple.

## Próximas etapas técnicas

1. Rodar o workflow arm64 e corrigir falhas de Apple Clang/Xcode até obter o IPA unsigned.
2. Instrumentar o boot e implementar os imports de startup em ordem observada, mantendo erros explícitos para APIs desconhecidas.
3. Receber e inventariar a estrutura WGame completa para testar leitura de arquivos.
4. Implementar subsistemas de memória, threads, kernel/XAM, MMIO e GPU Xenos→Metal; depois áudio/XMA e controles.
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
