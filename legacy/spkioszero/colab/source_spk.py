#!/usr/bin/env python3
"""Isolated Sparking! ZERO source acquisition: Drive/<root>/spk plus the signed base archive."""
from __future__ import annotations
import hashlib, re, shutil, subprocess, time
from pathlib import Path, PurePosixPath

FOLDER_MIME = "application/vnd.google-apps.folder"
SEVEN_Z_SIGNATURE = bytes.fromhex("377abcaf271c")
CHUNK = 64 * 1024 * 1024

def fail(message: str) -> None:
    raise SystemExit("[SpkIOSzero] ERROR: " + message)

def list_children(api, parent_id: str) -> list[dict]:
    files, token = [], None
    while True:
        result = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000, pageToken=token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files.extend(result.get("files", []))
        token = result.get("nextPageToken")
        if not token:
            return files

def by_name(items: list[dict], name: str) -> dict | None:
    return next((x for x in items if x.get("name", "").lower() == name.lower()
                 and x.get("mimeType") != FOLDER_MIME), None)

def safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return value or "package.nsp"

def download_drive_file(api, item: dict, target: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = int(item.get("size") or 0)
    md5 = str(item.get("md5Checksum") or "").lower()
    if target.is_file() and expected and target.stat().st_size == expected:
        if not md5:
            print(f"[SpkIOSzero] Reusing Drive file by size: {item['name']}")
            return
        digest = hashlib.md5()
        with target.open("rb") as f:
            for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest().lower() == md5:
            print(f"[SpkIOSzero] Reusing Drive file (MD5 verified): {item['name']}")
            return
    part = target.with_suffix(target.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        dl = MediaIoBaseDownload(stream, request, chunksize=CHUNK)
        done = False
        while not done:
            status, done = dl.next_chunk()
            if status:
                print(f"[SpkIOSzero] Drive {item['name']}: {status.progress()*100:.1f}%", flush=True)
    if expected and part.stat().st_size != expected:
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item['name']}")
    if not part.stat().st_size:
        part.unlink(missing_ok=True)
        fail(f"Drive file is empty: {item['name']}")
    part.replace(target)

def upload_drive_file(api, path: Path, parent_id: str, name: str) -> dict:
    from googleapiclient.http import MediaFileUpload
    size = path.stat().st_size
    media = MediaFileUpload(str(path), mimetype="application/octet-stream",
                            chunksize=CHUNK, resumable=True)
    request = api.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,size",
        supportsAllDrives=True,
    )
    item = None
    while item is None:
        status, item = request.next_chunk()
        if status:
            print(f"[SpkIOSzero] Uploading extracted base to Drive/spk/{name}: {status.progress()*100:.1f}%", flush=True)
    if int(item.get("size", -1)) != size:
        fail(f"Drive upload size mismatch for {name}: expected {size}, got {item.get('size')}")
    print(f"[SpkIOSzero] Extracted base persisted in Drive/spk/{name}: {size:,} bytes ({size/2**30:.2f} GiB).", flush=True)
    return {"id": item["id"], "name": item["name"], "size": size}


def download_7z(url: str, target: Path) -> None:
    import requests
    if target.is_file() and target.stat().st_size > 32:
        with target.open("rb") as f:
            if f.read(6) == SEVEN_Z_SIGNATURE:
                print(f"[SpkIOSzero] Reusing downloaded 7z ({target.stat().st_size:,} bytes).")
                return
    if not url.startswith(("https://", "http://")):
        fail("The signed base archive URL is missing or invalid.")
    part = target.with_suffix(".7z.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    total, last = 0, 0
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=(30, 180)) as response:
            if response.status_code >= 400:
                fail(f"Base archive URL returned HTTP {response.status_code}; it may have expired.")
            expected = int(response.headers.get("content-length") or 0)
            with part.open("wb") as out:
                for block in response.iter_content(8 * 1024 * 1024):
                    if not block:
                        continue
                    out.write(block); total += len(block)
                    if total - last >= 512 * 1024 * 1024:
                        print(f"[SpkIOSzero] Base archive: {total/2**30:.2f}/{expected/2**30:.2f} GiB" if expected else f"[SpkIOSzero] Base archive: {total/2**30:.2f} GiB", flush=True)
                        last = total
        if total < 32:
            fail("The base archive download is empty or truncated.")
        with part.open("rb") as f:
            if f.read(6) != SEVEN_Z_SIGNATURE:
                fail("The link did not return a valid 7z archive (it may have expired).")
        part.replace(target)
        print(f"[SpkIOSzero] Base 7z downloaded: {total:,} bytes ({total/2**30:.2f} GiB).")
    except SystemExit:
        part.unlink(missing_ok=True)
        raise
    except Exception as exc:
        part.unlink(missing_ok=True)
        fail(f"Base archive download failed ({type(exc).__name__}); issue a fresh signed link if it expired.")

