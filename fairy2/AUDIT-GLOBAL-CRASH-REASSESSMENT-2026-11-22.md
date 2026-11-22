# Fairy2iOS — global reassessment of repeated iPhone crashes (2026-11-22)

**Game:** FAIRY TAIL 2, title 0100B9801F872000, update v458752.  
**Status:** NOT PLAYABLE; no verified crash fix.  
**Reviewed branch:** Fairy2iOS at c38e72a5834013895b7f4bd7954754e67f52f1c5.  
**Last built candidate:** Actions 45056917685, G1S ReaderTrace, build commit 825df676fe8087dd47ab84a5ea7fcf4a37e538c9, generated IPA SHA-256 `5f713b1a06bdf8d8fcff63bd29d69cd3a5cff280f5cd42065973919c0d81c94a`. This was a host build and checksum validation, **not** a successful iPhone boot.

## Evidence timeline (not interchangeable failures)

| Provenance | Observed evidence | Correct conclusion |
|---|---|---|
| 44990224107 | main+0x227bd74 dereferences corrupted KTGL allocator free-list bin 47 | real invalid pointer; size guesses were not an adequate fix |
| NoOverlap builds | 2 GiB KTGL child moved clear of NVN pool, bin 47 no longer reported corrupt | resolves that overlap, not all startup failures |
| 45000495987 | two device logs both SIGTRAP at main+0xbfe2a8, Hash[0xfb9ebd24] | increasing 6GiB/5GiB VA is not a sufficient startup fix |
| 45046524330 | iPhone G1T trace: main+0x612120 rejected input header; G1T factory returned NULL | asset integrity and runtime parser behavior must be distinguished |
| 45050364099 | one-shot 48-byte G1T retry passed its validation; next failure G1S Hash[0xac9ed13e] | per-resource rescue is NOT a global root-cause repair |
| 45055194914 | exact Drive source G1T and G1S RDB/RDX/FDATA, full SHA/decompression verified | missing/corrupted on-Drive source records are disproved for these two assets |
| 45056917685 | 18 G1T/G1S branch probes and first G1S 184-byte read diagnostic built, SHA-checked | no iPhone G1S reader-return/first24 log has been supplied in the retrieved evidence |

## Source-byte integrity, exact

- RomFS source: 7,889,449,169 bytes, 14,770 entries. 16 external DLC containers.
- G1T: FileKTID `0xfb9ebd24`, TypeKTID `0xafbec60c`, 48 bytes, SHA256 `558ada8c563fe44fa18d894d01f39e8b1a230b26ad1bcd0782743797f815e494`.
- G1S: FileKTID `0xac9ed13e`, TypeKTID `0x7bcd279f`, 18,340 bytes, 16,384+1,956 decoded zlib chunks, SHA256 `edb3bceed3c426cfe5b851d78f2e7f56168abe8ac5d6aac3a6927bdaf6e3535a`.
- Both records belong to system.rdb through system.rdx marker zero, FDATA `Motor/ReleasePackage/KIDS_PLATFORM_NX/release/0x38f972af.fdata`. The last opened other FDATA file is not evidence of a missing record.
- Existing game shader map: 19,210 entries; Metal shader image SHA256 `ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b`.

## Verified upstream comparison

The pinned NXNative `b526a50b85e4cfa3142c111e1ad491d9fd11f0eb` and upstream `main` have matching core `h_fs_ReadFile` logic at `dm/host/hle_fs.c`: FH_OUT/FH_IN 16-byte-aligned handles, IMG_H image entry bounds, `pread` loop with EINTR/EFAULT handling and returned count. There is no demonstrated pinned-vs-head regression in this routine. The direct guest stream reader, resource factory ABI, or the guest's in-memory record may still fail: do NOT infer that host pread was successful just because source FDATA bytes exist.

Upstream sources:
- https://github.com/seedds/nxnative/blob/b526a50b85e4cfa3142c111e1ad491d9fd11f0eb/dm/host/hle_fs.c
- https://github.com/seedds/nxnative/blob/main/dm/host/hle_fs.c
- https://github.com/seedds/nxnative/blob/main/docs/reference/services.md

## Global root-cause decision gate

Identify the tested IPA's SHA from its on-device provenance and obtain the *same device run's* `log.txt` and `log.prev.txt`, especially lines beginning `FAIRY2_G1S_READER`, `FAIRY2_G1T_TRACE`, `FAIRY2_G1S`, `fs `, `[RED]`, and `CRASH`.

The 45056917685 G1S instrumentation should show the guest stream's first-read result, requested 184-byte header and first24 bytes. Interpret **only after correlating the same trace event and call stack**:

1. **Returned count < 184:** trace actual virtual stream implementation, underlying RDB/FDATA cursor, read dispatch, decompressor and `ReadFile` output. Repair the *common stream/reader* semantics; do not replace individual resources by hash.
2. **184 returned but header is zero/wrong:** trace destination pointer, caller/callee AArch64 ABI, guest memory protection/writeback, buffer lifetime and stream cursor. Compare guest expected G1S source prefix `5f53324735303030` (`_S2G5000`) before changing file bytes.
3. **184 returned and header valid:** determine first taken failure among G1S header validation, body read, allocator, native parser return and factory wrapper. Repair the *specific proven failure*, not the final SIGTRAP.
4. **Different crash location/signature:** do not force it into this hypothesis; correlate the new PC/stack and first fault to the earlier KTGL invariant and host logs.

Prohibited false fixes: NOP of resource-factory abort, arbitrary heap/VA enlargement, fabricated resource pointer, per-hash G1T/G1S payload substitution, patched RomFS bytes, full shader rebuild without shader evidence.

## Distribution and verification

The latest G1S ReaderTrace IPA is **diagnostic-only**. A green Actions result confirms assembly/signing/CRC, not runtime. Do not certify the game playable until an iPhone run executes beyond the original resource factory and a representative first scene; verify external RomFS/AOC, actual shader creation, memory pools, 30/60 preference and A/B input. Do not run further Action builds speculatively; the existing run 45056917685 already contains the necessary next read trace.

This document deliberately makes **no claim** of a verified global correction. A runtime code edit without the reader event or equivalent trace evidence would repeat the same unverified cycle.
