#!/usr/bin/env python3
"""Fetch the Biomutant base/update NSPs from the dedicated biotant Drive folder."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

TITLE_ID = "01004BA017CD6000"
GAME_FOLDER_ID = "1yrL87jYVf08FGB2eWV5CY0jBp2OTHYAs"
FOLDER_MIME = "application/vnd.google-apps.folder"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_chunks import download_drive_file


def fail(reason: str) -> None:
    raise RuntimeError("[BioiOSMutant input] " + reason)


def list_children(api, parent_id: str) -> list[dict]:
    items, page_token = [], None
    while True:
        page = api.files().list(
            q=f"'{parent_id}' in parents and trashed = false",
            pageSize=1000, pageToken=page_token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        items.extend(page.get("files", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            return items


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_source(api, drive_folder_id: str, runtime_root: Path) -> dict:
    parents = list_children(api, drive_folder_id)
    game_folders = [f for f in parents if f["id"] == GAME_FOLDER_ID
                    and f.get("mimeType") == FOLDER_MIME
                    and f.get("name", "").casefold() == "biotant"]
    if len(game_folders) != 1:
        fail("Drive folder biotant not found under the configured project parent")
    children = list_children(api, GAME_FOLDER_ID)
    nsp_items = [x for x in children if x.get("mimeType") != FOLDER_MIME
                 and x["name"].lower().endswith(".nsp")]
    if sorted(x["name"].lower() for x in nsp_items) != ["base.nsp", "update.nsp"]:
        fail("biotant must contain exactly one base.nsp and one update.nsp")
    by_name = {x["name"].lower(): x for x in nsp_items}
    keys = [x for x in children + parents if x["name"].casefold() == "prod.keys"
            and x.get("mimeType") != FOLDER_MIME]
    if len(keys) != 1:
        fail("Expected exactly one prod.keys in biotant or the shared Drive parent")
    key_path = runtime_root / "keys" / "prod.keys"
    download_drive_file(api, keys[0], key_path)
    packages = runtime_root / "input-packages"
    packages.mkdir(parents=True, exist_ok=True)
    paths = {"base": packages / "000_base_biomutant.nsp",
             "update": packages / "100_update_biomutant.nsp"}
    metadata = {}
    for key in ("base", "update"):
        item = by_name[key + ".nsp"]
        path = paths[key]
        download_drive_file(api, item, path)
        with path.open("rb") as data:
            if data.read(4) != b"PFS0":
                fail(f"{key} is not a valid PFS0 NSP; refusing to process")
        metadata[key] = {"id": item["id"], "name": item["name"],
                         "size": path.stat().st_size, "sha256": sha256(path)}
    if metadata["base"]["sha256"] == metadata["update"]["sha256"]:
        fail("Base and update are identical")
    print("[BioiOSMutant] Verified base/update SHA-256:", metadata, flush=True)
    # NXNative's real package scan in prepare_linux.py checks the content title ID.
    return {"package_dir": str(packages), "keys_path": str(key_path),
            "package_count": 2, "update_nsp_count": 1, "dlc_nsp_count": 0,
            "game_folder_id": GAME_FOLDER_ID, "source_files": metadata}
