# Kleo2iOS

Switch 2 to iOS Shared-App pipeline. Google Colab/Linux performs the verified offline preparation stages; GitHub Actions/macOS performs iOS Metal compilation, framework linking and Shared shell build.

## Branch and workflow isolation

- Created directly from main; unrelated KintTany application files were removed.
- Only workflow: .github/workflows/kleo2ios.yml.
- It triggers only when handoff.json changes on Kleo2iOS.
- The job has an explicit refs/heads/Kleo2iOS guard.
- One macOS job, no cache, no workflow_dispatch, no push trigger on any other branch.
- Ordinary source edits do not start a build. Colab uploads the private archive, then commits only its Drive file ID, size and SHA-256 to handoff.json. That one commit starts the build.

## Start Colab

[Open Kleo2iOS_Colab.ipynb in Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/Kleo2iOS/colab/Kleo2iOS_Colab.ipynb)

## Pipeline

### Colab / Linux

The notebook at colab/Kleo2iOS_Colab.ipynb pins NX2Apple v1.3.0-rc10, syncs the pinned NXNative engine and Route C patches, scans the NUP, extracts RomFS/ExeFS, rewrites code modules and performs the offline NVN shader split. It stops immediately before iOS Metal/Xcode compilation.

The Linux adapter refuses unknown profiles, Mac-host shader capture, Oodle/LZ5 decoder requirements and unsupported shader APIs. It does not emulate the game.

### GitHub Actions / macOS

The workflow downloads and verifies the handoff, resumes the same pinned build directory, compiles iOS Metal libraries, creates DmGame<TITLE_ID>.framework using NXNative's DM_FRAMEWORK_ONLY route, then uses the upstream Route C build_shell.sh to build and embed the framework in the unsigned DmShell app. The app is packaged as NX2Apple.ipa.

The artifact also contains game-data.tar.zst because the large RomFS and DLC data remain outside the IPA.

## One-time setup

1. Create a Google Cloud service account and enable the Google Drive API.
2. Create a Drive folder for Kleo2iOS and share it with the service account email as Viewer.
3. Add a GitHub Actions repository secret named GOOGLE_SERVICE_ACCOUNT_JSON containing the complete service-account JSON key.
4. Create a fine-grained GitHub token limited to this repository with Contents: Read and write. The notebook asks for it at the end and uses it only to commit handoff.json. Do not commit either credential.
5. Open colab/Kleo2iOS_Colab.ipynb in Google Colab with Python 3.12+ and run all cells. It asks for the NUP path, Drive folder ID and GitHub token.

The Drive folder must be shared with the service account before upload. No NUP, ROM, game dump, console key or other proprietary game data is committed to Git. NUP containers do not need prod.keys.

## iPhone data placement

Install NX2Apple.ipa with SideStore or another sideloading tool. Extract game-data.tar.zst and copy its games/<TITLE_ID>/ folder into the Shared app's Documents folder:

    Documents/
      games/
        <TITLE_ID>/
          romfs.img
          aoc/             (only if the NUP contains DLC)

The launcher checks the RomFS identity recorded in the framework manifest. An incomplete or mismatched image is not valid game data.

## Limitations

- Donkey Kong Bananza has upstream Mac playtesting, but iPhone/iPad remain explicitly untested. Its profile reserves a 9 GiB app pool (0x240000000) and a 9.75 GiB address reservation (0x270000000); iOS devices with a lower process-memory limit may fail allocations or be terminated. A successful IPA build does not prove the game boots or renders on iPhone.
- The target GPU is g18p, corresponding to the user's iPhone 17 Pro / A19 Pro. If Apple's metal-tt utility is unavailable on the runner, the optional offline pipeline archive may be omitted and the device will build pipeline bases on first launch.
- Colab currently supports registered NVN profiles whose offline shader split does not require a Mac-host decoder/capture. Unsupported cases fail closed.

## Upstream

- NX2Apple v1.3.0-rc10: https://github.com/LNPANDY/NX2Apple/tree/v1.3.0-rc10
- NXNative pin: https://github.com/seedds/nxnative/tree/c78d7375bea9c862679ec294a6a69ff3e22e18d0
- Route C shell patch: https://github.com/LNPANDY/NX2Apple/blob/v1.3.0-rc10/patches/0050-route-c-shell.patch
- Shell framework handoff patch: https://github.com/LNPANDY/NX2Apple/blob/v1.3.0-rc10/patches/0051-nsp-shell-framework.patch
