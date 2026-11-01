# Panda Cloud — native iOS port

This branch is the isolated Panda iOS workspace. The build workflow runs on
commits to `PandaiOS` only.

## Streaming engine identified and bundled

The supplied APK (package `com.qudian.qudianyun`, version 3.1.0) declares
`com.limelight.preferences.ComputerManagerService` with the label
"Computer Management Service". Its resources also contain the Moonlight
GameStream settings and connection strings. The iOS port therefore uses
the upstream Moonlight iOS/Common C code as the native streaming-engine base,
rather than treating the service as a plain HLS player.

The upstream Moonlight iOS source is pinned as a recursive Git submodule at
`ThirdParty/moonlight-ios`. Its `moonlight-common` static library is built
before the Panda SwiftUI app, force-loaded into the app binary, and linked
with the upstream OpenSSL package. The C bridge holds references to the
GameStream connection-start and controller-input entry points so the linker
must resolve the actual streaming and input APIs.

This build includes the protocol core, but the Objective-C session manager,
VideoToolbox/Opus render pipeline and Panda provider session adapter still
need to be wired into the app before a real stream can start.

## APK findings

See [ReverseEngineering/APK-BASELINE.md](ReverseEngineering/APK-BASELINE.md).
The original APK is not committed to the repository. Its main application
payload is protected by SecShell; `assets/classes0.jar` is encrypted and
the visible DEX is primarily a loader. Login, catalog, provider API and
session-allocation details are not yet decoded.

## Current app

- Native SwiftUI shell for iOS 16+.
- Moonlight Common C GameStream connection and controller-input APIs linked.
- OpenSSL is linked for GameStream protocol cryptography.
- GameController framework detection for connected controllers.
- Standalone HLS/MP4 playback remains a diagnostic tool only; it is not
  represented as the Panda streaming protocol.

## Next implementation stages

1. Decode the SecShell-protected Panda application payload.
2. Recover login, token refresh, catalog and session-allocation APIs.
3. Adapt Moonlight's native HTTP/RTSP session manager and VideoToolbox
   renderer to the Panda-provided host, certificate, app ID and session data.
4. Connect touch controls and GameController input to the active stream.
5. Verify a real Panda account session and gameplay before claiming parity.
