# Fairy2iOS KTGL read-delivery investigation — 2026-11-22

This is an evidence-led failure investigation, **NOT a gameplay fix**.
The previously advertised coherent KTGL build `45083487666`, SHA-256
`2e0cbbf938cbba40e6a36be8c1d0ce9704a8502ac88557da7e62de79310c8fd5`,
was executed on iPhone and still aborts at `main+0xbfe2a8`. Quarantined.

## Original resources are real, not missing

Actual Colab/Drive-backed Linux probe run `45055194914`:
- `Hash[0xfb9ebd24]` / type `0xafbec60c`: `system.rdb` → RDX →
  `Motor/ReleasePackage/KIDS_PLATFORM_NX/release/0x38f972af.fdata`, image entry
  **12943** in the real iPhone RomFS; FDATA record starts **3137776**,
  payload starts **3137864**, compressed stream **49 bytes**, inflates to
  **48 bytes** (SHA256 `558ada8c563fe44fa18d894d01f39e8b1a230b26ad1bcd0782743797f815e494`),
  first 8 bytes `GT1G0500`.
- `Hash[0xac9ed13e]` / type `0x7bcd279f`: same FDATA, record
  starts **185248**, compressed **4176**, decoded **18340**, magic `_S2G5000`,
  original two mode4 blocks, SHA256
  `edb3bceed3c426cfe5b851d78f2e7f56168abe8ac5d6aac3a6927bdaf6e3535a`.
- Actual iPhone file log confirms opening `0x38f972af.fdata` at about 59.67 s
  and `0x8baaa1ce.fdata` at 59.95 s, immediately before G1T resource
  failure. Opening a file does **not** prove a successful read at a specific
  offset or that the decoded bytes reach the parser.

## Actual ARM64 causality

`main+0xc11924` calls the KTGL factory `main+0xc10690`.
`main+0xc108ec` calls a virtual resource constructor. `main+0xc108f0`
stores its result; the later failure path reaches `main+0xc10b90`, then
resource abort `main+0xbfe2a8`.

In the G1T parser `main+0x6120e0`, the validator call is
`main+0x612118 → main+0x60db9c`, which reads exactly **0x14 bytes**
through the original reader vtable `+0x20`, then checks `GT1G`,
version and header fields. `main+0x612120` branches on success/failure.

Important: `x18` rewrites within `main+0xc10a6c..+0xc10b08` belong
to the **post-failure path for error description/hash lookup**; their
presence alone does not establish that they broke the FDATA stream.

## One diagnostic, no gameplay claim

Host-only xcode-27 Actions run
[45087848103](https://github.com/joao9vegeto-stack/KintTany/actions/runs/45087848103),
artifact [14780505681](https://github.com/joao9vegeto-stack/KintTany/actions/runs/45087848103/artifacts/14780505681),
**success**. IPA inside: `Fairy2iOS-FairyTail2-KTGL-CoherentConfig-NoFallback.ipa`
(**diagnostic contents**, despite inherited file name), SHA-256
`16ac84ebff44cd762b0f8a3ec721546fef363d2f2372113ee2b8c4c764058a14`.
19,210 shaders are reused, original RDB/FDATA and parsers untouched.
The diagnostic artifact includes `Diagnostic` in its name and is not
automatically selectable by the Colab release-IPA flow.

Two bounded markers in the iPhone log:
- `FAIRY2_FDATA_TRANSACTION`: **real** `nn::fs::ReadFile` for RomFS image
  entries **12943** and **13660**, offset/requested/clipped/returned bytes,
  destination, first 16 actual bytes (hex), and FNV64 on requests up to 65536 B.
  At most 256 entries. No changed file bytes or return codes.
- `FAIRY2_G1T_VALIDATOR_REAL_FAIL`: original G1T B.EQ result, actual
  guest reader pointer and 32 bytes of reader structure + parser local.
  A signal trap at `main+0x612120` **emulates the original condition**
  using the guest NZCV PSTATE.Z bit: on Z=1 branch to `main+0x6121d4`,
  else advance to `main+0x612124`. At most 64 failures logged, no
  forced valid G1T header or altered return.

## Decision table after device log

| Observed | Supported investigation direction |
|---|---|
| No FDATA `ReadFile` calls for entry 12943 | Resource pointer resolution/reader setup before HLE read; inspect direct vs async producer |
| FDATA reads but never cover 3137776 / 3137864 | RDB/RDX dereference, file offset translation or reader seek bug |
| Correct offsets requested but HLE returns short/zero | Fix actual `nn::fs`/RomFS backing issue, not G1T bytes |
| Correct FDATA delivered and G1T validator still fails | Fix guest reader cursor/decompression/producer synchronisation or HLE scheduling after the IO, not FS file presence |
| G1T validator succeeds, resource constructor fails elsewhere | Probe downstream constructor (no speculation on G1T magic) |

**Do not generate any further purportedly fixed IPA until the device trace
identifies an actual failure boundary.** No device test was or can be run by
the cloud-only GitHub Actions job.
