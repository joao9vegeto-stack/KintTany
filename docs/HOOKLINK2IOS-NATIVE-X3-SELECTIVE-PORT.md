# HookLink2iOS — port nativo seletivo X1/X2/X3 (sem recompilar shaders)

## Fatos e fonte

A IPA íntegra existente, `OcarinaOfTime-HookLink2iOS.ipa`, está no Drive: `1cd85ZhbrJXZo5VK1GMQPxA-8R17qpPPD`, 3.476.939.759 bytes, SHA-256 `448b28b4217b397299a1ec48fad03a3690fd29c60422aabacad181fb45b15bf7` (verificada por Actions). O build original utilizou `nxnative cf2a2fecc6ce3fb841131ffeffa90915cdadf109`. Na auditoria de 22/11, o upstream HookLink já estava em X3 (4.0), usando `nxnative hooklink ee3ce6a02bc737d38795f0a96cce494cee7a799c`.

**Este NÃO é um update completo do engine X3.** O próprio changelog original declara que a cadeia X3 alterou o tradutor de shaders e requer recompilação de shaders. Misturar todo o X3 com a imagem Metal antiga sem validar compatibilidade causaria crashes e erros gráficos. O objetivo deste caminho é portar código **nativo** aplicável sobre a base 1.8.5 e garantir que a imagem Metal permanece byte-idêntica à original.

## Patches de código reais

| Patch upstream | Aplicação sobre o runtime 1.8.5 | Benefício esperado | Limitação |
|---|---|---|---|
| `dsi-hub/nxnative@2ce8521f3cd7` | `dm/gfx/nvn/nvn_mtl.m`: `POOL_SPARES` 16 → 64 | Reutilizar buffer das tabelas de textura; upstream reportou cerca de 11% menos trabalho de CPU por desenho na cena de teste | Não garante +11% FPS nem comportamento idêntico em iPhone |
| `dsi-hub/nxnative@c03d45bd64d2` | `game.tsv`: `mem_alias` 8 → 16 GiB e reserva virtual correspondente | Evitar esgotar o espaço virtual durante longas sessões/cutscene da Master Sword | Espaço virtual não acrescenta RAM física; depende do entitlement iOS já presente |
| `dsi-hub/nxnative@c9aaed502b3d` | `dm/games/game.py` + `dm/gfx/nvn/nvn_mtl.m`: mapa dos estágios NDSR e bypass da cadeia intermediária MetalFX | Evitar que a rede de upscaling própria do jogo rode antes do MetalFX; upstream aponta redução de 5–10ms de GPU em certos quadros | Backport adaptado ao runtime antigo, sujeito a teste real no iPhone; mecanismo desativa bypass se MetalFX recusar |

Não foram forçados: nova tradução de shaders, grandes reescritas de layout de módulos, GPU occlusion experimental, heurísticas de escrita em páginas revertidas pelo X3 e alterações amplas no gerenciamento de pools que não passaram testes de estabilidade no upstream.

## Pipeline de host-only relink

1. Download por HTTP Range de 16 MiB da IPA existente do Drive com SHA-256 integral.
2. Clone do **mesmo commit original** do engine; validação de SHA do `dmsh_chain.lock` e do cabeçalho de cadeia.
3. Extração do binário Mach-O arm64 original do IPA e das seções embutidas `__dmmainx0`, `__dm...W,__img`, `__dmmainx1` (mesmo procedimento para `subsdk0` e `sdk`). Recuperação das tabelas `*.fixups.tsv` sem executar `patch_nso`.
4. Aplicação seletiva de patches em código Objective-C/C e no perfil. Uso do `gen_embed.py` do engine original para linkar **as mesmas páginas já reescritas** em um novo host iOS.
5. **Xcode compilando o host iOS nativo e os shaders utilitários internos do host**, mas nunca `shader_split.py`, `dmsh_build.py` nem o tradutor de shaders de jogo. A imagem Metal NVN preexistente permanece no IPA.
6. Verificação das seções ARM64 do jogo **uma a uma, byte por byte por SHA-256**, comparando Mach-O original com o novo. Uma divergência aborta o build.
7. Repack da IPA original substituindo **somente** executável host (além dos defaults do launcher), assinatura e validação CRC/SHA-256 das bibliotecas de shader, preservando compressão ZIP e RomFS externo. Bloqueio de IPA final acima de 4.000.000.000 bytes.
8. Upload do artefato contendo IPA, relatório de port nativo e relatório de repack. O notebook Colab escolhe a última IPA válida do Actions, baixa em chunks e envia ao Drive em upload resumível de 16 MiB.

