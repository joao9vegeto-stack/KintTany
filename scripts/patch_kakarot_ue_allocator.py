#!/usr/bin/env python3
"""Add the verified Kakarot UE4 legacy FMallocBinned3 layout to the pinned NXNative checkout.

This is a narrow, idempotent source patch. It does not change the game NSO.
After patching, it runs NXNative's production ue_malloc.find() against the exact
Kakarot main NSO and requires the measured constructor, call site, vtable and slot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TITLE_ID = "010051C0134F8000"
MAIN_BUILD_ID = "e99dffa39354b6068f8e7c984c77bc84"
MAIN_SHA256 = "ab7b273de977d13af28f34c027497e73248050ff01db74a4c9244876ee5ab9ba"
CONSTRUCTOR = 0x235C4A0
CALL_SITE = 0x24B37B8
VTABLE = 0x8A181E8
GETTER_SLOT = 17

OLD_LAYOUTS = "LAYOUTS = {19: 'Unreal Engine 4.26 / 4.27', 22: 'Unreal Engine 5', 26: 'Unreal Engine 5.6'}"
NEW_LAYOUTS = "LAYOUTS = {17: 'Unreal Engine 4 legacy (getter slot 17)', 19: 'Unreal Engine 4.26 / 4.27', 22: 'Unreal Engine 5', 26: 'Unreal Engine 5.6'}"

OLD_ENUM = "enum { UE5, UE4_27, UE5_6, UE3 };"
NEW_ENUM = "enum { UE5, UE4_LEGACY, UE4_27, UE5_6, UE3 };"
UE5_ROW = "    [UE5] = { 22, 26, 6, 7, 8, 9, 10, 11, 12, { 13, 14, 15, 19 } },"
LEGACY_ROW = (
    "    // Kakarot's measured legacy FMallocBinned3 vtable (getter slot 17): "
    "Malloc=3, Realloc=4, Free=5, QuantizeSize=6, GetAllocationSize=7. "
    "Trim/TLS setup/TLS teardown/DumpAllocatorStats (8/9/10/14) use host no-ops.\n"
    "    [UE4_LEGACY] = { 17, 22, 3, 0, 4, 0, 5, 6, 7, { 8, 9, 10, 14 } },\n"
)


def fail(message: str) -> None:
    raise SystemExit("[Kakarot UE allocator patch] ERROR: " + message)


def patch_layout_detector(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if NEW_LAYOUTS in source:
        print("[patch] already applied: ue_malloc.py getter-slot-17 detector")
        return
    if OLD_LAYOUTS not in source:
        fail("ue_malloc.py does not match the exact pinned context; refusing a fuzzy patch")
    path.write_text(source.replace(OLD_LAYOUTS, NEW_LAYOUTS, 1), encoding="utf-8")
    print("[patch] applied: ue_malloc.py getter-slot-17 detector")


def patch_host_layout(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    changed = False
    if NEW_ENUM not in source:
        if OLD_ENUM not in source:
            fail("hle_uemalloc.c enum does not match the exact pinned context")
        source = source.replace(OLD_ENUM, NEW_ENUM, 1)
        changed = True
    if LEGACY_ROW.strip() not in source:
        if UE5_ROW not in source:
            fail("hle_uemalloc.c UE5 layout row is missing; refusing a fuzzy insertion")
        source = source.replace(UE5_ROW, LEGACY_ROW + UE5_ROW, 1)
        changed = True
    # Fail closed on a duplicate or malformed legacy entry.
    if source.count("[UE4_LEGACY]") != 1:
        fail("hle_uemalloc.c must contain exactly one UE4_LEGACY layout")
    if changed:
        path.write_text(source, encoding="utf-8")
        print("[patch] applied: hle_uemalloc.c UE4 legacy slot-17 vtable layout")
    else:
        print("[patch] already applied: hle_uemalloc.c UE4 legacy slot-17 vtable layout")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--main-nso", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    pin_file = engine.parent / ".upstream-ref"
    if not pin_file.is_file() or pin_file.read_text(encoding="utf-8").strip() != "81906931262fb25d774cce8bca2db8926439e5a2":
        fail("NXNative .upstream-ref does not match the reviewed engine pin")

    main_nso = args.main_nso.resolve()
    if not main_nso.is_file():
        fail(f"Kakarot main NSO is missing: {main_nso}")
    digest = hashlib.sha256(main_nso.read_bytes()).hexdigest()
    if digest != MAIN_SHA256:
        fail(f"Kakarot main SHA-256 mismatch: {digest}")

    sys.path.insert(0, str(engine / "dm/tools"))
    import nso
    module = nso.read(str(main_nso))
    build_id = module.build_id.hex()
    if build_id != MAIN_BUILD_ID:
        fail(f"Kakarot main Build ID mismatch: {build_id}")

    tools = engine / "dm/tools"
    patch_layout_detector(tools / "ue_malloc.py")
    patch_host_layout(engine / "dm/host/hle_uemalloc.c")

    # Run the production detector after patching; there is no temporary layout override.
    import ue_malloc
    calls, vtable, slot, reason = ue_malloc.find(
        bytes(module.image), module.text_end, module.segments[1][0], module.segments[2][0])
    if tuple(calls or ()) != (CALL_SITE,) or vtable != VTABLE or slot != GETTER_SLOT:
        fail(
            "production detector did not identify the measured Kakarot allocator: "
            + json.dumps({"calls": [hex(x) for x in (calls or ())],
                          "vtable": hex(vtable) if vtable is not None else None,
                          "getter_slot": slot, "reason": reason}, sort_keys=True)
        )
    print(json.dumps({
        "status": "verified",
        "title_id": TITLE_ID,
        "main_build_id": build_id,
        "main_sha256": digest,
        "allocator_constructor": hex(CONSTRUCTOR),
        "constructor_call_sites": [hex(x) for x in calls],
        "vtable": hex(vtable),
        "getter_slot": slot,
        "layout": "UE4_LEGACY",
        "host_slots": {
            "malloc": 3, "realloc": 4, "free": 5,
            "quantize_size": 6, "get_allocation_size": 7,
            "no_op": [8, 9, 10, 14],
        },
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
