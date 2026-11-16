#!/usr/bin/env python3
"""Read-only audit of the existing Kakarot rewrite and Unreal memory hooks.

This restores only the already-uploaded 84 MB workspace archive from Drive.
It does not download NSP/XCI inputs, RomFS, AOC, shaders, or the IPA.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TITLE_ID = "010051C0134F8000"
PROJECT = "KaKaRoTiOS"
BRANCH = "KaKaRoTiOS"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"


def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS memory audit] ERROR: " + message)


def run_capture(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    print("$ " + " ".join(command), flush=True)
    print(output.rstrip() or "(no output)", flush=True)
    if result.returncode:
        fail(f"command exited {result.returncode}: {' '.join(command)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, default=Path("handoff.json"))
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    if (engine.parent / ".upstream-ref").read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("NXNative engine pin mismatch.")
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if (handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
            or handoff.get("title_id") != TITLE_ID or handoff.get("engine_pin") != ENGINE_PIN):
        fail("handoff identity or engine pin mismatch.")
    prep_record = handoff.get("prepared") or {}
    if prep_record.get("profile_type") != "provisional":
        fail("expected the original provisional Kakarot preparation.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("GOOGLE_SERVICE_ACCOUNT_JSON is empty.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # Reuse the exact transfer and archive-safety implementation from the production
    # Kakarot Actions restore code. Only the 84 MB workspace archive is restored.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prepare_kakarot_actions as restore

    restore.verify_drive_metadata(api, handoff["work_archive"], "Kakarot workspace archive")
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "kakarot-work.tar.zst"
    print("[audit] Downloading the existing workspace archive only.", flush=True)
    restore.download_drive_file(api, credentials, handoff["work_archive"], archive, parallel_workers=6)
    work = destination / "work"
    restore.extract_verified_archive(archive, work)
    archive.unlink(missing_ok=True)

    prep_path = work / "kakarot-linux-prep.json"
    if not prep_path.is_file():
        fail("kakarot-linux-prep.json is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "engine_pin", "profile_type",
                "profile_source", "modules", "main_build_id", "main_sha256", "rewrite_audit"):
        if prep.get(key) != prep_record.get(key):
            fail(f"workspace/handoff mismatch for {key}.")
    version = str(prep["package_version"])
    exefs = work / "extract" / version / "ExeFS"
    patched = work / f"patched_{version}"
    profile = work / "profile" / TITLE_ID / "game.tsv"
    main = exefs / "main"
    for path in (main, exefs / "main.npdm", patched / "main.patched.bin", profile,
                 patched / "main.cuts.tsv", patched / "main.obs.tsv", patched / "main.fixups.tsv"):
        if not path.is_file():
            fail(f"required audit input missing: {path}")

    print("\n=== ORIGINAL GAME PROFILE (memory/Unreal fields) ===", flush=True)
    profile_lines = profile.read_text(encoding="utf-8", errors="replace").splitlines()
    selected = [line for line in profile_lines if (
        line.startswith("#") or line.split("\t", 1)[0] in {
            "title_id", "program_id", "name", "build", "modules", "mem_reserve",
            "mem_alias", "mem_stack", "app_pool", "sys_resource", "mem_used",
            "game_args", "game_env", "stdalloc_cap"
        })]
    print("\n".join(selected), flush=True)

    print("\n=== ORIGINAL / REWRITTEN MODULE IDENTITY ===", flush=True)
    print(json.dumps({
        "main_build_id": prep.get("main_build_id"),
        "main_sha256": prep.get("main_sha256"),
        "modules": prep.get("modules"),
        "rewrite_audit": prep.get("rewrite_audit"),
    }, indent=2), flush=True)

    for name in ("main.cuts.tsv", "main.obs.tsv", "main.fixups.tsv"):
        path = patched / name
        print(f"\n=== {name} ===", flush=True)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if name == "main.fixups.tsv":
            lines = [line for line in lines if (
                line.startswith("#") or re.search(r"UE_MALLOC|UE_REGION|OBS_UE|region|malloc", line, re.I)
            )]
        print("\n".join(lines) if lines else "(empty)", flush=True)

    tools = engine / "dm" / "tools"
    print("\n=== PINNED GENERIC FMallocBinned3 DETECTOR ===", flush=True)
    ue_malloc_output = run_capture([sys.executable, str(tools / "ue_malloc.py"), str(main)])
    print("\n=== PINNED GENERIC UNREAL ENGINE-REGION DETECTOR ===", flush=True)
    ue_region_output = run_capture([sys.executable, str(tools / "ue_region.py"), str(main)])

    # Temporarily whitelist slot 17 to expose its vtable entries. This is read-only:
    # no engine file, game module, profile, or rewrite output is modified.
    print("\\n=== SLOT-17 FMallocBinned3 VTABLE DISASSEMBLY (diagnostic only) ===", flush=True)
    sys.path.insert(0, str(tools))
    import nso
    import ue_malloc
    module = nso.read(str(main))
    image = bytes(module.image)
    original_layouts = dict(ue_malloc.LAYOUTS)
    ue_malloc.LAYOUTS[17] = "diagnostic unknown slot-17 layout"
    calls, vtable, getter_slot, allocator_reason = ue_malloc.find(
        image, module.text_end, module.segments[1][0], module.segments[2][0])
    ue_malloc.LAYOUTS.clear()
    ue_malloc.LAYOUTS.update(original_layouts)
    print("allocator_reason=" + str(allocator_reason), flush=True)
    print("constructor_calls=" + repr([hex(x) for x in (calls or ())]), flush=True)
    print("vtable=" + (hex(vtable) if vtable is not None else "none")
          + " getter_slot=" + str(getter_slot), flush=True)
    if vtable is not None:
        relocated = ue_malloc.relocated(image)
        word_value = lambda offset: relocated.get(
            offset, int.from_bytes(image[offset:offset + 8], "little"))
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        disassembler = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        for index in range(0, min(24, getter_slot + 5)):
            pointer = word_value(vtable + index * 8)
            print(f"\\nVT[{index}] = {pointer:#x}", flush=True)
            if 0 < pointer < module.text_end:
                decoded = list(disassembler.disasm(
                    image[pointer:min(pointer + 0x60, module.text_end)], pointer))
                print(" | ".join(
                    f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}".rstrip()
                    for ins in decoded[:36]), flush=True)
            else:
                print("(not a code pointer in main text)", flush=True)

    print("\n=== DIAGNOSTIC VERDICT ===", flush=True)
    print("allocator_detector_has_call_sites=" + str(bool(re.search(r"FMallocBinned3 .*constructor", ue_malloc_output))), flush=True)
    print("engine_region_detector_has_gate=" + str(bool(re.search(r"reserved at .*nninitStartup", ue_region_output))), flush=True)
    print("engine_region_detector_red=" + str("[RED]" in ue_region_output), flush=True)
    print("audit_complete=true", flush=True)


if __name__ == "__main__":
    main()
