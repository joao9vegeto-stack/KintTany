#!/usr/bin/env python3
"""Restore the Mugiwara4iOS workspace, external RomFS and unique-title-ID AOC images."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from mugiwara_contract import PREPARED_MANIFEST_KEYS, copy_prepared_manifest, prepared_manifest_mismatches

PROJECT = "Mugiwara4iOS"
BRANCH = "Mugiwara4iOS"
TITLE_ID = "01008FE00E2F6000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
EXPECTED_PACKAGES = 46
EXPECTED_DLC_NSPS = 44

def fail(message: str) -> None:
    raise SystemExit("[Mugiwara4iOS] ERROR: " + message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_aoc_manifest(prep: dict, drive_records: list[dict]) -> bool:
    """AOC images are keyed by unique DLC Title IDs; source NSP count remains 44."""
    try:
        count = prep.get("aoc_count")
        title_ids = prep.get("aoc_title_ids")
        contents = prep.get("aoc_contents")
        images = prep.get("aoc_images")
        dlc_meta = prep.get("dlc_content_meta")
        packages = prep.get("input_packages")
        if type(count) is not int or not 1 <= count <= EXPECTED_DLC_NSPS:
            return False
        if not all(isinstance(x, list) for x in (title_ids, contents, images, dlc_meta, packages)):
            return False
        if (len(title_ids) != count or len(set(title_ids)) != count
                or len(contents) != count or len(images) != count or len(drive_records) != count
                or len(dlc_meta) < EXPECTED_DLC_NSPS
                or prep.get("dlc_content_meta_count") != len(dlc_meta)):
            return False
        app = int(TITLE_ID, 16)
        dlc_packages = {
            item.get("local_name"): item for item in packages
            if item.get("role") == "dlc" and item.get("type") == "NSP"
        }
        if len(dlc_packages) != EXPECTED_DLC_NSPS:
            return False
        best = {}
        for item in dlc_meta:
            tid_text = item.get("title_id", "")
            if (not isinstance(tid_text, str) or len(tid_text) != 16
                    or f"{int(tid_text, 16):016X}" != tid_text
                    or item.get("source_package") not in dlc_packages):
                return False
            tid = int(tid_text, 16)
            version = int(item.get("content_version", -1))
            package = dlc_packages[item["source_package"]]
            key = (version, int(package.get("size", 0)))
            if version < 0 or key[1] <= 0:
                return False
            if tid not in best or key > best[tid][0]:
                best[tid] = (key, item["source_package"], version)
        if set(title_ids) != {f"{tid:016X}" for tid in best}:
            return False
        if {item.get("source_package") for item in dlc_meta} != set(dlc_packages):
            return False
        content_by_title = {item.get("title_id"): item for item in contents}
        if len(content_by_title) != count or set(content_by_title) != set(title_ids):
            return False
        expected_names = set()
        for tid in sorted(best):
            title = f"{tid:016X}"
            index = tid - app - 0x1000
            name = f"{index}.img"
            expected_names.add(name)
            item = content_by_title[title]
            selected_package = dlc_packages[best[tid][1]]
            if (index <= 0 or item.get("aoc_index") != index or item.get("name") != name
                    or item.get("content_version") != best[tid][2]
                    or item.get("source_package") != best[tid][1]
                    or item.get("source_size") != int(selected_package.get("size", 0))
                    or item.get("source_sha256") != selected_package.get("sha256")):
                return False
        image_by_name = {item.get("name"): item for item in images}
        drive_by_name = {item.get("name"): item for item in drive_records}
        if (len(image_by_name) != count or len(drive_by_name) != count
                or set(image_by_name) != expected_names or set(drive_by_name) != expected_names):
            return False
        for title, content in content_by_title.items():
            image = image_by_name[content["name"]]
            drive = drive_by_name[content["name"]]
            digest = image.get("sha256", "")
            if (image.get("title_id") != title or image.get("aoc_index") != content["aoc_index"]
                    or int(image.get("size", 0)) <= 0 or len(digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in digest.lower())
                    or not drive.get("id") or drive.get("title_id") != title
                    or drive.get("aoc_index") != content["aoc_index"]
                    or int(drive.get("size", 0)) != int(image.get("size", -1))
                    or drive.get("sha256") != digest):
                return False
        return True
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return False

def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(str(value))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        fail(f"Unsafe {label} path in handoff: {value}")
    return path

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    from http.client import IncompleteRead
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done, retries = False, 0
        while not done:
            try:
                status, done = downloader.next_chunk()
                retries = 0
            except (IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(
                        f"Drive download failed after {retries-1} retries at "
                        f"{downloader._progress}: {exc}"
                    ) from exc
                delay = min(2 ** min(retries, 5), 30)
                print(
                    f"[Mugiwara4iOS] Drive transfer interrupted at {downloader._progress}; "
                    f"retry {retries}/10 in {delay}s ({type(exc).__name__}).",
                    flush=True,
                )
                time.sleep(delay)
                continue
            if status:
                print(
                    f"[Mugiwara4iOS] Drive {item.get('name', item['id'])}: "
                    f"{status.progress()*100:.1f}%",
                    flush=True,
                )
    size = part.stat().st_size
    expected_size = int(item.get("size", -1))
    if size <= 0 or size != expected_size:
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: {size} != {expected_size}.")
    digest = sha256_file(part)
    if digest.lower() != str(item.get("sha256", "")).lower():
        part.unlink(missing_ok=True)
        fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    part.replace(destination)

def extract_verified_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    if process.stdout is None:
        fail("Could not start zstd decompression.")
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as tar:
            for member in tar:
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    fail(f"Unsafe workspace archive path: {member.name}")
                lowered = member.name.lower()
                if (
                    lowered.endswith("/romfs.img")
                    or ("/aoc/" in lowered and lowered.endswith(".img"))
                    or lowered.endswith(".nsp") or lowered.endswith(".xci")
                    or lowered.endswith(".nsz") or lowered.endswith(".xcz")
                    or lowered.endswith("/prod.keys")
                ):
                    fail(
                        "Workspace archive must not contain external RomFS/AOC images, "
                        f"source packages or keys: {member.name}"
                    )
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    fail(f"Unsupported workspace archive entry: {member.name}")
                target = destination.joinpath(*[part for part in rel.parts if part not in ("", ".")])
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    fail(f"Cannot read workspace archive member {member.name}.")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    finally:
        process.stdout.close()
    if process.wait() != 0:
        fail("zstd/tar workspace extraction failed.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    prepared_handoff = handoff.get("prepared") or {}
    source_handoff = handoff.get("source") or {}
    game_data = handoff.get("game_data") or {}
    romfs_record = game_data.get("romfs") or {}
    aoc_records = game_data.get("aoc") or []

    if (
        handoff.get("format") != 2
        or handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
        or handoff.get("title_id") != TITLE_ID
        or handoff.get("nx2apple_tag") != NX2APPLE_TAG
        or handoff.get("engine_pin") != ENGINE_PIN
    ):
        fail("Handoff is not for Mugiwara4iOS/One Piece: Pirate Warriors 4 or uses a different pinned engine.")
    if handoff.get("package_version") != prepared_handoff.get("package_version"):
        fail("Handoff and preparation package versions disagree.")
    if prepared_handoff.get("format") != 4 or not isinstance(prepared_handoff.get("jit_required"), bool):
        fail("Preparation manifest is outdated or missing the 44-DLC/AOT contract; rerun Colab preparation.")
    if prepared_handoff.get("profile_type") != "provisional" or prepared_handoff.get("graphics_api") != "nvn":
        fail("Expected the generated One Piece: Pirate Warriors 4 provisional NVN profile.")
    if (
        source_handoff.get("package_count") != EXPECTED_PACKAGES
        or source_handoff.get("base_type") != "NSP"
        or source_handoff.get("update_nsp_count") != 1
        or source_handoff.get("dlc_nsp_count") != EXPECTED_DLC_NSPS
        or prepared_handoff.get("input_package_count") != EXPECTED_PACKAGES
        or prepared_handoff.get("input_nsp_count") != EXPECTED_PACKAGES
        or prepared_handoff.get("input_xci_count") != 0
        or prepared_handoff.get("input_update_nsp_count") != 1
        or prepared_handoff.get("input_dlc_nsp_count") != EXPECTED_DLC_NSPS
        or len(prepared_handoff.get("input_packages", [])) != EXPECTED_PACKAGES
    ):
        fail("Handoff does not describe exactly 1 base NSP + 1 update NSP + 44 DLC NSPs.")
    prep_aoc = prepared_handoff.get("aoc_images") or []
    if not valid_aoc_manifest(prepared_handoff, aoc_records):
        fail("Handoff AOC records do not match the unique DLC Title IDs and NXNative's highest-version selection.")
    for record in aoc_records:
        if (
            not record.get("id") or not record.get("sha256")
            or int(record.get("size", 0)) <= 0
            or not str(record.get("name", "")).endswith(".img")
            or Path(str(record.get("name", ""))).name != record.get("name")
        ):
            fail(f"Incomplete or unsafe Drive AOC record: {record.get('name')!r}.")
    for item in prepared_handoff["input_packages"]:
        if (
            item.get("type") != "NSP" or int(item.get("size", 0)) <= 0
            or not item.get("sha256") or item.get("role") not in ("base", "update", "dlc")
        ):
            fail("Input package metadata is incomplete or is not a standard NSP.")
    if not handoff.get("request_id") or not handoff.get("work_archive", {}).get("id"):
        fail("Handoff request ID or workspace archive Drive record is missing.")
    if not romfs_record.get("id") or not romfs_record.get("sha256") or int(romfs_record.get("size", 0)) <= 0:
        fail("External RomFS Drive record is incomplete.")
    if (
        game_data.get("romfs_relative_path") != prepared_handoff.get("romfs_relative_path")
        or game_data.get("romfs_id_relative_path") != prepared_handoff.get("romfs_id_relative_path")
        or game_data.get("aoc_relative_dir") != prepared_handoff.get("aoc_relative_dir")
    ):
        fail("Handoff and preparation RomFS/AOC paths disagree.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("GitHub Actions secret GOOGLE_SERVICE_ACCOUNT_JSON is empty.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)

    root = args.destination.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    archive = root / "mugiwara4ios-work.tar.zst"
    print("[Mugiwara4iOS] Downloading Colab workspace archive and verifying SHA-256...", flush=True)
    download_drive_file(api, handoff["work_archive"], archive)
    work = root / "work"
    print("[Mugiwara4iOS] Restoring the build-only workspace...", flush=True)
    extract_verified_archive(archive, work)
    archive.unlink()

    prep_path = work / "mugiwara4ios-linux-prep.json"
    if not prep_path.is_file():
        fail("mugiwara4ios-linux-prep.json is missing from the restored workspace.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    if (prep.get("format") != 4 or prep.get("display_version") != "1.8.7"
            or prep.get("base_content_version") != 0 or int(prep.get("update_content_version", 0)) <= 0
            or not isinstance(prep.get("jit_required"), bool)):
        fail("Restored Colab prep manifest is outdated or missing the format-4 unique-title-ID AOC/AOT contract.")

    mismatches = prepared_manifest_mismatches(prep, prepared_handoff)
    if mismatches:
        fail("Workspace and Drive handoff disagree on " + mismatches[0] + ".")
    try:
        prepared_contract = copy_prepared_manifest(prep)
    except ValueError as exc:
        fail(str(exc))
    if prep.get("package_version") != handoff["package_version"]:
        fail("Restored package version differs from the Drive handoff.")
    forbidden = [
        item for item in work.rglob("*") if item.is_file()
        and (
            item.suffix.lower() in (".nsp", ".xci", ".nsz", ".xcz")
            or item.name.lower() == "prod.keys"
            or item.name.lower() == "romfs.img"
            or (item.suffix.lower() == ".img" and "aoc" in item.parts)
        )
    ]
    if forbidden:
        fail(
            "Workspace archive contains external game data, original packages or keys: "
            + ", ".join(str(item.relative_to(work)) for item in forbidden[:12])
        )

    romfs_rel = safe_relative(prep["romfs_relative_path"], "RomFS")
    identity_rel = safe_relative(prep["romfs_id_relative_path"], "RomFS identity")
    aoc_rel = safe_relative(prep["aoc_relative_dir"], "AOC")
    romfs = work.joinpath(*romfs_rel.parts)
    identity = work.joinpath(*identity_rel.parts)
    aoc_dir = work.joinpath(*aoc_rel.parts)
    print("[Mugiwara4iOS] Restoring external RomFS from Drive and verifying SHA-256...", flush=True)
    download_drive_file(api, romfs_record, romfs)
    if romfs.stat().st_size != int(prep["romfs_size"]):
        fail("Restored RomFS size differs from Colab.")
    romfs_sha = sha256_file(romfs)
    if romfs_sha != prep["romfs_sha256"] or romfs_sha != romfs_record["sha256"]:
        fail("Restored RomFS SHA-256 differs from Colab and/or Drive.")

    print(f"[Mugiwara4iOS] Restoring {prep['aoc_count']} unique-title-ID AOC images and verifying every SHA-256...", flush=True)
    aoc_dir.mkdir(parents=True, exist_ok=True)
    expected_aoc = {item["name"]: item for item in prep_aoc}
    for record in aoc_records:
        expected = expected_aoc.get(record["name"])
        if not expected or int(expected.get("size", -1)) != int(record["size"]):
            fail(f"Drive AOC record differs from the NXNative preparation manifest: {record['name']}.")
        destination = aoc_dir / record["name"]
        download_drive_file(api, record, destination)
        if destination.stat().st_size != int(expected["size"]):
            fail(f"Restored AOC size differs from Colab: {record['name']}.")
        if sha256_file(destination) != expected["sha256"] or expected["sha256"] != record["sha256"]:
            fail(f"Restored AOC SHA-256 differs from Colab and/or Drive: {record['name']}.")
    restored_aoc = sorted(item.name for item in aoc_dir.glob("*.img") if item.is_file())
    if restored_aoc != sorted(expected_aoc):
        fail(f"Restored AOC filename set differs from the {prep['aoc_count']} unique DLC Title IDs: {restored_aoc}.")

    survey_rel = safe_relative(prep["survey_relative_path"], "survey")
    survey = work.joinpath(*survey_rel.parts)
    if not survey.is_file() or survey.stat().st_size != int(prep["survey_size"]):
        fail("Restored One Piece: Pirate Warriors 4 survey report is missing or has the wrong size.")
    if sha256_file(survey) != prep["survey_sha256"]:
        fail("Restored One Piece: Pirate Warriors 4 survey SHA-256 differs from Colab.")
    if not identity.is_file():
        fail("RomFS identity sidecar was not retained in the workspace archive.")
    try:
        identity_json = json.loads(identity.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Invalid RomFS identity sidecar: {exc}")
    if (
        identity_json.get("title") != TITLE_ID.lower()
        or identity_json.get("version") != prep["package_version"]
        or identity_json.get("bytes") != romfs_record["size"]
        or identity_json.get("sha256") != romfs_record["sha256"]
    ):
        fail("RomFS identity sidecar does not match the restored game/version/bytes/SHA-256.")

    profile_rel = safe_relative(prep["profile_relative_dir"], "profile")
    profile_dir = work.joinpath(*profile_rel.parts)
    profile_file = profile_dir / "game.tsv"
    if not profile_file.is_file():
        fail("Generated One Piece: Pirate Warriors 4 game.tsv profile is missing.")
    profile_text = profile_file.read_text(encoding="utf-8")
    if "Provisional game profile" not in profile_text:
        fail("Restored profile is not the NXNative-generated provisional profile.")
    exefs = work / "extract" / prep["package_version"] / "ExeFS"
    main = exefs / "main"
    patched = work / f"patched_{prep['package_version']}"
    for name in prep["modules"]:
        if not (patched / f"{name}.patched.bin").is_file():
            fail(f"Restored ARM64 rewrite output is missing for {name}.")
        if not (patched / f"{name}.fixups.tsv").is_file():
            fail(f"Restored rewrite audit is missing for {name}.")
    for item in (prep.get("rewrite_audit") or {}).get("module_artifacts", []):
        name = item["name"]
        if sha256_file(patched / f"{name}.patched.bin") != item["patched_sha256"]:
            fail(f"Restored ARM64 module SHA-256 mismatch: {name}.patched.bin")
        if sha256_file(patched / f"{name}.fixups.tsv") != item["fixups_sha256"]:
            fail(f"Restored ARM64 fixup audit SHA-256 mismatch: {name}.fixups.tsv")
    for path in (
        main, patched / "main.patched.bin", patched / "main.fixups.tsv",
        patched / "main.cuts.tsv", patched / "main.obs.tsv",
    ):
        if not path.is_file():
            fail(f"Restored source/rewrite artifact missing: {path.relative_to(work)}")

    prepared = dict(prepared_contract)
    prepared.update({
        "branch": BRANCH,
        "request_id": handoff["request_id"],
        "work_dir": str(work),
        "romfs_path": str(romfs), "romfs_id_path": str(identity),
        "aoc_dir": str(aoc_dir), "aoc_restored_names": restored_aoc,
        "survey_path": str(survey),
        "profile_dir": str(profile_dir), "exefs_dir": str(exefs), "patched_dir": str(patched),
        "game_data": game_data,
    })
    mismatches = prepared_manifest_mismatches(prepared, prep)
    if mismatches:
        fail("Generated Actions input lost or changed canonical field " + mismatches[0] + ".")
    output_path = root / "actions-input.json"
    output_path.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    print("[Mugiwara4iOS] Actions input validated:", output_path)
    print(f"[Mugiwara4iOS] Restored and verified external RomFS + {len(restored_aoc)} unique-title-ID AOC images from 44 DLC NSPs.")
    print("[Mugiwara4iOS] Original 46 NSPs and prod.keys were not restored to Actions.")

if __name__ == "__main__":
    main()
