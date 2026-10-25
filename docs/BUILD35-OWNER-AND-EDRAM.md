# XOWUE — Build 35 AOT owner recovery and Xenos copy-source verification

## Ground truth: user test Build 34 (2026-10-24, 21:52 BRT)
- Boot succeeded. XEX base=0x82000000, entry=0x82C3CAA8, 261 imports resolved.
- Previous blocked bctrl at 0x82361BF4 / CTR=0 passed (unlike Build 33).
- New fatal: AOT lookup at target=0x82C30BFC, CTR=0x82C30BFC, LR=0x82C30B10, callsite=0x82C30B0C, direct PPC instruction 0x4BFF9499, last AOT owner=0x82C30B08, slot is empty. This is **not** the old null-vtable crash.
- AOT: 995336 calls, 7219 distinct functions (Build33 148761/6973).
- Native Vulkan: 26 guest draw captures; 25 issued. Depth-only draw uses 4x MSAA tile 720, then copy attempts source RT0 tile 720 with no color target present. Readback: nonblack=0; don't invent pixels.
- RB_COPY_CONTROL=0x00100000: src_select=0 (RT0), command=(control>>20)&3=1 (Convert), per xenia-project/xenia src/xenia/gpu/registers.h RB_COPY_CONTROL. Depth source is index 4; do not treat existing depth tile as color data. The copy request remains unresolved until genuine color EDRAM writes exist.
- UI: native UIKit back navigation is **proven** by logs 'navigation.back tapped' / 'navigation.back dismissed UIKit landscape host'; scene returned to library. Orientation request initially logs portrait-only presentation warning.

## Build 35 change
- Extend verified owner-wide native PPC AOT continuation recovery to the exact observed target 0x82C30BFC. The recovery helper enumerates the one real owning PPC function in the archived AOT units, reconstructs every translated instruction label from its retained PPC opcode comments, creates compiled C++ wrappers and guest dispatch table entries for all verified internal addresses. It fails safely on unknown/ambiguous owners. This is no runtime PPC interpreter or JIT, no forged return address.
- Precompile additional nearby owner interiors, bounded by 72 owners and 12288 validated guest-instruction entries.
- GitHub Actions now requires an exact 0x82C30BFC entry in ppc_func_mapping.cpp **and** a 0x82C30BFC symbol in the linked Mach-O before uploading IPA.
- Xenos Vulkan render code now honors copy_src_select RT0..RT3, rejects unsupported depth/unrecognized commands instead of pretending RT0, and logs the selected source and absence of genuine EDRAM color. This does not generate artificial color frames.

## Proof limits and acceptance criteria
GitHub compilation passes do NOT prove runtime rendering. Check iPhone native diagnostics for:
- no 'AOT dispatch slot is empty' at 0x82C30BFC;
- new AOT execution milestone / any next PC, or a safe stop with precise owner and registers;
- real color EDRAM surface, successful resolve/writeback, nonblack GPU readback and eventual Wolverine menu frames;
- correct back navigation and file exports.
Branch XOWUE only, other branches unchanged.
