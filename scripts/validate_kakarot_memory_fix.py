#!/usr/bin/env python3
"""Re-run only Kakarot's main-module rewrite with the reviewed Unreal slot-17 host hook.

Restores the already uploaded 84 MB workspace. No NSP/XCI, RomFS, AOC, Metal
shader or existing IPA payload is downloaded by this validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TITLE_ID = "010051C0134F8000"
PROJECT = "KaKaRoTiOS"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
MAIN_BUILD_ID = "e99dffa39354b6068f8e7c984c77bc84"
MAIN_SHA256 = "ab7b273de977d13af28f34c027497e73248050ff01db74a4c9244876ee5ab9ba"
CALL_SITE = "0x24b37b8"
REGION_SITE = "0x24b3190"


def fail(message: str) -> None:
    raise SystemExit("[Kakarot memory-fix validation] ERROR: " + message)


def run(command: list[str], env: dict[str, str]) -> str:
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    if output:
        print(output.rstrip(), flush=True)
    if result.returncode:
        fail(f"command exited {result.returncode}: {' '.join(command)}")
    return output


def set_profile_value(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for key, value in updates.items():
        indices = [i for i, row in enumerate(lines) if row.partition("\t")[0] == key]
        if len(indices) > 1:
            fail(f"{path}: duplicate profile key {key}")
        row = f"{key}\t{value}"
        if indices:
            lines[indices[0]] = row
        else:
            lines.append(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    check = path.read_text(encoding="utf-8").splitlines()
    for key, value in updates.items():
        if check.count(f"{key}\t{value}") != 1:
            fail(f"{path}: could not set exactly one {key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, default=Path("handoff.json"))
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    engine = args.engine_root.resolve()
    if (engine.parent / ".upstream-ref").read_text(encoding="utf-8").strip() != ENGINE_PIN:
        fail("NXNative engine pin mismatch")
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if (handoff.get("project") != PROJECT or handoff.get("branch") != PROJECT
            or handoff.get("title_id") != TITLE_ID or handoff.get("engine_pin") != ENGINE_PIN):
        fail("Kakarot handoff identity/pin mismatch")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("GOOGLE_SERVICE_ACCOUNT_JSON is empty")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import prepare_kakarot_actions as restore

    restore.verify_drive_metadata(api, handoff["work_archive"], "Kakarot workspace archive")
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "kakarot-work.tar.zst"
    restore.download_drive_file(api, credentials, handoff["work_archive"], archive, parallel_workers=6)
    work = destination / "work"
    restore.extract_verified_archive(archive, work)
    archive.unlink(missing_ok=True)

    prep = json.loads((work / "kakarot-linux-prep.json").read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "engine_pin", "main_build_id", "main_sha256", "modules"):
        if prep.get(key) != (handoff.get("prepared") or {}).get(key):
            fail(f"handoff/workspace mismatch for {key}")
    if prep.get("main_build_id") != MAIN_BUILD_ID or prep.get("main_sha256") != MAIN_SHA256:
        fail("workspace does not contain the reviewed Kakarot main NSO")

    version = str(prep["package_version"])
    exefs = work / "extract" / version / "ExeFS"
    original_main = exefs / "main"
    sdk_nso = exefs / "sdk"
    patched = work / f"patched_{version}"
    profile = work / "profile" / TITLE_ID / "game.tsv"
    for path in (original_main, exefs / "main.npdm", sdk_nso, profile,
                 patched / "sdk.cuts.tsv", patched / "sdk.fixups.tsv"):
        if not path.is_file():
            fail(f"missing required source/audit file: {path}")

    print("\n=== SDK PROFILE / BUILD ID / EXISTING CUT AUDIT ===", flush=True)
    import importlib
    sys.path.insert(0, str(engine / "dm/tools"))
    import nso
    sdk_module = nso.read(str(sdk_nso))
    sdk_id = bytes(sdk_module.build_id[:16]).hex()
    sdk_sha = hashlib.sha256(sdk_nso.read_bytes()).hexdigest()
    print(f"sdk_build_id={sdk_id}", flush=True)
    print(f"sdk_sha256={sdk_sha}", flush=True)
    sdk_cuts = (patched / "sdk.cuts.tsv").read_text(encoding="utf-8", errors="replace").splitlines()
    for line in sdk_cuts:
        if line.strip() and not line.lstrip().startswith("#"):
            print(line, flush=True)
    node_cut_present = any("node area" in line.lower() for line in sdk_cuts)
    print(f"sdk_node_area_cut_present={str(node_cut_present).lower()}", flush=True)

    print("\n=== PATCH THE PINNED HOST AND VERIFY SLOT-17 DETECTOR ===", flush=True)
    patcher = Path(__file__).resolve().parent / "patch_kakarot_ue_allocator.py"
    patch_report = run([sys.executable, str(patcher), "--engine-root", str(engine),
                        "--main-nso", str(original_main)], os.environ.copy())
    if '"status": "verified"' not in patch_report:
        fail("slot-17 host patcher did not emit its verified result")

    print("\n=== SET PHONE-SIZED GUEST ADDRESS SPACE ===", flush=True)
    # Same proven iPhone guest-block budget used by the registered SpkIOSzero profile.
    # Kakarot's own OBS_UE_REGION gate caps Unreal's engine region to the alias space.
    memory = {
        "mem_reserve": "0xF0000000",
        "mem_alias": "0xC8000000",
        "mem_stack": "0x10000000",
        "app_pool": "0xCD500000",
    }
    set_profile_value(profile, memory)
    print("\n".join(row for row in profile.read_text(encoding="utf-8").splitlines()
                    if row.partition("\t")[0] in memory or row.partition("\t")[0] == "sys_resource"),
          flush=True)

    print("\n=== REWRITE ONLY KAKAROT MAIN; KEEP subsdk0/sdk MODULES ===", flush=True)
    for suffix in ("patched.bin", "fixups.tsv", "gates.tsv", "cuts.tsv", "obs.tsv", "changed.tsv", "sites.tsv"):
        (patched / f"main.{suffix}").unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "DM_GAME": TITLE_ID,
        "GAME": TITLE_ID,
        "DM_GAMES_DIR": str(work / "profile"),
        "DM_GAMES_FIRST": "1",
        "DM_REWRITE_J": str(min(4, os.cpu_count() or 1)),
    })
    run([sys.executable, str(engine / "dm/tools/patch_nso.py"),
         str(original_main), str(patched), "main"], env)

    print("\n=== REQUIRE BOTH UNREAL HOOKS AND THE PHONE PROFILE ===", flush=True)
    cuts = (patched / "main.cuts.tsv").read_text(encoding="utf-8", errors="replace").splitlines()
    obs = (patched / "main.obs.tsv").read_text(encoding="utf-8", errors="replace").splitlines()
    fixups = (patched / "main.fixups.tsv").read_text(encoding="utf-8", errors="replace").splitlines()
    allocator_cut = [line for line in cuts if CALL_SITE in line and "FMallocBinned3" in line]
    allocator_obs = [line for line in obs if CALL_SITE in line and "FMallocBinned3" in line]
    region_obs = [line for line in obs if REGION_SITE in line and "engine region" in line.lower()]
    if len(allocator_cut) != 1:
        fail(f"expected exactly one FMallocBinned3 constructor cut at {CALL_SITE}, found {len(allocator_cut)}")
    if len(allocator_obs) != 1:
        fail(f"expected exactly one OBS_UE_MALLOC gate at {CALL_SITE}, found {len(allocator_obs)}")
    if len(region_obs) != 1:
        fail(f"existing OBS_UE_REGION at {REGION_SITE} was not preserved")
    if not any("UE_MALLOC_VT" in line and "0x8a181e8" in line for line in fixups):
        fail("main.fixups.tsv does not carry the verified Kakarot FMallocBinned3 vtable")
    if not any("UE_MALLOC_SLOT" in line and ("0x11" in line or "\t17" in line) for line in fixups):
        fail("main.fixups.tsv does not carry getter slot 17")
    if node_cut_present is False:
        print("[WARNING] SDK audit has no node-area cut. Do not treat this profile as device-ready until SDK layout is checked.",
              flush=True)
    print("\n".join(allocator_cut + allocator_obs + region_obs), flush=True)
    print("\n".join(line for line in fixups if "UE_MALLOC" in line or "UE_REGION" in line), flush=True)

    print("\n=== NEW REWRITTEN MAIN HASH ===", flush=True)
    new_main = patched / "main.patched.bin"
    print("main_patched_sha256=" + hashlib.sha256(new_main.read_bytes()).hexdigest(), flush=True)
    print("memory_fix_validation=passed", flush=True)


if __name__ == "__main__":
    main()
