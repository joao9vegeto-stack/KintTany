#!/usr/bin/env python3
"""Restore and verify only the prepared SpkIOSzero workspace and external RomFS/AOC from Drive."""
from __future__ import annotations
import argparse, hashlib, http.client, json, os, shutil, subprocess, tarfile, time
from pathlib import Path, PurePosixPath

TITLE_ID = "010035F022078000"
PROJECT = "SpkIOSzero"
BRANCH = "SpkIOSzero"
NX2APPLE_TAG = "v1.3.1-rc2"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"

def fail(message: str) -> None:
    raise SystemExit("[SpkIOSzero] ERROR: " + message)

def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        fail(f"Unsafe {label} path in handoff: {value}")
    return path

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    digest, total = hashlib.sha256(), 0
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done, retries = False, 0
        while not done:
            try:
                status, done = downloader.next_chunk()
                retries = 0
            except (http.client.IncompleteRead, TimeoutError, ConnectionError, OSError) as exc:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Drive transfer failed after {retries-1} retries at {downloader._progress}/{item['size']} bytes: {exc}") from exc
                delay = min(2 ** min(retries, 5), 30)
                print(f"[SpkIOSzero] Drive interrupted at {downloader._progress}; retry {retries}/10 in {delay}s ({type(exc).__name__}).", flush=True)
                time.sleep(delay)
                continue
            if status: print(f"[SpkIOSzero] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    with part.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block); total += len(block)
    if total != int(item["size"]):
        part.unlink(missing_ok=True); fail(f"Drive size mismatch for {item.get('name')}: expected {item['size']}, got {total}.")
    if digest.hexdigest().lower() != str(item["sha256"]).lower():
        part.unlink(missing_ok=True); fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    part.replace(destination)

def extract_verified_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
    if proc.stdout is None: fail("Could not start zstd decompression.")
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                rel = PurePosixPath(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    fail(f"Unsafe archive path: {member.name}")
                if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                    fail(f"Unsupported archive entry: {member.name}")
                target = destination.joinpath(*[part for part in rel.parts if part not in ("", ".")])
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True); continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None: fail(f"Cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    finally:
        proc.stdout.close()
    if proc.wait() != 0: fail("zstd/tar workspace extraction failed.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if handoff.get("project") != PROJECT or handoff.get("branch") != BRANCH:
        fail("Handoff project/branch mismatch.")
    if handoff.get("title_id") != TITLE_ID or not handoff.get("package_version"):
        fail("Handoff does not identify the Sparking! ZERO title/package.")
    if handoff.get("nx2apple_tag") != NX2APPLE_TAG or handoff.get("engine_pin") != ENGINE_PIN:
        fail("Handoff NX2Apple/NXNative pin mismatch.")
    prepared_manifest = handoff.get("prepared") or {}
    if prepared_manifest.get("title_id") != TITLE_ID or prepared_manifest.get("package_version") != handoff["package_version"]:
        fail("Colab prepared manifest and handoff identity disagree.")
    if prepared_manifest.get("engine_pin") != ENGINE_PIN or prepared_manifest.get("nx2apple_tag") != NX2APPLE_TAG:
        fail("Colab prepared manifest uses a different engine pin.")
    if prepared_manifest.get("main_build_id") != "68edafd68c7bc1a1af50b82aac838018":
        fail("Colab manifest does not identify the reviewed Sparking! ZERO main build.")
    if prepared_manifest.get("main_sha256") != "a0f8f0644c92384ddb1baac1c21aecbeeace5bc99ad40895e216add61da78efe":
        fail("Colab manifest main SHA-256 differs from the reviewed SPK build.")
    if not handoff.get("request_id") or not handoff.get("work_archive", {}).get("id"):
        fail("Handoff request ID or workspace archive reference is missing.")
    game_data = handoff.get("game_data") or {}
    romfs_record = game_data.get("romfs") or {}
    aoc_records = game_data.get("aoc") or []
    if not romfs_record.get("id") or not romfs_record.get("sha256") or int(romfs_record.get("size", 0)) <= 0:
        fail("External RomFS Drive record is incomplete.")
    expected_aoc = {x.get("name") for x in prepared_manifest.get("aoc_images", [])}
    if not expected_aoc or expected_aoc != {x.get("name") for x in aoc_records}:
        fail("Drive AOC records do not match the Colab prepared manifest.")

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw: fail("GitHub Actions secret GOOGLE_SERVICE_ACCOUNT_JSON is empty.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)

    root = args.destination.resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    archive = root / "spk-work.tar.zst"
    print("[SpkIOSzero] Downloading the Colab-prepared workspace; no NSP or prod.keys are present in this handoff...", flush=True)
    download_drive_file(api, handoff["work_archive"], archive)
    work = root / "work"
    print("[SpkIOSzero] Verifying and restoring the build-only workspace...", flush=True)
    extract_verified_archive(archive, work)
    archive.unlink()

    prep_path = work / "spk-ios-zero-linux-prep.json"
    if not prep_path.is_file(): fail("Colab spk-ios-zero-linux-prep.json is missing.")
    prep = json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project", "title_id", "package_version", "nx2apple_tag", "engine_pin",
                "main_build_id", "main_sha256", "modules", "shader_chain",
                "romfs_relative_path", "romfs_id_relative_path", "aoc_relative_dir"):
        if prep.get(key) != prepared_manifest.get(key):
            fail(f"Handoff and workspace disagree on {key}.")
    if prep.get("package_version") != handoff["package_version"]:
        fail("Workspace package version differs from handoff.")
    forbidden = [p for p in work.rglob("*") if p.is_file()
        and (p.suffix.lower() in (".nsp", ".xci") or p.name.lower() == "prod.keys")]
    if forbidden:
        fail("Build workspace unexpectedly contains source packages/keys: " + ", ".join(str(x.relative_to(work)) for x in forbidden[:10]))

    romfs_rel = safe_relative(prep["romfs_relative_path"], "RomFS")
    identity_rel = safe_relative(prep["romfs_id_relative_path"], "RomFS identity")
    romfs = work.joinpath(*romfs_rel.parts)
    identity = work.joinpath(*identity_rel.parts)
    if game_data.get("romfs_relative_path") != prep["romfs_relative_path"]:
        fail("Drive handoff RomFS path differs from the Colab manifest.")
    aoc_dir = work / safe_relative(prep["aoc_relative_dir"], "AOC").as_posix()
    print("[SpkIOSzero] Restoring external RomFS and DLC AOC images from Drive...", flush=True)
    download_drive_file(api, romfs_record, romfs)
    aoc_dir.mkdir(parents=True, exist_ok=True)
    for item in aoc_records:
        name = Path(item.get("name", "")).name
        if not name.endswith(".img") or name in ("", ".", ".."): fail(f"Invalid AOC image name: {name}")
        expected = next((x for x in prep["aoc_images"] if x.get("name") == name), None)
        if not expected or int(expected.get("size", 0)) != int(item.get("size", -1)):
            fail(f"AOC size/manifest mismatch for {name}.")
        download_drive_file(api, item, aoc_dir / name)
    restored = sorted(p for p in aoc_dir.glob("*.img") if p.is_file())
    if {p.name for p in restored} != expected_aoc: fail("Restored AOC image names differ from the Colab manifest.")
    if not romfs.is_file() or romfs.stat().st_size != int(romfs_record["size"]):
        fail("External RomFS image size differs after restore.")
    if not identity.is_file(): fail("NX2Apple RomFS identity sidecar was not restored from the workspace.")
    try: identity_json = json.loads(identity.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc: fail(f"Invalid NX2Apple RomFS identity sidecar: {exc}")
    if identity_json.get("title") != TITLE_ID.lower() or identity_json.get("version") != prep["package_version"]:
        fail("RomFS identity sidecar belongs to another title/version.")
    if identity_json.get("bytes") != romfs_record["size"] or identity_json.get("sha256") != romfs_record["sha256"]:
        fail("RomFS identity sidecar does not match the Drive RomFS bytes/hash.")
    if romfs.stat().st_size != int(prep.get("romfs_size", -1)):
        fail("RomFS file size differs from the Colab preparation manifest.")

    prepared = {
        "project": PROJECT, "branch": BRANCH, "title_id": TITLE_ID,
        "package_version": prep["package_version"], "nx2apple_tag": NX2APPLE_TAG,
        "engine_pin": ENGINE_PIN, "request_id": handoff["request_id"],
        "work_dir": str(work), "romfs_path": str(romfs), "romfs_id_path": str(identity),
        "aoc_dir": str(aoc_dir), "aoc_count": len(restored),
        "aoc_images": [p.name for p in restored],
        "modules": prep["modules"], "shader_chain": prep["shader_chain"],
        "main_build_id": prep["main_build_id"], "main_sha256": prep["main_sha256"],
        "allocator": prep["allocator"], "unreal_shader_sources": prep["unreal_shader_sources"],
        "game_data": game_data,
    }
    output_path = root / "actions-input.json"
    output_path.write_text(json.dumps(prepared, indent=2) + "\n", encoding="utf-8")
    print("[SpkIOSzero] Actions input validated:", output_path)
    print("[SpkIOSzero] Source NSPs and prod.keys never leave Colab; only workspace + external RomFS/AOC are restored on macOS.")

if __name__ == "__main__": main()
