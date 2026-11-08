# Pipeline handoff contract

The handoff format is intentionally not frozen yet. It must be derived from an execution trace of the pinned NX2Apple/NXNative builder, not guessed from directory names.

Before enabling the macOS job, establish:
1. the exact Linux-safe commands and their output paths;
2. the complete list of files consumed by the Apple-only stage;
3. whether each game's shader path requires runtime capture or Apple Metal compilation;
4. the RomFS identity and separate-data packaging requirements;
5. a manifest and checksum validation performed before any compilation.

The finalizer must fail closed on missing, stale, mismatched or unsupported artifacts. It must not silently rebuild Linux-only stages on macOS or package an incomplete game framework.
