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

`Runtime/generate_runtime_stubs.py` gera adapters para as 261 APIs importadas. Neste estado, 24 têm comportamento básico e explícito: alocação/liberação e consulta de memória, tipo de processo, seções críticas de uma única thread, TLS, conversões ANSI/Unicode, frequência do relógio, consulta de launch data sem payload, criação mínima de evento, cache de arquivos e retorno de firmware. As outras 237 param com nome, LR, r3–r10 e até 128 eventos PPC recentes. A criação de evento ainda não oferece scheduler de waits; as seções críticas não têm sincronização multithread. O script também transforma as 160 palavras indecodificadas que têm entrada no mapa de funções em falhas explícitas; uma das 161 palavras reportadas não possui entrada própria no mapa. Nenhuma delas é apresentada como código resolvido.

### Validações concluídas no host

- O parser leu o XEX2: base `0x82000000`, entry point `0x82C3CAA8`, imagem carregada de 23.986.176 bytes, 12 seções e 261 imports.
- O engine e todo o código AOT ligaram em `XOWUEHostSmoke`.
- O smoke do host valida XEX2, executa `_xstart`, passa pela configuração de memória/vídeo e chega a `ExCreateThread`. O bloqueio medido é `LR=0x82C4C110`: handle out `r3=0x7FFEF6B0`, stack `r4=0x8000` (32 KiB), thread ID `r5=0x1013FA2C`, startup `r6=0x82C4D958`, rotina worker `r7=0x82690678`, contexto `r8=0x1013FA20`, flags `r9=0`. A rotina startup chama o worker, que é um loop de mensagens. XOWUE ainda não tem scheduler PPC nem ciclo de vida de threads; por isso, o runner para com erro explícito. Não chegou ao menu nem renderizou um frame.
- O workflow GitHub Actions `XOWUE iOS IPA` concluiu com sucesso no run #4 (ID `39888098218`), validando o commit de código `c784c75c3c770ffcf3cebca3dd21ed926f1cc779`. O runner macOS compilou o engine e o app para arm64, empacotou o IPA e passou pelas verificações do workflow. [Run do Actions](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39888098218).
- O run #6 (ID `39890657352`, commit `9f32c367b378721cc1887a2136c5801ed26e1ac7`) recompilou o engine arm64 com sucesso, mas o XcodeGen recusou o spec por falta de `info.path`; o app não foi compilado nem houve artefato IPA. [Run com a falha de configuração](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39890657352).
- O run #7 (ID `39891228913`, commit `257c62275a70e577690137ebe8e6f45c82924f06`) passou pelo XcodeGen e compilou o app SwiftUI. O empacotamento parou porque o workflow não criou o diretório `Payload` no caminho temporário de validação; não houve IPA. A correção cria esse diretório e ajusta a versão para que o run #8 produza **Build 1**. [Run com falha de empacotamento](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39891228913).
- O run #8 (ID `39891819489`, commit `f4d4ea11f1c211a5628608a6ce1f641731b0063b`) concluiu com sucesso: engine arm64, geração XcodeGen, compilação Swift, Info.plist, arquitetura arm64, Assets.car, tipo `.xex` e validação do IPA. Artifact `XOWUE-Build-1`, ID `12474638929`. [Run do Build 1](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39891819489).
- IPA: `XOWUE-Build-1.ipa`, 20.356.072 bytes, SHA-256 `d08e7cf391c9712ea80bfe63ad01b82d883af6a10b4d0ae94b53950225a94254`. ZIP do artifact: 20.137.008 bytes, SHA-256 `75312c6ad3aa3ffd2bce5c77e5aec982dbb7365de6e4295740200b82de1ad36d`.
- IPA entregue: `XOWUE-unsigned.ipa`, 20.024.250 bytes, SHA-256 `ed2d567b87a278317c2d2c61097ec6b1e2502b6ca22e9864620aaa17fe2e791d`. O ZIP do artifact da CI tem SHA-256 `b897a5ce17bc60dd81e4031debfa5a71fd5c46c7515aaba5e763db914bd2e0f9`.
- A inspeção local confirmou um ZIP IPA íntegro, executável Mach-O de 64 bits arm64, bundle `com.joaopedro.xowue` e versão mínima iOS 17.0. O pacote não contém assinatura Apple.

