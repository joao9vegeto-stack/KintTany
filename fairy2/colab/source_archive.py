#!/usr/bin/env python3
"""Read one base, one update and 16 DLC NSPs from Drive/fairy2."""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

TITLE_ID = "0100B9801F872000"
GAME_FOLDER_ID = "1QNa5LUK7Es-evrRIAjtUVzrhGUhENn5t"
FOLDER_MIME = "application/vnd.google-apps.folder"
DLC_COUNT = 16
DLC_NAMES = [f"dlc-{i:02d}.nsp" for i in range(1, DLC_COUNT + 1)]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_chunks import download_drive_file

def fail(message):
    raise RuntimeError("[Fairy2iOS input] " + message)

def list_children(api, folder):
    items, token = [], None
    while True:
        page = api.files().list(q=f"'{folder}' in parents and trashed = false",
            pageSize=1000, pageToken=token, orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        items.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return items

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def prepare_source(api, drive_folder_id, runtime_root):
    parents = list_children(api, drive_folder_id)
    folders = [x for x in parents if x.get("id") == GAME_FOLDER_ID
        and x.get("name", "").casefold() == "fairy2"
        and x.get("mimeType") == FOLDER_MIME]
    if len(folders) != 1:
        fail("Drive/fairy2 missing from the configured project parent")
    children = list_children(api, GAME_FOLDER_ID)
    filenames = ["base.nsp", "update.nsp", *DLC_NAMES]
    files = [x for x in children if x.get("mimeType") != FOLDER_MIME
             and x.get("name", "").lower().endswith(".nsp")]
    if sorted(x["name"].lower() for x in files) != sorted(filenames):
        fail(f"Expected base/update/16 DLC NSP files; found {[x['name'] for x in files]}")
    by_name = {x["name"].lower(): x for x in files}
    local_keys = [x for x in children if x.get("name", "").casefold() == "prod.keys"
                  and x.get("mimeType") != FOLDER_MIME]
    shared_keys = [x for x in parents if x.get("name", "").casefold() == "prod.keys"
                   and x.get("mimeType") != FOLDER_MIME]
    keys = local_keys if local_keys else shared_keys
    if len(keys) != 1:
        fail("Expected exactly one prod.keys in fairy2 or shared parent")
    root = Path(runtime_root)
    key_path = root / "keys" / "prod.keys"
    download_drive_file(api, keys[0], key_path)
    nsp_dir = root / "input-packages"
    nsp_dir.mkdir(parents=True, exist_ok=True)
    records, hashes = {}, set()
    for position, name in enumerate(filenames):
        if name == "base.nsp":
            local = nsp_dir / "000_base_fairy2.nsp"
        elif name == "update.nsp":
            local = nsp_dir / "100_update_fairy2.nsp"
        else:
            local = nsp_dir / f"200_dlc_{position-1:02d}_fairy2.nsp"
        item = by_name[name]
        download_drive_file(api, item, local)
        with local.open("rb") as inp:
            if inp.read(4) != b"PFS0":
                fail(f"Invalid NSP/PFS0 file: {name}")
        digest = sha256(local)
        if digest in hashes:
            fail(f"Duplicate NSP content: {name}")
        hashes.add(digest)
        records[name] = {"id": item["id"], "name": name, 
                         "size": local.stat().st_size, "sha256": digest}
    print("[Fairy2iOS] Verified 18 unique source NSPs", flush=True)
    return {"package_dir": str(nsp_dir), "keys_path": str(key_path),
            "package_count": 18, "update_nsp_count": 1, "dlc_nsp_count": 16,
            "game_folder_id": GAME_FOLDER_ID,
            "source_files": {"base": records["base.nsp"],
                             "update": records["update.nsp"],
                             "dlcs": [records[name] for name in DLC_NAMES]}}
