#!/usr/bin/env python3
"""GitHub Actions restore: verify the KaKaRoTiOS Drive handoff, workspace archive and external RomFS."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

PROJECT = "KaKaRoTiOS"
BRANCH = "KaKaRoTiOS"
TITLE_ID = "010051C0134F8000"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(str(value))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        fail(f"Unsafe {label} path in handoff: {value}")
    return path

def verify_drive_metadata(api, item: dict, label: str) -> None:
    record = api.files().get(fileId=item["id"],
        fields="id,name,size,md5Checksum,trashed", supportsAllDrives=True).execute()
    if record.get("trashed") or record.get("name") != item.get("name"):
        fail(f"Drive {label} is missing, trashed, or has the wrong filename.")
    if int(record.get("size", -1)) != int(item.get("size", -2)):
        fail(f"Drive {label} size differs from the upload manifest.")
    expected_md5 = str(item.get("md5", "")).lower()
    if expected_md5 and str(record.get("md5Checksum", "")).lower() != expected_md5:
        fail(f"Drive {label} md5Checksum differs from the Colab upload record.")
    if not item.get("sha256"):
        fail(f"Drive {label} has no local SHA-256 in the Colab manifest.")
    print(f"[KaKaRoTiOS] Drive {label} metadata verified: {record['size']} bytes; MD5 matches.", flush=True)

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
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
            except (TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Drive download failed after {retries-1} retries at {downloader._progress}: {exc}") from exc
                import time
                delay = min(2 ** min(retries, 5), 30)
                print(f"[KaKaRoTiOS] Drive interrupted at {downloader._progress}; retry {retries}/10 in {delay}s.", flush=True)
                time.sleep(delay)
                continue
            if status:
                print(f"[KaKaRoTiOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    size = part.stat().st_size
    if size != int(item.get("size", -1)):
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: {size} != {item.get('size')}.")
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
                if (lowered.endswith("/romfs.img") or lowered.endswith(".nsp")
                        or lowered.endswith(".xci") or lowered.endswith(".nsz")
                        or lowered.endswith(".xcz") or lowered.endswith("/prod.keys")):
                    fail(f"Workspace archive must not contain external RomFS, source packages or keys: {member.name}")
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
    prep_handoff = handoff.get("prepared") or {}
    if (handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH
            or handoff.get("title_id") != TITLE_ID
            or handoff.get("nx2apple_tag") != NX2APPLE_TAG
            or handoff.get("engine_pin") != ENGINE_PIN):
        fail("Handoff is not for KaKaRoTiOS/Kakarot or uses a different pinned engine.")
    if handoff.get("package_version") != prep_handoff.get("package_version"):
        fail("Handoff and preparation package versions disagree.")
    if prep_handoff.get("profile_type") != "provisional" or prep_handoff.get("graphics_api") != "nvn":
        fail("Expected the generated Kakarot provisional NVN profile.")
    scanned_packages = prep_handoff.get("input_packages", [])
    scanned_dlcs = [pkg for pkg in scanned_packages if str(pkg.get("name", "")).startswith("dlc_")]
    if (prep_handoff.get("input_package_count") != 22 or len(scanned_packages) != 22
            or prep_handoff.get("input_dlc_package_count") != 20 or len(scanned_dlcs) != 20):
        fail("Preparation manifest must contain exactly base + update + 20 DLCs (22 inputs).")
    source_record = handoff.get("source") or {}
    source_dlcs = source_record.get("dlc_packages") or []
    if (source_record.get("package_count") != 2
            or source_record.get("dlc_package_count") != 20 or len(source_dlcs) != 20):
        fail("Handoff source inventory must record the base/update pair and exactly 20 DLC Drive files.")
    scanned_dlc_by_name = {pkg.get("name"): pkg for pkg in scanned_dlcs}
    if len(scanned_dlc_by_name) != 20:
        fail("NXNative DLC input filenames are duplicated.")
    for item in source_dlcs:
        local_name = item.get("local_name")
        scanned = scanned_dlc_by_name.get(local_name)
        if (not scanned or int(scanned.get("size", -1)) != int(item.get("size", -2))
                or scanned.get("type") not in ("NSP", "XCI")
                or not scanned.get("sha256")):
            fail(f"NXNative input does not match the staged DLC Drive inventory: {local_name}")
    for pkg in scanned_packages:
        if pkg.get("type") not in ("NSP", "XCI") or int(pkg.get("size", 0)) <= 0 or not pkg.get("sha256"):
            fail("Input package metadata is incomplete or has an unsupported package type.")
    if not handoff.get("request_id") or not handoff.get("work_archive", {}).get("id"):
        fail("Handoff request ID or workspace archive Drive record is missing.")
    game_data = handoff.get("game_data") or {}
    base_record = game_data.get("base_package") or {}
    update_record = game_data.get("update_package") or {}
    source_record = handoff.get("source") or {}
    if not base_record.get("id") or not update_record.get("id"):
        fail("Both reconstructed base and update package records are required in Drive.")
    for label, drive_item in (("base", base_record), ("update", update_record)):
        source_item = source_record.get(label) or {}
        package_type = source_item.get("type")
        expected_name = f"{label}.nsp" if package_type == "NSP" else f"{label}.xci" if package_type == "XCI" else ""
        if not expected_name or drive_item.get("name") != expected_name:
            fail(f"Drive {label} filename/format differs from the reconstructed package manifest.")
        if (int(drive_item.get("size", -1)) != int(source_item.get("size", -2))
                or drive_item.get("sha256") != source_item.get("sha256")):
            fail(f"Drive {label} package size/SHA-256 differs from the local reconstructed package.")
        if source_item.get("archive", {}).get("package_type") != package_type:
            fail(f"RAR extraction and NSP/XCI header audit disagree for {label}.")
        package_from_scan = next((x for x in prep_handoff.get("input_packages", [])
                                  if x.get("name") == expected_name), None)
        if not package_from_scan or package_from_scan.get("type") != package_type:
            fail(f"NXNative package scan does not contain the reconstructed {label} package.")
        if int(package_from_scan.get("size", -1)) != int(source_item.get("size", -2)) or package_from_scan.get("sha256") != source_item.get("sha256"):
            fail(f"NXNative scanned {label} package size/SHA-256 differs from the RAR extraction result.")
    if source_record.get("rar_parts_deleted_after_upload") is not True:
        fail("RAR volume cleanup was not recorded after the base/update Drive uploads.")
    for label, item, expected_type in (
        ("base", base_record, "NSP" if str(base_record.get("name", "")).lower().endswith(".nsp") else "XCI"),
        ("update", update_record, "NSP" if str(update_record.get("name", "")).lower().endswith(".nsp") else "XCI"),
    ):
        if int(item.get("size", 0)) <= 0 or not item.get("sha256") or not item.get("md5"):
            fail(f"Drive {label} package manifest is incomplete.")
        if not item["name"].lower().endswith((".nsp", ".xci")):
            fail(f"Drive {label} package has an unsupported extension.")
    aoc_records = game_data.get("aoc") or []
    if int(game_data.get("aoc_count", -1)) != len(aoc_records):
        fail("Drive AOC count differs from its image records.")
    if not game_data.get("aoc_folder_id"):
        fail("Drive AOC folder ID is missing.")
    if len(aoc_records) != int(prep_handoff.get("aoc_count", -1)):
        fail("Drive AOC count differs from the NXNative preparation manifest.")
    prep_aoc = prep_handoff.get("aoc_images", [])
    if {x.get("name"): (x.get("size"), x.get("sha256")) for x in aoc_records} != {
        x.get("name"): (x.get("size"), x.get("sha256")) for x in prep_aoc
    }:
        fail("Drive AOC image names/sizes/SHA-256 differ from the NXNative preparation manifest.")
    romfs_record = game_data.get("romfs") or {}
    if not romfs_record.get("id") or not romfs_record.get("sha256") or int(romfs_record.get("size", 0)) <= 0:
        fail("External RomFS Drive record is incomplete.")
    if (game_data.get("romfs_relative_path") != prep_handoff.get("romfs_relative_path")
            or game_data.get("romfs_id_relative_path") != prep_handoff.get("romfs_id_relative_path")):
        fail("Handoff and preparation RomFS paths disagree.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("GitHub Actions secret GOOGLE_SERVICE_ACCOUNT_JSON is empty.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)
    verify_drive_metadata(api, base_record, "base package")
    verify_drive_metadata(api, update_record, "update package")
    verify_drive_metadata(api, handoff["work_archive"], "workspace archive")
    verify_drive_metadata(api, romfs_record, "RomFS")
    for item in aoc_records:
        if not item.get("id") or not item.get("sha256") or not item.get("md5") or int(item.get("size", 0)) <= 0:
            fail(f"AOC Drive record is incomplete: {item.get('name')}")
        if not str(item.get("name", "")).lower().endswith(".img"):
            fail(f"Unsupported AOC filename: {item.get('name')}")
        verify_drive_metadata(api, item, f"AOC image {item['name']}")

    root = args.destination.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    archive = root / "kakarot-work.tar.zst"
    print("[KaKaRoTiOS] Downloading Colab workspace archive and verifying SHA-256...", flush=True)
    download_drive_file(api, handoff["work_archive"], archive)
    work = root / "work"
    print("[KaKaRoTiOS] Restoring only the prepared game workspace...", flush=True)
    extract_verified_archive(archive, work)
    archive.unlink()

    prep_path = work / "kakarot-linux-prep.json"
    if not prep_path.is_file():
        fail("kakarot-linux-prep.json is missing from the restored workspace.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    compare_keys = (
        "project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
        "profile_type", "profile_source", "profile_relative_dir",
        "modules", "main_build_id", "main_sha256", "rewrite_audit",
        "graphics_api", "unreal_shader_sources", "pak_audit", "shader_chain",
        "romfs_relative_path", "romfs_id_relative_path",
        "romfs_size", "romfs_sha256", "aoc_relative_dir", "aoc_count", "aoc_images",
        "survey_relative_path", "survey_size", "survey_sha256",
        "input_package_count", "input_dlc_package_count", "input_packages",
    )
    for key in compare_keys:
        if prep.get(key) != prep_handoff.get(key):
            fail(f"Workspace and handoff disagree on {key}.")
    if prep.get("package_version") != handoff["package_version"]:
        fail("Restored package version differs from the Drive handoff.")
    forbidden = [p for p in work.rglob("*") if p.is_file()
                 and (p.suffix.lower() in (".nsp", ".xci", ".nsz", ".xcz")
                      or p.name.lower() == "prod.keys")]
    if forbidden:
        fail("Workspace archive contains original package/key material: "
             + ", ".join(str(p.relative_to(work)) for p in forbidden[:12]))

    romfs_rel = safe_relative(prep["romfs_relative_path"], "RomFS")
    identity_rel = safe_relative(prep["romfs_id_relative_path"], "RomFS identity")
    aoc_rel = safe_relative(prep.get("aoc_relative_dir", "aoc"), "AOC")
    if str(game_data.get("aoc_relative_dir", "aoc")) != str(aoc_rel):
        fail("Drive handoff AOC relative path differs from Colab.")
    romfs = work.joinpath(*romfs_rel.parts)
    identity = work.joinpath(*identity_rel.parts)
    aoc_dir = work.joinpath(*aoc_rel.parts)
    # AOC is stored separately on Drive, never inside the compressed workspace.
    bundled_aoc = [p for p in aoc_dir.rglob("*") if p.is_file()] if aoc_dir.exists() else []
    if bundled_aoc:
        fail("Workspace archive unexpectedly contains AOC images; AOC must be restored from its separate Drive folder.")
    aoc_dir.mkdir(parents=True, exist_ok=True)
    print(f"[KaKaRoTiOS] Restoring {len(aoc_records)} AOC image(s) separately from Drive...", flush=True)
    for item in aoc_records:
        name = Path(item["name"]).name
        if name != item["name"]:
            fail(f"Unsafe AOC filename: {item['name']}")
        download_drive_file(api, item, aoc_dir / name)
    restored_aoc = sorted(p for p in aoc_dir.glob("*.img") if p.is_file() and not p.is_symlink())
    if {p.name for p in restored_aoc} != {x["name"] for x in aoc_records}:
        fail("Restored AOC image filenames differ from the Drive handoff.")
    for path in restored_aoc:
        record = next(x for x in aoc_records if x["name"] == path.name)
        if path.stat().st_size != int(record["size"]) or sha256_file(path) != record["sha256"]:
            fail(f"Restored AOC image size/SHA-256 mismatch: {path.name}")
    print("[KaKaRoTiOS] Restoring external RomFS as a separate Drive object...", flush=True)
    download_drive_file(api, romfs_record, romfs)
    if romfs.stat().st_size != int(prep["romfs_size"]):
        fail("Restored RomFS size differs from Colab.")
    romfs_sha = sha256_file(romfs)
    if romfs_sha != prep["romfs_sha256"] or romfs_sha != romfs_record["sha256"]:
        fail("Restored RomFS SHA-256 differs from Colab and/or Drive.")
    survey_rel = safe_relative(prep["survey_relative_path"], "survey")
    survey = work.joinpath(*survey_rel.parts)
    if not survey.is_file() or survey.stat().st_size != int(prep["survey_size"]):
        fail("Restored Kakarot survey report is missing or has the wrong size.")
    if sha256_file(survey) != prep["survey_sha256"]:
        fail("Restored Kakarot survey report SHA-256 differs from Colab.")
    if not identity.is_file():
        fail("RomFS identity sidecar was not retained in the workspace archive.")
    try:
        identity_json = json.loads(identity.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"Invalid RomFS identity sidecar: {exc}")
    if (identity_json.get("title") != TITLE_ID.lower()
            or identity_json.get("version") != prep["package_version"]
            or identity_json.get("bytes") != romfs_record["size"]
            or identity_json.get("sha256") != romfs_record["sha256"]):
        fail("RomFS identity sidecar does not match the restored game/version/bytes/SHA-256.")

    profile_rel = safe_relative(prep["profile_relative_dir"], "profile")
    profile_dir = work.joinpath(*profile_rel.parts)
    profile_file = profile_dir / "game.tsv"
    if not profile_file.is_file():
        fail("Generated Kakarot game.tsv profile is missing.")
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
    for path in (main, patched / "main.patched.bin", patched / "main.fixups.tsv",
                 patched / "main.cuts.tsv", patched / "main.obs.tsv"):
        if not path.is_file():
            fail(f"Restored source/rewrite artifact missing: {path.relative_to(work)}")

    prepared = {
        "project": PROJECT, "branch": BRANCH, "title_id": TITLE_ID,
        "package_version": prep["package_version"],
        "nx2apple_tag": NX2APPLE_TAG, "engine_pin": ENGINE_PIN,
        "request_id": handoff["request_id"],
        "work_dir": str(work),
        "romfs_path": str(romfs),
        "romfs_id_path": str(identity),
        "survey_path": str(survey),
        "survey_sha256": prep["survey_sha256"],
        "profile_dir": str(profile_dir),
        "exefs_dir": str(exefs),
        "patched_dir": str(patched),
        "profile_type": prep["profile_type"],
        "profile_source": prep["profile_source"],
        "modules": prep["modules"],
        "input_package_count": prep["input_package_count"],
        "input_dlc_package_count": prep["input_dlc_package_count"],
        "main_build_id": prep["main_build_id"],
        "main_sha256": prep["main_sha256"],
        "rewrite_audit": prep["rewrite_audit"],
        "graphics_api": prep["graphics_api"],
        "unreal_shader_sources": prep["unreal_shader_sources"],
        "pak_audit": prep["pak_audit"],
        "shader_chain": prep["shader_chain"],
        "input_packages": prep["input_packages"],
        "aoc_dir": str(aoc_dir),
        "aoc_images": [str(p) for p in restored_aoc],
        "aoc_count": len(restored_aoc),
        "base_package": base_record,
        "update_package": update_record,
        "game_data": game_data,
    }
    output_path = root / "actions-input.json"
    output_path.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    print("[KaKaRoTiOS] Actions input validated:", output_path)
    print(f"[KaKaRoTiOS] Verified Drive base/update packages, workspace, RomFS and {len(restored_aoc)} AOC image(s). No base/update package or prod.keys was downloaded again onto the runner.")

if __name__ == "__main__":
    main()
