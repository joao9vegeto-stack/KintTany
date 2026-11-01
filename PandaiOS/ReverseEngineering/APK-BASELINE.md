# Panda Android APK — static baseline

## Identity

- Package: `com.qudian.qudianyun`
- Version: `3.1.0` (manifest version code 310)
- SHA-256: `72d3f472a778e400473095407b24244b780e9871b1541345099f9422b937716b`
- ABI: ARM64 and ARMv7
- Original APK remains outside the repository; no user credentials are included.

## Confirmed application structure

The Android manifest identifies these app activities:

- `com.qudian.qudianyun.activities.InitialActivity` (launcher)
- `LoginActivity` and `LoginVerifyCodeActivity`
- `MainActivity`
- `GameDetailActivity`
- `RoomDetailActivity` and `SingleRoomDetailActivity`
- `SettingActivity`, `AccountManagerActivity`, `UserMainActivity`
- Wallet, VIP, message, discussion and search activities

The manifest also declares the `com.limelight.preferences.ComputerManagerService`
service with label "Computer Management Service". This is the strongest
static indicator that the app embeds the Limelight/Moonlight GameStream
client for the actual remote-play session. The iOS implementation should
reuse the native Moonlight GameStream core and provide a Panda-specific
provider/session adapter around it.

## Protection and payload layout

- The visible `classes.dex` contains the SecShell loader and
  `com.qudian.qudianyun.MyApp`; it is not the full application logic.
- `assets/classes0.jar` is 7,424,840 bytes and does not begin with a ZIP/JAR
  header. It is an encrypted/protected payload.
- The visible loader includes SecShell classes and a reference to
  `dalvik.system.PathClassLoader`.
- `libzeus_direct_dex.so` exports `LoadDirectDex` and registers
  `com/volcengine/zeus/dex/DirectDex.native_load_direct_dex`.
- `assets/1728530695` is a nested APK/ZIP payload containing additional
  ad/media SDK libraries and DEX files; it is not the main Panda business
  logic.
- Native libraries include `libijkplayerplugin.so`, `libmmkv.so`,
  `libsgcore.so`, and `libzeus_direct_dex.so`.

The presence of IJKPlayer alone does not prove that the cloud-game stream
uses HLS, RTMP, or another IJK-supported media protocol. The Limelight
service declaration is the concrete evidence for the GameStream engine.

## Consequences for the iOS port

The port is split into two independent layers:

1. **Panda provider layer:** account login, verification, catalog, cloud
   machine allocation, session credentials and server discovery.
2. **GameStream layer:** host pairing/session negotiation, RTSP, low-latency
   audio/video transport, decoding and gamepad/keyboard/mouse input, supplied
   by the upstream Moonlight Common C implementation.

No Panda API hostname, endpoint, token format, host certificate or session
key is inferred from the APK metadata. These must be recovered from the
protected application payload before provider integration.
