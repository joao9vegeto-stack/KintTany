#!/usr/bin/env python3
"""GitHub Actions -> Colab -> Drive: verified BioiOSMutant IPA transfer.

Read-only GitHub PAT with Actions permission is accepted via BIOMUTANT_GITHUB_TOKEN;
nothing uses the token to access the signed download CDN or logs its value.
"""
from __future__ import annotations

import concurrent.futures as futures
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "BioiOSMutant"
WORKFLOW = "biomutant.yml"
TITLE_ID = "01004BA017CD6000"
DRIVE_GAME_FOLDER = "1yrL87jYVf08FGB2eWV5CY0jBp2OTHYAs"
BLOCK = 64 * 1024 * 1024
WORKERS = 6


def require(condition, reason):
    if not condition:
        raise RuntimeError("[BioiOSMutant] " + reason)


def hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest(), md5.hexdigest()


def signed_download(url, expected_size, expected_sha, target):
    import requests
    headers = {"Accept-Encoding": "identity"}
    with requests.get(url, headers={**headers, "Range": "bytes=0-0"},
                      stream=True, timeout=(30, 180)) as probe:
        if probe.status_code == 206:
            match = re.fullmatch(r"bytes 0-0/(\d+)", probe.headers.get("Content-Range", ""))
            require(match is not None and len(next(probe.iter_content(chunk_size=1), b"")) == 1,
                    "GitHub CDN returned invalid HTTP Range probe")
            size = int(match.group(1))
            range_ok = True
        elif probe.status_code == 200:
            size = int(probe.headers.get("Content-Length") or expected_size or 0)
            range_ok = False
        else:
            probe.raise_for_status()
            raise RuntimeError("Signed ZIP endpoint returned unexpected HTTP status")
    require(size > 0 and (not expected_size or size == expected_size),
            "GitHub ZIP size does not match GitHub artifact metadata")
    temp = Path(str(target) + ".part")
    temp.unlink(missing_ok=True)
    started = time.monotonic()
    if range_ok and size >= BLOCK:
        local = threading.local()
        fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_RDWR, 0o600)
        os.ftruncate(fd, size)
        try:
            def get_range(start, end):
                length = end - start + 1
                if not hasattr(local, "http"):
                    local.http = requests.Session()
                for attempt in range(1, 6):
                    try:
                        with local.http.get(url, headers={
                                **headers, "Range": f"bytes={start}-{end}"},
                                stream=True, timeout=(30, 180)) as response:
                            require(response.status_code == 206,
                                    f"HTTP {response.status_code}: server stopped honoring ranges")
                            require(response.headers.get("Content-Range") == f"bytes {start}-{end}/{size}",
                                    f"Content-Range mismatch for {start}-{end}")
                            count = 0
                            for data in response.iter_content(chunk_size=8 * 1024 * 1024):
                                if not data:
                                    continue
                                require(count + len(data) <= length, "ZIP HTTP range exceeded declared length")
                                view, offset = memoryview(data), start + count
                                while view:
                                    wrote = os.pwrite(fd, view, offset)
                                    require(wrote > 0, "ZIP positional write failed")
                                    offset += wrote
                                    view = view[wrote:]
                                count += len(data)
                            require(count == length, f"ZIP truncated range {start}-{end}")
                            return count
                    except Exception as exc:
                        if attempt == 5:
                            raise RuntimeError(f"ZIP Range {start}-{end} failed after five attempts") from exc
                        time.sleep(min(2 ** (attempt-1), 16))
                raise RuntimeError("Unreachable")
            ranges = [(i, min(i + BLOCK, size) - 1) for i in range(0, size, BLOCK)]
            done = 0
            with futures.ThreadPoolExecutor(max_workers=min(WORKERS, len(ranges))) as pool:
                for completed in futures.as_completed([pool.submit(get_range, a, b)
                                                       for a, b in ranges]):
                    done += completed.result()
                    print(f"[BioiOSMutant] GitHub ZIP {done / size:.0%} "
                          f"({done / 2**20:.1f}/{size / 2**20:.1f} MiB), "
                          f"{done / max(time.monotonic() - started, 0.01) / 2**20:.1f} MiB/s", flush=True)
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        print("[BioiOSMutant] GitHub CDN não oferece ranges; usando stream de 8 MiB.", flush=True)
        with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with temp.open("wb") as f:
                count = 0
                for data in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if data:
                        f.write(data)
                        count += len(data)
                        if count % BLOCK < len(data):
                            print(f"[BioiOSMutant] GitHub ZIP: {count / size:.0%}", flush=True)
    require(temp.is_file() and temp.stat().st_size == size, "GitHub ZIP truncated")
    actual_sha, _ = hashes(temp)
    require(not expected_sha or actual_sha == expected_sha, "GitHub ZIP SHA-256 mismatch")
    temp.replace(target)
    print(f"[BioiOSMutant] ZIP validado: {size:,} bytes; SHA-256 {actual_sha}", flush=True)
    return actual_sha


