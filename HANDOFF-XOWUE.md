# Handoff técnico — XOWUE

**Jogo:** X-Men Origins: Wolverine — Xbox 360
**Title ID:** `41560816`
**Repositório:** [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany)
**Branch:** `XOWUE`
**Workflow:** [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml)

## Última evidência

Action #22, commit `5bde4c19e988c72b9affd4556e0e11e56be7530c`, concluiu com sucesso e publicou o IPA Build 8. SHA-256 do IPA: `8946aae7c1443c91223a03e78adb7f1959dec053a0ca11f7e00b6afcfee974ad`. O pacote contém o executável arm64 e `libvulkan_kosmickrisp.dylib` arm64; a Action compilou o engine AOT, gerou o projeto Xcode, validou o IPA sem assinatura e enviou o artifact.

A correção de `KeEnterCriticalRegion` e dos acessos PPC que precisavam receber `base` está incluída no Build 8. O engine arm64 compilou com os 344 arquivos de unidade AOT e os 261 adapters de imports gerados. Isso confirma o build e o empacotamento, não um boot completo do jogo.

O último relatório de aparelho ainda é do Build 7: XEX2 reconhecido, ring Xenos configurado, 24 opcodes draw observados, 5 buffers indiretos, 0 swaps guest e 0 frames decodificados; a execução parou em `KeEnterCriticalRegion` (LR `0x82B537A4`). O Build 8 ainda precisa ser executado no aparelho para confirmar a próxima etapa. Os números de comandos do Build 7 não provam que os draws foram executados pela GPU.

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
