# Handoff técnico — XOWUE

**Jogo:** X-Men Origins: Wolverine — Xbox 360
**Title ID:** `41560816`
**Repositório:** [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany)
**Branch:** `XOWUE`
**Workflow:** [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml)

## Última evidência

Action #24, no commit `75cab56cfa0579ab54718bc151628f970233c047`, concluiu com sucesso e publicou o Build 10 ([workflow](https://github.com/joao9vegeto-stack/KintTany/actions/runs/40011161715)). O IPA arm64 sem assinatura tem SHA-256 `0e9251550e5289b31b4db5caab90c3a3553469136f533f2c5d766ff0cd823c6a`; o ZIP do artifact tem SHA-256 `f3e2d6c05f40225820c298c18172ca4572a613b0527f85f7bd31646b28b0cc1f`.

O relatório do Build 8 e o IPS do LiveContainer apontaram `EXC_BAD_ACCESS`, `PC=0`, `FAR=0` e falha de tradução de página. A inspeção do executável confirmou que o boot havia carregado o XEX2 e resolvido 261 imports antes de cair. A causa encontrada foi o AOT: funções PPC estavam publicadas como aliases weak e o dyld tentava resolvê-las por weak lookup. O Build 9 passou na compilação, mas a inspeção do IPA mostrou 87.736 definições weak e 87.736 weak lookups; portanto, aquele pacote não corrigia a falha.

O Build 10 normaliza os fontes PPC reconstruídos do archive antes da compilação e valida o Mach-O final lendo `LC_SYMTAB` e `LC_DYLD_CHAINED_FIXUPS`. A verificação no IPA entregue encontrou 133.351 definições AOT fortes, zero definições/referências weak e zero weak dyld lookups; o símbolo que aparecia na queda, `sub_8237CA18`, está presente como definição forte. O pacote inclui KosmicKrisp arm64 e mantém o log nativo persistente de início do boot em `crash-build-N.txt`.

O Build 10 ainda não foi executado no aparelho; portanto, não há contagem de frames guest confirmada para esta versão. O IPA CI é sem assinatura e não inclui `default.xex`, saves ou DLC.

## Árvore e isolamento

O conteúdo de projeto fica na raiz da branch: `Runtime/`, `iOS/`, `generated/config/`, `dist/`, `patches/`, `tools/`, `upload/` e documentos XOWUE. A branch mantém `.github/workflows/xowue-ios.yml`; seu workflow usa caminhos relativos à raiz. O commit de reorganização recria a árvore diretamente na raiz e sem arquivos de projeto de `main`. O `default.xex`, saves, DLC e title updates não entram no Git.

## CPU, kernel e AOT

- O XEX fornecido tem base `0x82000000`, entry `0x82C3CAA8`, Title ID `41560816` e 261 imports únicos.
- O archive versionado em partes contém 344 unidades de funções PPC mais `ppc_func_mapping.cpp`. A Action recompõe e valida o SHA-256 antes de compilar o engine ARM64.
- `generate_runtime_stubs.py` exige exatamente 261 imports e falha se houver nome sem rota ou handler compatível sem despacho explícito. A contagem atual é 128 handlers explicitamente roteados no gerador e 133 imports classificados pelo dispatcher de compatibilidade. Há políticas offline e rotinas stub; essa cobertura não afirma equivalência de cada API Xbox.
- O runtime inclui scheduler PPC/KTHREAD, TLS, sincronização, memória física/virtual, arquivos e handlers kernel/XAM usados no caminho de inicialização observado. `KeEnterCriticalRegion` e `KeLeaveCriticalRegion` atualizam o APC-disable do KTHREAD e verificam entrega de APC ao reabilitar. O commit `5bde4c1` também passa o ponteiro `base` aos helpers PPC e às rotas de spinlock que escrevem em memória guest; essa versão compilou na Action #22.
- O log de recompilação registra 161 palavras PPC não decodificadas. O gerador instrumenta as que têm entrada em `ppc_func_mapping.cpp` e marca o caminho se alcançado.

## Gráficos: KosmicKrisp e Xenos

KosmicKrisp segue como backend gráfico. O workflow fixa o commit Mesa, aplica os patches iOS/Metal WSI e compila o ICD arm64. O app cria instância Vulkan, surface `CAMetalLayer`, device, swapchain e presents da imagem host.

O runtime lê `CP_RB_WPTR`, expande indirect buffers, conta pacotes/opcodes draw e reconhece os marcadores `VdSwap`. `VdSwap` lê o fetch constant, valida argumentos, registra formato/extent e tenta decodificar framebuffer RGBA para os formatos Xenos 6 e 54. Quando a decodificação passa, o callback encaminha os pixels para a fila de apresentação de KosmicKrisp.

O frontend ainda não executa shaders Xenos nem o pipeline de render target/EDRAM, depth/blend e resolves. Assim, contar draws não escreve por si só um framebuffer. O critério de imagem real continua sendo um frame guest decodificado e apresentado, confirmado no diagnóstico do aparelho. O painel do app mostra contagens do último boot e não afirma entrega de frame se `decoded_frames=0`.