## Validação e limites

`tests/test_hooklink2ios_native_relink.py` gera Mach-O sintético e verifica que as seções originais não podem mudar silenciosamente. `tests/test_hooklink2ios_perf_repack.py` valida RomFS, launcher, partes Metal e compressão. O workflow roda esses testes **antes do download** de 3,48 GiB.

O ganho real de CPU/GPU, a ausência de novos bugs e 30/60 FPS constantes **só podem ser comprovados em execução no iPhone 17 Pro**. Frames gerados pelo MetalFX não equivalem a 60 FPS reais de simulação e de input. O port é intencionalmente parcial para maximizar compatibilidade com a imagem de shaders atual.

### Referências

- [Changelog HookLink original X1/X2/X3](https://github.com/dsi-hub/HookLink/blob/main/CHANGELOG.md)
- [Upstream aumento de tabelas de textura](https://github.com/dsi-hub/nxnative/commit/2ce8521f3cd7)
- [Upstream alias 16 GiB](https://github.com/dsi-hub/nxnative/commit/c03d45bd64d2)
- [Upstream bypass completo do upscaler NDSR](https://github.com/dsi-hub/nxnative/commit/c9aaed502b3d)


## 2026-11-23 — correção da regressão gráfica / pressão de memória

**Evidência do log real no iPhone 17 Pro:** o renderizador passou de 1.299 MB residentes (frame 600) para 4.432 MB (frame 900); chegou a 5.461 MB (frame 1500). `MapPhysicalMemory` recusou oito pedidos de `0x15000` com 6,96 GB já retidos e apenas 0,68 GB de folga. Resolução dinâmica variou de 1440×810 até 960×540. O jogo continuou apresentando frames; não houve shader ausente nem GPU hang explícito. Isso não prova que o corte de memória, isoladamente, produziu a tela preta.

**Correção de regressão (no host):** `DM_HOOKLINK_X3_CHAIN` agora fica **0 por padrão**. O código X3 completo permanece disponível como modo experimental (`1`), mas seu bypass de passes NDSR deixa de atuar silenciosamente. Preserva-se o comportamento funcional do host 1.8.5: o jogo produz os passes intermediários; `DM_UPSCALER=metalfx` pode continuar substituindo somente o estágio final reconhecido, sem exigir imagens intermediárias que o X3 tenha omitido. O renderizador registra explicitamente no log `NDSR whole-chain bypass: OFF`. `DM_FRAME_MODE` 30, 30+FG e 60 não foram removidos; shaders, RomFS, guest ARM64 continuam byte-idênticos à IPA fonte.

**Recuperação de memória:** perfil de iPhone passa a usar `DM_NVN_WS_MB=4800` como orçamento de atuação **antecipada**, não como limite físico de alocação. A função nativa preexistente `alias_retire_idle` considera 85% desse orçamento para começar a remover texturas *compartilhadas que não sejam referidas por nenhum objeto vivo e estejam ociosas por pelo menos 64 submissões*; tenta voltar a 75%. Isso evita elevar o limite de jetsam ou cancelar o cutoff de segurança. A eficácia depende do conjunto de texturas realmente elegíveis; não é garantida. Override de usuário em `Documents/env.txt` pode substituir esse valor. Não alteramos a reciclagem dos heaps (`DM_NVN_RT_RECYCLE`) nem ativamos GPU occlusion experimental.

**Validação necessária:** num novo log deve aparecer `NDSR whole-chain bypass: OFF`, nenhuma recusa de `MapPhysicalMemory` durante o teste, frame-resident mais baixo nas entradas/saídas de áreas, e cena 3D preservada durante a variação de resolução. O build de host-only relink precisa passar testes, SHA dos guest pages e SHA dos shaders. A execução no iPhone continua indispensável antes de declarar o defeito resolvido.

**Fontes comparadas:** [changelog HookLink X2.0.1/X3](https://github.com/dsi-hub/HookLink/blob/main/CHANGELOG.md), [nxnative NDSR X3](https://github.com/dsi-hub/nxnative/commit/c9aaed502b3d), [nxnative host original `cf2a2fecc6ce`](https://github.com/dsi-hub/nxnative/tree/cf2a2fecc6ce3fb841131ffeffa90915cdadf109).
