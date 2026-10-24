# XOWUE — Global native PPC AOT recovery and portrait host

## Scope
- Xbox 360 executable: Wolverine (Title ID 41560816), user's unchanged XEX.
- Git branch: `XOWUE` only. Does not touch PoPTST, PsTJohn or other branches.
- iPhone host orientation: portrait only, including the game surface.
- Guest 1280×720 pixels are rotated and aspect-fitted by the existing
  `KKWriteGuestFrame` into the portrait CAMetalLayer. This does not create
  missing guest GPU draws.

## Global AOT pipeline
Earlier native switch lowering handled four XEX-verified `bctr` tables,
but a distinct table at `0x82D31E40`, with 440 entries and 260 destinations,
still produced an unregistered guest entry at `0x82D34198`.

The new global recovery processes 54 decoded XEX jump-table candidates
(3,198 entries) **in one run**, before compiling all 344 AOT source units.
It does not assume every candidate or destination is a valid local branch:
it compares table branches with the actual translated `bctr` instruction,
checks guest PC-to-AOT instruction indices and reuses native instruction bodies.

Verified within-function targets become direct C++ `goto` branches. When
a verified table target belongs to another existing compiled function *but
is not a public entry*, the builder can generate a compiled ARM64 native
continuation for that target, rather than interpreting a PPC instruction.
Unverifiable and cross-function targets remain guarded by the prior AOT
dispatcher; their addresses appear in the JSON evidence report.

No JIT, CPU emulation fallback, no NOPs and no fabricated successful GPU
draws are inserted.

## Source provenance
To avoid including the copyrighted full XEX, the repository retains
`tools/xowue_tables.guest.bin.z`: 54 verified raw big-endian jump-offset
tables compressed with zlib. The archive and its SHA256 are checked in CI.
`tools/patch_xowue_global_native.py.z` is the companion compressed Python
source and CI unpacks it to a readable .py, checks the SHA256 and uploads that
source as an Actions artifact. The scripts are always run against the
actual archived AOT source tree.

## Acceptance criteria
1. Global-AOT builder produces a nonempty per-table JSON audit, with explicit
   counts of local branches, native continuations and unverifiable targets.
2. iOS build succeeds without changing unrelated Git branches.
3. iPhone rotates neither the library nor the game surface to landscape.
4. The *real* Xenos path must submit Vulkan draws and EDRAM resolves before
   any build may be described as rendering Wolverine's gameplay.

**Important:** changing the UI orientation does not solve the Xenos render
pipeline. Compilation and a successful IPA are not proof of the first game
frame. The existing shaders are real guest shaders; the missing GPU pipeline
remains separate until draws, textures, EDRAM and resolves are fully linked.


## Build 25 structural correction
- Actual iOS gameplay switches to landscape-right, while the library returns to portrait; Info.plist advertises both before UIWindowScene geometry requests.
- Global AOT recovery includes real terminal PPC `blr` tails and verified small linear function suffixes, using compiled ARM64 translation only. Unsafe paths remain guarded and are counted; a CI check enforces the known Build 24 target `0x831A9EBC`.
- Xenos register snapshots `PA_CL_VTE_CNTL` and `PA_CL_VPORT_*` are carried with each PM4 draw, and guest coordinates are converted to Vulkan clip space. Landscape viewports preserve 1280x720 aspect.
- An accepted Vulkan draw is **not** proof of non-black pixels. GPU readback continues to report measured pixels.
- On-device XEX execution is required to prove new gameplay, since macOS Actions cannot boot the Xbox guest in the iPhone runtime.
