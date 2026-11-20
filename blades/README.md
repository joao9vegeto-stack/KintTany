# BladesTime — Blades of Time iOS 26

This branch is based on Dante2iOS commit `c26310badf71f79b4263036ff658fbb87eaa0f6d`.
The game base is title `0100CFA00CC74000` (v0); the update version is discovered by reading the update NSP's internal content meta.

## Verified Drive inputs

- Shared parent: https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm
- `botime`: https://drive.google.com/drive/folders/18G7EletOjZZ-eTtdPdM2ZPZsKVymHsZt
- NSP base and `update.nsp` (distinct file IDs, SHA-256 computed in Colab)
- `prod.keys` remains outside repository/IPA.

## Procedure

1. Open `blades/colab/BladesTime.ipynb` in Google Colab. Authorize Drive and run the prepare cell. Linux NativeAOT nx_extract inspects actual content metadata, makes an unregistered-game profile when necessary, merges base+update into an external RomFS, rewrites ARM64 modules and performs the offline shader split. A game requiring an Apple Silicon Oodle/capture stage **fails honestly** rather than marking a skipped step successful.
2. Preparation uploads the original-version-correct external `games/0100CFA00CC74000/romfs.img`, compressed workspace and a handoff manifest (including content hashes) into a new `BladesTime_BoTime_*` directory inside `botime`.
3. Optional Colab recovery cell retrieves the last manifest without rerunning the NSP extraction. The dispatch cell submits **only** `blades/handoff.json` to `BladesTime`. It rejects duplicate request IDs.
4. That single file triggers only `.github/workflows/bladestime.yml` on the `BladesTime` branch. One xcode-27 job validates metadata, downloads the prepared assets with the existing `GOOGLE_SERVICE_ACCOUNT_JSON` secret, compiles the actual Metal shader library, embeds and verifies its SHA-256 in the game framework and thin iOS 26 IPA.
5. Install the generated IPA, move the external merged `romfs.img` to the game title-ID data location, and test on the device.

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
