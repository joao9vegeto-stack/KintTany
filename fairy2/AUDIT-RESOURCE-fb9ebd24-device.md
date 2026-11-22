# Fairy2iOS - resource factory crash, 22 November 2026

## Device evidence: two NEW iPhone runs after 6GiB/5GiB IPA

Both log.txt and log.prev.txt in the current conversation show exact same fatal trap: CRASH sig=5 pc=main+0xbfe2a8. The complete formatted message, including the part after the initial 48-byte dump, is "can't create resource Name[Unknown] Hash[0xfb9ebd24]".

In both runs:
- stack: main+0xc10b90, main+0xc11928, main+0xc6ff10, main+0xc723bc;
- the guest code at main+0xc108ec dispatches the type resource factory through a vtable; main+0xc108f0 saves the NULL return; main+0xc10b8c calls the deliberate error trap;
- 6GiB guest reservation 0x180000000, alias 0x158000000, 5GiB internal allocator root; 128MiB guest heap; no 4GiB-root cap;
- GPU NVN pool 0x3816ac000..0x3d20ac000, corrected 2GiB KTGL child, relocated bin47 0x3ed800178 with no reported pointer corruption;
- 14,770 RomFS entries and 16 AOC containers mount; 3,206 reads / 64.4MiB logged;
- immediately before fatal trap: successful OpenFile rom:/Motor/ReleasePackage/KIDS_PLATFORM_NX/release/0x8baaa1ce.fdata (RomFS entry 13660), then more guest MapPhysicalMemory.
- In first run DM_NVN_ENC_THREAD=0, PREFETCH=0, PSO_PREBUILD=0, PSO_MTL4=0; in second run these graphical options enabled. Identical fatal trap.

No ResultOutOfMemory, ReadFile error, RED corrupted-data line, or bin47 corruption appears in supplied logs at the fatal site. This does NOT prove their absence in internal guest code.

The previous 6GiB/5GiB hypothesis was experimentally falsified as a *sufficient fix*. CI success only proves the IPA packages correctly; it did not establish runtime success. Do not enlarge virtual memory again without new cause-specific evidence.

## Relevant primary source comparison

Pinned NXNative b526a50b85e4cfa3142c111e1ad491d9fd11f0eb:
- dm/tools/romfs_image.py: 32-byte DMROMFS1 header, 24-byte indexed entries at image end; entry 13660 is a packed guest file, not an ordinary iOS path.
- dm/host/hle_fs.c: OpenFile looks up the guest path and ReadFile uses pread into the image entry's data offset.
- dm/gfx/tools/shader_split.py: IDRK0000 header containing entry_size, stored_size, inflated_size, FileKtid, TypeKtid and flags; compressed chunks use LZ4 or zlib.
- DeathChaos25/fdata_dump at https://github.com/DeathChaos25/fdata_dump declares support for FAIRY TAIL 2, with independently implemented RDB.cs.
- https://github.com/umin135/katanaDOCS/blob/main/01_katana_engine_asset_system.md documents RDB/RDX to FDATA resource resolution. This reference covers Koei Tecmo titles but does NOT establish the exact failed asset without looking at this game's bytes.

The target resource hash 0xfb9ebd24 must be checked in actual root.rdb/system.rdb and the associated RDX/FDATA content. The last successful fdata OpenFile does NOT establish that the requested record was found, decompressed, or accepted by the factory. Missing aoc*/file.prio and some TEST-only SplitDB json files are not sufficient evidence for this fatal resource.

## Next factual gate before any other Action

The exact device RomFS source was generated in Colab and stored on Drive: 7,889,449,169 bytes, SHA256 recorded in handoff 5816aed06355a7de7913768db002b256c7cec8d0bbe70fe08311562a46933fd3. The connected Google Drive file download interface refuses it because of its 256MiB download limit.

Use authenticated partial HTTP Range reads in a one-cell Colab auditor: read only DMROMFS1 header, index and the five relevant guest files (root.rdb, root.rdx, system.rdb, system.rdx, 0x8baaa1ce.fdata). Report matching KTID/TypeKTID and exact record bounds and first decompressed chunk. The user-uploaded log files have no asset bytes from which these assertions could be proved.

A self-contained notebook is included as a conversation artifact. No shaders or host binaries need compilation for this audit. Never claim that the problem has been repaired until on-device gameplay progresses beyond main+0xbfe2a8.

## Quarantined artifact

The 6GiB IPA from run 45000495987 (SHA-256 df6cd6c826a3218fd965b03161ea2355cf348c13c369e13f2afb7dff74c953c2) is CONFIRMED to crash. fairy2/colab/transfer_ipa.py refuses this run and digest BEFORE downloading its 1.62GiB ZIP. Do not label it fixed.