def install_7zip() -> str:
    binary = shutil.which("7z") or shutil.which("7zz")
    if binary:
        return binary
    subprocess.run(["apt-get", "update", "-qq"], check=True)
    for package in ("p7zip-full", "7zip"):
        r = subprocess.run(["apt-get", "install", "-y", "-qq", package],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        binary = shutil.which("7z") or shutil.which("7zz")
        if r.returncode == 0 and binary:
            return binary
    fail("Unable to install 7-Zip in Colab.")
    raise AssertionError("unreachable")

PACKAGE_SUFFIXES = {".nsp", ".xci"}

def find_packages(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in PACKAGE_SUFFIXES
        and not p.name.startswith("._")
    )


def validate_package(path: Path) -> str:
    """Match NXNative is_package(): NSP=PFS0 at 0; XCI=HEAD at offset 0x100."""
    if not path.is_file():
        fail(f"Game package does not exist: {path}")
    suffix = path.suffix.lower()
    with path.open("rb") as stream:
        header = stream.read(0x104)
    if suffix == ".nsp":
        if len(header) < 4 or header[:4] != b"PFS0":
            fail(f"{path.name} has .nsp extension but does not contain the PFS0 header.")
        return "NSP"
    if suffix == ".xci":
        if len(header) < 0x104 or header[0x100:0x104] != b"HEAD":
            fail(f"{path.name} has .xci extension but does not contain the XCI HEAD magic at offset 0x100.")
        return "XCI"
    fail(f"Unsupported game package extension: {path.name}; expected .nsp or .xci.")
    raise AssertionError("unreachable")


def extract_single_base(archive: Path, destination: Path, sevenzip: str) -> Path:
    listing = subprocess.run([sevenzip, "l", "-slt", str(archive)], check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    for line in listing.splitlines():
        if not line.startswith("Path = "):
            continue
        raw = line[7:].strip()
        if raw in (str(archive), archive.name):
            continue
        name = raw.replace("\\", "/")
        member = PurePosixPath(name)
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in member.parts:
            fail(f"Unsafe path inside base archive: {raw}")
    if "Symbolic Link =" in listing or "Hard Link =" in listing:
        fail("The base archive contains links; refusing unsafe extraction.")
    test = subprocess.run([sevenzip, "t", str(archive)], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    if test.returncode:
        fail("7-Zip integrity test failed; archive may be damaged or password protected.")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sevenzip, "x", str(archive), f"-o{destination}", "-y"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        fail("7-Zip extraction failed: " + result.stdout[-2000:])
    packages = find_packages(destination)
    if len(packages) != 1:
        details = "; ".join(
            f"{p.relative_to(destination)} ({p.stat().st_size:,} bytes)"
            for p in packages
        )
        fail(
            "Base 7z must contain exactly one supported game package (.nsp or .xci); "
            f"found {len(packages)}: {details or '(no NSP/XCI files)'}"
        )
    validate_package(packages[0])
    return packages[0]

def prepare_source(api, drive_folder_id: str, runtime_root: Path, archive_url: str) -> dict:
    root_items = list_children(api, drive_folder_id)
    spk_folder = next((x for x in root_items if x.get("mimeType") == FOLDER_MIME
                       and x.get("name", "").lower() == "spk"), None)
    if not spk_folder:
        fail("The configured Drive folder must contain the dedicated 'spk' subfolder.")
    spk_items = list_children(api, spk_folder["id"])

    root_keys = [x for x in root_items if x.get("name", "").lower() == "prod.keys"
                 and x.get("mimeType") != FOLDER_MIME]
    spk_keys = [x for x in spk_items if x.get("name", "").lower() == "prod.keys"
                and x.get("mimeType") != FOLDER_MIME]
    if len(root_keys) > 1 or len(spk_keys) > 1 or not (root_keys or spk_keys):
        fail(f"Expected prod.keys in Drive root or Drive/spk (max one per folder); found {len(root_keys)} in root and {len(spk_keys)} in spk.")
    keys_item = (spk_keys or root_keys)[0]

    package_items = [
        x for x in spk_items
        if x.get("mimeType") != FOLDER_MIME
        and Path(x.get("name", "")).suffix.lower() in PACKAGE_SUFFIXES
    ]
    update_items = [x for x in package_items if x.get("name", "").lower() == "update.nsp"]
    if len(update_items) != 1:
        fail(f"Expected exactly one update.nsp in Drive/spk; found {len(update_items)}.")
    update_item = update_items[0]

    dlc_items = sorted(
        (x for x in package_items
         if x["id"] != update_item["id"]
         and re.fullmatch(r"dlc[^/]*\.nsp", x.get("name", ""), re.I)),
        key=lambda x: x.get("name", "").lower(),
    )
    if len(dlc_items) != 10:
        fail(f"Expected exactly 10 DLC NSPs (dlc*.nsp) in Drive/spk; found {len(dlc_items)}.")

    excluded_ids = {update_item["id"], *(x["id"] for x in dlc_items)}
    base_items = [x for x in package_items if x["id"] not in excluded_ids]
    if len(base_items) > 1:
        fail("Drive/spk contains more than one base package besides update.nsp and dlc*.nsp; keep exactly one .nsp or .xci.")
    base_item = base_items[0] if base_items else None

    input_dir = runtime_root / "input-packages"
    keys_path = runtime_root / "keys" / "prod.keys"
    input_dir.mkdir(parents=True, exist_ok=True)
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    download_drive_file(api, keys_item, keys_path)

    if base_item:
        base_extension = Path(base_item["name"]).suffix.lower()
        base_type = "XCI" if base_extension == ".xci" else "NSP"
        base_path = input_dir / f"000_base{base_extension}"
        download_drive_file(api, base_item, base_path)
        validate_package(base_path)
        print(f"[SpkIOSzero] Base {base_type} reused from Drive/spk as {base_item['name']}; the 7z link is not needed.")
    else:
        temp = runtime_root / "7z-temporary"
        archive = temp / "sparking-zero-base.7z"
        extracted = temp / "extracted"
        temp.mkdir(parents=True, exist_ok=True)
        candidates = find_packages(extracted)
        if not candidates:
            download_7z(archive_url, archive)
            sevenzip = install_7zip()
            base_extracted = extract_single_base(archive, extracted, sevenzip)
        else:
            if len(candidates) != 1:
                fail(f"Cached base extraction is ambiguous: {len(candidates)} NSP/XCI packages.")
            base_extracted = candidates[0]
            validate_package(base_extracted)
        base_extension = base_extracted.suffix.lower()
        base_type = "XCI" if base_extension == ".xci" else "NSP"
        base_path = input_dir / f"000_base{base_extension}"
        for stale in input_dir.glob("000_base.*"):
            if stale != base_path:
                stale.unlink(missing_ok=True)
        shutil.copy2(base_extracted, base_path)
        upload_drive_file(api, base_path, spk_folder["id"], f"base{base_extension}")
        print(f"[SpkIOSzero] Persisted extracted base {base_type} as base{base_extension} in Drive/spk.")

    update_path = input_dir / "001_update.nsp"
    download_drive_file(api, update_item, update_path)
    validate_package(update_path)
    package_paths = [base_path, update_path]
    dlc_records = []
    for index, item in enumerate(dlc_items, start=2):
        name = safe_name(item["name"])
        target = input_dir / f"{index:03d}_{name}"
        download_drive_file(api, item, target)
        validate_package(target)
        package_paths.append(target)
        dlc_records.append({
            "name": target.name, "drive_name": item["name"], "size": target.stat().st_size
        })

    expected = {p.resolve() for p in package_paths}
    for old in list(input_dir.iterdir()):
        if old.is_file() and old.suffix.lower() in PACKAGE_SUFFIXES and old.resolve() not in expected:
            old.unlink()
    if len(package_paths) != 12 or len(dlc_records) != 10:
        fail(f"Expected 12 game packages (1 base {base_type} + 1 update NSP + 10 DLC NSPs); found {len(package_paths)}.")
    nsp_count = sum(p.suffix.lower() == ".nsp" for p in package_paths)
    xci_count = sum(p.suffix.lower() == ".xci" for p in package_paths)
    if xci_count != (1 if base_type == "XCI" else 0):
        fail(f"Expected exactly one base package in {base_type} format; found {xci_count} XCI package(s).")
    total_bytes = sum(p.stat().st_size for p in package_paths)
    print(
        f"[SpkIOSzero] Source set: 12 packages (1 base {base_type} + 1 update NSP + 10 DLC NSPs), "
        f"{total_bytes/2**30:.2f} GiB; Drive source folder is {spk_folder['name']}.",
        flush=True,
    )
    return {
        "package_dir": str(input_dir),
        "keys_path": str(keys_path),
        "source_folder_id": spk_folder["id"],
        "source_folder_name": spk_folder["name"],
        "package_count": len(package_paths),
        "base_type": base_type,
        "base_extension": base_extension,
        "base_file_name": base_path.name,
        "input_nsp_count": nsp_count,
        "input_xci_count": xci_count,
        "update_nsp_count": 1,
        "dlc_nsp_count": len(dlc_records),
        "dlc_files": dlc_records,
    }
