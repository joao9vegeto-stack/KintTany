# Handoff técnico — XOWUE

**Jogo:** X-Men Origins: Wolverine — Xbox 360
**Title ID:** `41560816`
**Repositório:** [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany)
**Branch:** `XOWUE`
**Workflow:** [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml)

## Última evidência

Action #20, commit `98e54e2cc262e0e2ad10f632a418b3f722002d9b`, concluiu com sucesso e publicou o IPA Build 7. Esse pacote tem SHA-256 `8141b57adf3b993c4ef23db9c6d7a3216c020dda3f9f229b23484da499551c61`.

O relatório de aparelho registrado para o Build 7 mostra: XEX2 reconhecido, engines Xenos inicializados, ring buffer configurado, 24 opcodes draw observados, 5 buffers indiretos, 0 swaps guest e 0 frames decodificados. A chamada registrada como parada foi `KeEnterCriticalRegion` (LR `0x82B537A4`); o código do Build 7 ainda não tinha esse import. O commit `d547096` adiciona a rota e o handler de região crítica com APC disable por KTHREAD e entrega de APC ao sair da região. A Action #21 gerou os 261 adapters, mas falhou ao compilar o engine porque alguns acessos PPC não recebiam o ponteiro de memória guest `base`. O código atual passa esse ponteiro às rotas e será verificado na Action seguinte; ainda não há relatório de aparelho com essa correção.

Os números 24/5 descrevem comandos contabilizados pelo parser. Eles não provam que os draws foram executados pela GPU. O último log de diagnóstico é a fonte para a conclusão sobre frames; a Action verde prova somente compilação, ligação e empacotamento.

## Árvore e isolamento

O conteúdo de projeto fica na raiz da branch: `Runtime/`, `iOS/`, `generated/config/`, `dist/`, `patches/`, `tools/`, `upload/` e documentos XOWUE. A branch mantém `.github/workflows/xowue-ios.yml`; seu workflow usa caminhos relativos à raiz. O commit de reorganização recria a árvore diretamente na raiz e sem arquivos de projeto de `main`. O `default.xex`, saves, DLC e title updates não entram no Git.

## CPU, kernel e AOT

- O XEX fornecido tem base `0x82000000`, entry `0x82C3CAA8`, Title ID `41560816` e 261 imports únicos.
- O archive versionado em partes contém 344 unidades de funções PPC mais `ppc_func_mapping.cpp`. A Action recompõe e valida o SHA-256 antes de compilar o engine ARM64.
- `generate_runtime_stubs.py` exige exatamente 261 imports e falha se houver nome sem rota ou handler compatível sem despacho explícito. A contagem atual é 128 handlers explicitamente roteados no gerador e 133 imports classificados pelo dispatcher de compatibilidade. Há políticas offline e rotinas stub; essa cobertura não afirma equivalência de cada API Xbox.
- O runtime inclui scheduler PPC/KTHREAD, TLS, sincronização, memória física/virtual, arquivos e handlers kernel/XAM usados no caminho de inicialização observado. No commit `d547096`, `KeEnterCriticalRegion` e `KeLeaveCriticalRegion` atualizam o APC-disable do KTHREAD e verificam entrega de APC ao reabilitar. A correção seguinte passa o ponteiro de memória guest aos helpers PPC e às rotas de spinlock que escrevem em memória.
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
