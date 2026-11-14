#!/usr/bin/env python3
"""Idempotent, build-ID-gated Sparking! ZERO changes for the pinned NXNative engine."""
from __future__ import annotations
import argparse
from pathlib import Path

BUILD_ID = "68edafd68c7bc1a1af50b82aac838018"
MAIN_SHA256 = "a0f8f0644c92384ddb1baac1c21aecbeeace5bc99ad40895e216add61da78efe"
CUT_ADDR = 0x1e4db30
CUT_BYTES = "6b740194"
OBS_ADDR = 0x1e4db34
OBS_WORD = "f9035293"
VTABLE = 0x8703ab8
OBS_UE_MALLOC = 21
OBS_OBJECT_REGISTER = 19

def fail(message: str) -> None:
    raise SystemExit("[SpkIOSzero] ERROR: " + message)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        fail(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)

def patch(engine_root: Path) -> None:
    engine = engine_root.resolve()
    hle = engine / "dm/host/hle_uemalloc.c"
    nso = engine / "dm/tools/patch_nso.py"
    if not hle.is_file() or not nso.is_file():
        fail(f"pinned NXNative source tree is incomplete: {engine}")
    h = hle.read_text(encoding="utf-8")
    h = replace_once(
        h,
        "enum { UE5, UE4_27, UE5_6, UE3 };",
        "enum { UE5, UE4_27, UE5_6, UE5_SPK, UE3 };",
        "allocator layout enum",
    )
    row = (
        "    [UE5_SPK] = { 23, 27, 3, 4, 5, 6, 7, 8, 9, { 10, 11, 12, 16 }, false },"
        "   // Sparking! ZERO UE5.1: getter slot 23; vtable main+0x8703ab8"
    )
    anchor = (
        "    [UE5_6] = { 26, 32, 6, 7, 8, 9, 10, 13, 14, { 15, 16, 17, 18, 19, 23 } },"
    )
    if "[UE5_SPK]" not in h:
        h = replace_once(h, anchor, anchor + "\n" + row, "allocator layout row")
    if "[UE5_SPK]" not in h:
        fail("UE5_SPK allocator layout was not installed")

    # The HLE only installs its malloc zone for a Build ID in k_ue. A dynamic
    # object (obj=0) is populated by OBS_UE_MALLOC, whose upper byte selects x19.
    table_anchor = (
        'static const struct { const char *build, *what; int layout; uint64_t obj, vtable, cut; uint32_t cut_insn; } k_ue[] = {'
    )
    table_row = (
        '    { "68edafd68c7bc1a1af50b82aac838018", "DRAGON BALL: Sparking! ZERO 2.0.76", '
        'UE5_SPK, 0, 0x8703ab8, 0x1e4db30, 0xd503201f },'
        ' // dynamic FMallocBinned3 object arrives through OBS_UE_MALLOC(x19)'
    )
    if "DRAGON BALL: Sparking! ZERO 2.0.76" not in h:
        h = replace_once(h, table_anchor, table_anchor + "\n" + table_row, "allocator Build ID row")
    if "DRAGON BALL: Sparking! ZERO 2.0.76" not in h:
        fail("UE5_SPK k_ue Build ID row was not installed")
    hle.write_text(h, encoding="utf-8")

    p = nso.read_text(encoding="utf-8")
    detect_anchor = "UE_CALLS, UE_VT, UE_SLOT, ue_why = ue_malloc.find(bytes(IMG), TEXT_END, RO_OFF, DATA_OFF)\n"
    detect_patch = detect_anchor + f'''SPK_FIXED_MAIN = NAME == "main" and BUILD_ID == "{BUILD_ID}"
if SPK_FIXED_MAIN:
    # The standard detector deliberately rejects this engine's duplicated lazy
    # constructors. The inspected main build has a confirmed direct call, vtable
    # and object register; pin them only to this exact Build ID.
    assert IMG[{CUT_ADDR:#x}:{CUT_ADDR:#x}+4].hex() == "{CUT_BYTES}", "Sparking! ZERO allocator cut bytes changed"
    assert IMG[{OBS_ADDR:#x}:{OBS_ADDR:#x}+4].hex() == "{OBS_WORD}", "Sparking! ZERO allocator observation instruction changed"
    UE_CALLS, UE_VT, UE_SLOT = ({CUT_ADDR:#x},), {VTABLE:#x}, 23
    ue_why = "DRAGON BALL: Sparking! ZERO UE5.1 fixed allocator layout (reviewed main build)"
'''
    p = replace_once(p, detect_anchor, detect_patch, "allocator detection hook")

    obs_anchor = r'''for _c in UE_CALLS or ():
    assert _c not in kinds and not any(lo <= _c < hi for wseg in windows for lo, hi in [(wseg[0].address, wseg[-1].address + 4)]), f'FMallocBinned3 gate conflicts with a rewrite site {_c:#x}'
    region_obs.append((_c, OBS_UE_MALLOC, f'{NOP:08x}', 'FMallocBinned3 constructor call (cut): the object in x0; the host puts its allocator\'s vtable in (hle_uemalloc.c)'))
'''
    obs_patch = f'''if SPK_FIXED_MAIN:
    # The constructor call is cut at main+{CUT_ADDR:#x}; x19 contains the allocator object
    # at the following store. Gate there and replace the vtable through that object.
    assert {OBS_ADDR:#x} not in kinds and not any(lo <= {OBS_ADDR:#x} < hi for wseg in windows for lo, hi in [(wseg[0].address, wseg[-1].address + 4)]), "Sparking! ZERO allocator observation conflicts with a rewrite site"
    region_obs.append(({OBS_ADDR:#x}, OBS_UE_MALLOC | ({OBS_OBJECT_REGISTER} << 8), "{OBS_WORD}", "Sparking! ZERO FMallocBinned3 object in x19; install the host allocator vtable"))
else:
    for _c in UE_CALLS or ():
        assert _c not in kinds and not any(lo <= _c < hi for wseg in windows for lo, hi in [(wseg[0].address, wseg[-1].address + 4)]), f'FMallocBinned3 gate conflicts with a rewrite site {{_c:#x}}'
        region_obs.append((_c, OBS_UE_MALLOC, f'{{NOP:08x}}', 'FMallocBinned3 constructor call (cut): the object in x0; the host puts its allocator\\'s vtable in (hle_uemalloc.c)'))
'''
    p = replace_once(p, obs_anchor, obs_patch, "allocator observation gate")
    nso.write_text(p, encoding="utf-8")
    print("[SpkIOSzero] UE5_SPK allocator layout and exact-build rewrite/gate patches installed.")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-root", type=Path, required=True)
    patch(ap.parse_args().engine_root)

if __name__ == "__main__":
    main()
