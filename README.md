# AscensionRecomp — PS3 -> iOS ARM64 (M0)

**Alvo exclusivo:** God of War: Ascension (PlayStation 3), executado futuramente em iPhone 17 Pro. Projeto de pesquisa de recompilacao estatica, independente de PsTJon/KosmicKrisp.

## Estado verificavel
- M0: ambiente de analise + testes de ELF + compilacao experimental do runtime ps3recomp ARM64/macOS pelo GitHub Actions.
- **NAO** executa Ascension, nao contem EBOOT, nao oferece uma IPA jogavel.
- M1 depende de um **EBOOT.ELF descriptografado do jogo legitimamente obtido**, fornecido em privado pelo proprietario.
- PS3 usa PPU PowerPC (ELF64 big endian) e SPU (ELF32 big endian). Recompilacao antecipada nao elimina a necessidade de HLE LV2, RSX, sincronizacao, memoria e shader translation.

## Isolamento
Somente a branch AscensionRecomp. Nao modificar main, PsTJon-KosmicKrisp, MadeiraJon, VitaJoN ou qualquer outra.
Somente o workflow .github/workflows/ascension-recomp-m0.yml, com filtro exclusivo de branch.
Cada incremento: um commit e um disparo de workflow, nunca multiplos builds por commit.

## Origem tecnica
- ps3recomp https://github.com/sp00nznet/ps3recomp (pin: a2c20108af45174dbb7d3e2f87f6acaaef09c6b4)
- Referencia iOS com Metal: https://github.com/andrebrumdev/gow2-recomp
- RPCS3 (oraculo de comportamento): https://github.com/RPCS3/rpcs3
- Material protegido pelo direito autoral NAO esta nem sera incluído no repositorio.

## Preflight local (macOS, Linux ou Python 3)
```bash
python3 -m unittest discover -s tests -v
python3 tools/elf_inventory.py --elf /caminho/seguro/EBOOT.ELF --out ascension-manifest.json
# Opcional: --spu /caminho/para/modulo_spu.elf (repetivel)
```

Se so houver EBOOT.BIN SELF criptografado, extraia o EBOOT.ELF de SUA propria copia com ferramentas adequadas. Nao altere nomes nem publique chaves, jogos, arquivos PKG/RAP ou firmware.

O manifest JSON e diagnostico estrutural: SHA256, formato, arquitetura, entrada, PT_LOAD e verificacoes de limites. Nao contem bytes de codigo do jogo. Compartilhar somente o JSON inicialmente.

## Criterios de passagem
- M0: testes locais validam ELF64 PPU/ELF32 SPU; CI compila libps3recomp_runtime.a macOS/ARM64 e guarda checksums.
- M1: loader real do Ascension extrai image/functions/imports/TOC com dados reprodutiveis.
- M2: lifter PPU gera C/C++ e registra HLE NIDs; valida desvio indireto e TOC.
- M3: identificar/liftar programas SPU, DMA e SPURS com verificacao cruzada RPCS3.
- M4: boot nativo iOS com runtime, entitlements e VFS, sem conteúdo de jogo incorporado.
- M5: RSX -> Metal direto ou via Vulkan/KosmicKrisp, comparacao empirica de fidelidade.
- M6: gameplay e transicoes; cronometragem PPU, SPU, RSX, GPU; erros e crash traces.
- M7: estabilizar 30 fps reais sem corrupcao, medir p5, p50, p95 e tempo de quadro.
- M8: avaliar 60 fps, upscaling/framegen somente apos fidelidade validada.

**Nunca marcar etapas como aprovadas por apenas compilar ou abrir uma tela vazia.**
