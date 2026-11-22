# Fairy2iOS — auditoria regressiva desde a primeira IPA (22/11/2026)

**Jogo:** FAIRY TAIL 2 v458752, `0100B9801F872000`. **Estado:** o iPhone 17 Pro ainda aborta; **nenhuma IPA com gameplay verificado**. Referência: `log.txt` e `log.prev.txt` fornecidos pelo proprietário em 22/11. O relatório não contém os dados privados do jogo nem substitui uma reprodução no Mac/iPhone.

## Resumo: o que o iPhone comprovou

| Item | Log anterior (otimizações OFF) | Log recente (otimizações ON) |
| --- | --- | --- |
| Fim | SIGTRAP 5 `main+0xbfe2a8` | mesmo |
| Stack | `main+0xc10b90 → main+0xc11928 → main+0xc6ff10 → main+0xc723bc` | mesmo |
| Recurso | G1T `0xfb9ebd24`, `can't create resource Name[Unknown]` | mesmo |
| GPU | encoder, prefetch, snapshot, Metal4, PSO prebuild = 0 | todos = 1 |
| Fonte | RomFS 14.770 entradas, 16 AOC, root/system RDB+RDX abertos | mesmo |
| MapPhysicalMemory | 159 chamadas, união ~2.14551 GiB | mesmo |
| Interceptações | nenhuma recuperação `FAIRY2_KTGL_ORIGINAL_DIRECT_READ_RECOVERED` registrada | mesmo |

A ausência de mensagem positiva não prova que um hook não foi chamado: o código anterior só registra quando consegue recuperar. `bf6f0546bc10` no log é o marcador embutido do host inicial, **não** a SHA da IPA reempacotada.

## Histórico relevante: cada build verde NÃO é um jogo funcional

| Run | Intervenção | Prova / limite |
| --- | --- | --- |
| `44965722551` | Primeira IPA; NSO reescrito, Metal 19.210 shaders | Actions OK, `provisional_profile=true`, `provisional_heap_and_region_checks_skipped_on_linux`; sem gameplay confirmado |
| `44990224107` | VA 4 GiB/global memory | Crash do bin47, pool NVN ultrapassava o filho KTGL 1.25 GiB |
| `44995690307` | Filho KTGL ampliado a 2 GiB | Corrigiu a **sobreposição geométrica conhecida**, mas não o erro de criação G1T |
| `45000495987` | 6 GiB reserva host, 5 GiB root, 5 trampolins ARM64 | iPhone ainda SIGTRAP G1T |
| `45046524330` | Probe cabeçalho G1T | Header em execução rejeitado |
| `45050364099` | Injeção única artificial de G1T | Prosseguiu até outro crash G1S; contorno, não fix |
| `45055194914` | G1T/G1S reais extraídos de RDB/FDATA Drive | G1T 48 B `GT1G0500`, G1S 18.340 B `_S2G5000`, zlib integral verificado |
| `45056917685` | Probe da leitura G1S | Posteriormente observado primeiro read 0/184 para G1S problemático |
| `45064035915` | Probe FS RDB/FDATA | 45/45 leituras HLE `got==wanted`; não prova buffer KTGL |
| `45068245797` | 64 retries | Candidato especulativo rejeitado, sem teste em dispositivo |
| `45075542017` | fallback libz apenas se o inflater falhar | Mesmo crash G1T em dispositivo |
| `45078767146` | fallback leitor direto, traps `+0xc11b80/+0xc11f9c` | Mesmo crash G1T nos **dois** logs novos |

### Paridade executável real, não apenas 4.104 bytes

SHA original NSO0 v458752: `2e16abd340e922d60f177e49239262cee9fcaa8d8e210a5b8df78d92175b5986` (46.127.964 B).
SHA AOT Linux: `64b6e12a8e20ccc28d44f14762f8f823057599ddd84728194f89eacff79fe34f` (47.624.072 B).
**26.301 instruções diferentes** dentro do texto original (`0..0x22d4000`). Em regiões delimitadas:

