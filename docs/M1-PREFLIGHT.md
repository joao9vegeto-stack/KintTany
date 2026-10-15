# M1 (preflight) — God of War Ascension PKG, 2026-10-14

- Param.SFO metadata read from user-supplied file locally, **not committed**:
  - TITLE_ID NPUA80918; TITLE God of War: Ascension; VERSION 01.00; APP_VER 01.12
  - CATEGORY HG, PS3_SYSTEM_VER 04.3000, TARGET_APP_VER 01.11.
- The supplied EBOOT.BIN is a 74,160-byte SCE SELF, with an embedded big-endian ELF64 PowerPC machine 21 header (offset 0x90). **The presence of an ELF header does not mean decrypted code is present.**
- SHA-256 (local file identification only):
  - EBOOT.BIN: 006942ded7ea5cfcf1236205d2f1e81bbb06b253bcc39d99a718bfca1ab6a1d8
  - PARAM.SFO: d24746836c9d2ad86033c0108c96a8e4144b2afee8b0ab0d91fc56634abea16d
- The Title ID comes from SFO; ELF/SELF container alone doesn't cryptographically attest it belongs to that title. Do not claim matching executable verified until decrypted.
- New tool: tools/package_preflight.py; tests use synthetic bytes only, no game code.
- Still blocked for PPU lift until a decrypted EBOOT.ELF is available from user's legally held game; PS3Recomp loader reads the ELF and needs imports/OPD, then PPU/SPU discovery.

## Next steps
1. Ask user to export EBOOT.ELF from their own RPCS3, using Utilities > Decrypt PS3 Binaries on desktop, or an enabled decrypted executable dump.
2. Request folder filename listing for NPUA80918/USRDIR to find .self/.sprx modules, not assets.
3. Validate decrypted ELF with tools/elf_inventory.py and ppu_loader.py, then lift.
4. Keep all game binaries PRIVATE, never upload to GitHub; commit only metadata/parser changes.
