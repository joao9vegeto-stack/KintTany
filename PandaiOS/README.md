# Panda Cloud — iOS native port

This branch is an isolated working tree for the iOS port. It contains no files or workflows inherited into the branch's current tree from `main`.

## Current implementation

- Native SwiftUI application shell (iOS 16+).
- AVFoundation/AVPlayer direct-playback diagnostic for HTTPS HLS and MP4 URLs.
- Manual-only GitHub Actions workflow that builds an unsigned iOS IPA.
- No Android runtime, emulator, or Android binary is bundled into the iOS app.

## Important reverse-engineering boundary

The APK analysis previously recorded the package identifier `com.qudian.qudianyun` and native modules including IJKPlayer and MMKV. Those facts do **not** establish that Panda's cloud stream uses ordinary HLS, nor do they identify its authentication, session negotiation, transport, codec configuration, or controller protocol.

The current player is explicitly a diagnostic path. It is not represented as a working Panda account/session integration.

## Required next input

The original APK (preferably the exact version used for the earlier inspection) must be available in the working session to inspect:

1. Manifest, exported activities/services/receivers and permissions.
2. DEX loading and unpacking path for secondary payloads.
3. Native library exports/imports and JNI call sites.
4. Login/API hosts, token lifecycle and device attestation dependencies.
5. Streaming handshake, transport, codec/audio configuration, latency control and gamepad input mapping.

Only after these are identified should the Panda provider adapter be implemented. Secrets, account tokens and private user data must not be committed.