| Função | Rewrites no AOT |
| --- | ---: |
| Validador G1T `+0x60db9c..+0x60dcf8` | 0 |
| Parser G1T `+0x612000..+0x612400` | 0 |
| Parser G1S `+0x6e7b60..+0x6e7d00` | 0 |
| Adapter de stream `+0xc09500..+0xc09800` | 0 |
| Factory KTGL `+0xc10630..+0xc10c00` | **11**, todos sites `x18` |
| Dispatch direto `+0xc11800..+0xc11980` | 0 |
| Leitor direto `+0xc11b60..+0xc11fa0` | 0 |
| Inflater `+0xc0ef70..+0xc0f100` | 0 |
| Scheduler `+0xc6f000..+0xc73000` | **60** (32 `x18`, 28 `W`) |

Os sites de `x18` na factory são `+0xc10a6c, +0xc10aa0, +0xc10abc, +0xc10ac0, +0xc10ac8, +0xc10acc, +0xc10af0, +0xc10af8, +0xc10b00, +0xc10b04, +0xc10b08`. Precisam teste semântico de preservação, não só igualdade de bytes. Este AOT **não é a IPA assinada**: não inclui patches manuais pós-AOT.

## Causa, memória e referência externa

- Proveniência dos assets **não é o defeito identificado**. O probe `45055194914` descompactou o G1T esperado com prefixo `GT1G0500`, estrutura aceita pelo validador nativo `main+0x60db9c`. Falta provar o que **o objeto guest de stream** realmente entregou na falha.
- O patch do KTGL interno para **2 GiB** eliminou uma colisão concreta entre NVN 1.290 MiB e metadata bin47. Não reverter sem reproduzir a geometria.
- A limitação 60 GiB original → 4 GiB e depois 5 GiB (**cinco trampolins no código guest**) permanece uma alteração com possíveis consequências, não validada como semântica equivalente.
- Nenhum log registra `MapPhysicalMemory refused`; o perfil `mem_map_limit=1` continua assunto de comparação, mas não há prova de que causou o SIGTRAP.
- Referência realmente jogável no iPhone: [ROMANCE OF THE THREE KINGDOMS 8 REMAKE](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/0100C2A01A730000/README.md), KTGL moderno, RDB/RDX/PDRK/IDRK, zlib em blocos 16 KiB, SDK 17.5.3. **Diferença:** `sys_resource=0` e heap comum 4 GiB, não VA 60 GiB original.
- [Atelier Ryza DX](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/0100199023B2E000/game.tsv) tem G1T/G1S, jogável no Mac, iPhone ainda não comprovado. [Age of Calamity](https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/games/01002B00111A2000/README.md) usa KTGL/worker mas SDK anterior.
- O HEAD atual do upstream possui `dm/tools/mod_layout.py` para separar 16KiB RX/W; os três NSOs Fairy2 originais já têm `data_off` além de `text_end` arredondado para 16KiB, portanto essa alteração **não explica** o bug.

## Ações e critérios para qualquer próxima IPA

1. Quarentena da IPA comprovadamente falha `45078767146`, SHA `ef2e6edff30d0072796066d9ae46eb1be0ec27248dbec5b52b958cf001f4c22b`, em `fairy2/colab/transfer_ipa.py`, testada em `test_confirmed_crash_gate.py`. O seletor não a reentrega.
2. **Não disparar novos repacks** por alterações hipotéticas de buffer, retry ou magic. O teste anterior em C criava seu *próprio* stream sintético e não reproduziu o objeto do crash.
3. Antes de afirmar regressão de um patch, diff entre o primeiro IPA assinado `44965722551` e o último `45078767146` nas seções reais `__dmmainx0, __DMmainW/__img, __dmmainx1`, incluindo todos os sites originais, trampolins, flags, hle_svc e host. CRC/compilação não bastam.
4. Precisamos de valores `vtable`, `reader+8..+0x28`, RDB/FDATA offsets, bytes comprimidos, contadores de retorno e estado do producer **na mesma chamada que retorna 0**, comparados com leitura nativa no Switch ou execução Mac. Identificar o erro na **origem**, não injetar um cabeçalho por hash.
5. Só publicar IPA "corrigida" quando teste de execução comprovar passagem além da factory e cena inicial real no iPhone; preservar shaders 19.210, RomFS/AOC externos, menus 30/60 e A/B.

**Veredito:** a falha funcional persiste. A auditoria fundamenta o problema no caminho KTGL guest e expõe as lacunas dos patches sucessivos, mas **não prova ainda a causa raiz do stream inválido**. O rewriter `x18` e as regiões VA são alvos sérios de investigação, não causas demonstradas.
