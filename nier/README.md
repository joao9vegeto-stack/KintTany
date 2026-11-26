# Nier2iOS — NieR:Automata The End of YoRHa Edition
Title ID USA: 010056B015FE8000; update 1.0.3 (v131072); iOS 26; registered NXNative NVN profile at b526a50b85e4cfa3142c111e1ad491d9fd11f0eb.
Drive: https://drive.google.com/drive/folders/11udbko06i5QvX930AiwR-VQ8Lu0bP39E
Open [Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/Nier2iOS/nier/colab/Nier2iOS.ipynb).
The notebook ingests source packages, overlays translation ZIP's Asia/USA RomFS onto the US image, verifies hashes and builds Linux workspace. Only the explicit handoff cell triggers the Mac workflow; no game data or signed source URLs are committed.
Shared Shell provides per-button mapping (including A/B and X/Y) and native game exit. Launcher includes 30/60 and PT-BR status. No Fairy Tail KTGL, Blades or Biomutant game-specific payloads retained. External RomFS/AOC; thin IPA.
Initial port source implementation; not tested with real game files or Xcode yet. Any unknown translation path, incompatible version or invalid archive fails closed.
