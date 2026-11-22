# Fairy2iOS — Revisão KTGL baseada em ports comprovados (22/11/2026)

**Escopo:** FAIRY TAIL 2, Title ID `0100B9801F872000`, update v458752. A reprodução do crash no iPhone continua pendente de correção. Este relatório **não certifica uma IPA funcional**.

## Referências escolhidas por semelhança técnica (não por tamanho)

| Port NXNative | Plataforma verificada no próprio README | Subsistema pertinente |
|---|---|---|
| [Romance of the Three Kingdoms 8 Remake](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/0100C2A01A730000/README.md) | **iPhone** | KTGL moderno, RDB+RDX+FDATA, PDRK/IDRK, modo 4 zlib em blocos ≤16 KiB; SDK 17.5.3 |
| [Hyrule Warriors: Age of Calamity](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/01002B00111A2000/README.md) | **iPhone** | KTGL KIDS task/resource scheduling, RDB, memória e orçamento real do áudio |
| [Atelier Ryza DX](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/0100199023B2E000/README.md) | **Mac**; iOS **não verificado** | KTGL, G1T e G1S, zlib em blocos |

Não tratar o sucesso de Actions como sucesso no dispositivo. A branch BioiOSMutant é origem de automações, mas seu README na época não certificava boot do jogo; não deve ser a única referência de compatibilidade.

O motor NXNative fixado nas branches Fairy2iOS, BladesTime e BioiOSMutant é o mesmo **b526a50b85e4cfa3142c111e1ad491d9fd11f0eb**. Em Git compare BioiOSMutant→Fairy2iOS não há mudanças compartilhadas em `patches/` ou `tools/`: os desvios acumulados estão em `fairy2/` e seus 19 workflows.

## Prova com bytes reais do usuário (sem enviar código de jogo ao repositório)

Fonte: workspace original verificado `fairy2-work.tar.zst`, 113117348 bytes, SHA-256 `61890137d23a64c46a3c8b0799a863537508aba34c0c8eb688d47d9d2e1ba10a`.

- NSO original compactado: `extract/v458752/ExeFS/main`, 21719564 bytes, SHA-256 `32294f4f27d9b18438971521d72cc049a6e0b6d795edd195f7ea39402411a189`.
- NSO original descomprimido NSO0 text/ro/data: 46127964 bytes, SHA-256 `2e16abd340e922d60f177e49239262cee9fcaa8d8e210a5b8df78d92175b5986`.
- `patched_v458752/main.patched.bin`: 47624072 bytes, SHA-256 `64b6e12a8e20ccc28d44f14762f8f823057599ddd84728194f89eacff79fe34f`.

**Resultado:** 10 trechos críticos, **4.104 bytes ARM64 idênticos antes e depois do AOT**, incluindo parser G1T/G1S, adapter, as **duas rotas de leitura**, inflater e factory. Esta é uma prova *localizada*: não diz que todas as outras instruções, o host ou os objetos de memória são corretos.

Verificador reproduzível: `fairy2/scripts/ktgl_reference_baseline.py`. O guard `fairy2/scripts/prepare_actions.py` exige essa prova **a partir do workspace recuperado do Colab, antes do download da RomFS 7,9 GB**. O workflow `fairy2-ktgl-reference-baseline.yml` valida o código com fixtures Linux e publica somente o relatório JSON do **workspace verdadeiro**, usando o handoff/Drive autorizados; não publica NSP, ROMFS, NSO nem AOT.

## Correção da análise técnica anterior: NÃO existe somente uma rota assíncrona

Disassembly ARM64 original (v458752), verificado por instrução:

**Rota A — tarefas/eventos:** `main+0xc10630` chama factory `main+0xc10690` com contexto de produtor; no modo correspondente há produção de chunks por `main+0xc10d80`, envolvendo `nn::os::SignalEvent`.

**Rota B — leitura direta:** `main+0xc1191c` zera o par de opções do produtor; `main+0xc11924` chama a **mesma factory** `main+0xc10690`, que pode usar leitor virtual `main+0xc11b60` e inflate `main+0xc0ef70`, conforme a variante de compressão. **Esse caminho não pressupõe passar por `c10d80`**.

No leitor direto, `main+0xc11b80` carrega dois campos de `[reader+0x8]`; se o primeiro é nulo, `c11b98` cai no retorno zero em `c11f9c`. Trata-se de **uma possibilidade real no código do jogo**, *não* da prova de que o reader falho no iPhone seguiu essa rota. Precisamos identificar o vtable verdadeiro e o estado inicial do reader na execução.

O adapter `main+0xc09728` encaminha `[adapter+0x10]` ao backing stream virtual `+0x20`. Tanto G1T quanto G1S sofrem falha antes ou na leitura nativa, mas não se deduz apenas disso se a causa é cursor, buffer, inflate ou worker.

## Fatos do iPhone que continuam válidos

- No run **45064035915**, as **45 leituras HLE FDATA monitoradas** retornaram `wanted==got`; isso **não comprova o conteúdo já descomprimido**.
- G1T `0xfb9ebd24` 48 bytes e G1S `0xac9ed13e` 18340 bytes: origem Drive decodificada e SHA verificados; ambos modo4 zlib. Três G1S anteriores tiveram seus cabeçalhos completos de 184 bytes; o G1S seguinte retornou `0/184` e o parser/factory retornaram NULL, seguido de SIGTRAP `main+0xbfe2a8`.
- A alteração anterior que substituía um G1T de 48B era um **contorno, não correção**. O repack subsequente de 64 tentativas (`45068245797`) era hipótese sem demonstração de atraso; o usuário rejeitou a IPA. **Seu run e SHA foram excluídos da seleção automática para Drive, sem falsamente declarar crash confirmado** (testes Linux Actions `45073270825`).

## Critérios para a próxima alteração de runtime

1. Identificar de maneira inequívoca qual dos **dois backings** chegou ao parser na execução que falha (vtable do adapter + `[adapter+0x10]`, vtable do backing).
2. Na mesma chamada, comparar os campos de início/fim/cursor/estado do buffer, retorno da descompressão e conteúdo dos primeiros bytes com os 184 bytes esperados. Para a rota direta, começar pelas condições do `c11b80…c11b98`; para o produtor com worker, verificar estado de conclusão e evento. Nunca extrapolar um para o outro.
3. Corrigir **a fonte comum provada do estado incorreto** (host/semântica do worker/objeto/dados), no local de implementação que atende também aos ports KTGL, com teste específico que falha antes do patch e passa depois.
4. Só então repack host mínimo, mantendo shaders/AOC/RomFS externos, e exigir **uma cena real no iPhone** antes de chamar de corrigido.

**Não gerar outra IPA de tentativa de leitura, não aplicar NOP no parser, não injetar ativos, não inflar heap aleatoriamente.** O presente trabalho termina no gate de proveniência/paridade e no diagnóstico correto de dois caminhos; não inventa uma resolução ainda não medida.
