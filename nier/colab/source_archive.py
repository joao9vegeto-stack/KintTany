#!/usr/bin/env python3
"""Read one base, one update and 16 DLC NSPs from Drive/nier."""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

TITLE_ID = "010056B015FE8000"
GAME_FOLDER_ID = "11udbko06i5QvX930AiwR-VQ8Lu0bP39E"
FOLDER_MIME = "application/vnd.google-apps.folder"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drive_chunks import download_drive_file

def fail(message):
    raise RuntimeError("[Nier2iOS input] " + message)

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
        and x.get("name", "").casefold() == "nier"
        and x.get("mimeType") == FOLDER_MIME]
    if len(folders) != 1:
        fail("Drive/nier missing from the configured project parent")
    children = list_children(api, GAME_FOLDER_ID)
    files = [x for x in children if x.get("mimeType") != FOLDER_MIME and x.get("name", "").lower().endswith((".nsp", ".xci"))]
    dlc_names = sorted(x["name"].lower() for x in files if x["name"].lower().startswith("dlc-") and x["name"].lower().endswith(".nsp"))
    filenames = ["base.xci", "update.nsp", *dlc_names]
    if not dlc_names or sorted(x["name"].lower() for x in files) != sorted(filenames):
        fail(f"Unexpected base/update/DLC file inventory: {[x['name'] for x in files]}")
    mods = [x for x in children if x.get("name", "").lower() == "translation.zip"]
    if len(mods) != 1: fail("Expected exactly one translation.zip")
    by_name = {x["name"].lower(): x for x in files}
    local_keys = [x for x in children if x.get("name", "").casefold() == "prod.keys"
                  and x.get("mimeType") != FOLDER_MIME]
    shared_keys = [x for x in parents if x.get("name", "").casefold() == "prod.keys"
                   and x.get("mimeType") != FOLDER_MIME]
    keys = local_keys if local_keys else shared_keys
    if len(keys) != 1:
        fail("Expected exactly one prod.keys in nier or shared parent")
    root = Path(runtime_root)
    key_path = root / "keys" / "prod.keys"
    download_drive_file(api, keys[0], key_path)
    nsp_dir = root / "input-packages"
    nsp_dir.mkdir(parents=True, exist_ok=True)
    records, hashes = {}, set()
    for position, name in enumerate(filenames):
        if name == "base.xci":
            local = nsp_dir / "000_base_nier.xci"
        elif name == "update.nsp":
            local = nsp_dir / "100_update_nier.nsp"
        else:
            local = nsp_dir / f"200_dlc_{position-1:02d}_nier.nsp"
        item = by_name[name]
        download_drive_file(api, item, local)
        with local.open("rb") as inp:
            if name.endswith(".xci"):
                inp.seek(0x100)
                if inp.read(4) != b"HEAD": fail("Invalid XCI header")
            elif inp.read(4) != b"PFS0":
                fail(f"Invalid NSP/PFS0 file: {name}")
        digest = sha256(local)
        if digest in hashes:
            fail(f"Duplicate NSP content: {name}")
        hashes.add(digest)
        records[name] = {"id": item["id"], "name": name, 
                         "size": local.stat().st_size, "sha256": digest}
    if {x.name for x in nsp_dir.iterdir() if x.suffix.lower() in (".xci", ".nsp")} != {"000_base_nier.xci", "100_update_nier.nsp", *[f"200_dlc_{i:02d}_nier.nsp" for i in range(1,len(dlc_names)+1)]}:
        fail("Stale package files in local cache")
    translation_zip = root / "translation.zip"
    download_drive_file(api, mods[0], translation_zip)
    print(f"[Nier2iOS] Verified {len(files)} unique source packages and translation ZIP", flush=True)
    return {"package_dir": str(nsp_dir), "keys_path": str(key_path),
            "package_count": len(files), "update_nsp_count": 1, "dlc_nsp_count": len(dlc_names), "translation_zip": str(translation_zip),
            "game_folder_id": GAME_FOLDER_ID,
            "source_files": {"base": records["base.xci"],
                             "update": records["update.nsp"],
                             "dlcs": [records[name] for name in dlc_names], "translation": {"id": mods[0]["id"], "name": "translation.zip", "size": translation_zip.stat().st_size, "sha256": sha256(translation_zip)}}}
