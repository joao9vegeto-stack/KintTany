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