def children(api, parent):
    records, token = [], None
    while True:
        result = api.files().list(q=f"'{parent}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum)", pageSize=1000,
            pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        records.extend(result.get("files", []))
        token = result.get("nextPageToken")
        if not token:
            return records


def upload(api, path, parent, name):
    from googleapiclient.http import MediaFileUpload
    source = Path(path)
    sha, md5 = hashes(source)
    size = source.stat().st_size
    existing = [i for i in children(api, parent) if i.get("name") == name]
    require(len(existing) <= 1, f"Drive has duplicate ambiguous files named {name}")
    if existing:
        item = existing[0]
        require(int(item.get("size") or -1) == size and
                str(item.get("md5Checksum") or "").lower() == md5,
                f"Drive has a different file with the same name: {name}")
        print(f"[BioiOSMutant] Arquivo já enviado ao Drive e verificado: {name}", flush=True)
        return {"id": item["id"], "sha256": sha, "md5": md5, "size": size}
    upload_data = MediaFileUpload(str(source), mimetype="application/octet-stream",
                                  chunksize=BLOCK, resumable=True)
    req = api.files().create(body={"name": name, "parents": [parent]},
                 media_body=upload_data, fields="id,name,size,md5Checksum", supportsAllDrives=True)
    result = None
    while result is None:
        status, result = req.next_chunk()
        if status:
            print(f"[BioiOSMutant] Upload {name}: {status.progress():.0%}", flush=True)
    require(int(result.get("size") or -1) == size and
            str(result.get("md5Checksum") or "").lower() == md5,
            f"Drive upload of {name} failed size/MD5 verification")
    print(f"[BioiOSMutant] Upload verificado: {name} ({size:,} bytes) SHA-256 {sha}", flush=True)
    return {"id": result["id"], "sha256": sha, "md5": md5, "size": size}


def main():
    import google.auth
    import requests
    from googleapiclient.discovery import build
    token = os.environ.get("BIOMUTANT_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT (Actions: Read) para KintTany")
    api_root = f"https://api.github.com/repos/{REPO}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "BioiOSMutant-GitHub-to-Drive"}

    def github_get(path, params=None):
        response = requests.get(api_root + path, headers=headers, params=params, timeout=60)
        require(response.ok, f"GitHub HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    print("[BioiOSMutant] 1/4: Último Actions bem-sucedido da branch BioiOSMutant...", flush=True)
    wid = github_get(f"/actions/workflows/{WORKFLOW}")["id"]
    selected = None
    for page in range(1, 4):
        runs = github_get(f"/actions/workflows/{wid}/runs",
                          {"branch": BRANCH, "status": "success", "page": page,
                           "per_page": 100}).get("workflow_runs", [])
        for run in runs:
            if run.get("conclusion") != "success" or run.get("head_branch") != BRANCH:
                continue
            artifacts = github_get(f"/actions/runs/{run['id']}/artifacts",
                                   {"per_page": 100}).get("artifacts", [])
            choices = [a for a in artifacts
                       if a.get("name", "").startswith("BioiOSMutant-Biomutant-")
                       and not a.get("expired")]
            if choices:
                selected = (run, max(choices, key=lambda a: a.get("created_at") or ""))
                break
        if selected or len(runs) < 100:
            break
    require(selected is not None,
            "Nenhuma IPA BioiOSMutant encontrada em run bem-sucedido. Termine o Actions primeiro.")
    run, artifact = selected
    commit = str(run["head_sha"])
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "GitHub run commit is invalid")
    print(f"[BioiOSMutant] Run {run['id']} / commit {commit} / artifact {artifact['name']}", flush=True)

    print("[BioiOSMutant] 2/4: Download GitHub ZIP por seis ranges + SHA-256...", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=headers, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308)
            and bool(response.headers.get("Location")),
            f"GitHub ZIP endpoint did not return a signed download (HTTP {response.status_code})")
    cdn_url = response.headers["Location"]
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "GitHub artifact reported invalid SHA-256")
    work = Path("/content/biomutant-ipa-transfer")
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "artifact.zip"
    zip_sha = signed_download(cdn_url, int(artifact.get("size_in_bytes") or 0),
                              expected_sha, zip_path)

    print("[BioiOSMutant] 3/4: Validando ZIP, build-report e IPA...", flush=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        require(z.testzip() is None, "Artifact ZIP CRC check failed")
        names = z.namelist()
        require(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names),
                "Artifact ZIP contains unsafe member names")
        ipa_names = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        report_names = [n for n in names if Path(n).name == "build-report.json"]
        require(len(ipa_names) == 1 and len(report_names) == 1,
                "Artifact must contain one IPA and one build-report.json")
        report = json.loads(z.read(report_names[0]))
        require(report.get("project") == BRANCH and
                report.get("title_id") == TITLE_ID and
                report.get("romfs_in_ipa") is False and
                report.get("ios_deployment_target") == "26.0",
                "Build report is not a BioiOSMutant iOS 26 thin-IPA report")
        name = Path(ipa_names[0]).name
        require(report.get("ipa") == name, "IPA and build report filenames differ")
        ipa = work / name
        with z.open(ipa_names[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    require(ipa.stat().st_size == int(report.get("ipa_size_bytes") or -1),
            "IPA length differs from the signed build-report")
    ipa_sha, _ = hashes(ipa)
    print(f"[BioiOSMutant] IPA válida: {ipa.name}, {ipa.stat().st_size:,} bytes SHA-256 {ipa_sha}", flush=True)

    print("[BioiOSMutant] 4/4: Drive biotant/ipa — upload resumable de 64 MiB...", flush=True)
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    parent = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                               fields="id,name,mimeType,trashed").execute()
    require(parent.get("name") == "biotant" and
            parent.get("mimeType") == "application/vnd.google-apps.folder" and
            not parent.get("trashed"), "The configured Drive biotant folder is invalid")
    subfolders = [a for a in children(drive, DRIVE_GAME_FOLDER)
                  if a.get("name") == "ipa" and
                  a.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subfolders) <= 1, "Duplicate Drive biotant/ipa folders")
    if subfolders:
        folder = subfolders[0]["id"]
    else:
        folder = drive.files().create(body={"name": "ipa", "parents": [DRIVE_GAME_FOLDER],
            "mimeType": "application/vnd.google-apps.folder"},
            fields="id", supportsAllDrives=True).execute()["id"]
    uploaded = upload(drive, ipa, folder, ipa.name)
    provenance = {
        "project": BRANCH, "title_id": TITLE_ID, "run_id": run["id"],
        "run_url": f"https://github.com/{REPO}/actions/runs/{run['id']}",
        "commit": commit, "artifact_id": artifact["id"], "artifact_name": artifact["name"],
        "artifact_zip_sha256": zip_sha, "artifact_zip_expected_sha256": expected_sha,
        "ipa_name": ipa.name, "ipa_size": ipa.stat().st_size, "ipa_sha256": ipa_sha,
        "drive_ipa_id": uploaded["id"], "report": report,
    }
    record = work / (ipa.stem + "-provenance.json")
    record.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    upload(drive, record, folder, record.name)
    print("[BioiOSMutant] COMPLETO. IPA e relatório de proveniência enviados e verificados.", flush=True)
    print(f"Drive: https://drive.google.com/drive/folders/{folder}", flush=True)
    print(f"Run: {provenance['run_url']}", flush=True)


if __name__ == "__main__":
    main()
