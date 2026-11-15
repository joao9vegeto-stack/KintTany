#!/usr/bin/env python3
"""Download six RAR volumes, reconstruct Kakarot base/update NSP/XCI, and stage Drive keys."""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse, urljoin

FOLDER_MIME = "application/vnd.google-apps.folder"
PACKAGE_SUFFIXES = {".nsp", ".xci"}
RAR_SIGNATURES = (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")
VOLUME_COUNT = 3

def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS] ERROR: " + message)

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def package_type(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 0x104:
        fail(f"{path}: package is missing, symlinked, or too small.")
    with path.open("rb") as stream:
        header = stream.read(0x104)
    if header[:4] == b"PFS0":
        return "NSP"
    if header[0x100:0x104] == b"HEAD":
        return "XCI"
    fail(f"{path.name}: extracted file does not contain a valid NSP (PFS0) or XCI (HEAD@0x100) header.")

def validate_package(path: Path, expected_suffix: str | None = None) -> str:
    suffix = (expected_suffix or path.suffix).lower()
    if suffix not in PACKAGE_SUFFIXES:
        fail(f"{path.name}: expected .nsp or .xci.")
    detected = package_type(path)
    expected = "XCI" if suffix == ".xci" else "NSP"
    if detected != expected:
        fail(f"{path.name}: extension says {expected}, but the package header identifies {detected}.")
    return detected

def parse_disposition_name(value: str | None) -> str | None:
    if not value:
        return None
    message = Message()
    message["content-disposition"] = value
    name = message.get_filename()
    if not name:
        return None
    name = unquote(str(name)).replace("\\", "/").split("/")[-1].strip()
    if name in ("", ".", "..") or "\x00" in name:
        return None
    return name

def url_name(url: str) -> str | None:
    name = unquote(Path(urlparse(url).path).name).strip()
    if name and re.search(r"\.(?:rar|r\d{2})$", name, re.IGNORECASE) and name not in (".", ".."):
        return name
    return None

def safe_volume_name(name: str, label: str) -> str:
    name = str(name).strip().replace("\\", "/")
    if "/" in name or name in ("", ".", "..") or "\x00" in name:
        fail(f"{label} volume filename must be a simple filename, got {name!r}.")
    if not re.search(r"\.(?:rar|r\d{2})$", name, re.IGNORECASE):
        fail(f"{label} volume filename must end in .rar or a legacy .rNN extension, got {name!r}.")
    return name

def is_rar_volume(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 8:
        return False
    with path.open("rb") as stream:
        head = stream.read(8)
    return head.startswith(RAR_SIGNATURES)

def validate_volume_sequence(names: list[str], label: str) -> dict:
    if len(names) != VOLUME_COUNT:
        fail(f"{label}: expected exactly three RAR volumes; received {len(names)}.")
    normalized = [x.lower() for x in names]
    modern = [re.fullmatch(r"(?P<prefix>.+)\.part(?P<num>\d+)\.rar", x) for x in normalized]
    if all(modern):
        prefixes = {m.group("prefix") for m in modern}
        widths = {len(m.group("num")) for m in modern}
        numbers = [int(m.group("num")) for m in modern]
        if len(prefixes) == 1 and len(widths) == 1 and numbers == [1, 2, 3]:
            return {"scheme": "modern", "prefix": next(iter(prefixes)), "numbers": numbers}
        fail(f"{label}: RAR .part sequence is inconsistent or not ordered 1,2,3: {names}.")
    first = re.fullmatch(r"(?P<prefix>.+)\.rar", normalized[0])
    second = re.fullmatch(r"(?P<prefix>.+)\.r00", normalized[1])
    third = re.fullmatch(r"(?P<prefix>.+)\.r01", normalized[2])
    if first and second and third and first.group("prefix") == second.group("prefix") == third.group("prefix"):
        return {"scheme": "legacy", "prefix": first.group("prefix"), "numbers": [0, 1, 2]}
    fail(
        f"{label}: could not prove that the three filenames are one ordered RAR set. "
        "Use BASE_PART_NAMES / UPDATE_PART_NAMES with the original volume names "
        "(modern: name.part1.rar, name.part2.rar, name.part3.rar; legacy: name.rar, name.r00, name.r01). "
        f"Received: {names}"
    )

def install_unrar() -> str:
    executable = shutil.which("unrar")
    if executable:
        return executable
    if not os.geteuid() == 0:
        fail("RAR extraction requires the RARLAB unrar binary and Colab does not have root access.")
    update = subprocess.run(["apt-get", "update", "-qq"], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    if update.returncode:
        fail("apt-get update failed while preparing RAR extraction: " + update.stdout[-3000:])
    install = subprocess.run(["apt-get", "install", "-y", "-qq", "unrar"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if install.returncode:
        subprocess.run(["apt-get", "install", "-y", "-qq", "software-properties-common"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        add = subprocess.run(["add-apt-repository", "-y", "multiverse"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if add.returncode == 0:
            subprocess.run(["apt-get", "update", "-qq"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
            install = subprocess.run(["apt-get", "install", "-y", "-qq", "unrar"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    executable = shutil.which("unrar")
    if not executable:
        fail("Could not install RARLAB unrar from Ubuntu multiverse: " + install.stdout[-4000:])
    version = subprocess.run([executable], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True).stdout.splitlines()
    print("[KaKaRoTiOS] RAR extractor ready: " + (version[0] if version else executable), flush=True)
    return executable

class AkiraBoxDownloadPageParser(HTMLParser):
    """Read the normal download anchor; never solve CAPTCHAs or anti-bot checks."""
    def __init__(self) -> None:
        super().__init__()
        self.download_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        if values.get("id") == "download-button" and values.get("href"):
            self.download_href = values["href"]


_AKIRABOX_METADATA_CACHE: dict[str, dict] = {}


def _akirabox_file_code(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"akirabox.to", "www.akirabox.to", "akirabox.com", "www.akirabox.com"}:
        return None
    match = re.fullmatch(r"/([A-Za-z0-9_-]+)/file/?", parsed.path or "")
    return match.group(1) if match else None


def _akirabox_metadata(url: str) -> dict:
    """Call AkiraBox's documented public file-status endpoint."""
    import requests
    code = _akirabox_file_code(url)
    if not code:
        raise RuntimeError(f"Not a supported AkiraBox share URL: {url}")
    if url in _AKIRABOX_METADATA_CACHE:
        return _AKIRABOX_METADATA_CACHE[url]

    canonical_share_url = f"https://akirabox.com/{code}/file"
    try:
        response = requests.get(
            "https://akirabox.com/api/files",
            params={"url": canonical_share_url},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=(20, 45),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(
            f"AkiraBox status API could not validate {url}: {type(exc).__name__}: {exc}"
        ) from exc

    api_status = payload.get("status", response.status_code) if isinstance(payload, dict) else response.status_code
    if response.status_code != 200 or api_status != 200:
        message = payload.get("message", "file unavailable") if isinstance(payload, dict) else "invalid API response"
        raise RuntimeError(
            f"AkiraBox reports {url} unavailable (HTTP {response.status_code}, status {api_status}): {message}"
        )
    name = str(payload.get("name") or "").strip()
    if not name or payload.get("type", "file") != "file":
        raise RuntimeError(f"AkiraBox status API did not identify {url} as a file: {payload}")
    metadata = {
        "file_code": code, "name": name, "size": payload.get("size"),
        "mime": payload.get("mime"), "url": payload.get("url") or canonical_share_url,
    }
    _AKIRABOX_METADATA_CACHE[url] = metadata
    return metadata


def preflight_akirabox_links(groups: list[dict]) -> list[dict]:
    """Validate six share URLs and each returned filename before any RAR transfer."""
    seen_codes: set[str] = set()
    checked: list[dict] = []
    for group in groups:
        label, urls, names = str(group["label"]), list(group["urls"]), list(group["names"])
        if len(urls) != VOLUME_COUNT or len(names) != VOLUME_COUNT:
            raise RuntimeError(f"{label}: expected exactly three AkiraBox URLs and three expected filenames.")
        for index, (url, expected_name) in enumerate(zip(urls, names), 1):
            metadata = _akirabox_metadata(str(url).strip())
            if metadata["file_code"] in seen_codes:
                raise RuntimeError(f"{label} part{index}: duplicate AkiraBox file ID {metadata['file_code']}.")
            seen_codes.add(metadata["file_code"])
            actual_name = PurePosixPath(metadata["name"].replace("\\", "/")).name
            if actual_name.casefold() != str(expected_name).casefold():
                raise RuntimeError(
                    f"{label} part{index}: AkiraBox identifies this file as {actual_name!r}, "
                    f"not the expected {expected_name!r}. No download was started."
                )
            lower_name = actual_name.lower()
            if (str(group["title_id"]).lower() not in lower_name
                    or str(group["version"]).lower() not in lower_name
                    or not lower_name.endswith(f".part{index}.rar")):
                raise RuntimeError(
                    f"{label} part{index}: AkiraBox filename does not match Title ID, version and order: {actual_name!r}."
                )
            checked.append({"group": label, "part": index, **metadata})
            print(
                f"[KaKaRoTiOS] AkiraBox link verified: {label} part{index}/3 — "
                f"{actual_name}; size={metadata['size']}; ID={metadata['file_code']}.",
                flush=True,
            )
    if len(checked) != 6:
        raise RuntimeError(f"AkiraBox preflight expected six files, validated {len(checked)}.")
    print("[KaKaRoTiOS] All six AkiraBox share links passed metadata/name/order preflight.", flush=True)
    return checked


def _resolve_akirabox_download(url: str):
    """Open the share page normally and read its download button without evading human checks."""
    import requests
    metadata = _akirabox_metadata(url)
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        page = session.get(url, headers=headers, allow_redirects=True, timeout=(25, 60))
        page.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if status in (401, 403, 429):
            raise RuntimeError(
                f"AkiraBox share page returned HTTP {status} for {url}. "
                "It requires a browser session or human verification; no CAPTCHA/anti-bot bypass was attempted."
            ) from exc
        raise RuntimeError(f"AkiraBox share page could not be opened ({status}): {url}") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not open AkiraBox share page {url}: {type(exc).__name__}: {exc}") from exc

    parser = AkiraBoxDownloadPageParser()
    parser.feed(page.text or "")
    if not parser.download_href:
        lowered = (page.text or "").lower()
        if any(token in lowered for token in (
            "captcha", "verify you are human", "cf-chl-", "challenge-platform",
            "cloudflare", "human verification",
        )):
            reason = "the page requires human/Cloudflare verification"
        else:
            reason = "the normal download button was not present in the returned page"
        raise RuntimeError(
            f"AkiraBox confirmed the file metadata ({metadata['name']}) but {reason}. "
            "Open the share link in Safari and complete the provider's own verification; "
            "this downloader will not attempt to bypass it."
        )
    return session, urljoin(page.url, parser.download_href), page.url, metadata


def download_blob(url: str, destination: Path, retries: int = 10) -> dict:
    """Download one RAR volume from a direct URL or an AkiraBox share page."""
    import requests
    if not url or not url.startswith(("https://", "http://")):
        fail(f"No valid source URL supplied for {destination.name}.")
    fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
    part = destination.with_suffix(destination.suffix + ".part")
    source_path = destination.with_suffix(destination.suffix + ".source.json")
    if destination.is_file() and source_path.is_file():
        try:
            old = json.loads(source_path.read_text(encoding="utf-8"))
            if old.get("url_sha256") == fingerprint and old.get("size") == destination.stat().st_size:
                if is_rar_volume(destination) and old.get("sha256") == sha256_file(destination):
                    return {
                        "path": str(destination), "remote_name": old["remote_name"],
                        "size": destination.stat().st_size, "sha256": old["sha256"],
                        "url_sha256": fingerprint,
                    }
        except (OSError, ValueError, KeyError):
            pass
    if part.exists():
        marker = part.with_suffix(part.suffix + ".urlsha256")
        previous_source = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
        if previous_source != fingerprint:
            part.unlink(missing_ok=True)
    marker = part.with_suffix(part.suffix + ".urlsha256")
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)

    is_akira = _akirabox_file_code(url) is not None
    if is_akira:
        session, request_url, page_url, metadata = _resolve_akirabox_download(url)
        metadata_name = metadata["name"]
        request_headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "identity",
            "Referer": page_url,
        }
        print(
            f"[KaKaRoTiOS] AkiraBox download button resolved for {metadata_name}; "
            f"provider size={metadata['size']}.", flush=True
        )
    else:
        session = requests.Session()
        request_url, metadata_name = url, None
        request_headers = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}

    last_error = None
    for attempt in range(1, retries + 1):
        offset = part.stat().st_size if part.exists() else 0
        headers = dict(request_headers)
        if offset:
            headers["Range"] = f"bytes={offset}-"
        response = None
        try:
            print(
                f"[KaKaRoTiOS] Downloading RAR volume {destination.name}; "
                f"attempt {attempt}/{retries}; resume={offset:,} bytes.", flush=True
            )
            with session.get(request_url, headers=headers, stream=True,
                             allow_redirects=True, timeout=(30, 240)) as response:
                if response.status_code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise RuntimeError(f"unexpected Content-Range: {content_range!r}")
                    mode = "ab"
                elif response.status_code == 200:
                    mode, offset = "wb", 0
                else:
                    response.raise_for_status()
                    raise RuntimeError(f"unexpected HTTP status {response.status_code}")
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    raise RuntimeError(
                        "AkiraBox returned an HTML verification page instead of RAR bytes; "
                        "human verification is required and will not be bypassed."
                    )
                remote_name = (
                    parse_disposition_name(response.headers.get("Content-Disposition"))
                    or url_name(response.url) or metadata_name or url_name(url)
                )
                length = response.headers.get("Content-Length")
                total = offset + int(length) if length is not None else 0
                if not total:
                    match = re.match(r"bytes\s+\d+-\d+/(\d+|\*)", response.headers.get("Content-Range", ""))
                    total = int(match.group(1)) if match and match.group(1) != "*" else 0
                written = offset
                with part.open(mode) as output:
                    for block in response.iter_content(chunk_size=16 * 1024 * 1024):
                        if block:
                            output.write(block)
                            written += len(block)
                if total and written != total:
                    raise RuntimeError(f"short transfer: expected {total:,} bytes, received {written:,}")
            if not is_rar_volume(part):
                raise RuntimeError("downloaded content does not start with a RAR4/RAR5 volume signature")
            if destination.exists():
                destination.unlink()
            part.replace(destination)
            marker.unlink(missing_ok=True)
            if remote_name:
                remote_name = safe_volume_name(remote_name, "downloaded")
            record = {
                "url_sha256": fingerprint, "remote_name": remote_name or "",
                "name": destination.name, "size": destination.stat().st_size,
                "sha256": sha256_file(destination),
            }
            source_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            return {
                "path": str(destination), "remote_name": record["remote_name"],
                "size": record["size"], "sha256": record["sha256"],
                "url_sha256": fingerprint,
            }
        except Exception as exc:
            last_error = exc
            current = part.stat().st_size if part.exists() else 0
            print(
                f"[KaKaRoTiOS] RAR download interrupted at {current:,} bytes: "
                f"{type(exc).__name__}: {exc}", flush=True
            )
            status = response.status_code if response is not None else None
            if status in (400, 401, 403, 404, 410, 429):
                break
            if isinstance(exc, RuntimeError) and any(
                token in str(exc).lower() for token in ("verification", "human", "captcha")
            ):
                break
            if attempt < retries:
                delay = min(2 ** min(attempt, 5), 30)
                print(f"[KaKaRoTiOS] Retrying after {delay}s.", flush=True)
                time.sleep(delay)
    raise RuntimeError(f"Could not download {destination.name}; last result: {last_error}") from last_error

def resolve_volume_names(records: list[dict], overrides: list[str] | None, label: str) -> list[str]:
    if overrides:
        if len(overrides) != VOLUME_COUNT or any(not str(x).strip() for x in overrides):
            fail(f"{label}_PART_NAMES must contain three complete original filenames or be left entirely blank.")
        names = [safe_volume_name(x, label) for x in overrides]
        for record, expected in zip(records, names):
            actual = str(record.get("remote_name") or "").strip()
            if actual and PurePosixPath(actual.replace("\\", "/")).name.casefold() != expected.casefold():
                fail(
                    f"{label}: AkiraBox returned filename {actual!r}, but notebook expects {expected!r}; "
                    "refusing to combine volumes from different archives."
                )
    else:
        names = [safe_volume_name(x["remote_name"], label) if x.get("remote_name") else ""
                 for x in records]
        if any(not names):
            fail(f"{label}: the download server did not expose all three original RAR filenames. "
                 f"Fill {label}_PART_NAMES with the exact original names in volume order.")
    validate_volume_sequence(names, label)
    return names

def extract_rar_set(unrar: str, volume_paths: list[Path], names: list[str],
                    destination: Path, label: str) -> tuple[Path, dict]:
    """Extract exactly once, starting from volume 1; UnRAR chains volumes and checks file CRC."""
    validate_volume_sequence(names, label)
    for path, name in zip(volume_paths, names):
        if not path.is_file() or not is_rar_volume(path):
            fail(f"{label}: missing/invalid RAR volume {name}.")
    first = volume_paths[0]
    listing = subprocess.run([unrar, "lb", "-idq", "-p-", str(first)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if listing.returncode != 0:
        fail(f"{label}: UnRAR could not list the complete volume set: {listing.stdout[-2500:]}")
    archive_names = [x.strip() for x in listing.stdout.splitlines() if x.strip()]
    for item in archive_names:
        normalized = item.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", normalized):
            fail(f"{label}: archive contains an unsafe extraction path: {item!r}")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    log = destination.parent / f"{label.lower()}-unrar.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run([unrar, "x", "-y", "-o+", "-idq", "-p-",
                                  str(first), str(destination) + os.sep],
            stdout=stream, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-5000:]
        shutil.rmtree(destination, ignore_errors=True)
        fail(f"{label}: multi-volume RAR extraction failed (UnRAR exit {result.returncode}). "
             f"Check the missing/incorrect volume, password or CRC. Log tail:\n{tail}")
    symlinks = [p for p in destination.rglob("*") if p.is_symlink()]
    if symlinks:
        fail(f"{label}: archive produced symlinks; refusing to consume them: {symlinks[:5]}")
    candidates = sorted(p for p in destination.rglob("*")
                        if p.is_file() and p.suffix.lower() in PACKAGE_SUFFIXES)
    if len(candidates) != 1:
        fail(f"{label}: expected exactly one complete NSP/XCI after extracting the three RAR volumes; "
             f"found {len(candidates)}: {[p.name for p in candidates[:12]]}")
    package = candidates[0]
    kind = validate_package(package)
    audit = {
        "rar_names": names,
        "rar_volumes": [
            {"name": name, "size": path.stat().st_size, "sha256": sha256_file(path)}
            for path, name in zip(volume_paths, names)
        ],
        "archive_entry_count": len(archive_names),
        "extracted_package": package.name,
        "package_type": kind,
        "package_size": package.stat().st_size,
        "package_sha256": sha256_file(package),
        "unrar_exit_code": result.returncode,
    }
    print(f"[KaKaRoTiOS] {label}: extracted one verified {kind}, {audit['package_size']:,} bytes; CRC check passed.", flush=True)
    return package, audit

def list_children(api, parent_id: str) -> list[dict]:
    items, token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000, pageToken=token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return items

def get_or_create_folder(api, name: str, parent_id: str) -> dict:
    found = [x for x in list_children(api, parent_id)
             if x.get("mimeType") == FOLDER_MIME and x.get("name", "").lower() == name.lower()]
    if len(found) > 1:
        fail(f"More than one Drive/{name} folder exists; keep one to avoid writing to the wrong workspace.")
    if found:
        return found[0]
    return api.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id,name", supportsAllDrives=True).execute()

def download_drive_file(api, item: dict, destination: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    request = api.files().get_media(fileId=item["id"], supportsAllDrives=True)
    with part.open("wb") as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"[KaKaRoTiOS] Drive {item.get('name', item['id'])}: {status.progress()*100:.1f}%", flush=True)
    size = part.stat().st_size
    if size <= 0:
        part.unlink(missing_ok=True)
        fail(f"Drive returned an empty {item.get('name', 'file')}.")
    expected_size = int(item.get("size", size))
    if size != expected_size:
        part.unlink(missing_ok=True)
        fail(f"Drive size mismatch for {item.get('name')}: expected {expected_size}, received {size}.")
    expected_sha = item.get("sha256")
    if expected_sha and sha256_file(part).lower() != str(expected_sha).lower():
        part.unlink(missing_ok=True)
        fail(f"Drive SHA-256 mismatch for {item.get('name')}.")
    expected_md5 = item.get("md5") or item.get("md5Checksum")
    if expected_md5 and md5_file(part).lower() != str(expected_md5).lower():
        part.unlink(missing_ok=True)
        fail(f"Drive MD5 mismatch for {item.get('name')}.")
    part.replace(destination)

def recover_uploaded_packages(api, drive_root_id: str, runtime_root: Path,
                              url_fingerprints: dict, keys_path: Path) -> dict | None:
    """After a Colab runtime reset, rebuild the local inputs from already verified Drive NSP/XCI files."""
    folders = [x for x in list_children(api, drive_root_id)
               if x.get("mimeType") == FOLDER_MIME and x.get("name", "").startswith("KaKaRoTiOS_")]
    folders.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)
    for folder in folders:
        try:
            children = list_children(api, folder["id"])
            pipeline = [x for x in children if x.get("mimeType") == FOLDER_MIME and x.get("name") == "pipeline"]
            if len(pipeline) != 1:
                continue
            manifests = [x for x in list_children(api, pipeline[0]["id"])
                         if x.get("mimeType") != FOLDER_MIME and x.get("name") == "source-manifest.json"]
            if len(manifests) != 1:
                continue
            remote_manifest = manifests[0]
            local_manifest = runtime_root / "drive-source-manifest.json"
            download_drive_file(api, remote_manifest, local_manifest)
            saved = json.loads(local_manifest.read_text(encoding="utf-8"))
            if saved.get("input_url_fingerprints") != url_fingerprints:
                continue
            if saved.get("drive_output_folder_id") != folder["id"]:
                continue
            package_dir = runtime_root / "input-packages"
            package_dir.mkdir(parents=True, exist_ok=True)
            for label in ("base", "update"):
                record = saved.get(f"drive_{label}_package") or {}
                metadata = saved.get(label) or {}
                if (not record.get("id") or not record.get("sha256") or not record.get("md5")
                        or int(record.get("size", 0)) <= 0):
                    raise ValueError(f"Drive {label} package record is incomplete.")
                expected_type = metadata.get("type")
                if expected_type not in ("NSP", "XCI"):
                    raise ValueError(f"Drive {label} package type is invalid.")
                suffix = ".xci" if expected_type == "XCI" else ".nsp"
                expected_name = f"{label}{suffix}"
                if record.get("name") != expected_name or int(record["size"]) != int(metadata.get("size", -1)):
                    raise ValueError(f"Drive {label} package name/size differs from the saved RAR reconstruction.")
                if record.get("sha256") != metadata.get("sha256"):
                    raise ValueError(f"Drive {label} package SHA-256 differs from the saved RAR reconstruction.")
                path = package_dir / expected_name
                download_drive_file(api, record, path)
                if validate_package(path) != expected_type or sha256_file(path) != metadata["sha256"]:
                    raise ValueError(f"Recovered Drive {label} package failed header/SHA-256 verification.")
                saved[f"{label}_path"] = str(path)
            saved["package_dir"] = str(package_dir)
            saved["keys_path"] = str(keys_path)
            saved["archive_dir"] = str(runtime_root / "rar-volumes")
            # The previous runtime is gone; its six RAR volumes are not required
            # because both complete NSP/XCI files have already been recovered.
            saved["rar_parts_cleanup_pending"] = False
            saved["rar_parts_deleted_after_drive_upload"] = True
            (runtime_root / "source-manifest.json").write_text(
                json.dumps(saved, indent=2) + "\n", encoding="utf-8")
            print(f"[KaKaRoTiOS] Recovered base + update from the previous Drive run {folder['name']}; the six RAR volumes will not be downloaded again.", flush=True)
            return saved
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            print(f"[KaKaRoTiOS] Skipping incomplete Drive source checkpoint {folder['name']}: {exc}", flush=True)
            continue
    return None

def prepare_source(api, drive_root_id: str, runtime_root: Path,
                   base_part_urls: list[str], update_part_urls: list[str],
                   base_part_names: list[str] | None = None,
                   update_part_names: list[str] | None = None) -> dict:
    """Fetch and extract two independent three-volume RAR sets; prod.keys stays in Colab."""
    for label, urls in (("BASE", base_part_urls), ("UPDATE", update_part_urls)):
        if len(urls) != VOLUME_COUNT or any(not str(x).strip() for x in urls):
            fail(f"{label}_PART_URLS must contain exactly three non-empty direct-download URLs.")
    configured_root_id = drive_root_id
    configured_root_items = list_children(api, configured_root_id)
    kakarot_folders = [x for x in configured_root_items
                       if x.get("mimeType") == FOLDER_MIME
                       and x.get("name", "").lower() == "kakarot"]
    if len(kakarot_folders) != 1:
        fail(f"Expected exactly one 'kakarot' folder under the already-configured Drive root; found {len(kakarot_folders)}.")
    kakarot_folder_id = kakarot_folders[0]["id"]
    kakarot_items = list_children(api, kakarot_folder_id)

    # Match the existing Link2iOS/SpkIOSzero convention: prod.keys may be
    # in the configured shared root or inside the game-specific subfolder.
    root_keys = [x for x in configured_root_items
                 if x.get("name", "").lower() == "prod.keys"
                 and x.get("mimeType") != FOLDER_MIME]
    kakarot_keys = [x for x in kakarot_items
                    if x.get("name", "").lower() == "prod.keys"
                    and x.get("mimeType") != FOLDER_MIME]
    if len(root_keys) > 1 or len(kakarot_keys) > 1 or not (root_keys or kakarot_keys):
        fail("Expected at most one prod.keys in the configured Drive root and at most one in Drive/kakarot, with at least one available.")
    keys_item = (kakarot_keys or root_keys)[0]
    drive_root_id = kakarot_folder_id

    runtime_root.mkdir(parents=True, exist_ok=True)
    keys_path = runtime_root / "keys" / "prod.keys"
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    download_drive_file(api, keys_item, keys_path)
    if keys_path.stat().st_size < 1024:
        fail("prod.keys is unexpectedly small; verify the Drive copy.")

    url_fingerprints = {
        "base": [hashlib.sha256(str(x).strip().encode("utf-8")).hexdigest() for x in base_part_urls],
        "update": [hashlib.sha256(str(x).strip().encode("utf-8")).hexdigest() for x in update_part_urls],
    }
    source_manifest = runtime_root / "source-manifest.json"
    if source_manifest.is_file():
        try:
            cached = json.loads(source_manifest.read_text(encoding="utf-8"))
            reusable = cached.get("input_url_fingerprints") == url_fingerprints
            for label in ("base", "update"):
                item = cached[label]
                path = Path(cached[f"{label}_path"])
                reusable = reusable and path.is_file()
                if reusable:
                    reusable = (path.stat().st_size == int(item["size"])
                                and sha256_file(path) == item["sha256"]
                                and package_type(path) == item["type"])
            if reusable:
                cached["keys_path"] = str(keys_path)
                cached["drive_kakarot_folder_id"] = drive_root_id
                cached["drive_configured_root_id"] = configured_root_id
                cached["archive_dir"] = str(runtime_root / "rar-volumes")
                cached["rar_parts_cleanup_pending"] = (runtime_root / "rar-volumes").exists()
                print("[KaKaRoTiOS] Reusing the already reconstructed and SHA-256-verified base/update packages; RAR redownload is not needed.", flush=True)
                return cached
        except (OSError, ValueError, KeyError, TypeError):
            pass

    recovered = recover_uploaded_packages(api, drive_root_id, runtime_root,
                                          url_fingerprints, keys_path)
    if recovered is not None:
        recovered["drive_kakarot_folder_id"] = drive_root_id
        recovered["drive_configured_root_id"] = configured_root_id
        return recovered

    unrar = install_unrar()
    # Keep completed volumes and partial .part downloads across notebook retries.
    # Each partial is bound to its URL fingerprint, so a changed URL is restarted.
    rar_root = runtime_root / "rar-volumes"
    rar_root.mkdir(parents=True, exist_ok=True)
    package_dir = runtime_root / "input-packages"
    shutil.rmtree(package_dir, ignore_errors=True)
    package_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for label, urls, overrides in (
        ("BASE", base_part_urls, base_part_names),
        ("UPDATE", update_part_urls, update_part_names),
    ):
        lower = label.lower()
        volume_dir = rar_root / lower
        volume_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        for index, url in enumerate(urls, 1):
            slot = volume_dir / f"volume-{index}.download"
            record = download_blob(str(url).strip(), slot)
            downloaded.append(record)
        names = resolve_volume_names(downloaded, overrides, label)
        name_info = validate_volume_sequence(names, label)
        rar_group_bytes = sum(int(item["size"]) for item in downloaded)
        free_bytes = shutil.disk_usage(runtime_root).free
        minimum_free = int(rar_group_bytes * 2.0 + 3 * 1024**3)
        if free_bytes < minimum_free:
            fail(f"{label}: not enough Colab disk space to extract this three-volume set safely. "
                 f"{free_bytes / 2**30:.1f} GiB free; require at least {minimum_free / 2**30:.1f} GiB "
                 "(twice the downloaded RAR bytes plus 3 GiB). The downloaded volumes are retained for retry.")
        print(f"[KaKaRoTiOS] {label} disk preflight: {free_bytes / 2**30:.1f} GiB free; "
              f"{minimum_free / 2**30:.1f} GiB extraction budget.", flush=True)
        final_paths = []
        for record, name in zip(downloaded, names):
            destination = volume_dir / name
            source = Path(record["path"])
            if source.resolve() != destination.resolve():
                if destination.exists():
                    destination.unlink()
                source.replace(destination)
            final_paths.append(destination)
        # Verify there are exactly three volumes and each belongs to the expected set/order.
        for path in final_paths:
            if not is_rar_volume(path):
                fail(f"{label}: {path.name} is not a RAR volume.")
        extract_dir = rar_root / f"{lower}-extracted"
        extracted, audit = extract_rar_set(unrar, final_paths, names, extract_dir, label)
        suffix = ".xci" if audit["package_type"] == "XCI" else ".nsp"
        normalized = package_dir / f"{lower}{suffix}"
        shutil.copy2(extracted, normalized)
        if sha256_file(normalized) != audit["package_sha256"] or package_type(normalized) != audit["package_type"]:
            fail(f"{label}: normalized package copy failed its SHA-256/header check.")
        outputs[lower] = {
            "path": str(normalized),
            "name": normalized.name,
            "type": audit["package_type"],
            "size": normalized.stat().st_size,
            "sha256": sha256_file(normalized),
            "md5": md5_file(normalized),
            "archive": audit,
            "volume_scheme": name_info["scheme"],
        }
    if outputs["base"]["sha256"] == outputs["update"]["sha256"]:
        fail("Base and update packages have identical SHA-256; check that the six URLs are grouped correctly.")
    source = {
        "package_dir": str(package_dir),
        "keys_path": str(keys_path),
        "archive_dir": str(rar_root),
        "rar_parts_cleanup_pending": True,
        "input_url_fingerprints": url_fingerprints,
        "package_count": 2,
        "base": {k: v for k, v in outputs["base"].items() if k != "path"},
        "update": {k: v for k, v in outputs["update"].items() if k != "path"},
        "base_path": outputs["base"]["path"],
        "update_path": outputs["update"]["path"],
        "keys_drive_id": keys_item["id"],
        "drive_kakarot_folder_id": drive_root_id,
        "drive_configured_root_id": configured_root_id,
        "input_nsp_count": int(outputs["base"]["type"] == "NSP") + int(outputs["update"]["type"] == "NSP"),
        "input_xci_count": int(outputs["base"]["type"] == "XCI") + int(outputs["update"]["type"] == "XCI"),
    }
    source_manifest.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    total_rar = sum(x["size"] for label in ("base", "update") for x in source[label]["archive"]["rar_volumes"])
    print(f"[KaKaRoTiOS] Two RAR sets reconstructed: base {source['base']['type']} {source['base']['size']:,} bytes; update {source['update']['type']} {source['update']['size']:,} bytes.", flush=True)
    print(f"[KaKaRoTiOS] Downloaded RAR volumes total: {total_rar:,} bytes. Volumes are retained until both package files are verified on Google Drive.", flush=True)
    print("[KaKaRoTiOS] prod.keys remains local to Colab and is excluded from Drive build data.", flush=True)
    return source

def cleanup_rar_parts(source: dict) -> None:
    """Remove only downloaded RAR volumes after both reconstructed packages were uploaded and verified."""
    archive_dir = Path(source["archive_dir"])
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    source["rar_parts_cleanup_pending"] = False
    source["rar_parts_deleted_after_drive_upload"] = True
    manifest = Path(source["package_dir"]).parent / "source-manifest.json"
    if manifest.is_file():
        manifest.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print("[KaKaRoTiOS] All six downloaded RAR volumes and extraction scratch were deleted after Drive upload verification.", flush=True)
