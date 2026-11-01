# Panda Cloud — native iOS port

Branch: `PandaiOS`. The only build workflow is `.github/workflows/pandaios.yml`,
triggered by commits to this branch.

## Implemented

- SwiftUI iOS client shell and GameController device detection.
- Moonlight iOS/Common C pinned as a recursive submodule.
- Moonlight Common C and OpenSSL linked into the app.
- Link-time references to GameStream connection and controller-input APIs.
- Provider-neutral `PandaSessionDescriptor` matching the data required by
  Moonlight's `StreamConfiguration`.
- Validation of host, certificate, RTSP session URL, app identity and stream
  parameters.
- Device-only Keychain storage for session data.
- Local JSON session-import screen for testing recovered session responses.

## Reverse engineering

The static APK baseline is in `ReverseEngineering/APK-BASELINE.md`.
The visible manifest confirms the Limelight ComputerManagerService, but
the main app payload is protected by SecShell. The encrypted
`assets/classes0.jar` is required to recover login, catalog and cloud-room
allocation APIs. The original APK is not committed to this repository.

No Panda endpoint, login request, token, host certificate or RTSP session
value has been invented.

## Required for real gameplay

1. Recover the protected Panda payload and the actual login, catalog and
   machine-allocation request/response formats.
2. Implement the provider adapter from those recovered contracts.
3. Integrate upstream Objective-C StreamManager, HTTP pairing/session
   manager, VideoToolbox renderer, Opus audio and controller mapping.
4. Convert a real provider response into `PandaSessionDescriptor`.
5. Verify pairing, RTSP negotiation, audio/video and gameplay.

The HLS/MP4 player remains a separate media diagnostic.
