# Fairy2iOS — Fairy Tail 2 (Switch → iOS 26)

**Branch**: `Fairy2iOS`, forked from `BioiOSMutant`. **Title ID**: `0100B9801F872000`.

**Drive**: [fairy2](https://drive.google.com/drive/folders/1QNa5LUK7Es-evrRIAjtUVzrhGUhENn5t), child of [the project root](https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm). The game-local folder is precreated.

**Notebook**: [Fairy2iOS_FairyTail2.ipynb](colab/Fairy2iOS_FairyTail2.ipynb). Open the notebook in Google Colab and run code cells 1 through 8 in order.

1. Authenticate Drive OAuth, locate parent and fairy2 folder. Place `prod.keys` in game folder or shared parent.
2. Clone **only** `Fairy2iOS` and import the game-local Colab scripts.
3. Download three supplied signed links (base RAR, update RAR, single 16-DLC pack RAR). **6 HTTP Range workers × 64 MiB**, SHA-256 chunk ledger, retry/resume, safe fallback streaming for hosts that ignore Range. Process **one RAR at a time**: extract NSP(s), validate PFS0, upload `base.nsp`, `update.nsp`, `dlc-01.nsp` ... `dlc-16.nsp` to Drive/fairy2 with resumable **64 MiB uploads**. Verify Drive remote size/MD5; only then remove source RAR. Refresh source URL variables if their tokens expire.
4. Recover a verified Linux handoff when previously completed, without repeating extraction or recompilation.
5. On Colab/Linux, use the real NXNative `build_ipa_from_nsp.py` to inspect NCA/CNMT, detect **actual update version** and DLC content, create provisional game profile if missing, merge RomFS, extract AOC, rewrite ARM64 modules and split/decode shaders that can be completed in Linux. Upload SHA-256 identified game assets (external RomFS + actual AOC images) and a compact immutable work archive to Drive/fairy2.
6. Gate on **18 distinct NSP sources** and **16 DLC packages**, actual engine version/shader provenance and complete handoff integrity.
7. Publish **only** `fairy2/handoff.json` to `Fairy2iOS`. The commit triggers exactly **one** [Fairy2iOS macOS build workflow](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/fairy2.yml).
8. Following a successful workflow, download and validate the branch-specific IPA and build report from GitHub, then upload to Drive/fairy2/ipa.

## Linux first, macOS only when necessary

| Google Colab / Linux (heavy) | GitHub Actions / macOS xcode-27 |
| --- | --- |
| RAR downloads, extraction and Drive uploads | Retrieve verified Linux work via same multi-range Drive transport |
| Build real LibHac Linux extractor and scan base/update/16 DLC | Apple-Silicon-only shader captures (when genuinely required) |
| Provisional profile, RomFS merge, AOC extraction, AArch64 rewrite | Metal iOS compilation, framework and shared Shell build |
| All host-independent shader work, cache, SHA-256 handoff | Ad-hoc signature, real Metal payload verification, IPA artifact |

The **thin IPA does not embed RAR, NSP, prod.keys, RomFS or AOC images**. User installs the external `romfs.img` under `Documents/games/0100B9801F872000/`, and the externally uploaded AOC images alongside the appropriate game folder. The framework is required to include actual compiled Metal shaders. The inherited launcher offers **30/60 FPS target** and optional A/B swap, but 60 actual rendered FPS needs a real-device test.

## Accuracy and status

The game data has *not* been extracted by this setup, the actual update version and number of generated AOC images are *not yet known*, and no game-specific compatibility is claimed. Do not dispatch macOS until the real Colab preparation has uploaded and verified the complete handoff. The `BioiOSMutant` source branch is not changed.
