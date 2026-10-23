# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** `41560816`  
**Branch:** `XOWUE`  
**Estado:** Build 2 confirmado; runner iOS de desenvolvimento; ainda não chega ao menu nem produz frame do jogo.
**IPA:** `XOWUE-Build-2.ipa`, `CFBundleVersion=2`, arm64, unsigned. [GitHub Actions](https://github.com/joao9vegeto-stack/KintTany/actions/runs/39897706560).

## O que está neste branch

- Recompilação PPC AOT: 344 unidades de funções mais o mapa de despacho.
- Loader XEX2/LZX, mapeamento PPC 32-bit, tabela de despacho e execução do entry point.
- 24 adapters básicos em 261 imports; 237 ainda param de forma explícita com nome, LR, r3–r10 e eventos PPC recentes.
- A pasta local aparece em **Arquivos > No Meu iPhone > XOWUE > Jogos**. O app detecta `default.xex` na raiz ou uma pasta abaixo, e usa o seletor nativo do iOS para importar uma pasta completa ou um XEX.
- `diagnostico.txt` e `crash.txt` são gravados na raiz Documents do app, visível em Arquivos > No Meu iPhone > XOWUE. Há botões para compartilhar os dois logs.
- Ícone Wolverine profissional em aço, amarelo e azul; número Build vem de `CFBundleVersion` e aparece na tela.
- `Runtime/Graphics/KosmicKrisp/` mantém o patch iOS Metal WSI da branch `PsTJohn`, no commit `db014165eb39429ae37d1946db6fc83c600c63b3`.

## Bloqueio técnico atual

O smoke host chega a `ExCreateThread` (LR `0x82C4C110`, stack 32 KiB, worker `0x82690678`). A rotina worker entra em um loop de mensagens. O runtime ainda não tem scheduler PPC, contexto completo de threads nem objetos de espera. Não retornar sucesso fictício mantém esse erro visível.

KosmicKrisp fornece o lado Vulkan→Metal/WSI. XOWUE ainda precisa de um frontend Xenos/D3D, tradução de comandos/shaders, superfícies e resolução de render targets. O patch está versionado, porém ainda não é compilado nem ligado ao app. Também faltam MMIO, integração WGame, XMA/áudio e teste em iPhone. Nenhum frame do jogo foi comprovado.

O app não inclui `default.xex`, DLC, title update ou assets. Não os adicione ao Git.

## Teste local

No host Clang 18, recompile os adapters e rode:

```bash
python3 XOWUE/Runtime/generate_runtime_stubs.py \
  --ppc-dir XOWUE/generated/ppc \
  --recompile-log XOWUE/generated/config/XOWUE-recompile.log \
  --output build-runtime-clang/runtime-generated/XOWUEImportStubs.cpp
cmake --build build-runtime-clang --target XOWUEHostSmoke -j2
./build-runtime-clang/XOWUEHostSmoke /caminho/local/default.xex boot
```

## IPA

Build 2 concluiu no Actions run #11. O app compilou com Build 2 visível por `CFBundleVersion`, mas a pasta/seletor e a execução precisam de teste físico no iPhone. O smoke host ainda para em `ExCreateThread`; não há frame comprovado. Consulte `HANDOFF-XOWUE.md` para hashes, logs e limites completos.


`.github/workflows/xowue-ios.yml` cria um IPA unsigned em cada execução bem-sucedida. O número conta somente os builds IPA bem-sucedidos desde o Build 1 (run #8), então uma tentativa falha não pula a numeração. Consulte `HANDOFF-XOWUE.md` para os resultados do Actions, hashes e próximas etapas.
