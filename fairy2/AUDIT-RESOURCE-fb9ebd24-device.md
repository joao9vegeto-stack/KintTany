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

## Guest-specific breakthrough: requested type is G1T texture

The crash registers in BOTH 6GiB device runs show `x24=0x3e3532fd0` and the first 64-bit word at `*x24=0xafbec60c20000001`. This is two little-endian u32 values: state 0x20000001 and **resource TypeKTID 0xafbec60c**. At main+0xc108a8 the original guest ARM64 executes `ldr w1,[x24,#4]`, passing **0xafbec60c** into its type lookup at main+0xbfe790 before virtual factory dispatch at main+0xc108ec. The abort reports the separate **resource hash 0xfb9ebd24**. Whether this is the actual RDB FileKTID still needs inspection of the asset index. They must NOT be conflated.

External independent source mappings confirm 0xafbec60c = **G1T texture**:
- https://github.com/eArmada8/yumia_fdata_tools (yumia_mod_lib.py, mapping)
- https://github.com/eterniti/qrdbtool (RDB MatchesType 0xafbec60c indicates G1T)
- https://github.com/Joschuka/Project-G1M/issues/42 (distinct G1T-like 0xad57ebba type)
- https://github.com/lunixxx37/NupExplorer (G1T Switch pixel formats, linear vs tiled layout).

Reconstructing the failed type's vtable from the original Colab handoff guest main at guest+0x2b90368 gives virtual method at slot +0xa0 = guest **main+0x1dc3a60**. That method calls guest **main+0xc09be0** (preparation) and **main+0x112eb28** (resource stream/materialization), then either initializes an object or yields NULL. The latter enters main+0xc109c4 and reports the exact G1T resource hash. The underlying resource stream reader at **main+0x6120e0** parses binary data and can return NULL when read/validation fails. Without the actual record bytes or a branch/return trace, neither malformed G1T nor HLE error nor allocation failure is PROVEN. No safe patch is to skip fatal abort or fabricate a texture pointer.

The crash's final successful OpenFile of 0x8baaa1ce.fdata is a strong candidate source but **is not yet proven to contain the requested FileKTID 0xfb9ebd24**; only RDB/RDX+FDATA index verification can prove that link. An intentionally read-only Colab report must print both FileKTID and TypeKTID and only identify a G1T record when actual bytes verify it.


## Colab report received — November 22, v458752, authoritative on-byte findings

