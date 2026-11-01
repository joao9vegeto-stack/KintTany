# Panda Android APK — static baseline

## Identity

- Package: `com.qudian.qudianyun`
- Version: `3.1.0` (manifest version code 310)
- APK SHA-256: `72d3f472a778e400473095407b24244b780e9871b1541345099f9422b937716b`
- ABI: ARM64 and ARMv7
- The original APK was available in the conversation upload and analyzed locally; it is intentionally not committed to this repository.

## Confirmed application structure

The Android manifest identifies the Panda application and its launcher/application classes. Resource names and manifest declarations expose these app screens/components:

- `com.qudian.qudianyun.activities.InitialActivity` (launcher)
- `LoginActivity` and `LoginVerifyCodeActivity`
- `MainActivity`
- `GameDetailActivity`
- `RoomDetailActivity` and `SingleRoomDetailActivity`
- `SettingActivity`, `AccountManagerActivity`, `UserMainActivity`
- Wallet, VIP, message, discussion, search and network-game list screens
- `com.limelight.preferences.ComputerManagerService`, labelled "Computer Management Service"

The Limelight service declaration is strong static evidence that the app embeds the Limelight/Moonlight GameStream client for remote-play sessions. The iOS implementation should reuse Moonlight Common C and implement a Panda provider/session adapter around it.

## Protection and payload layout

- The visible `classes.dex` is a Dalvik DEX 035 file (~1.02 MB) containing SecShell loader classes, `com.qudian.qudianyun.MyApp`, `attachBaseContext`, and reflective/dynamic loading references including `DexFile`, `PathClassLoader`, `dexElements` and `loadClass`. It is not the full application logic.
- `assets/classes0.jar` is 7,424,840 bytes, does not begin with ZIP/JAR magic, and has SHA-256 `44ab9442895ef3daab72fb23299baf6159f8177c6f7e5e2c052db67601ae7e4c`. Its measured byte entropy is ~7.9906 bits/byte, consistent with encrypted or strongly transformed data. It cannot be treated as an ordinary JAR.
- ARM64 `libSecShell.so` is 1,204,461 bytes (SHA-256 `b28184e5941fa57cace2cb4148f2248cfe0c42977bfc71dd15cd70ee1e0c1421`). Its printable native strings include `JNI_OnLoad`, `loadDgg`, `find_dexfile`, `multidex_jar_allpath_art`, `asset_payload`, `assetsCacheDir`, `add_assets`, `open_zip_buffer`, `mthfilekey`, `nthfilekey` and `string_key`. These indicate a native asset/payload and DEX-loading path; they do not reveal the decryption key or the decrypted Java classes by themselves.
- `assets/meta-data/manifest.mf`, `rsa.pub` and `rsa.sig` are part of the protection metadata. Their presence alone does not establish the payload cipher, key derivation or a valid decryption procedure.
- `libzeus_direct_dex.so` is a separate small ARM64 library; its strings/symbol references identify a direct-DEX loading component (`LoadDirectDex` / `DirectDex.native_load_direct_dex`).
- `assets/1728530695` is a 6,372,990-byte nested APK/ZIP (SHA-256 `66efc2ebd1f2eb49ce490045f88cd3677c09849c23d6202fd9956493d7b5d936`). Its largest DEX and native libraries, package strings and resources identify it as an advertising/media SDK payload (including Pangle/TTPlayer components), not the main Panda business-logic payload.
- Native libraries also include `libijkplayerplugin.so`, `libmmkv.so` and `libsgcore.so`.

The IJKPlayer library alone does not prove that cloud-game streaming uses HLS, RTMP or another IJK-supported media protocol. The Limelight service declaration is the concrete GameStream evidence.

## What this analysis establishes — and does not establish

Established:
- Panda has login and verification-code UI flows, game/detail and room screens, and a Limelight/GameStream integration point.
- The primary application logic is protected behind SecShell's native loading path.
- The large nested `assets/1728530695` archive is an ad/media SDK payload, not the missing Panda business layer.

Not established:
- No Panda API hostname, login endpoint, request signature, token format, game catalog endpoint, room-allocation endpoint, host certificate, session key or RTSP URL has been recovered from the visible plaintext.
- No claim is made that `classes0.jar` has been decrypted or that a working Panda account/session can be reproduced from static inspection alone.

## Consequences for the iOS port

The port has two independent layers:

1. **Panda provider layer:** account login, verification, catalog, cloud-machine allocation, session credentials and server discovery.
2. **GameStream layer:** host pairing/session negotiation, RTSP, low-latency audio/video transport, decoding and gamepad/keyboard/mouse input, supplied by upstream Moonlight Common C and its iOS rendering/session components.

The next reverse-engineering milestone is to recover the protected classes at runtime on an authorized Android test device (or obtain an unprotected/development build or protocol documentation), then trace the actual login → catalog → room allocation → GameStream handoff. Static strings must not be promoted into invented API contracts.
