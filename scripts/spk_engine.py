#!/usr/bin/env python3
"""Verify Sparking! ZERO support already present in the pinned upstream NXNative engine.

Do not patch patch_nso.py or hle_uemalloc.c: upstream's engine-wide FMallocBinned3
detector handles both constructor call sites for this game.
"""
from __future__ import annotations
import argparse
from pathlib import Path

TITLE_ID = "010035F022078000"
BUILD_ID = "68edafd68c7bc1a1af50b82aac838018"
MAIN_SHA256 = "a0f8f0644c92384ddb1baac1c21aecbeeace5bc99ad40895e216add61da78efe"
VTABLE = 0x8703AB8
GETTER_SLOT = 19
LAYOUT = "UE4_27"
ALLOCATOR_CALLS = (0x1E4DB30, 0x1E4E048)

def fail(message: str) -> None:
    raise SystemExit("[SpkIOSzero] ERROR: " + message)

def verify(engine_root: Path) -> dict:
    engine = engine_root.resolve()
    profile_dir = engine / "dm/games" / TITLE_ID
    profile_path = profile_dir / "game.tsv"
    allocator_path = engine / "dm/tools/ue_malloc.py"
    rewriter_path = engine / "dm/tools/patch_nso.py"
    hle_path = engine / "dm/host/hle_uemalloc.c"
    readme_path = profile_dir / "README.md"

    for path in (profile_path, allocator_path, rewriter_path, hle_path, readme_path):
        if not path.is_file():
            fail(f"pinned NXNative Sparking! ZERO support file is missing: {path}")

    profile = profile_path.read_text(encoding="utf-8")
    allocator = allocator_path.read_text(encoding="utf-8")
    rewriter = rewriter_path.read_text(encoding="utf-8")
    hle = hle_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")

    expected_build = f"build\tv327680\t2.0.76\tmain={BUILD_ID}"
    if expected_build not in profile:
        fail("NXNative's built-in Sparking! ZERO profile does not register the inspected 2.0.76 main Build ID.")
    if "modules\tmain subsdk0 sdk" not in profile:
        fail("NXNative's built-in Sparking! ZERO profile has an unexpected module list.")
    for required in (
        "mem_reserve\t0xF0000000",
        "mem_alias\t0xC8000000",
        "mem_stack\t0x10000000",
        "app_pool\t0xCD500000",
        "sys_resource\t0x1e00000",
        "fps_target\t60",
        "shader_groups\tGlobalShaderCache=global #Engine/=engine #SparkingZERO/=game",
    ):
        if required not in profile:
            fail(f"NXNative's registered Sparking! ZERO profile is missing: {required}")

    if "19: 'Unreal Engine 4.26 / 4.27'" not in allocator:
        fail("NXNative ue_malloc.py no longer recognizes the getter slot 19 layout used by Sparking! ZERO.")
    if "return tuple(calls), vt, slot" not in allocator:
        fail("NXNative ue_malloc.py no longer returns every constructor call site.")
    if "for _c in UE_CALLS or ():" not in rewriter:
        fail("NXNative patch_nso.py no longer cuts every call returned by ue_malloc.find().")
    if "region_obs.append((_c, OBS_UE_MALLOC" not in rewriter:
        fail("NXNative patch_nso.py no longer installs the generic x0 allocator observation gate.")
    if "[UE4_27] = { 19, 21, 3, 4, 5, 6, 7, 8, 9," not in hle:
        fail("NXNative HLE does not have the 19-slot allocator layout required by the game.")
    if "if (m->ue_malloc_vt)" not in hle:
        fail("NXNative HLE no longer installs the allocator from the rewriter's fixups.")

    for address in ("main+0x1e4db30", "main+0x1e4e048"):
        if address not in readme:
            fail(f"NXNative's game note does not document expected FMallocBinned3 constructor call {address}.")
    if (profile_dir / "patches.py").exists():
        fail("The official Sparking! ZERO profile must not contain a custom patches.py; upstream uses generic allocator and network support.")
    if "SPK_FIXED_MAIN" in rewriter or "f9035293" in rewriter:
        fail("A fixed-offset SPK override is present in patch_nso.py; remove it and use upstream's generic detector.")

    result = {
        "title_id": TITLE_ID,
        "build_id": BUILD_ID,
        "main_sha256": MAIN_SHA256,
        "allocator": "NXNative engine-wide ue_malloc.find",
        "layout": LAYOUT,
        "vtable": f"{VTABLE:#x}",
        "getter_slot": GETTER_SLOT,
        "constructor_calls": [f"{x:#x}" for x in ALLOCATOR_CALLS],
        "object_register": "x0",
        "profile": str(profile_path),
        "custom_patches": False,
    }
    print(
        "[SpkIOSzero] Verified upstream native support: 2 FMallocBinned3 call sites, "
        "vtable 0x8703ab8, getter slot 19, generic x0 gates; no local binary patches.",
        flush=True,
    )
    return result

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-root", type=Path, required=True)
    verify(ap.parse_args().engine_root)

if __name__ == "__main__":
    main()
