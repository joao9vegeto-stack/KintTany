#!/usr/bin/env python3
"""GitHub Actions -> Colab -> Drive: verified Fairy2iOS IPA transfer.

Read-only GitHub PAT with Actions permission is accepted via FAIRY2_GITHUB_TOKEN;
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
from ipa_validator import validate_ipa

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "Fairy2iOS"
WORKFLOW = "fairy2.yml"
TITLE_ID = "0100B9801F872000"
DRIVE_GAME_FOLDER = "1QNa5LUK7Es-evrRIAjtUVzrhGUhENn5t"
BLOCK = 64 * 1024 * 1024
WORKERS = 6


def require(condition, reason):
    if not condition:
        raise RuntimeError("[Fairy2iOS] " + reason)


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
                    print(f"[Fairy2iOS] GitHub ZIP {done / size:.0%} "
                          f"({done / 2**20:.1f}/{size / 2**20:.1f} MiB), "
                          f"{done / max(time.monotonic() - started, 0.01) / 2**20:.1f} MiB/s", flush=True)
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        print("[Fairy2iOS] GitHub CDN não oferece ranges; usando stream de 8 MiB.", flush=True)
        with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with temp.open("wb") as f:
                count = 0
                for data in response.iter_content(chunk_size=8 * 1024 * 1024):
                    if data:
                        f.write(data)
                        count += len(data)
                        if count % BLOCK < len(data):
                            print(f"[Fairy2iOS] GitHub ZIP: {count / size:.0%}", flush=True)
    require(temp.is_file() and temp.stat().st_size == size, "GitHub ZIP truncated")
    actual_sha, _ = hashes(temp)
    require(not expected_sha or actual_sha == expected_sha, "GitHub ZIP SHA-256 mismatch")
    temp.replace(target)
    print(f"[Fairy2iOS] ZIP validado: {size:,} bytes; SHA-256 {actual_sha}", flush=True)
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
        print(f"[Fairy2iOS] Arquivo já enviado ao Drive e verificado: {name}", flush=True)
        return {"id": item["id"], "sha256": sha, "md5": md5, "size": size}
    upload_data = MediaFileUpload(str(source), mimetype="application/octet-stream",
                                  chunksize=BLOCK, resumable=True)
    req = api.files().create(body={"name": name, "parents": [parent]},
                 media_body=upload_data, fields="id,name,size,md5Checksum", supportsAllDrives=True)
    result = None
    while result is None:
        status, result = req.next_chunk()
        if status:
            print(f"[Fairy2iOS] Upload {name}: {status.progress():.0%}", flush=True)
    require(int(result.get("size") or -1) == size and
            str(result.get("md5Checksum") or "").lower() == md5,
            f"Drive upload of {name} failed size/MD5 verification")
    print(f"[Fairy2iOS] Upload verificado: {name} ({size:,} bytes) SHA-256 {sha}", flush=True)
    return {"id": result["id"], "sha256": sha, "md5": md5, "size": size}


def try_transfer_host_repack():
    """Select the NEWEST host-only repack, never silently re-upload the crashing base IPA.

    Does not trigger a build or download any game/ROMFS content.
    """
    import requests
    from googleapiclient.discovery import build
    import google.auth
    from ipa_validator import validate_ipa

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT com permissão Actions: Read")
    api_root = f"https://api.github.com/repos/{REPO}"
    auth = {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Fairy2iOS-Host-Repack-Transfer"}
    def get(url, params=None):
        res = requests.get(api_root + url, headers=auth, params=params, timeout=60)
        require(res.ok, f"GitHub HTTP {res.status_code}: {res.text[:160]}")
        return res.json()

    wf = get("/actions/workflows/fairy2-host-repack.yml")
    runs = get(f"/actions/workflows/{wf['id']}/runs",
               {"branch": BRANCH, "per_page": 30}).get("workflow_runs", [])
    runs = [r for r in runs if r.get("head_branch") == BRANCH]
    require(bool(runs),
            "Nenhum run do repack host-only encontrado: operação interrompida. "
            "A IPA original que crashou não é uma alternativa.")
    newest = max(runs, key=lambda r: (r.get("created_at") or "", int(r.get("id") or 0)))
    require(newest.get("status") == "completed" and newest.get("conclusion") == "success",
            f"Host-only repack mais recente ainda não teve sucesso: "
            f"{newest.get('id')} ({newest.get('status')}/{newest.get('conclusion')}). "
            "Não vou selecionar a IPA antiga com crash.")
    artifacts = get(f"/actions/runs/{newest['id']}/artifacts",
                    {"per_page": 100}).get("artifacts", [])
    choices = [a for a in artifacts
               if str(a.get("name", "")).startswith("Fairy2iOS-host-memory-repack-")
               and not a.get("expired")]
    require(len(choices) == 1,
            f"Run {newest['id']} precisa conter exatamente um artefato IPA de host repack")
    artifact = choices[0]
    print(f"[Fairy2iOS] 1/4: Run correto {newest['id']} / commit {newest.get('head_sha')} "
          f"/ artifact {artifact['name']}", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=auth, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308) and
            response.headers.get("Location"),
            f"GitHub não forneceu link ZIP assinado (HTTP {response.status_code})")
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "Artifact digest inválido")
    work = Path("/content/fairy2-host-repack-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / ("artifact-" + str(newest["id"]) + ".zip")
    print("[Fairy2iOS] 2/4: Baixando ZIP do host repack, 6 ranges + SHA-256...", flush=True)
    outer_sha = signed_download(response.headers["Location"],
                 int(artifact.get("size_in_bytes") or 0), expected_sha, outer)
    print("[Fairy2iOS] 3/4: Extraindo/verificando IPA do host repack e relatório...", flush=True)
    with zipfile.ZipFile(outer) as zipf:
        require(zipf.testzip() is None, "ZIP externo do host repack corrompido")
        names=zipf.namelist()
        require(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names),
                "Caminho inseguro no artifact")
        ipa_items = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        reports = [n for n in names if Path(n).name == "host-repack-report.json"]
        require(len(ipa_items) == 1 and len(reports) == 1,
                "Artifact host repack não tem uma IPA e um relatório")
        record = json.loads(zipf.read(reports[0]))
        require(record.get("project") == BRANCH and
                record.get("source_run_id") == 44965722551 and
                record.get("method", "").startswith("HookLink2iOS") and
                record.get("host_recompiled") is True and
                record.get("game_shaders_recompiled") is False and
                record.get("guest_modules_rewritten") is False and
                record.get("shared_shell_recompiled") is False and
                record.get("external_romfs_aoc_unchanged") is True and
                record.get("heap_region_after_bytes") == 1073741824,
                "Relatório da IPA não confirma o repack seletivo correto")
        require(record.get("metal_shader_sha256") ==
                "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b",
                "Shader Metal não é o original reutilizado")
        name = Path(ipa_items[0]).name
        require(name == "Fairy2iOS-FairyTail2-host-memory-repack.ipa"
                and record.get("output_ipa") == name,
                "Nome da IPA corrigida não confere")
        ipa = work / name
        with zipf.open(ipa_items[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    require(ipa.stat().st_size == int(record.get("output_size_bytes") or -1)
            and digest == record.get("output_sha256"),
            "IPA extraída diverge de size/SHA-256 do relatório host repack")
    original_report = {
        "framework": f"DmGame{TITLE_ID}.framework",
        "shader_payload": {
            "ipa_path": f"Frameworks/DmGame{TITLE_ID}.framework/msl/b-0724088d3779.img",
            "size_bytes": 2640519506
        }
    }
    details = validate_ipa(ipa, original_report, verify_crc=True)
    require(details["fps"] == [30, 60] and details["swap_ab"],
            "Configurações 30/60 FPS / A-B ausentes")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    root = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                             fields="id,name,mimeType,trashed").execute()
    require(root.get("name") == "fairy2" and
            root.get("mimeType") == "application/vnd.google-apps.folder" and
            not root.get("trashed"), "Pasta Drive fairy2 incorreta")
    subs = [x for x in children(drive, DRIVE_GAME_FOLDER)
            if x.get("name") == "ipa"
            and x.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subs) == 1, "Pasta fairy2/ipa não encontrada ou ambígua")
    folder = subs[0]["id"]
    destination_name = ipa.stem + "-run" + str(newest["id"]) + ".ipa"
    print("[Fairy2iOS] 4/4: Upload validado para fairy2/ipa...", flush=True)
    uploaded = upload(drive, ipa, folder, destination_name)
    provenance = {
        "project": BRANCH, "run_id": newest["id"], "artifact_id": artifact["id"],
        "source_run_id": 44965722551,
        "run_url": f"https://github.com/{REPO}/actions/runs/{newest['id']}",
        "branch_commit": newest.get("head_sha"),
        "ipa_name": destination_name, "ipa_size": ipa.stat().st_size,
        "ipa_sha256": digest, "artifact_zip_sha256": outer_sha,
        "ipa_internal_validation": details, "report": record,
        "drive_ipa_id": uploaded["id"]
    }
    prov_file = work / ("Fairy2iOS-host-repack-run" + str(newest["id"]) + "-provenance.json")
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n")
    upload(drive, prov_file, folder, prov_file.name)
    print("[Fairy2iOS] HOST REPACK verificado e enviado:",destination_name,flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder,flush=True)
    print("Actions: " + provenance["run_url"],flush=True)
    return True


def try_transfer_region_cut():
    """Select the NEWEST five-instruction AArch64 region cut repack, never silently re-upload the crashing base IPA.

    Does not trigger a build or download any game/ROMFS content.
    """
    import requests
    from googleapiclient.discovery import build
    import google.auth
    from ipa_validator import validate_ipa

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT com permissão Actions: Read")
    api_root = f"https://api.github.com/repos/{REPO}"
    auth = {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Fairy2iOS-Host-Repack-Transfer"}
    def get(url, params=None):
        res = requests.get(api_root + url, headers=auth, params=params, timeout=60)
        require(res.ok, f"GitHub HTTP {res.status_code}: {res.text[:160]}")
        return res.json()

    wf = get("/actions/workflows/fairy2-region-repack.yml")
    runs = get(f"/actions/workflows/{wf['id']}/runs",
               {"branch": BRANCH, "per_page": 30}).get("workflow_runs", [])
    runs = [r for r in runs if r.get("head_branch") == BRANCH]
    require(bool(runs),
            "Nenhum run do repack host-only encontrado: operação interrompida. "
            "A IPA original que crashou não é uma alternativa.")
    newest = max(runs, key=lambda r: (r.get("created_at") or "", int(r.get("id") or 0)))
    require(newest.get("status") == "completed" and newest.get("conclusion") == "success",
            f"Host-only repack mais recente ainda não teve sucesso: "
            f"{newest.get('id')} ({newest.get('status')}/{newest.get('conclusion')}). "
            "Não vou selecionar a IPA antiga com crash.")
    artifacts = get(f"/actions/runs/{newest['id']}/artifacts",
                    {"per_page": 100}).get("artifacts", [])
    choices = [a for a in artifacts
               if str(a.get("name", "")).startswith("Fairy2iOS-3GiB-region-cut-")
               and not a.get("expired")]
    require(len(choices) == 1,
            f"Run {newest['id']} precisa conter exatamente um artefato IPA de host repack")
    artifact = choices[0]
    print(f"[Fairy2iOS] 1/4: Run correto {newest['id']} / commit {newest.get('head_sha')} "
          f"/ artifact {artifact['name']}", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=auth, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308) and
            response.headers.get("Location"),
            f"GitHub não forneceu link ZIP assinado (HTTP {response.status_code})")
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "Artifact digest inválido")
    work = Path("/content/fairy2-region-cut-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / ("artifact-" + str(newest["id"]) + ".zip")
    print("[Fairy2iOS] 2/4: Baixando ZIP do host repack, 6 ranges + SHA-256...", flush=True)
    outer_sha = signed_download(response.headers["Location"],
                 int(artifact.get("size_in_bytes") or 0), expected_sha, outer)
    print("[Fairy2iOS] 3/4: Extraindo/verificando IPA do host repack e relatório...", flush=True)
    with zipfile.ZipFile(outer) as zipf:
        require(zipf.testzip() is None, "ZIP externo do host repack corrompido")
        names=zipf.namelist()
        require(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names),
                "Caminho inseguro no artifact")
        ipa_items = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        reports = [n for n in names if Path(n).name == "region-cut-report.json"]
        require(len(ipa_items) == 1 and len(reports) == 1,
                "Artifact host repack não tem uma IPA e um relatório")
        record = json.loads(zipf.read(reports[0]))
        require(record.get("project") == BRANCH and
                record.get("title_id") == TITLE_ID and
                record.get("source_run_id") == 44977592488 and
                record.get("native_host_recompiled") is False and
                record.get("game_shaders_recompiled") is False and
                record.get("guest_modules_rewritten") is False and
                record.get("romfs_aoc_external_unchanged") is True and
                record.get("allocator_original_bytes") == 0xf00000000 and
                record.get("allocator_patched_bytes") == 0xc0000000 and
                record.get("alias_region_bytes") == 0xe0000000 and
                record.get("guest_main_instruction_patches") == 5 and
                len(record.get("guest_main_patch_audit", {}).get("changes", [])) == 5 and
                record.get("crash_fixed_on_iphone_verified") is False,
                "Relatório não comprova a correção binária das cinco instruções")
        require(record.get("game_shader_sha256") ==
                "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b",
                "Shaders Metal não são idênticos aos originais")
        name = Path(ipa_items[0]).name
        require(name == "Fairy2iOS-FairyTail2-3GiB-region-cut.ipa"
                and record.get("output_ipa") == name,
                "Nome da IPA corrigida não confere")
        ipa = work / name
        with zipf.open(ipa_items[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    require(ipa.stat().st_size == int(record.get("output_size_bytes") or -1)
            and digest == record.get("output_sha256"),
            "IPA extraída diverge de size/SHA-256 do relatório host repack")
    original_report = {
        "framework": f"DmGame{TITLE_ID}.framework",
        "shader_payload": {
            "ipa_path": f"Frameworks/DmGame{TITLE_ID}.framework/msl/b-0724088d3779.img",
            "size_bytes": 2640519506
        }
    }
    details = validate_ipa(ipa, original_report, verify_crc=True)
    require(details["fps"] == [30, 60] and details["swap_ab"],
            "Configurações 30/60 FPS / A-B ausentes")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    root = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                             fields="id,name,mimeType,trashed").execute()
    require(root.get("name") == "fairy2" and
            root.get("mimeType") == "application/vnd.google-apps.folder" and
            not root.get("trashed"), "Pasta Drive fairy2 incorreta")
    subs = [x for x in children(drive, DRIVE_GAME_FOLDER)
            if x.get("name") == "ipa"
            and x.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subs) == 1, "Pasta fairy2/ipa não encontrada ou ambígua")
    folder = subs[0]["id"]
    destination_name = ipa.stem + "-run" + str(newest["id"]) + ".ipa"
    print("[Fairy2iOS] 4/4: Upload validado para fairy2/ipa...", flush=True)
    uploaded = upload(drive, ipa, folder, destination_name)
    provenance = {
        "project": BRANCH, "run_id": newest["id"], "artifact_id": artifact["id"],
        "source_run_id": 44977592488,
        "run_url": f"https://github.com/{REPO}/actions/runs/{newest['id']}",
        "branch_commit": newest.get("head_sha"),
        "ipa_name": destination_name, "ipa_size": ipa.stat().st_size,
        "ipa_sha256": digest, "artifact_zip_sha256": outer_sha,
        "ipa_internal_validation": details, "report": record,
        "drive_ipa_id": uploaded["id"]
    }
    prov_file = work / ("Fairy2iOS-region-cut-run" + str(newest["id"]) + "-provenance.json")
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n")
    upload(drive, prov_file, folder, prov_file.name)
    print("[Fairy2iOS] PATCH DE REGIÃO verificado e enviado:",destination_name,flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder,flush=True)
    print("Actions: " + provenance["run_url"],flush=True)
    return True



def try_transfer_heap128():
    """Select the NEWEST five-instruction AArch64 region cut repack, never silently re-upload the crashing base IPA.

    Does not trigger a build or download any game/ROMFS content.
    """
    import requests
    from googleapiclient.discovery import build
    import google.auth
    from ipa_validator import validate_ipa

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT com permissão Actions: Read")
    api_root = f"https://api.github.com/repos/{REPO}"
    auth = {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Fairy2iOS-Host-Repack-Transfer"}
    def get(url, params=None):
        res = requests.get(api_root + url, headers=auth, params=params, timeout=60)
        require(res.ok, f"GitHub HTTP {res.status_code}: {res.text[:160]}")
        return res.json()

    wf = get("/actions/workflows/fairy2-heap128-repack.yml")
    runs = get(f"/actions/workflows/{wf['id']}/runs",
               {"branch": BRANCH, "per_page": 30}).get("workflow_runs", [])
    runs = [r for r in runs if r.get("head_branch") == BRANCH]
    require(bool(runs),
            "Nenhum run do repack host-only encontrado: operação interrompida. "
            "A IPA original que crashou não é uma alternativa.")
    newest = max(runs, key=lambda r: (r.get("created_at") or "", int(r.get("id") or 0)))
    require(newest.get("status") == "completed" and newest.get("conclusion") == "success",
            f"Host-only repack mais recente ainda não teve sucesso: "
            f"{newest.get('id')} ({newest.get('status')}/{newest.get('conclusion')}). "
            "Não vou selecionar a IPA antiga com crash.")
    artifacts = get(f"/actions/runs/{newest['id']}/artifacts",
                    {"per_page": 100}).get("artifacts", [])
    choices = [a for a in artifacts
               if str(a.get("name", "")).startswith("Fairy2iOS-128MiB-heap-repack-")
               and not a.get("expired")]
    require(len(choices) == 1,
            f"Run {newest['id']} precisa conter exatamente um artefato IPA de host repack")
    artifact = choices[0]
    print(f"[Fairy2iOS] 1/4: Run correto {newest['id']} / commit {newest.get('head_sha')} "
          f"/ artifact {artifact['name']}", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=auth, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308) and
            response.headers.get("Location"),
            f"GitHub não forneceu link ZIP assinado (HTTP {response.status_code})")
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "Artifact digest inválido")
    work = Path("/content/fairy2-heap128-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / ("artifact-" + str(newest["id"]) + ".zip")
    print("[Fairy2iOS] 2/4: Baixando ZIP do host repack, 6 ranges + SHA-256...", flush=True)
    outer_sha = signed_download(response.headers["Location"],
                 int(artifact.get("size_in_bytes") or 0), expected_sha, outer)
    print("[Fairy2iOS] 3/4: Extraindo/verificando IPA do host repack e relatório...", flush=True)
    with zipfile.ZipFile(outer) as zipf:
        require(zipf.testzip() is None, "ZIP externo do host repack corrompido")
        names=zipf.namelist()
        require(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names),
                "Caminho inseguro no artifact")
        ipa_items = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        reports = [n for n in names if Path(n).name == "heap128-report.json"]
        require(len(ipa_items) == 1 and len(reports) == 1,
                "Artifact host repack não tem uma IPA e um relatório")
        record = json.loads(zipf.read(reports[0]))
        audit = record.get("heap_instruction_audit", {})
        require(record.get("project") == BRANCH and
                record.get("title_id") == TITLE_ID and
                record.get("source_run_id") == 44980090949 and
                record.get("heap_before_bytes") == 0x1400000 and
                record.get("heap_after_bytes") == 0x8000000 and
                audit.get("offset") == "main+0x2295a88" and
                audit.get("old_opcode") == "1328a052" and
                audit.get("new_opcode") == "1300a152" and
                audit.get("byte_changes") == 2 and
                record.get("five_region_cut_movs_preserved") is True and
                record.get("native_host_recompiled") is False and
                record.get("game_shaders_recompiled") is False and
                record.get("romfs_aoc_external_unchanged") is True and
                record.get("crash_fixed_on_iphone_verified") is False,
                "Relatório não confirma o repack de heap 128 MiB/uma instrução")
        require(record.get("game_shader_sha256") ==
                "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b",
                "Biblioteca Metal mudou no repack; recusando download")
        name = Path(ipa_items[0]).name
        require(name == "Fairy2iOS-FairyTail2-128MiB-heap-repack.ipa"
                and record.get("output_ipa") == name,
                "Nome da IPA corrigida não confere")
        ipa = work / name
        with zipf.open(ipa_items[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    require(ipa.stat().st_size == int(record.get("output_size_bytes") or -1)
            and digest == record.get("output_sha256"),
            "IPA extraída diverge de size/SHA-256 do relatório host repack")
    original_report = {
        "framework": f"DmGame{TITLE_ID}.framework",
        "shader_payload": {
            "ipa_path": f"Frameworks/DmGame{TITLE_ID}.framework/msl/b-0724088d3779.img",
            "size_bytes": 2640519506
        }
    }
    details = validate_ipa(ipa, original_report, verify_crc=True)
    require(details["fps"] == [30, 60] and details["swap_ab"],
            "Configurações 30/60 FPS / A-B ausentes")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    root = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                             fields="id,name,mimeType,trashed").execute()
    require(root.get("name") == "fairy2" and
            root.get("mimeType") == "application/vnd.google-apps.folder" and
            not root.get("trashed"), "Pasta Drive fairy2 incorreta")
    subs = [x for x in children(drive, DRIVE_GAME_FOLDER)
            if x.get("name") == "ipa"
            and x.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subs) == 1, "Pasta fairy2/ipa não encontrada ou ambígua")
    folder = subs[0]["id"]
    destination_name = ipa.stem + "-run" + str(newest["id"]) + ".ipa"
    print("[Fairy2iOS] 4/4: Upload validado para fairy2/ipa...", flush=True)
    uploaded = upload(drive, ipa, folder, destination_name)
    provenance = {
        "project": BRANCH, "run_id": newest["id"], "artifact_id": artifact["id"],
        "source_run_id": 44980090949,
        "run_url": f"https://github.com/{REPO}/actions/runs/{newest['id']}",
        "branch_commit": newest.get("head_sha"),
        "ipa_name": destination_name, "ipa_size": ipa.stat().st_size,
        "ipa_sha256": digest, "artifact_zip_sha256": outer_sha,
        "ipa_internal_validation": details, "report": record,
        "drive_ipa_id": uploaded["id"]
    }
    prov_file = work / ("Fairy2iOS-heap128-run" + str(newest["id"]) + "-provenance.json")
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n")
    upload(drive, prov_file, folder, prov_file.name)
    print("[Fairy2iOS] HEAP 128 MiB verificado e enviado:",destination_name,flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder,flush=True)
    print("Actions: " + provenance["run_url"],flush=True)
    return True





def try_transfer_align64():
    """Select the NEWEST five-instruction AArch64 region cut repack, never silently re-upload the crashing base IPA.

    Does not trigger a build or download any game/ROMFS content.
    """
    import requests
    from googleapiclient.discovery import build
    import google.auth
    from ipa_validator import validate_ipa

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT com permissão Actions: Read")
    api_root = f"https://api.github.com/repos/{REPO}"
    auth = {"Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Fairy2iOS-Host-Repack-Transfer"}
    def get(url, params=None):
        res = requests.get(api_root + url, headers=auth, params=params, timeout=60)
        require(res.ok, f"GitHub HTTP {res.status_code}: {res.text[:160]}")
        return res.json()

    wf = get("/actions/workflows/fairy2-align64-repack.yml")
    runs = get(f"/actions/workflows/{wf['id']}/runs",
               {"branch": BRANCH, "per_page": 30}).get("workflow_runs", [])
    runs = [r for r in runs if r.get("head_branch") == BRANCH]
    require(bool(runs),
            "Nenhum run do repack host-only encontrado: operação interrompida. "
            "A IPA original que crashou não é uma alternativa.")
    newest = max(runs, key=lambda r: (r.get("created_at") or "", int(r.get("id") or 0)))
    require(newest.get("status") == "completed" and newest.get("conclusion") == "success",
            f"Host-only repack mais recente ainda não teve sucesso: "
            f"{newest.get('id')} ({newest.get('status')}/{newest.get('conclusion')}). "
            "Não vou selecionar a IPA antiga com crash.")
    artifacts = get(f"/actions/runs/{newest['id']}/artifacts",
                    {"per_page": 100}).get("artifacts", [])
    choices = [a for a in artifacts
               if str(a.get("name", "")).startswith("Fairy2iOS-KTGL-64KiB-alignment-")
               and not a.get("expired")]
    require(len(choices) == 1,
            f"Run {newest['id']} precisa conter exatamente um artefato IPA de host repack")
    artifact = choices[0]
    print(f"[Fairy2iOS] 1/4: Run correto {newest['id']} / commit {newest.get('head_sha')} "
          f"/ artifact {artifact['name']}", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=auth, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308) and
            response.headers.get("Location"),
            f"GitHub não forneceu link ZIP assinado (HTTP {response.status_code})")
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "Artifact digest inválido")
    work = Path("/content/fairy2-align64-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / ("artifact-" + str(newest["id"]) + ".zip")
    print("[Fairy2iOS] 2/4: Baixando ZIP do host repack, 6 ranges + SHA-256...", flush=True)
    outer_sha = signed_download(response.headers["Location"],
                 int(artifact.get("size_in_bytes") or 0), expected_sha, outer)
    print("[Fairy2iOS] 3/4: Extraindo/verificando IPA do host repack e relatório...", flush=True)
    with zipfile.ZipFile(outer) as zipf:
        require(zipf.testzip() is None, "ZIP externo do host repack corrompido")
        names=zipf.namelist()
        require(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in names),
                "Caminho inseguro no artifact")
        ipa_items = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        reports = [n for n in names if Path(n).name == "align64-report.json"]
        require(len(ipa_items) == 1 and len(reports) == 1,
                "Artifact host repack não tem uma IPA e um relatório")
        record = json.loads(zipf.read(reports[0]))
        audit = record.get("arena_alignment_instruction_audit", {})
        require(record.get("project") == BRANCH and
                record.get("title_id") == TITLE_ID and
                record.get("source_run_id") == 44981941022 and
                record.get("alloc_alignment_before_bytes") == 16 and
                record.get("alloc_alignment_after_bytes") == 65536 and
                audit.get("offset") == "main+0x21b6a74" and
                audit.get("old_opcode") == "02028052" and
                audit.get("new_opcode") == "2200a052" and
                audit.get("byte_changes") == 3 and
                record.get("heap128_mib_patch_preserved") is True and
                record.get("five_region_cut_movs_preserved") is True and
                record.get("native_host_recompiled") is False and
                record.get("game_shaders_recompiled") is False and
                record.get("romfs_aoc_external_unchanged") is True and
                record.get("crash_fixed_on_iphone_verified") is False,
                "Relatório não confirma a correção da alocação KTGL (64 KiB) sem shaders")
        require(record.get("game_shader_sha256") ==
                "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b",
                "Biblioteca Metal mudou no repack; recusando download")
        name = Path(ipa_items[0]).name
        require(name == "Fairy2iOS-FairyTail2-64KiB-aligned-allocator.ipa"
                and record.get("output_ipa") == name,
                "Nome da IPA corrigida não confere")
        ipa = work / name
        with zipf.open(ipa_items[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    require(ipa.stat().st_size == int(record.get("output_size_bytes") or -1)
            and digest == record.get("output_sha256"),
            "IPA extraída diverge de size/SHA-256 do relatório host repack")
    original_report = {
        "framework": f"DmGame{TITLE_ID}.framework",
        "shader_payload": {
            "ipa_path": f"Frameworks/DmGame{TITLE_ID}.framework/msl/b-0724088d3779.img",
            "size_bytes": 2640519506
        }
    }
    details = validate_ipa(ipa, original_report, verify_crc=True)
    require(details["fps"] == [30, 60] and details["swap_ab"],
            "Configurações 30/60 FPS / A-B ausentes")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    root = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                             fields="id,name,mimeType,trashed").execute()
    require(root.get("name") == "fairy2" and
            root.get("mimeType") == "application/vnd.google-apps.folder" and
            not root.get("trashed"), "Pasta Drive fairy2 incorreta")
    subs = [x for x in children(drive, DRIVE_GAME_FOLDER)
            if x.get("name") == "ipa"
            and x.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subs) == 1, "Pasta fairy2/ipa não encontrada ou ambígua")
    folder = subs[0]["id"]
    destination_name = ipa.stem + "-run" + str(newest["id"]) + ".ipa"
    print("[Fairy2iOS] 4/4: Upload validado para fairy2/ipa...", flush=True)
    uploaded = upload(drive, ipa, folder, destination_name)
    provenance = {
        "project": BRANCH, "run_id": newest["id"], "artifact_id": artifact["id"],
        "source_run_id": 44981941022,
        "run_url": f"https://github.com/{REPO}/actions/runs/{newest['id']}",
        "branch_commit": newest.get("head_sha"),
        "ipa_name": destination_name, "ipa_size": ipa.stat().st_size,
        "ipa_sha256": digest, "artifact_zip_sha256": outer_sha,
        "ipa_internal_validation": details, "report": record,
        "drive_ipa_id": uploaded["id"]
    }
    prov_file = work / ("Fairy2iOS-align64-run" + str(newest["id"]) + "-provenance.json")
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n")
    upload(drive, prov_file, folder, prov_file.name)
    print("[Fairy2iOS] ALINHAMENTO 64 KiB verificado e enviado:",destination_name,flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder,flush=True)
    print("Actions: " + provenance["run_url"],flush=True)
    return True





def transfer_original_explicit():
    """Legacy first-build transfer, not selected by the current notebook."""
    import google.auth
    import requests
    from googleapiclient.discovery import build
    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa de GitHub PAT (Actions: Read) para KintTany")
    api_root = f"https://api.github.com/repos/{REPO}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "Fairy2iOS-GitHub-to-Drive"}

    def github_get(path, params=None):
        response = requests.get(api_root + path, headers=headers, params=params, timeout=60)
        require(response.ok, f"GitHub HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    print("[Fairy2iOS] 1/4: Último Actions bem-sucedido da branch Fairy2iOS...", flush=True)
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
                       if a.get("name", "").startswith("Fairy2iOS-FairyTail2-")
                       and not a.get("expired")]
            if choices:
                selected = (run, max(choices, key=lambda a: a.get("created_at") or ""))
                break
        if selected or len(runs) < 100:
            break
    require(selected is not None,
            "Nenhuma IPA Fairy2iOS encontrada em run bem-sucedido. Termine o Actions primeiro.")
    run, artifact = selected
    commit = str(run["head_sha"])
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "GitHub run commit is invalid")
    print(f"[Fairy2iOS] Run {run['id']} / commit {commit} / artifact {artifact['name']}", flush=True)

    print("[Fairy2iOS] 2/4: Download GitHub ZIP por seis ranges + SHA-256...", flush=True)
    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=headers, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308)
            and bool(response.headers.get("Location")),
            f"GitHub ZIP endpoint did not return a signed download (HTTP {response.status_code})")
    cdn_url = response.headers["Location"]
    expected_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_sha)),
            "GitHub artifact reported invalid SHA-256")
    work = Path("/content/fairy2-ipa-transfer")
    work.mkdir(parents=True, exist_ok=True)
    zip_path = work / "artifact.zip"
    zip_sha = signed_download(cdn_url, int(artifact.get("size_in_bytes") or 0),
                              expected_sha, zip_path)

    print("[Fairy2iOS] 3/4: Validando ZIP, build-report e IPA...", flush=True)
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
                "Build report is not a Fairy2iOS iOS 26 thin-IPA report")
        name = Path(ipa_names[0]).name
        require(report.get("ipa") == name, "IPA and build report filenames differ")
        ipa = work / name
        with z.open(ipa_names[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    require(ipa.stat().st_size == int(report.get("ipa_size_bytes") or -1),
            "IPA length differs from the signed build-report")
    ipa_sha, _ = hashes(ipa)
    validation = validate_ipa(ipa, report, verify_crc=True)
    print(f"[Fairy2iOS] IPA interna verificada: Payload/{validation['app']}, "
          f"{validation['framework']}, shaders, CRC ZIP, 30/60 FPS e troca A/B.", flush=True)
    print(f"[Fairy2iOS] IPA válida: {ipa.name}, {ipa.stat().st_size:,} bytes SHA-256 {ipa_sha}", flush=True)

    print("[Fairy2iOS] 4/4: Drive fairy2/ipa — upload resumable de 64 MiB...", flush=True)
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    parent = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                               fields="id,name,mimeType,trashed").execute()
    require(parent.get("name") == "fairy2" and
            parent.get("mimeType") == "application/vnd.google-apps.folder" and
            not parent.get("trashed"), "The configured Drive fairy2 folder is invalid")
    subfolders = [a for a in children(drive, DRIVE_GAME_FOLDER)
                  if a.get("name") == "ipa" and
                  a.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subfolders) <= 1, "Duplicate Drive fairy2/ipa folders")
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
        "drive_ipa_id": uploaded["id"], "ipa_md5": uploaded["md5"],
        "ipa_internal_validation": validation, "report": report,
    }
    record = work / (ipa.stem + "-provenance.json")
    record.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    upload(drive, record, folder, record.name)
    print("[Fairy2iOS] COMPLETO. IPA e relatório de proveniência enviados e verificados.", flush=True)
    print(f"Drive: https://drive.google.com/drive/folders/{folder}", flush=True)
    print(f"Run: {provenance['run_url']}", flush=True)


def main():
    """Only newest guarded 64KiB KTGL arena repack; no fallback to crashing IPAs."""
    selected=try_transfer_align64()
    require(selected is True,"Novo repack KTGL 64 KiB indisponível; todas as IPAs antigas bloqueadas.")
    return selected


if __name__ == "__main__":
    main()
