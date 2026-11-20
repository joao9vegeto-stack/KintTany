# BladesTime — Blades of Time iOS 26

This branch is based on Dante2iOS commit `c26310badf71f79b4263036ff658fbb87eaa0f6d`.
The game base is title `0100CFA00CC74000` (v0); the update version is discovered by reading the update NSP's internal content meta.

## Verified Drive inputs

- Shared parent: https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm
- `botime`: https://drive.google.com/drive/folders/18G7EletOjZZ-eTtdPdM2ZPZsKVymHsZt
- NSP base and `update.nsp` (distinct file IDs, SHA-256 computed in Colab)
- `prod.keys` remains outside repository/IPA.

## Procedure — exact 13-cell Dante2iOS notebook, adapted for Blades of Time

The uploaded and tested Dante notebook `Dante2iOS_DMC2_LinuxNativeAOT.ipynb` is the cell-by-cell source of `blades/colab/BladesTime.ipynb`; the port preserves its 13-cell order, the top GitHub-to-Drive transfer cell, Linux NativeAOT recovery and the final handoff dispatch.

1. Run **cells 2, 4, 6, 8, 10 and 12**, like the Dante original. Authenticate Google Drive, check out **only BladesTime**, recover a previously uploaded handoff if present, otherwise download exactly two NSPs (base v0 + update with content-meta-discovered version) from **botime** and run NXNative preparation.
2. Colab downloads large inputs with **six 64 MiB concurrent ranges**, verifies Drive metadata and SHA-256, and uploads external `romfs.img`, workspace and handoff with resumable chunks. It preserves game cache on retries and never includes original NSP/keys in the IPA.
3. Inspect the handoff gate: base version zero, actual update version greater than zero, 2 packages, 1 update, 0 DLCs, graphics profile, external RomFS/workspace.
4. Cell 12 submits **only `blades/handoff.json`** to branch `BladesTime`. This triggers only `.github/workflows/bladestime.yml`, one xcode-27 game build, real compiled iOS shaders and thin IPA.
5. **Only after successful Actions**, run **cell 1** at the top to find the exact BladesTime workflow and IPA artifact. It verifies the artifact ZIP SHA-256 (when GitHub supplies one), checks the archive and IPA identity, and uploads it to **botime/ipa** with provenances recorded on Drive.

The extra `blades/colab/transfer_ipa.py` remains available as an optional CLI transfer utility; the notebook itself uses the faithful original transfer cell rather than that wrapper.

## Invariants

- iOS 26, Xcode 27, `DM_SHOW_FPS=YES`, `DM_COPY_ROMFS=NO`, `--gpu none`.
- No original base/update NSP, keys or external RomFS embedded in the IPA.
- Do not trigger a game build just by editing scripts; only an authenticated handoff commit starts it.
- Do not touch `Dante2iOS` or other branches. No fabricated profile, shader list, update version or successful game-boot claim.

## Drive download transport — same as KaKaRoTiOS

Both Colab (`blades/colab/source_archive.py`, `blades/colab/run_colab.py`) and Actions
(`blades/scripts/prepare_actions.py`) import `blades/drive_chunks.py`.

- Large files: 6 concurrent HTTP `Range: bytes=start-end` workers, **64 MiB each**.
  Each worker validates exact HTTP 206 `Content-Range`, payload length, and retries
  its own failed range up to 5 times. `os.pwrite` writes by offset safely.
- Strict Range probe. A server that ignores Range falls back to the Google API downloader,
  fetching **32 MiB chunks** with up to 10 retries.
- Completed local files are reused only when the full content matches the supplied
  size and SHA-256/Google Drive MD5. New files are atomically promoted from `.part`
  after final full-file verification. Interrupted worker requests retry per range.
- Colab verifies the base/update NSP and prod.keys from Drive; Actions verifies the
  prepared workspace archive and external merged RomFS. Uploads are resumable 64 MiB.
- This is **download/chunk retry**, not durable cross-session reuse of incomplete
  `.part` files: a newly launched Colab session still needs a completed Drive checkpoint.

Run the offline transport tests without contacting Google Drive: `python3 -m unittest discover -s blades/tests -v`. The game workflow executes them before installing expensive build prerequisites.

## Linux-first shader handoff and native-only macOS capture

The successful ARM64 rewrite from the user test is preserved. The previous
generic `required_host_capture` stop is now an explicit, verified handoff
checkpoint that identifies the exact shader dependencies, instead of claiming
a shader split completed when it has not.

Colab performs NSP decryption, Base+Update RomFS merge, real NXNative provisional
profile, AArch64 rewrite, offline NVN shader split when possible and Linux UE
LZ4/zlib decoding without the game-owned Oodle decoder. All inputs are cached
and the output is uploaded by verified Drive chunks.

Actions uses the prepared work and runs **only** the native Apple Silicon host
captures or Oodle/IoStore/JIT work actually requested by NXNative source
detection. A Mac NVN shader split happens **only** when its missing inputs
require native Mac capture first; complete Linux splits are reused by hash.
Metal translation, Xcode, signing and IPA packing follow. GL/Vulkan shader
resources are staged and verified as real Metal libraries too.

The user still needs to run Colab and then Actions to verify actual game data;
this change has not yet been tested against the private NSPs.

## Fail-fast Colab validation

Before downloading gigabytes of NSP data, the `run_colab.prepare` entrypoint
compiles every Linux/Mac Python stage and runs the host-stage regression tests
without requiring Google Drive credentials or a game runtime. This catches
syntax or routing mistakes while leaving the cached NSPs and rewritten
content intact.

## Multi-version shader inputs

Some NXNative profiles need shaders from both the base and an updated game
version. The Colab uploads any additional required shader-version RomFS
images separately with their own SHA-256 and provenance, next to the packed
external `romfs.img`. Actions restores **exactly** those images (by version)
before native capture or the dependent shader split, but never includes
these extra images in the IPA. The cached work archive continues excluding
all giant RomFS images.
