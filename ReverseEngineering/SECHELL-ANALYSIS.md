# SecShell and protected Panda payload — analysis notes

APK analyzed: `com.qudian.qudianyun` v3.1.0  
APK SHA-256: `72d3f472a778e400473095407b24244b780e9871b1541345099f9422b937716b`

## Reproducible observations

| Artifact | Size | SHA-256 | Observation |
|---|---:|---|---|
| `assets/classes0.jar` | 7,424,840 | `44ab9442895ef3daab72fb23299baf6159f8177c6f7e5e2c052db67601ae7e4c` | Not a ZIP/JAR; first bytes `fa d2 9c 33...`; entropy ~7.9906 bits/byte |
| `lib/arm64-v8a/libSecShell.so` | 1,204,461 | `b28184e5941fa57cace2cb4148f2248cfe0c42977bfc71dd15cd70ee1e0c1421` | Native SecShell loader/protection component |
| `assets/meta-data/manifest.mf` | 34,415 | `771bda9c8a363634ac0f061878f676d879942e4d1568444a2774fb098d826653` | Encoded/protection metadata |
| `assets/meta-data/rsa.pub` | 274 | `4c4525dc9abe0f079d60c37c944bd646d9761541c346311941f105805f56ae10` | RSA-related metadata |
| `assets/meta-data/rsa.sig` | 257 | `bdc34720dca325e7640c4028628c8b7c78bb773ac43c25a6012a5fb7e370f8d6` | Signature-related metadata |
| `assets/1728530695` | 6,372,990 | `66efc2ebd1f2eb49ce490045f88cd3677c09849c23d6202fd9956493d7b5d936` | Nested APK/ZIP, advertising/media SDK |

Hashes above are for the exact files extracted from the uploaded APK; they are useful for confirming future analysis uses the same sample.

## SecShell loader indicators

The visible DEX contains:
- `com/SecShell/SecShell/*` classes
- `com.qudian.qudianyun.MyApp`
- `attachBaseContext`
- `dalvik.system.DexFile` and `dalvik.system.PathClassLoader`
- reflective multidex references such as `dexElements`, `dexFile`, `makeDexElements` and `loadClass`

Printable strings in ARM64 `libSecShell.so` include:
- `JNI_OnLoad`
- `loadDgg`
- `find_dexfile`
- `multidex_jar_allpath_art`
- `asset_payload`, `assetsCacheDir`, `add_assets`
- `open_zip_buffer`, `open_zip_infile`, `setup_zipres`
- `mthfilekey`, `nthfilekey`, `string_key`, `g_rkeyumFile0001`

This supports the conclusion that native code participates in preparing/loading the protected DEX and asset payload. It does **not** expose a verified decryption key, algorithm, key derivation input or plaintext output. The library's ELF layout is nonstandard/stripped, so these printable names are leads for runtime tracing, not proof that each string is an exported callable symbol.

## Nested payload classification

The archive at `assets/1728530695` is a valid ZIP/nested APK with hundreds of entries. Its largest DEX and native libraries are accompanied by Pangle/TTPlayer advertising and media components. Its contents include ad mediation, playable-ad, video-player and HTTP-DNS strings. This is not the protected Panda application layer and should not be mined for Panda login or game-room endpoints.

## UI/resource clues

The outer APK's resources expose names such as `activity_login`, `activity_login_verify_code`, `activity_netgame_list`, game-history list layouts, and the app's `QDSurfaceView`. Combined with the manifest's activity declarations, this confirms that login/verification and game/room browsing are app features. Resource names do not reveal the network contracts.

## Safe next step

The remaining high-value step is runtime observation on an authorized Android installation:
1. Capture the point at which SecShell materializes or loads the protected DEX.
2. Record the loaded class/package names and map the login, catalog and room-allocation call sites.
3. Capture sanitized request/response schemas with credentials, cookies, personal data and live tokens removed.
4. Trace the room response into the Limelight/Moonlight service and record the actual GameStream handoff fields.
5. Implement the iOS provider adapter only after those contracts are verified.

A static-only analysis of the encrypted JAR cannot responsibly provide the Panda API, account auth or host/session details. No endpoints, keys or tokens have been guessed in this report.