Source: user-provided \`fairy2-resource-fb9ebd24-report.json\` from the authenticated Range auditor. Source RomFS size 7,889,449,169, 14,770 index entries, 664,697 index bytes.

- \`system.rdb\`: 85,436 bytes, SHA-256 \`00994767b00868e69809b9ef1a4c8058c62f5dabcc1378579c3c8cd94aba88e5\`.
- One exact \`IDRK\` match: index offset **83860 (0x14794)**; entry length 101; stored length **13**; uncompressed size 48; FileKTID **0xfb9ebd24**; TypeKTID **0xafbec60c (G1T)**; flags **0x420000**; pointer bytes are in the last 13 bytes at \`system.rdb+83948\`.
- \`root.rdb\`: 6,326,888 bytes with 70,292 indexed IDRK entries, no match for file KTID; \`system.rdb\` has 1,127 records.
- \`system.rdx\`: exactly 40 bytes, 5 \`<HBBI\` entries, SHA-256 \`db0b933405e37d1c0c74f9f475a24857ed644530533eed744a36cde55a55f1c5\`. Its first two marker/hash tuples are marker 0 → 0x38f972af, marker 1 → 0x52482d03. The actual matching marker remains unread because v1 did not dump the 13 pointer bytes.
- \`root.rdx\`: 17,552 bytes, includes fdata hash 0x8baaa1ce. That container is **not automatically the source** for a \`system.rdb\` record; correct resolution is through \`system.rdx\`.
- \`0x8baaa1ce.fdata\`: 2,408,559,912 bytes, not downloaded by v1 (max-file 192 MiB).
- No NCA damaged flags for those five sampled files.

**CRITICAL V1 AUDITOR ERROR:** V1 labels the 13-byte \`system.rdb\` locator as \`invalid: compressed first chunk exceeds record\`. This is NOT a confirmed corrupt G1T. Under Koei Tecmo's newer RDB/FDATA design, flag bit 0x20000 represents an **external stored location** and the RDB's terminal 13-byte payload is a pointer of the form \`01 04 + variable-length offset + variable-length entry size + u16 RDX marker + 00\`. Actual content and compression flags must be read from the referenced FDATA IDRK. The parser had incorrectly zlib-parsed locator bytes.

Independent code evidence: \`eArmada8/yumia_fdata_tools/yumia_mod_lib.py\`, functions \`create_rdb_idrk\`, \`append_rdx\`, \`read_fdata_file\`:
https://github.com/eArmada8/yumia_fdata_tools/blob/main/yumia_mod_lib.py
The source constructs 13-byte external pointers and 8-byte RDX records in exactly that structure. It identifies 0xafbec60c as G1T.

**Corrected targeted auditor V2** in the conversation artifact, \`Fairy2iOS_Auditoria_G1T_v2_corrigida.ipynb\`:
1. Reads source DMROMFS1 index, \`system.rdb\`, \`system.rdx\` only.
2. Decodes one locator, resolves the exact RDX marker to its .fdata basename and verifies it exists in the actual RomFS.
3. HTTP Range reads the IDRK header at exactly that FDATA offset; checks FileKTID, TypeKTID, sizes and flags against original \`system.rdb\`.
4. Decodes ONLY the first compressed data chunk (zlib for compression type 4, LZ4 for 5); reports GT1G/G1TG first bytes and errors, without pulling 2.4GB.
5. Produces read-only JSON. 10 local synthetic regression tests passed (including missing FDATA, missing PDRK, bad hash and invalid zlib). It has NOT been run with the user's real FDATA bytes yet.

**No new IPA or Actions run**, because the report pinpoints an external G1T reference but does not prove which runtime operation returns NULL. Do not patch guest factory to suppress the SIGTRAP, do not classify the 13-byte pointer as corrupted, and do not recompile shaders before resolving the actual payload.


## V2 from actual Colab Drive — definitive end-to-end asset identity (22 Nov 2026)

The authenticated partial-read report \`fairy2-resource-fb9ebd24-pointer-v2.json\` is **complete** and identifies the failing resource without inference:
- **RDB:** \`system.rdb\`, IDRK index offset 83860, \`FileKTID=0xfb9ebd24\`, \`TypeKTID=0xafbec60c (G1T)\`, flags \`0x420000\` (= pointer flag \`0x20000\` + compression type \`4\`), terminal external pointer \`0104f0e02f0089000000000000\`.
- **Pointer:** FDATA offset **3,137,776**, full entry length **137** bytes, RDX marker **0**.
- **RDX:** \`system.rdx\` marker 0 resolves to **\`Motor/ReleasePackage/KIDS_PLATFORM_NX/release/0x38f972af.fdata\`**, not the last logged \`0x8baaa1ce.fdata\`.
- **FDATA:** 267,741,963 bytes, \`PDRK0000\` header; its IDRK entry at offset 3,137,776 matches **both hashes exactly**. Stored bytes 49, inflated bytes **48**, flags \`0x400000\` (chunked zlib), payload offset 3,137,864.
- **Decoded first chunk:** 37-byte zlib stream SHA-256 \`f4a0ffed01e78a9455e33c4de3b9c409d8def0715db87c8a28112715e1ffc2c6\`, yields **48 bytes** and begins \`47543147303530303000000020000000\` = \`GT1G\`, version \`0500\`, total length \`0x30\` (48), offset table begins \`0x20\`.
- NCA damaged-content flag is **false**. These facts establish that the referenced G1T is present, the pointer is correct, and the stored compressed first chunk is readable from Google Drive. They **do not** prove that the complete resource parser or GPU texture construction succeeded on the iPhone.

**Refined ROMFS log correlation:** both iPhone logs show \`fs open .../0x38f972af.fdata\` around the start of asset loading, before the later \`0x8baaa1ce.fdata\` open and resource trap. Prior claim that the *last* FDATA open identifies the failing asset was wrong.

## Why we need the remaining 32 decompressed bytes

48 bytes are the **whole** requested G1T, not merely a truncated sample. V2 saved only its first 16 bytes. The native ARM64 parser at \`main+0x60db9c\` reads magic/version, platform at G1T+0x14, metadata at +0x18, and for version 0500 checks whether platform is in **{0,7,10,14,16}** (mask \`0x14481\`) before it proceeds. Function \`main+0x6120e0\` then allocates/reads each texture; \`main+0x112eb28\` returns a null resource on a failed stream/parser. Distinguishing a header rejection from allocation and texture upload requires these remaining 32 bytes and/or a targeted live return-value trace.

A new **read-only Colab V3 notebook** was created in this conversation: \`Fairy2iOS_Auditoria_G1T_v3_48bytes.ipynb\`. It reads exactly the 49-byte compressed FDATA payload using authenticated HTTP Range, verifies prior digest and decompresses all 48 bytes, then saves the complete G1T hex plus header / platform / texture record checks. It requires no Actions, IPA rebuild, shaders, or 7.9GB download. Ten synthetic regression tests passed; actual user-source V3 results not yet available. Only after this can a justified implementation fix be selected.

**Do not re-enable the known-crashing 45000495987 IPA in Colab's transfer script or claim the port fixed on device.**
