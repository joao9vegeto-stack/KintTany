# HookLink2iOS resources — HookLink 4.0 (X3)

This folder contains the native iOS resources for Ocarina of Time Switch 2, update v131072.

**Verified official pins:** HookLink 4.0 `b5c41acf469edb99abc5156f1f6f18397261f54a`, nxnative `ee3ce6a02bc737d38795f0a96cce494cee7a799c`, Metal shader chain `b6112b954691`.

- `Resources/engine.json`: matching upstream engine version; NOT the legacy 1.8.5 code.
- `Resources/presets/iphone.env`: X3-compatible runtime settings. QoS/dynamic resolution/thermal limits are **launcher defaults** defined in the X3 builder, not locked in env.txt.
- `Resources/presets/entitlements.plist`: ad-hoc signed increased-memory entitlement.
- `Resources/tools/hl_resolution.py`: resolution overlay generator; original previously verified overlay reused.
- `scripts/push_romfs.sh`: external RomFS installation helper.

Source games, keys, RomFS and converted shaders are not committed to Git. The NUP is read by the macOS full rebuild pipeline from the user's verified private Drive handoff and authenticated/hashed before extraction. iOS target: 26.0; runner xcode-27; offline PSO: none; 42,848 game shader map entries need the **new** X3 translator and fresh Metal libraries. Build output alone is not proof of runtime stability.

See [the complete X3 migration report](../docs/HOOKLINK2IOS-V4-MIGRATION.md). The old 1.8.5 runtime can still be examined using [the historical native relink report](../docs/HOOKLINK2IOS-NATIVE-X3-SELECTIVE-PORT.md); it is not the same as the native 4.0 upgrade.
