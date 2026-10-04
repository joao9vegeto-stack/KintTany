# VitaJoN

Branch isolada para o port PS Vita no iOS.

Base de emulação: Tsubomi 0.47.0 (Vita3K iOS), fixado no commit:
7e53bac87f442e770a39b1d9b032133418337f6d

Objetivo desta primeira build:
- preservar o Dynarmic/Oaknut JIT compatível com iOS 26 usado pelo Tsubomi;
- manter Vulkan -> MoltenVK -> Metal;
- perfil inicial focado em jogos pesados (resolução 0,75x e memory mapping sem double-buffer);
- solicitar get-task-allow, increased-memory-limit e extended-virtual-addressing no IPA;
- bundle separado com nome VitaJoN;
- suporte iOS a relaunch LoadExec (necessário para jogos como Uncharted que trocam do eboot.bin para outro SELF);
- perfil PCSA00029: High Accuracy + Surface Sync + resolução 1x;
- correção de partial color-surface e reinterpret cast byte-equivalente (720x8 B -> 1440x4 B) para o framebuffer do Uncharted;
- implementação de ColorSurface Clip e fallback seguro de sampler para cube textures;
- um único workflow para gerar o IPA unsigned/ad-hoc para sideload.

Nenhum código ou workflow do KintTany é usado nesta branch.

0.47.5: ported Vita3K+ typeless transfer synchronization and Uncharted shader fixes (zeroed private register banks, scalar DUAL broadcast, F16 reinterpret handling, shader-cache version bump).

0.47.6: substitui o typeless copy antigo do Tsubomi pelo compute-deinterleave do Vita3K+ e compila o shader SPIR-V no Actions.

0.47.8: MoltenVK 1.4.2 (fix oficial de channel corruption em Apple Silicon para color RT usados como transfer source), compute typeless alinhado ao Vita3K+ e Double Buffer forçado no PCSA00029 em 1x.
