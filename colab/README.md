# Colab preparation stage

The notebook for this stage will be added after the Linux/Apple boundary is verified against the pinned upstream revision.

Expected responsibilities:
- accept a user-supplied NSP/XCI/NUP or supported extracted dump;
- keep prod.keys/title.keys in the Colab runtime only;
- run only preparation and AOT steps that do not require macOS, Xcode, iOS SDK or Apple's Metal compiler;
- preserve all generated modules, metadata, shader inputs and game-data identity required by the macOS finalizer;
- create a manifest with upstream revision, game title ID/version, input hashes, output file hashes and required next-stage commands;
- upload the private handoff archive to the user's Google Drive.

The notebook must never commit game data or keys to GitHub.
