# AscensionRecomp M2.0 — PPU manifest boundary repair and CI native-lifter proof

Target remains **God of War: Ascension PS3, NPUA80918**, iPhone 17 Pro arm64; real 30 FPS stable is goal, not yet achieved.

## What is actually proven
- A privately decrypted GOWA.ELF was audited locally, SHA256:
  4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5.
- In real ELF sections with SHF_EXECINSTR, 1,664,866 instruction-sized PowerPC slots.
  This is an upper-bound structural scan, not proof all words are instructions.
- 7,643 PPU entry descriptors, 350 firmware imports.
- True executable last byte exclusive: **0x669F8C**. Pass this to upstream
  `ppu_lifter.py --code-end 0x669f8c`; do NOT extend a code range into data.
- **Two** loader function intervals cross executable section boundaries:
  - 0x10200..0x10338 must clip to 0x1022c (268 extraneous bytes).
  - 0x6652d8..0x81e468 must clip to 0x6652fc (1,806,700 extraneous bytes).
  In total, clipping excludes 1,806,968 bytes and preserves 7,643 starts.
- Scanning direct/conditional branches yields 12,001 unique direct linked targets, of which
  11,766 are not in the OPD start set. **Do not** interpret these as 11,766 missing functions:
  they include intra-function calls, local thunks, and potential data false positives.
- Very large function intervals may still need split/sanity checks even inside .text,
  without per-scene hacks. RSX/SPU remain entirely unported.

## What the public CI validates
- Builds pinned PS3Recomp runtime on macOS arm64, as before.
- Generates a synthetic 2-function PPC64/Cell-LV2 ELF with no Sony or game code.
- Executes pinned PS3Recomp's **real** ppu_loader.py and ppu_lifter.py
  (with --functions, --hle-stubs and --code-end).
- Uses clang++ -fsyntax-only on the generated C++.
- One commit, one workflow run, only AscensionRecomp; no game binary or license on GitHub.
- **It does not recompile the commercial Ascension ELF in GitHub Actions.**

## Private M2 next gate
1. Run the private `GOWA.ELF` with pinned loader and manifest sanitizer,
   `--code-end 0x669f8c --jobs 2 --chunk-lines 120000`, benchmarking memory and elapsed time.
2. Translate PPU functions into host C++ and measure missing opcode coverage,
   generated C++ errors, indirect branch targets, HLE/import mapping, SPURS.
3. Recompile SPU jobs and map scheduler/DMA; compare against PsTJon RPCS3 logs.
4. Only then link iOS host, evaluate RSX Metal/KosmicKrisp and produce an honest IPA.
