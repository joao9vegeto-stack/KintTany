# Kleo2iOS

Pipeline for building a Nintendo Switch game for iOS using a Linux preparation stage (Google Colab) and a macOS finalization stage (GitHub Actions).

## Build architecture

1. **Colab / Linux** — inspect the supplied game package and run only preparation/AOT stages that are verified to work on Linux. Produce a versioned handoff bundle and a manifest. Do not put game dumps, keys, or copyrighted game data in this repository.
2. **Google Drive** — hold the private handoff bundle. The Colab notebook must upload it to a user-owned Drive location.
3. **GitHub Actions / macOS 26** — retrieve the handoff bundle using user-provided secrets, run the Apple-only compilation steps (iOS SDK, Metal and Xcode), build the per-game framework, integrate it into the Shared shell, and package an unsigned IPA.
4. **iPhone** — install the IPA with the user's sideloading method and copy the separate game data to the location expected by the launcher.

## Non-negotiable constraints

- The only workflow in this branch must trigger on pushes to `Kleo2iOS` (plus manual dispatch on that branch). No workflow should run for pushes to other branches.
- Keep the game data and console keys out of Git.
- No paid Apple Developer account or App Store signing; produce an unsigned IPA for sideloading.
- Keep the IPA and game data separate when the upstream runtime supports the separate-RomFS mode.
- Do not claim the Linux stage is complete until every Linux command and every handoff artifact has been validated against the pinned NX2Apple/NXNative revision.
- Do not use caches in Actions unless explicitly justified and requested.

## Current status

This is a clean project branch created from `main`. The inherited KintTany application, old workflows, tests, patches and unrelated documentation have been removed. The Colab preparation pipeline and macOS Shared-App finalizer are the next implementation stages; the initial workflow is deliberately limited to branch-isolation validation.
