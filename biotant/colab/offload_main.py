#!/usr/bin/env python3
"""Biomutant main-only rewrite offload from Colab to a Linux Actions runner.

The private NSO is transported only through the user's Google Drive. The
public Git repository receives a file ID, hashes and non-secret metadata,
never the original game module, NSP, keys, or patched game binary.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

import requests
from googleapiclient.http import MediaFileUpload

TITLE_ID = "01004BA017CD6000"
BRANCH = "BioiOSMutant"
REPO = "joao9vegeto-stack/KintTany"
GAME_FOLDER_ID = "1yrL87jYVf08FGB2eWV5CY0jBp2OTHYAs"
ENGINE_PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
CHUNK = 64 * 1024 * 1024


def insist(value, message):
    if not value:
        raise RuntimeError("[BioiOSMutant main offload] " + message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def list_files(api, parent, name=None):
    filters = [f"'{parent}' in parents", "trashed = false"]
    if name:
        filters.append("name = '" + name.replace("'", "\\'") + "'")
    files, page = [], None
    while True:
        d = api.files().list(
            q=" and ".join(filters), pageToken=page, pageSize=1000,
            fields="nextPageToken,files(id,name,size,md5Checksum,modifiedTime,mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True
        ).execute()
        files.extend(d.get("files", []))
        page = d.get("nextPageToken")
        if not page:
            break
    return files


def folder(api, parent, name):
    d = api.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder",
              "parents": [parent]},
        fields="id", supportsAllDrives=True
    ).execute()
    return d["id"]


def upload(api, file, parent, name):
    file = Path(file)
    size = file.stat().st_size
    import hashlib as hl
    md5 = hl.md5()
    with file.open("rb") as source:
        for part in iter(lambda: source.read(8 * 1024 * 1024), b""):
            md5.update(part)
    req = api.files().create(
        body={"name": name, "parents": [parent]},
        media_body=MediaFileUpload(str(file), mimetype="application/octet-stream",
                                   resumable=True, chunksize=CHUNK),
        supportsAllDrives=True, fields="id,name,size,md5Checksum"
    )
    result = None
    while result is None:
        status, result = req.next_chunk(num_retries=5)
        if status:
            print(f"[BioiOSMutant] Upload main-only: {status.progress():.1%}", flush=True)
    insist(int(result["size"]) == size and result.get("md5Checksum") == md5.hexdigest(),
           "Drive upload size/MD5 mismatch")
    return {"id": result["id"], "name": name, "size": size,
            "sha256": sha(file), "md5": md5.hexdigest()}


def pack_zstd(staging: Path, destination: Path):
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tar", delete=False) as f:
        scratch = Path(f.name)
    try:
        with tarfile.open(scratch, "w") as archive:
            for p in sorted(staging.rglob("*")):
                if p.is_symlink():
                    raise RuntimeError("Symlinks not allowed in rewrite source")
                if p.is_file():
                    archive.add(p, arcname=p.relative_to(staging).as_posix(), recursive=False)
        subprocess.run(["zstd", "-f", "-T2", "-5", "-o", str(destination), str(scratch)],
                       check=True)
    finally:
        scratch.unlink(missing_ok=True)


def unpack_zstd(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tar", delete=False) as f:
        scratch = Path(f.name)
    try:
        with scratch.open("wb") as sink:
            subprocess.run(["zstd", "-dc", str(archive)], stdout=sink, check=True)
        with tarfile.open(scratch, "r") as tar:
            names = set()
            for entry in tar.getmembers():
                path = Path(entry.name)
                insist(not path.is_absolute() and ".." not in path.parts
                       and entry.isfile() and not entry.issym() and not entry.islnk(),
                       "Unsafe output archive member: " + entry.name)
                insist(entry.name not in names, "Duplicate output archive member")
                names.add(entry.name)
                with tar.extractfile(entry) as inp:
                    target = destination / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("wb") as out:
                        shutil.copyfileobj(inp, out)
    finally:
        scratch.unlink(missing_ok=True)


def prepare(api, *, token=None, runtime="/content/biomutant",
            repo="/content/BioiOSMutant-repo"):
    root, git = Path(runtime), Path(repo)
    work = root / "work"
    versions = [p for p in (work / "extract").glob("v[0-9]*")
                if p.is_dir() and (p / "ExeFS/main").is_file()]
    insist(len(versions) == 1, f"Exactly one selected extracted version needed: {versions}")
    version = versions[0].name
    nsomain = versions[0] / "ExeFS/main"
    part = work / ("patched_" + version + ".partial")
    state = part / ".bio-rewrite-fingerprint.json"
    insist(state.is_file(), "Previous protected rewrite checkpoint absent")
    fingerprint = json.loads(state.read_text()).get("fingerprint")
    insist(re.fullmatch(r"[0-9a-f]{64}", fingerprint or ""),
           "Invalid previous rewrite fingerprint")
    names = ("subsdk0", "sdk", "nro0")
    for name in names:
        insist((part / (name + ".patched.bin")).is_file()
               and (part / (name + ".fixups.tsv")).is_file()
               and (part / (".bio-done-" + name + ".json")).is_file(),
               f"Completed {name} checkpoint missing; not offloading.")
    record = part / "build_src.sha256"
    insist(record.is_file(), "Original rewriter dependency digest record missing")
    source_rewriter = root / "NX2Apple/engine/dm/tools/patch_nso.py"
    insist(source_rewriter.is_file(), "Current pinned rewriter missing")
    project_profile = work / "profile" / TITLE_ID
    insist((project_profile / "game.tsv").is_file(), "Game's derived profile missing")
    insist((root / "NX2Apple/.upstream-ref").read_text().strip() == ENGINE_PIN,
           "Engine pin changed")
    source_commit = subprocess.check_output(
        ["git", "-C", str(root / "NX2Apple"), "rev-parse", "HEAD"], text=True).strip()
    local_commit = subprocess.check_output(
        ["git", "-C", str(git), "rev-parse", "HEAD"], text=True).strip()
    insist(source_commit == local_commit,
           "Source checkout changed between Colab and engine; fetch branch and synchronize first")

    request_id = uuid.uuid4().hex
    folder_id = folder(api, GAME_FOLDER_ID, "main-rewrite-" + request_id[:12])
    stage = root / "main-offload-staging"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(nsomain, stage / "main.nso")
    shutil.copytree(project_profile, stage / "profile" / TITLE_ID,
                    ignore=shutil.ignore_patterns("__pycache__"))
    info = {
        "format": 1, "project": BRANCH, "branch": BRANCH, "request_id": request_id,
        "title_id": TITLE_ID, "version": version,
        "source_commit": source_commit, "engine_pin": ENGINE_PIN,
        "main_sha256": sha(nsomain), "patch_nso_sha256": sha(source_rewriter),
        "build_src_sha256": sha(record), "fingerprint": fingerprint,
        "other_modules": list(names),
        "profile_hashes": {
            x.relative_to(stage).as_posix(): sha(x)
            for x in sorted((stage / "profile").rglob("*")) if x.is_file()
        },
    }
    (stage / "input.json").write_text(json.dumps(info, indent=2) + "\n")
    archive = root / ("main-rewrite-" + request_id + ".tar.zst")
    pack_zstd(stage, archive)
    record_uploaded = upload(api, archive, folder_id, "main-input.tar.zst")
    request = {
        "format": 1, "project": BRANCH, "branch": BRANCH,
        "title_id": TITLE_ID, "version": version,
        "request_id": request_id, "folder_id": folder_id,
        "engine_pin": ENGINE_PIN, "source_commit": source_commit,
        "main_sha256": info["main_sha256"],
        "fingerprint": fingerprint,
        "archive": record_uploaded,
    }
    # Keep private game bytes out of this public repository. A GitHub push
    # contains only metadata and the Drive file ID; input remains on Drive.
    token = token or os.environ.get("BIOMUTANT_GITHUB_TOKEN", "").strip()
    if not token:
        import getpass
        token = getpass.getpass("GitHub PAT (KintTany Contents: Read/Write): ").strip()
    insist(bool(token), "GitHub PAT required to trigger this separate Linux workflow")
    url = f"https://api.github.com/repos/{REPO}/contents/biotant/main-rewrite-request.json"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json"}
    current = requests.get(url, headers=headers, params={"ref": BRANCH}, timeout=60)
    insist(current.status_code in (200, 404),
           f"GitHub request read failed HTTP {current.status_code}")
    payload = {
        "branch": BRANCH, "message": "BioiOSMutant: dispatch main-only Linux rewrite " + request_id[:12],
        "content": base64.b64encode(
            (json.dumps(request, indent=2) + "\n").encode()).decode(),
    }
    if current.status_code == 200:
        payload["sha"] = current.json()["sha"]
    published = requests.put(url, headers=headers, json=payload, timeout=90)
    insist(published.status_code in (200, 201),
           f"GitHub main rewrite request failed HTTP {published.status_code}: "
           + published.text[:900])
    (root / "main-offload-request.json").write_text(json.dumps(request, indent=2))
    print("[BioiOSMutant] Main-only Linux workflow triggered. "
          "3 restored module checkpoints remain on Colab.", flush=True)
    print("GitHub workflow: https://github.com/" + REPO
          + "/actions/workflows/biomutant-main-linux.yml", flush=True)
    print("Request:", request_id, "Drive source:", folder_id, flush=True)
    return request


def receive(api, *, runtime="/content/biomutant"):
    from source_archive import list_children
    from drive_chunks import download_drive_file
    import rewrite_guard
    root = Path(runtime)
    request_path = root / "main-offload-request.json"
    insist(request_path.is_file(), "Run main offload preparation first in this runtime")
    req = json.loads(request_path.read_text())
    prefix = "main-result-" + req["request_id"] + ".tar.zst"
    files = [x for x in list_children(api, req["folder_id"]) if x.get("name") == prefix]
    insist(files, "Main rewrite result not yet in Drive; check Linux workflow status")
    insist(len(files) == 1, "Ambiguous rewrite results; refusing to use an arbitrary file")
    item = files[0]
    target = root / prefix
    download_drive_file(api, item, target)
    received = root / "main-rewrite-result-extracted"
    if received.exists():
        shutil.rmtree(received)
    unpack_zstd(target, received)
    report = json.loads((received / "result.json").read_text())
    for key in ("project", "title_id", "request_id", "version", "engine_pin",
                "main_sha256", "fingerprint"):
        insist(report.get(key) == req.get(key), "Offload result provenance mismatch: " + key)
    work = root / "work"
    version = req["version"]
    main = work / "extract" / version / "ExeFS/main"
    part = work / ("patched_" + version + ".partial")
    insist(main.is_file() and sha(main) == req["main_sha256"],
           "Original main changed since Linux submission")
    fingerprint = json.loads((part / ".bio-rewrite-fingerprint.json").read_text()).get("fingerprint")
    insist(fingerprint == req["fingerprint"],
           "Rewrite cache fingerprint changed since Linux submission")
    original = part / "build_src.sha256"
    insist(original.is_file() and sha(original) == report["build_src_sha256"],
           "Rewriter dependency inventory drift: refusing offloaded main")
    prefix_names = {name + "." + suffix for name in ("main",) for suffix in rewrite_guard.NEEDED}
    insist(set(report.get("file_hashes", {})) == prefix_names,
           "Offload output inventory is incomplete/has unexpected entries")
    # Check every file before modifying the local cache.
    for name, digest in report["file_hashes"].items():
        insist(re.fullmatch(r"[a-f0-9]{64}", digest or "")
               and (received / name).is_file() and sha(received / name) == digest,
               "Offloaded main content checksum mismatch: " + name)
    for name in prefix_names:
        shutil.copy2(received / name, part / (name + ".returned"))
    for name in prefix_names:
        (part / (name + ".returned")).replace(part / name)
    rewrite_guard.save_module(part, "main", main, fingerprint)
    print("[BioiOSMutant] Main restored from Linux runner and SHA-256 "
          "checkpointed. Re-run Colab preparation; main will NOT be rewritten.",
          flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "receive"))
    args = parser.parse_args()
    import google.auth
    from googleapiclient.discovery import build
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    api = build("drive", "v3", credentials=creds, cache_discovery=False)
    if args.command == "prepare":
        prepare(api)
    else:
        receive(api)


if __name__ == "__main__":
    main()