`iOS/` contém o app SwiftUI, ícone Wolverine e biblioteca local. `Documents` é exposto no Arquivos e recebe `Jogos`, `diagnostico.txt` e `crash.txt` na raiz. O seletor usa `UIDocumentPickerViewController` para abrir uma pasta completa ou `default.xex`; uma pasta externa é copiada para a área local com progresso. O diagnóstico registra busca, escolha, escopo de segurança, importação, inspeção XEX2, boot, resultado nativo e os últimos eventos PPC. `crash.txt` recebe checkpoints de boot e exceções Objective-C; um boot iniciado sem registro final é marcado na próxima abertura. O iOS não oferece aqui um capturador confiável de falhas por sinal nativo.

O caminho recomendado é **Arquivos → No Meu iPhone → XOWUE → Jogos**. A configuração inclui `UIFileSharingEnabled`, `LSSupportsOpeningDocumentsInPlace` e o tipo `com.xowue.xex`. A interface mostra o estado observado do runtime, o resultado do boot e a versão da IPA em uso.

O workflow define `CFBundleVersion` como **Build 1, Build 2, Build 3…** e nomeia o arquivo `XOWUE-Build-N.ipa`. O contador usa execuções bem-sucedidas de IPA a partir do run #8; falhas de CI não consomem números.

### Limites atuais

Este IPA é um **runner de desenvolvimento**, não uma versão jogável. A execução atual para em `ExCreateThread`; falta scheduler PPC com contexto, pilhas, estados de espera e encerramento de threads. O patch KosmicKrisp iOS Metal WSI está versionado em `Runtime/Graphics/KosmicKrisp/patches/`, vindo do último commit `db014165eb39429ae37d1946db6fc83c600c63b3` da branch `PsTJohn`, mas não está compilado nem ligado ao XOWUE. Ele oferece uma camada Vulkan→Metal/WSI; ainda falta a frente Xenos/D3D, interpretação de comandos, shaders e superfícies. Também faltam MMIO, XMA/áudio, integração dos arquivos WGame e teste no iPhone. Nenhum frame do jogo foi comprovado.

O pacote de assets WGame completo não está neste workspace. O repositório não recebe o `default.xex`, assets, DLC, title updates ou arquivos extraídos desses dados. O arquivo AOT contém código derivado do executável fornecido e foi incluído no branch para a CI compilar o engine; não é incluído o executável original.

O IPA `XOWUE-Build-1.ipa` empacotado pela CI é unsigned e não contém perfil Apple. Para instalar em iPhone, configure assinatura Apple compatível (identificador `com.joaopedro.xowue`, certificado e provisioning profile) ou assine localmente com o método de sideload escolhido.

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

1. Instalar e testar o próximo IPA no iPhone: seletor nativo, pasta local, os dois logs, ícone e Build visível.
2. Implementar scheduler PPC para `ExCreateThread`/`ExTerminateThread` e os imports de espera, handles e eventos descobertos no smoke.
3. Implementar MMIO e um frontend Xenos/D3D que emita Vulkan commands; depois compilar/integrar o driver KosmicKrisp/Mesa e ligar a superfície Metal à tela do app.
4. Integrar os arquivos WGame, XMA/áudio e controles.
5. Só declarar boot jogável depois de capturar um frame real do jogo no dispositivo alvo.

## Arquivos importantes

- `Runtime/`: loader PPC, C API, CMake, adapters de import e `Graphics/KosmicKrisp/`.
- `iOS/`: app SwiftUI, bridging header e spec do XcodeGen.
- `dist/XOWUE-AOT-source.partNN`: partes do archive AOT usado pela GitHub Actions.
- `tools/package_xowue_aot.py`: atualiza archive, partes e SHA-256 após nova recompilação.
- `dist/SHA256SUMS`: integridade do archive AOT.
- `generated/config/`: TOML, tabelas, logs e histórico da análise.
- `patches/XenonRecomp-XOWUE.patch`: patch para a revisão upstream pinada.
- `tools/`: auditoria, geração, validação de sintaxe e análise de helpers/tabelas.
