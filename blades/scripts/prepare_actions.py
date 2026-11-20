#!/usr/bin/env python3
"""Download only the Colab-prepared Route C workspace and external Blades of Time game data."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from pathlib import Path, PurePosixPath


TITLE_ID = "0100CFA00CC74000"
NX2APPLE_REF = "BladesTime"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"


def fail(message: str) -> None:
    raise SystemExit("[BladesTime] ERROR: " + message)


# Identical six-worker Range downloader used by Colab.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_chunks import download_drive_file as _download_chunks


def download_drive_file(api, item: dict, destination: Path) -> None:
    _download_chunks(api, item, destination)


def extract_verified_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    if proc.stdout is None:
        fail("could not start zstd decompression.")
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    fail(f"unsafe archive path: {member.name}")
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    fail(f"unsupported archive entry: {member.name}")
                target = destination.joinpath(*[part for part in rel.parts if part not in ("", ".")])
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    fail(f"cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    finally:
        proc.stdout.close()
    if proc.wait() != 0:
        fail("zstd decompression failed.")



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    d = json.loads(args.handoff.read_text())
    if d.get("project") != "BladesTime" or d.get("branch") != "BladesTime" or d.get("title_id") != TITLE_ID:
        fail("wrong game/project/branch")
    version = d.get("package_version", "")
    if not re.fullmatch(r"v[1-9][0-9]*", version) or d.get("engine_pin") != ENGINE_PIN:
        fail("update version/engine mismatch")
    prep = d.get("prepared", {})
    if (prep.get("title_id") != TITLE_ID or prep.get("engine_pin") != ENGINE_PIN
            or prep.get("package_version") != version or prep.get("input_package_count") != 2
            or prep.get("input_update_count") != 1 or prep.get("input_dlc_count") != 0):
        fail("Linux preparation base + update identity mismatch")
    if prep.get("graphics") not in ("nvn", "gl", "vulkan") or d.get("game_data", {}).get("aoc") != []:
        fail("unsupported graphics backend or unexpected DLC")
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("Actions secret GOOGLE_SERVICE_ACCOUNT_JSON is required (Drive folder must be shared with this account)")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    auth = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=auth, cache_discovery=False)
    root = args.destination.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    archive = root / "blades-work.tar.zst"
    download_drive_file(api, d["work_archive"], archive)
    work = root / "work"
    extract_verified_archive(archive, work)
    archive.unlink()
    recorded = work / "bladestime-linux-prep.json"
    if not recorded.is_file():
        fail("missing Linux preparation manifest")
    real = json.loads(recorded.read_text())
    for field in ("project", "title_id", "package_version", "engine_pin",
                  "graphics", "shader_package_key", "shader_chain", "modules",
                  "romfs_relative_path", "romfs_id_relative_path", "provisional",
                   "shader_split_stage", "source_capture_flags", "mac_host_stages",
                   "shader_versions", "jit_required", "linux_ue_decode_complete"):
        if prep.get(field) != real.get(field):
            fail(f"Drive handoff and workspace disagree on {field}")
    relative = PurePosixPath(real["romfs_relative_path"])
    id_relative = PurePosixPath(real["romfs_id_relative_path"])
    for path in (relative, id_relative):
        if path.is_absolute() or ".." in path.parts:
            fail("unsafe relative path")
    romfs = work.joinpath(*relative.parts)
    identity = work.joinpath(*id_relative.parts)
    if not identity.is_file():
        fail("RomFS identity sidecar missing")
    download_drive_file(api, d["game_data"]["romfs"], romfs)
    # Base/update shader inputs may span more than the selected packed
    # version. RomFS images are transferred externally, never inside the IPA.
    expected_extra = set(real["shader_versions"]) - {version}
    extras = d["game_data"].get("shader_romfs", [])
    if not isinstance(extras, list) or len(extras) != len(expected_extra):
        fail("incomplete additional shader-version RomFS handoff")
    if {x.get("version") for x in extras} != expected_extra:
        fail("extra shader input versions disagree with verified Linux manifest")
    for item in extras:
        source_version = item["version"]
        if not re.fullmatch(r"v[0-9]+", source_version):
            fail("unsafe source-version marker")
        extra_romfs = work / "extract" / source_version / "RomFS.img"
        extra_identity = work / "extract" / source_version / "RomFS.img.id"
        if not extra_identity.is_file():
            fail(f"extra shader-version RomFS identity missing: {source_version}")
        download_drive_file(api, item, extra_romfs)
        extra_meta = json.loads(extra_identity.read_text())
        if (extra_meta.get("title") != TITLE_ID.lower()
                or extra_meta.get("version") != source_version
                or extra_meta.get("bytes") != item.get("size")
                or extra_meta.get("sha256") != item.get("sha256")):
            fail(f"extra shader RomFS provenance failed: {source_version}")
    record = json.loads(identity.read_text())
    image = d["game_data"]["romfs"]
    if record.get("title") != TITLE_ID.lower() or record.get("version") != version:
        fail("restored RomFS belongs to wrong game or version")
    if record.get("bytes") != image.get("size") or record.get("sha256") != image.get("sha256"):
        fail("RomFS metadata mismatch")
    if real.get("provisional") and not (work / "profile" / TITLE_ID / "game.tsv").is_file():
        fail("provisional game.tsv not preserved in workspace")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from port_stages import require_valid_stage_list
    host_stages = require_valid_stage_list(real.get("mac_host_stages"))
    shader_stage = real.get("shader_split_stage")
    if real["graphics"] == "nvn":
        if shader_stage == "linux_complete":
            if not re.fullmatch(r"[0-9a-f]{64}", real.get("shader_package_key") or ""):
                fail("completed Linux NVN shader split key missing")
            if not (work / "shader" / "pkg").is_dir():
                fail("completed Linux NVN shader package absent")
        elif shader_stage != "mac_pending" or not host_stages or real.get("shader_package_key") is not None:
            fail("NVN shader split is neither complete nor delegated to real native host")
    elif shader_stage != "metal_deferred" or real.get("shader_package_key") is not None:
        fail("GL/Vulkan shader checkpoint is inconsistent")
    manifest = {
        "project": "BladesTime", "branch": "BladesTime",
        "request_id": d["request_id"], "title_id": TITLE_ID,
        "package_version": version, "source_ref": "BladesTime",
        "engine_pin": ENGINE_PIN, "graphics": real["graphics"],
        "work_dir": str(work), "romfs_path": str(romfs),
        "romfs_id_path": str(identity), "shader_chain": real["shader_chain"],
        "shader_package_key": real.get("shader_package_key"),
        "shader_split_stage": shader_stage, "source_capture_flags": real["source_capture_flags"],
        "mac_host_stages": host_stages, "jit_required": real["jit_required"],
        "shader_versions": real["shader_versions"],
        "linux_ue_decode_complete": real["linux_ue_decode_complete"],
        "modules": real["modules"], "provisional": real["provisional"],
        "romfs_relative_path": real["romfs_relative_path"],
        "romfs_id_relative_path": real["romfs_id_relative_path"],
        "game_data": d["game_data"], "aoc_count": 0, "aoc_images": [],
        "source_files": d.get("source_files", {}),
    }
    (root / "actions-input.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("[BladesTime] Original NSP and prod.keys were NOT downloaded into Actions.")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