Referência de compatibilidade usada na auditoria: [Xenia `VdSwap`](https://github.com/xenia-project/xenia/blob/master/src/xenia/kernel/xboxkrnl/xboxkrnl_video.cc), [Xenia command processor](https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/command_processor.cc) e [Xenia Vulkan command processor](https://github.com/xenia-project/xenia/blob/master/src/xenia/gpu/vulkan/vulkan_command_processor.cc). Em Xenia, `VdSwap` produz fetch constant e pacote XE_SWAP; a execução de draws passa pela implementação GPU/EDRAM/shader, não pelo simples reconhecimento do opcode.

## Build e teste

A Action baixa XenonRecomp no commit `ddd128bcca99fe8bfbb99bea583c972351fa6ace`, aplica `patches/XenonRecomp-XOWUE.patch`, reconstitui o AOT de `dist/`, compila KosmicKrisp e o engine ARM64, gera o projeto Xcode, valida o IPA sem assinatura e publica `XOWUE-Build-N` como artifact.

Para uma compilação host, obtenha XenonRecomp no commit pinado e extraia o archive AOT:

```sh
git clone --recursive https://github.com/hedge-dev/XenonRecomp.git vendor/XenonRecomp
git -C vendor/XenonRecomp checkout ddd128bcca99fe8bfbb99bea583c972351fa6ace
git -C vendor/XenonRecomp submodule update --init --recursive
git -C vendor/XenonRecomp apply "$PWD/patches/XenonRecomp-XOWUE.patch"
cat dist/XOWUE-AOT-source.part* > /tmp/XOWUE-AOT-source.tar.gz
shasum -a 256 -c dist/SHA256SUMS
tar -xzf /tmp/XOWUE-AOT-source.tar.gz -C generated
cmake -S Runtime -B /tmp/xowue-build \
  -DCMAKE_C_COMPILER=clang-18 \
  -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_BUILD_TYPE=Release \
  -DXENONRECOMP_ROOT="$PWD/vendor/XenonRecomp" \
  -DXOWUE_BUILD_HOST_SMOKE=ON
cmake --build /tmp/xowue-build --target XOWUEHostSmoke --parallel 4
```

Em aparelho, instale IPA assinado, abra o jogo pela pasta local ou picker, e envie `diagnostico-build-N.txt` e `crash-build-N.txt` para comparar imports, ring, swaps, frames decodificados e eventos de thread. O IPA CI é arm64 sem assinatura e não contém o jogo.

## Referências de licença

Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de redistribuir patches, binários do app ou bibliotecas compiladas.


## Build 26 corrective scope — observed 24 Oct 2026 iPhone log

- Build 25 log proves `orientation.request.failed ... Supported: portrait`; Info.plist alone was insufficient. New UIKit `UIApplicationDelegate` returns dynamic orientation mask, set before `UIWindowScene.requestGeometryUpdate`. Verify on-device landscape presentation.
- Build 25 execution stopped at indirect `guestTarget=0x830F0400` with `LR=0x830F02FC`, while `lastAotEntry=0x82C2A1F0` was NOT the target owner. Generator scans owner instruction comments and precompiles nearby native continuations, limited by a 4096-entry budget and verification of owner labels.
- Build 25 graphics: 26 guest queued draws; 24 native Vulkan draws submitted; `XENOS_COMPOSITED_GPU_READBACK nonblack=0 samples=8193` (sparse), `VdSwap` decoded two frames. Now logs full-frame pixel occupancy and independently scans guest-swap RGBA; do not report GPU success until nonblack pixel evidence.
- All code remains AOT PPC translated to ARM64 + Xenos/Vulkan/Metal; no PPC interpretive execution, JIT or guessed stub.
- CI compile/link/IPA is necessary but not proof of visible gameplay. Capture guest decoded frame counts, host full pixel color metrics and landscape orientation in subsequent phone diagnostics.

## Build 27 — diagnóstico da Build 26 recebido 24/10/2026
- PPC falhou em 0x831AA0B0 (LR 0x831A9F50, lastAotEntry 0x831A9F48); incluir owner AOT verificado e cobertura preventiva regional, sem interpretador, JIT ou retorno simulado.
- 26 draws Xenos / 24 draws submetidos; GPU readback 0/3.162.132 pixels coloridos. 2 swaps 1280x720; o log do guest RGBA anterior à abertura do logger podia ser perdido. Salvar estatística e registrar por draw.
- Orientação: o primeiro request landscape falhou, mas a swapchain redimensionou depois a 2622x1222; retry UIKit limitado e preservação da tela retrato na biblioteca.
- GPU ainda não equivale a renderer Xenos completo (EDRAM, resolve, depth, blending). Falha de primeiro frame permanece até teste real no iPhone; CI prova somente tradução/compilação/link/IPA.
- Política: somente branch XOWUE; um commit, uma execução do workflow; assets do jogo não incluídos.

## Build 28 — lifetime real da memória Xenos, descriptors e FATAL (24/10/2026)
- A B27 morreu antes de o backend processar os dois rectangles com VFETCH. Os 24 draws point/no-fetch passam mas não geram pixels. Memória de 4GiB guest era weak_ptr e morria após exceção PPC. Retenção forte exclusiva de gráficos até novo boot, cópias protegidas por shared_ptr.
- Vertex fetch usa palavra0 bits2:31 como endereço físico em bytes; palavra1 bits2:25 como tamanho declarado em dwords; removida estimativa que ultrapassava buffers de resolve. Recusar alocações grandes/inválidas, sem NOP/stub.
- Registrar XENOS_FETCH_CAPTURE, GRAPHICS_BLOCKER, XENOS_NATIVE_DRAW_OUTCOME e metadados memexport de VS/PS. Memexport completa permanece componente a validar, não é fingida.
- FATAL AOT_DISPATCH em crash-build-*.txt para exceções fail-closed e FATAL SIGNAL/SIGDETAIL/ARM64REG para sinais reais seguindo padrão PoPTST.
- Exigir AOT de 0x82B34028 (B27) e validação no Mach-O. A ausência de pixel colorido segue não resolvida até prova em hardware.
