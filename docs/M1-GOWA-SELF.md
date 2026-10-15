# AscensionRecomp M1.1 — GOWA.SELF reconnaissance

This document contains **only public-format metadata** from the privately supplied SELF. The 8.7 MB user file, and the user's license, were **not committed**.

## User-file findings (local analysis)
- GOWA.SELF length: 8,719,872 bytes
- SHA256: 27898398a0a7075486755dbe74ef913631b5fa8252a71dca04923fd82ef7b1d4
- SCE revision 0x001c; program type 8 (NPDRM)
- NPDRM license type 2 (local), content ID `UP9000-NPUA80918_00-GOWADIGITALVERS1`
- Embedded PPU big-endian ELF64: 8 program headers, entry 0x8283f8, 31 section headers
- PT_LOAD[0] 8,447,080 bytes; PT_LOAD[1] 247,280 bytes in file / 2,389,816 in memory; other auxiliary segments
- The embedded ELF header is not the decrypted ELF. `tools/unfself.py` only unpacks debug 0x8000 fSELF, not this retail 0x001c SELF.

## Cross-check from existing PsTJon log
An earlier NPUA80918 PsTJon session logs
- `Loading RAP file UP9000-NPUA80918_00-GOWADIGITALVERS1.rap`
- `ppu-...-GOWA.SELF` CPU cache, and a PPU LLVM compilation queue.
This is **not** proof that a decrypted ELF file is already accessible to us.

## Privacy and actions
- Never publish commercial executable bytes, title license .rap, private IDs or keys to any public repository/artifact.
- Read-only tool `tools/self_inventory.py` prints metadata into JSON (no binary segments).
- Tests use generated fake SELF data only.
- User should check the iOS RPCS3 profile's installed license under `dev_hdd0/home/00000001/exdata/` and/or the emulator license import UI. The correct RAP basename matches the content ID. Avoid uploading the license to a public GitHub repository.
- Preferred next gate: use RPCS3's legal-title SELF decryptor locally to export **GOWA.ELF**; pass that genuine decrypted ELF to `ps3recomp/tools/ppu_loader.py`.
- No game code lifted, no iOS IPA, no frame-rate evidence yet.
