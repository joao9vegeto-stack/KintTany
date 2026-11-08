# Google Colab preparation

Open Kleo2iOS_Colab.ipynb in Google Colab and run the cells from top to bottom.

The notebook pins NX2Apple v1.3.0-rc10, syncs the exact NXNative pin and Route C patches, and runs the repository's own NUP extraction, module rewriter and offline shader splitter. It stops before Metal/Xcode. The Apple-only build is performed by the macOS Actions runner.

Requirements:
- Python 3.12+ Colab runtime;
- a Google Drive folder shared with the Actions service account (Viewer);
- GitHub secret GOOGLE_SERVICE_ACCOUNT_JSON;
- a fine-grained GitHub token with Contents read/write for joao9vegeto-stack/KintTany;
- enough Colab disk and Drive quota for the NUP plus extracted RomFS and build intermediates.

The notebook does not ask for console keys: a NUP container does not need prod.keys.
