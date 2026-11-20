# BladesTime — Blades of Time iOS 26

This branch is based on Dante2iOS commit `c26310badf71f79b4263036ff658fbb87eaa0f6d`.
The game base is title `0100CFA00CC74000` (v0); the update version is discovered by reading the update NSP's internal content meta.

## Verified Drive inputs

- Shared parent: https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm
- `botime`: https://drive.google.com/drive/folders/18G7EletOjZZ-eTtdPdM2ZPZsKVymHsZt
- NSP base and `update.nsp` (distinct file IDs, SHA-256 computed in Colab)
- `prod.keys` remains outside repository/IPA.

## Procedure — one code cell, Dante-style handoff

1. Open `blades/colab/BladesTime.ipynb` and run its **only code cell**, with `PREPARAR + ACTIONS` selected. It authenticates Drive, downloads base+update from `botime` using six 64-MiB parallel chunks (when supported), reads actual update content meta, performs NXNative Linux survey/extraction/ARM64 rewrite and offline shader handling. An unsupported Oodle/capture stage fails clearly rather than fabricating a successful game build.
2. Preparation uploads the external `games/0100CFA00CC74000/romfs.img`, compressed workspace and integrity manifest to `botime/BladesTime_BoTime_*`, excluding NSP and keys.
3. **Within that same execution**, the Colab prompts for a fine-grained PAT with Contents Read/Write, creates only `blades/handoff.json` in the BladesTime branch and triggers only `.github/workflows/bladestime.yml`. When recovering after successful upload, select `RECUPERAR UPLOAD + ACTIONS`, still from the same code cell. Duplicate request IDs are rejected.
4. One xcode-27 Actions job checks hashes, retrieves the workspace and external RomFS in parallel chunks, compiles a real Metal shader image, embeds it and verifies it inside the thin iOS 26 IPA.
5. **After** Actions succeeds, choose `TRANSFERIR IPA PARA DRIVE` in the same cell. It selects the latest successful exact BladesTime workflow, verifies the artifact ZIP, IPA SHA-256 and build report, and uploads the IPA and provenance to `botime/ipa`.
6. Sideload the generated IPA and place its external merged `romfs.img` in the game's Documents data folder. Only an iPhone test can validate gameplay.


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
