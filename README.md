# SpotiJon — Android

Branch **SpotiJon** of **joao9vegeto-stack/KintTany**, isolated from every iOS branch.

## What was done

The user provided `Sonora-1.1.1-unsigned.ipa` (iOS, `com.daniel.sonora`).
The archive has SwiftUI ARM64 binaries, two JavaScript YouTube stream
resolver files, localized strings, and design assets, **not the original
Swift source**. It cannot be recompiled as an APK.

The Android deliverable is an **initial functional Android adaptation**, NOT
a bytecode translation or a faithful pixel-for-pixel port. To retain the
features identified in the IPA, the build compiles a pinned open-source
native Android YouTube Music implementation (Metrolist v13.3.0), adds a
SpotiJon launcher identity, and exposes its playback, queue, search,
background audio, offline caching and library features.

Missing Sonora-specific implementation: SwiftUI visual parity, Sonora's
proprietary stream solver, exact AutoMix/BPM engine, app-level import of
Sonora data, and its original authentication state. No unsupported
claim of exact feature parity should be made.

## Git isolation and one-commit build

This branch is a *fresh clean tree* with just SpotiJon Android files;
all KintTany iOS files/workflows are absent. The branch is squashed to one
commit relative to main, with no modifications to other branches.

The mobile launcher is advertised using a direct, independent Android
intent filter, while the upstream mobile launcher aliases and Android TV
filter are preserved. The upstream aliases made naive checks misleading. GitHub Actions
validates both an APK signature and a home-screen launchable activity.

## Reproducible build

GitHub Actions workflow `.github/workflows/build-spotijon-android.yml`
fetches the fixed upstream commit
`89060fca00f2f8849e9f6b0c2b9ddb799f102c8e`
from [MetrolistGroup/Metrolist](https://github.com/MetrolistGroup/Metrolist),
runs `scripts/brand.sh` and uses Gradle to build
`:app:assembleFossDebug`.

Application ID: `com.spotijon.music`, display name: **SpotiJon**.
The release is a DEBUG-signed APK, installable without a Google Play account.
The signing key is generated on the GitHub-hosted runner, so future builds
may require uninstalling before installing an APK signed with a different key.

The **FOSS** debug flavor is used with a distinct SpotiJon Android application ID. A physical Android device
has not been tested from this repository.

## Open source and attribution

This repository contains only original branding/build scripts, not a copy of
Metrolist source. Metrolist is distributed under the **GNU GPL-3.0**; its
corresponding Android source is checked out at the pinned commit above when
the APK is built. Redistribution must preserve the GPL-3.0 attribution and
source availability. Source and license:
[Metrolist 13.3.0](https://github.com/MetrolistGroup/Metrolist/tree/v13.3.0).

No code/assets were copied from the compiled Sonora IPA. Any new Sonora-derived
feature must be implemented and tested separately.

## Build and artifact

Open **Actions → SpotiJon Android APK** on branch `SpotiJon`. Successful
runs publish **SpotiJon-Android-APK**, containing the installable APK,
its SHA-256 and Android package information.

The app's streaming relies on unofficial YouTube Music interfaces and may
be affected by service changes, geographic restrictions or authentication.
