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


# Quarantined by actual A19 Pro crash log, not by CI build status.
DEVICE_CRASH_RUNS = frozenset({44990224107, 44992666178, 44995690307, 45000495987, 45046524330, 45050364099, 45056917685, 45064035915, 45075542017, 45078767146, 45083487666})
DEVICE_CRASH_SHA256 = frozenset({"6faba771ab897cec3c19277a03815e42c3428be1c6c92e522195a0133db196d1", "6b3803ac5359c724fb43781688c1e3eab7cb3b80dde723a64f73e945c0574c0c", "b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd", "df6cd6c826a3218fd965b03161ea2355cf348c13c369e13f2afb7dff74c953c2", "5f713b1a06bdf8d8fcff63bd29d69cd3a5cff280f5cd42065973919c0d81c94a", "416b9582e27cf2ca3ae4d10e2001b07ee95717c398451766b5445efc80dd3a6e", "2e771e0efa89671c9525726990329916eaa71aa9a4ee006706a2d28c4734cfec", "ef2e6edff30d0072796066d9ae46eb1be0ec27248dbec5b52b958cf001f4c22b", "2e0cbbf938cbba40e6a36be8c1d0ce9704a8502ac88557da7e62de79310c8fd5"})


# Build 45068245797 is structurally valid, but it is a speculative, untested
# 64x original-stream retry that the project owner explicitly declined to use.
# Do NOT label it a confirmed crash. Keep it out of automatic IPA selection
# until a *reference-based* fix is validated on an actual device.
USER_REJECTED_UNVERIFIED_RUNS = frozenset({45068245797})
USER_REJECTED_UNVERIFIED_SHA256 = frozenset({
    "db906123fba2a6b215da72a737d5aa2da9e241a03d5eecbc843b52a30e8ad669",
})

def reject_user_rejected_unverified(run_id, sha256=None):
    """Do not silently distribute an experimental IPA rejected by the owner."""
    require(int(run_id) not in USER_REJECTED_UNVERIFIED_RUNS and
            str(sha256 or "").lower() not in USER_REJECTED_UNVERIFIED_SHA256,
            "IPA experimental SEM validação de gameplay e expressamente "
            "recusada pelo usuário (run 45068245797). Não selecionar nem "
            "transferir automaticamente; NÃO é crash confirmado.")

def reject_confirmed_device_crash(run_id, sha256=None):
    """A structurally valid IPA can still be proven to crash on real hardware."""
    require(int(run_id) not in DEVICE_CRASH_RUNS and
            str(sha256 or "").lower() not in DEVICE_CRASH_SHA256,
            "IPA com CRASH CONFIRMADO no iPhone. A versão 6GiB do "
            "run 45000495987 aborta em main+0xbfe2a8 (Hash[0xfb9ebd24]); "
            "o run instrumentado 45046524330 confirmou G1T header-validation-failed "
            "em main+0x612120 nos dois logs do iPhone. "
            "G1S run 45056917685 e FDATA IOProbe run 45064035915 abortaram: stream 0/184, parser/factory NULL, SIGTRAP. O run 45078767146 (KTGL direct reader) foi testado duas vezes no iPhone e repetiu SIGTRAP main+0xbfe2a8 com o hash G1T 0xfb9ebd24, independentemente das otimizações gráficas; nenhuma mensagem FAIRY2_KTGL_ORIGINAL_DIRECT_READ_RECOVERED. O run 45075542017 (fallback libz) também abortou em main+0xbfe2a8 com Hash[0xfb9ebd24] em dois logs novos, sem mensagem FAIRY2_MODE4_ORIGINAL_ZLIB_RECOVERED. As 45 leituras monitoradas do FDATA no run 45064035915 completaram; o defeito está após a leitura. Não transferir builds com crash comprovado.")

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
    reject_confirmed_device_crash(newest["id"])
    reject_user_rejected_unverified(newest["id"])
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






def try_transfer_global_memory():
    """Select only the SHA-verified 6GiB iOS VA / 5GiB resource root global candidate.

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

    wf = get("/actions/workflows/fairy2-full-resource-va.yml")
    runs = get(f"/actions/workflows/{wf['id']}/runs",
               {"branch": BRANCH, "per_page": 30}).get("workflow_runs", [])
    runs = [r for r in runs if r.get("head_branch") == BRANCH]
    require(bool(runs),
            "Nenhum run do repack host-only encontrado: operação interrompida. "
            "A IPA original que crashou não é uma alternativa.")
    newest = max(runs, key=lambda r: (r.get("created_at") or "", int(r.get("id") or 0)))
    # Fail EARLY: the latest completed 6GiB build now has TWO independently
    # confirmed iPhone resource-factory traps. Do not download 1.62GiB.
    reject_confirmed_device_crash(int(newest["id"]))
    reject_user_rejected_unverified(int(newest["id"]))
    # Never fall back to any earlier device-crashing IPA.
    # A green build yields a *candidate*; the iPhone still must verify gameplay.
    require(newest.get("status") == "completed" and newest.get("conclusion") == "success",
            f"Host-only repack mais recente ainda não teve sucesso: "
            f"{newest.get('id')} ({newest.get('status')}/{newest.get('conclusion')}). "
            "Não vou selecionar a IPA antiga com crash.")
    artifacts = get(f"/actions/runs/{newest['id']}/artifacts",
                    {"per_page": 100}).get("artifacts", [])
    choices = [a for a in artifacts
               if str(a.get("name", "")).startswith("Fairy2iOS-FullResourceVA-")
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
    work = Path("/content/fairy2-full-resource-va-transfer")
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
        reports = [n for n in names if Path(n).name == "full-resource-va-report.json"]
        require(len(ipa_items) == 1 and len(reports) == 1,
                "Artifact host repack não tem uma IPA e um relatório")
        record = json.loads(zipf.read(reports[0]))
        geo = record.get("global_geometry", {})
        patch = record.get("guest_root_5g_patch", {})
        require(record.get("project") == BRANCH and
                record.get("title_id") == TITLE_ID and
                record.get("source_run_id") == 44995690307 and
                record.get("source_sha256") ==
                "b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd" and
                geo.get("guest_reserve") == 0x180000000 and
                geo.get("alias_after") == 0x158000000 and
                geo.get("heap_after") == 0x8000000 and
                geo.get("root_before") == 0x100000000 and
                geo.get("root_after") == 0x140000000 and
                geo.get("root_end") == 0x46c000000 and
                geo.get("root_free_after_initial_regions") == 0x6ae00000 and
                geo.get("no_guest_overlap") is True and
                geo.get("physical_memory_pool_unchanged") is True and
                geo.get("ktgl_child_size") == 0x80000000 and
                patch.get("old_root") == 0x100000000 and
                patch.get("new_root") == 0x140000000 and
                patch.get("trampoline_count") == 5 and
                patch.get("old_cave_all_zeros") is True and
                patch.get("x0_size", 0) > 0x2295a50 and
                patch.get("w_size", 0) > 0 and
                patch.get("x0_size", 0) + patch.get("w_size", 0) == 0x2c60000 and
                patch.get("x1_size", 0) >= 0x40000 and
                str(patch.get("code_cave", "")).startswith("main+0x") and
                0x2c80000 <= int(str(patch.get("code_cave", "main+0x0")).split("+0x")[1], 16) < 0x2d6c000 and
                len(str(patch.get("w_sha256", ""))) == 64 and
                len(patch.get("sites", [])) == 5 and
                record.get("host_recompiled") is True and
                record.get("game_shaders_recompiled") is False and
                record.get("guest_modules_rewritten") is False and
                record.get("shell_recompiled") is False and
                record.get("external_romfs_aoc_unchanged") is True and
                record.get("fps_selector") == [30, 60] and
                record.get("ab_swap_available") is True and
                record.get("device_boot_verified") is False and
                record.get("runtime_fs_trace") is True and
                record.get("runtime_resource_hash_trace") is True and
                record.get("ktgl_virtual_region_overlap_repaired") is True and
                record.get("bin47_alias_offset") == "0xc5800178",
                "Relatório não comprova os cinco stubs de 5GiB, o VA global de 6GiB e o rastreamento")
        require(record.get("metal_shader_sha256") ==
                "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b",
                "Shaders Metal modificados: recusando transferência")
        name = Path(ipa_items[0]).name
        require(name == "Fairy2iOS-FairyTail2-FullResourceVA-6GiB.ipa"
                and record.get("output_ipa") == name,
                "Nome da IPA corrigida não confere")
        ipa = work / name
        with zipf.open(ipa_items[0]) as inp, ipa.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    reject_confirmed_device_crash(newest["id"], digest)
    reject_user_rejected_unverified(newest["id"], digest)
    require(ipa.stat().st_size == int(record.get("output_ipa_size_bytes") or -1)
            and digest == record.get("output_ipa_sha256"),
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
        "source_run_id": 44995690307,
        "run_url": f"https://github.com/{REPO}/actions/runs/{newest['id']}",
        "branch_commit": newest.get("head_sha"),
        "ipa_name": destination_name, "ipa_size": ipa.stat().st_size,
        "ipa_sha256": digest, "artifact_zip_sha256": outer_sha,
        "ipa_internal_validation": details, "report": record,
        "runtime_verified_on_iphone": False,
        "release_status": "FULL_RESOURCE_VA_CANDIDATE_NOT_IPHONE_VERIFIED",
        "drive_ipa_id": uploaded["id"]
    }
    prov_file = work / ("Fairy2iOS-full-resource-va-run" + str(newest["id"]) + "-provenance.json")
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n")
    upload(drive, prov_file, folder, prov_file.name)
    print("[Fairy2iOS] CANDIDATA GLOBAL 6GiB VA / 5GiB ROOT (AINDA NÃO VALIDADA NO IPHONE):",destination_name,flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder,flush=True)
    print("Actions: " + provenance["run_url"],flush=True)
    return True







def try_transfer_g1s_reader_trace():
    """Transfer ONLY the device-untested, one-shot G1S reader-trace IPA from verified run.

    Never fall back to the crashing 6GiB/old IPA; fail before downloading if
    GitHub changed the expected run, commit, artifact or provenance.
    """
    import requests
    import google.auth
    from googleapiclient.discovery import build

    RUN_ID = 45056917685
    RUN_SHA = "825df676fe8087dd47ab84a5ea7fcf4a37e538c9"
    ARTIFACT_NAME = "Fairy2iOS-G1S-ReaderTrace-4"
    IPA_NAME = "Fairy2iOS-FairyTail2-G1S-ReaderTrace.ipa"
    SHADER_SHA = "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b"
    G1T_SHA = "558ada8c563fe44fa18d894d01f39e8b1a230b26ad1bcd0782743797f815e494"
    SOURCE_SHA = "b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd"

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "Precisa do GitHub PAT com Actions: Read")
    api_root = f"https://api.github.com/repos/{REPO}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "Fairy2iOS-G1S-ReaderTrace-Drive-Transfer"}

    def get(path, params=None):
        response = requests.get(api_root + path, headers=headers, params=params, timeout=60)
        require(response.ok, f"GitHub API HTTP {response.status_code}: {response.text[:180]}")
        return response.json()

    run = get(f"/actions/runs/{RUN_ID}")
    require(run.get("id") == RUN_ID and run.get("head_sha") == RUN_SHA and
            run.get("head_branch") == BRANCH and
            run.get("name") == "Fairy2iOS - G1S factory and stream first-read diagnosis (host-only)" and
            run.get("status") == "completed" and run.get("conclusion") == "success",
            f"Run de diagnóstico {RUN_ID} não corresponde à execução esperada ou não concluiu com sucesso")
    reject_confirmed_device_crash(RUN_ID)
    reject_user_rejected_unverified(RUN_ID)
    artifacts = get(f"/actions/runs/{RUN_ID}/artifacts", {"per_page": 100}).get("artifacts", [])
    matches = [a for a in artifacts if a.get("name") == ARTIFACT_NAME and not a.get("expired")]
    require(len(matches) == 1,
            f"Esperado exatamente um artefato {ARTIFACT_NAME}, encontrado {len(matches)}")
    artifact = matches[0]
    require(int(artifact.get("size_in_bytes") or 0) > 1500 * 1000 * 1000,
            "Artifact do G1T é pequeno demais; IPA suspeita")
    source = (artifact.get("workflow_run") or {})
    require(source.get("id") == RUN_ID and source.get("head_sha") == RUN_SHA,
            "Proveniência do artifact não coincide com o run validado")
    print(f"[Fairy2iOS] 1/4: G1T HeaderRescue — run {RUN_ID}, artifact {ARTIFACT_NAME}.", flush=True)

    response = requests.get(api_root + f"/actions/artifacts/{artifact['id']}/zip",
                            headers=headers, allow_redirects=False, timeout=60)
    require(response.status_code in (301, 302, 303, 307, 308)
            and response.headers.get("Location"),
            f"GitHub não retornou URL ZIP assinada: HTTP {response.status_code}")
    expected_zip_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(bool(re.fullmatch(r"[0-9a-f]{64}", expected_zip_sha)),
            "GitHub artifact precisa conter SHA-256 verificável")
    work = Path("/content/fairy2-g1t-branchtrace-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / f"artifact-{RUN_ID}.zip"
    print("[Fairy2iOS] 2/4: Baixando ZIP do G1T em 6 ranges e conferindo SHA-256...", flush=True)
    zip_sha = signed_download(response.headers["Location"],
              int(artifact["size_in_bytes"]), expected_zip_sha, outer)

    print("[Fairy2iOS] 3/4: Validando IPA, relatório e shaders existentes...", flush=True)
    with zipfile.ZipFile(outer) as z:
        require(z.testzip() is None, "ZIP externo do artifact corrompido")
        names = z.namelist()
        require(len(names) == len(set(names))
                and all(not Path(n).is_absolute() and ".." not in Path(n).parts
                        and "\\" not in n for n in names),
                "ZIP externo contém nomes duplicados ou caminhos inseguros")
        ipa_names = [n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        report_names = [n for n in names
                        if Path(n).name == "g1s-readertrace-report.json"]
        require(len(ipa_names) == 1 and len(report_names) == 1,
                "Artefato precisa conter exatamente 1 IPA e 1 relatório G1T")
        record = json.loads(z.read(report_names[0]))
        geo = record.get("global_geometry") or {}
        patch = record.get("guest_root_5g_patch") or {}
        require(record.get("project") == BRANCH and record.get("title_id") == TITLE_ID
                and record.get("source_run_id") == 44995690307
                and record.get("source_sha256") == SOURCE_SHA
                and record.get("output_ipa") == IPA_NAME
                and record.get("branch_trace_sites") == 18
                and len(patch.get("resource_stage_traps", [])) == 18
                and patch.get("resource_stage_trap_opcode") == "40403ed4"
                and record.get("resource_stage_trace") is True
                and record.get("not_a_gameplay_fix") is True
                and record.get("device_boot_verified") is False
                and record.get("g1t_fallback_preserved") is True
                and record.get("g1s_factory") == "main+0x1dbdc14"
                and record.get("g1s_parser") == "main+0x6e7b60"
                and record.get("g1s_hash") == "0xac9ed13e"
                and record.get("g1s_header_read") == "virtual [vtable+0x20] requests 184 bytes"
                and record.get("g1s_full_original_sha256") == "edb3bceed3c426cfe5b851d78f2e7f56168abe8ac5d6aac3a6927bdaf6e3535a"
                and record.get("host_recompiled") is True
                and record.get("game_shaders_recompiled") is False
                and record.get("guest_modules_rewritten") is False
                and record.get("external_romfs_aoc_unchanged") is True
                and record.get("metal_shader_sha256") == SHADER_SHA
                and geo.get("guest_reserve") == 0x180000000
                and geo.get("root_after") == 0x140000000
                and geo.get("ktgl_child_size") == 0x80000000
                and record.get("fps_selector") == [30, 60]
                and record.get("ab_swap_available") is True,
                "Relatório não comprova a versão G1T rastreada e a preservação dos shaders")
        name = Path(ipa_names[0]).name
        require(name == IPA_NAME, "O artifact contém IPA de outra versão")
        ipa = work / name
        with z.open(ipa_names[0]) as inp, ipa.open("wb") as dest:
            shutil.copyfileobj(inp, dest, length=8 * 1024 * 1024)
    digest, _ = hashes(ipa)
    reject_confirmed_device_crash(RUN_ID, digest)
    reject_user_rejected_unverified(RUN_ID, digest)
    require(ipa.stat().st_size == int(record.get("output_ipa_size_bytes") or -1)
            and digest == record.get("output_ipa_sha256"),
            "IPA extraída não corresponde ao SHA-256/tamanho do relatório")
    details = validate_ipa(ipa, {
        "framework": f"DmGame{TITLE_ID}.framework",
        "shader_payload": {
            "ipa_path": f"Frameworks/DmGame{TITLE_ID}.framework/msl/b-0724088d3779.img",
            "size_bytes": 2640519506
        }
    }, verify_crc=True)
    require(details["fps"] == [30, 60] and details["swap_ab"],
            "Menu 30/60 FPS e inversão A/B ausentes")

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    parent = drive.files().get(fileId=DRIVE_GAME_FOLDER, supportsAllDrives=True,
                               fields="id,name,mimeType,trashed").execute()
    require(parent.get("name") == "fairy2" and
            parent.get("mimeType") == "application/vnd.google-apps.folder"
            and not parent.get("trashed"), "Pasta fairy2 incorreta")
    subfolders = [a for a in children(drive, DRIVE_GAME_FOLDER)
                  if a.get("name") == "ipa" and
                  a.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(subfolders) <= 1, "Existem pastas fairy2/ipa duplicadas")
    if subfolders:
        folder = subfolders[0]["id"]
    else:
        folder = drive.files().create(body={"name": "ipa",
            "parents": [DRIVE_GAME_FOLDER],
            "mimeType": "application/vnd.google-apps.folder"},
            fields="id", supportsAllDrives=True).execute()["id"]
    destination_name = f"Fairy2iOS-G1S-ReaderTrace-run{RUN_ID}.ipa"
    print(f"[Fairy2iOS] 4/4: Enviando {destination_name} ao Drive fairy2/ipa...", flush=True)
    uploaded = upload(drive, ipa, folder, destination_name)

    provenance = {
        "project": BRANCH, "run_id": RUN_ID,
        "run_url": f"https://github.com/{REPO}/actions/runs/{RUN_ID}",
        "run_commit": RUN_SHA, "artifact_id": artifact["id"],
        "artifact_name": ARTIFACT_NAME, "artifact_zip_sha256": zip_sha,
        "ipa_name": destination_name, "ipa_sha256": digest,
        "ipa_size": ipa.stat().st_size, "drive_ipa_id": uploaded["id"],
        "device_tested": False, "gameplay_fix_claimed": False,
        "status": "G1S_READER_DIAGNOSTIC_NOT_DEVICE_VERIFIED",
        "ipa_validation": details, "build_report": record
    }
    prov = work / f"Fairy2iOS-G1S-ReaderTrace-run{RUN_ID}-provenance.json"
    prov.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    upload(drive, prov, folder, prov.name)
    print("[Fairy2iOS] IPA candidata G1T HeaderRescue enviada e validada:", destination_name, flush=True)
    print("Drive: https://drive.google.com/drive/folders/" + folder, flush=True)
    print("Actions: " + provenance["run_url"], flush=True)
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


def select_latest_successful_ipa_artifact(github_get, max_pages=10):
    """Find the newest produced Fairy2iOS IPA across ALL branch workflows.

    Order is from GitHub's branch-filtered run feed, not a hard-coded run,
    artifact number or one historical workflow file. A successful CI run is
    only a successful build; device-known crash builds are quarantined.
    """
    skipped_crash = []
    examined = 0
    for page in range(1, max_pages + 1):
        data = github_get("/actions/runs", {
            "branch": BRANCH, "status": "success", "per_page": 100, "page": page,
        })
        runs = data.get("workflow_runs", [])
        require(isinstance(runs, list), "GitHub Actions returned an invalid run list")
        for run in sorted(runs, key=lambda x: (
                x.get("run_started_at") or x.get("created_at") or "",
                int(x.get("id") or 0)), reverse=True):
            if not (run.get("head_branch") == BRANCH and
                    run.get("status") == "completed" and
                    run.get("conclusion") == "success" and
                    str(run.get("name") or "").startswith("Fairy2iOS")):
                continue
            rid = int(run.get("id") or 0)
            if not re.fullmatch(r"[0-9a-f]{40}", str(run.get("head_sha") or "")):
                continue
            if rid in DEVICE_CRASH_RUNS:
                skipped_crash.append(rid)
                continue
            if rid in USER_REJECTED_UNVERIFIED_RUNS:
                skipped_crash.append(rid)
                continue
            examined += 1
            artifacts = github_get(f"/actions/runs/{rid}/artifacts", {
                "per_page": 100
            }).get("artifacts", [])
            choices = []
            for a in artifacts:
                n = str(a.get("name") or "")
                if (not n.startswith("Fairy2iOS-") or
                    any(bad in n.lower() for bad in
                        ("failure", "diagnostic", "capture", "forensic",
                         "resourceorigin", "resource-origin", "audit", "logs")) or
                    a.get("expired") or int(a.get("size_in_bytes") or 0) < 100 * 1024 * 1024):
                    continue
                attached = a.get("workflow_run") or {}
                if attached and (int(attached.get("id") or 0) != rid or
                                 attached.get("head_sha") != run.get("head_sha")):
                    continue
                choices.append(a)
            if choices:
                selected = max(choices, key=lambda a: (
                    a.get("created_at") or "", int(a.get("id") or 0)))
                return run, selected, skipped_crash
        if len(runs) < 100:
            break
    raise RuntimeError(
        "[Fairy2iOS] Nenhuma IPA candidata disponível em runs bem-sucedidos "
        "da branch, ou todas as IPAs conhecidas estão em quarentena. "
        f"Execuções analisadas: {examined}; crashes ignorados: {skipped_crash}. "
        "Não vou enviar um ZIP de logs nem selecionar uma IPA sabidamente defeituosa."
    )


def verified_ipa_report(z, ipa_name):
    """Select the report linked to this exact IPA, not the first JSON in ZIP."""
    reports = []
    for n in z.namelist():
        if not n.endswith(".json") or not Path(n).name.endswith("report.json"):
            continue
        try:
            report = json.loads(z.read(n))
        except (ValueError, UnicodeDecodeError):
            continue
        if (report.get("project") == BRANCH and
            str(report.get("title_id") or "").upper() == TITLE_ID and
            (report.get("output_ipa") or report.get("ipa")) == ipa_name):
            reports.append((n, report))
    require(bool(reports),
            f"Artefato sem relatório de build para a IPA exata {ipa_name}")
    # Host repacks commonly upload full-resource-va-report.json AND a more
    # specific stage report for the *same* output IPA. Reject contradictions,
    # then use the most specific report for provenance and validation.
    sizes = {int(obj.get("output_ipa_size_bytes", obj.get("ipa_size_bytes")) or 0)
             for _, obj in reports}
    hashes_seen = {str(obj.get("output_ipa_sha256", obj.get("ipa_sha256"))).lower()
                   for _, obj in reports
                   if obj.get("output_ipa_sha256", obj.get("ipa_sha256"))}
    require(len(sizes) == 1 and next(iter(sizes)) > 100 * 1024 * 1024,
            f"Relatórios discordam do tamanho da IPA {ipa_name}")
    require(len(hashes_seen) <= 1, "Relatórios divergem no SHA-256 da mesma IPA")
    reports.sort(key=lambda item: (
        Path(item[0]).name == "build-report.json",
        Path(item[0]).name == "full-resource-va-report.json",
        -len(item[1]),
        item[0]))
    return reports[0]


def transfer_latest_successful_ipa():
    """GitHub latest successful Fairy2iOS IPA -> Drive, cryptographically checked.

    This function never rebuilds shaders or a game. CI success is deliberately
    not called a successful iPhone launch.
    """
    import requests
    import google.auth
    from googleapiclient.discovery import build

    token = os.environ.get("FAIRY2_GITHUB_TOKEN", "").strip()
    require(bool(token), "GitHub PAT com Actions: Read necessário para baixar artefatos")
    api_root = f"https://api.github.com/repos/{REPO}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Fairy2iOS-latest-successful-IPA"
    }

    def github_get(uri, params=None):
        response = requests.get(api_root + uri, headers=headers, params=params,
                                timeout=(30, 90))
        require(response.ok, f"GitHub HTTP {response.status_code}: "
                f"{response.text[:240]}")
        return response.json()

    print("[Fairy2iOS] 1/4: Buscando a última IPA válida em TODOS os workflows "
          "bem-sucedidos da branch...", flush=True)
    run, artifact, skipped = select_latest_successful_ipa_artifact(github_get)
    rid = int(run["id"])
    reject_confirmed_device_crash(rid)
    reject_user_rejected_unverified(rid)
    print(f"[Fairy2iOS] Selecionado run {rid} commit {run['head_sha']} "
          f"artefato {artifact['name']} ({artifact['size_in_bytes']:,} B).", flush=True)
    if skipped:
        print(f"[Fairy2iOS] IPAs antigas com crash comprovado ignoradas: {skipped}",
              flush=True)

    response = requests.get(
        api_root + f"/actions/artifacts/{artifact['id']}/zip",
        headers=headers, allow_redirects=False, timeout=(30, 90))
    require(response.status_code in (301, 302, 303, 307, 308) and
            response.headers.get("Location"),
            f"GitHub não forneceu URL assinada do ZIP (HTTP {response.status_code})")
    expected_zip_sha = str(artifact.get("digest") or "").removeprefix("sha256:").lower()
    require(not expected_zip_sha or bool(re.fullmatch(r"[0-9a-f]{64}", expected_zip_sha)),
            "GitHub devolveu SHA-256 inválido para o artefato")
    work = Path("/content/fairy2-latest-ipa-transfer")
    work.mkdir(parents=True, exist_ok=True)
    outer = work / f"artifact-{rid}-{artifact['id']}.zip"
    print("[Fairy2iOS] 2/4: Baixando ZIP de artefato com 6 HTTP ranges e SHA...",
          flush=True)
    zip_sha = signed_download(
        response.headers["Location"], int(artifact["size_in_bytes"]),
        expected_zip_sha, outer)

    print("[Fairy2iOS] 3/4: Extraindo SOMENTE o arquivo .ipa, validando "
          "manifesto, shaders, assinatura de conteúdo e CRC...", flush=True)
    with zipfile.ZipFile(outer) as z:
        require(z.testzip() is None, "CRC do ZIP externo não confere")
        members = z.namelist()
        require(len(members) == len(set(members)) and
                all(not Path(n).is_absolute() and ".." not in Path(n).parts
                    and "\\" not in n for n in members),
                "O artefato possui caminhos inválidos ou duplicados")
        ipa_files = [n for n in members if n.lower().endswith(".ipa") and
                     not n.endswith("/")]
        require(len(ipa_files) == 1, "Artefato não possui exatamente uma IPA")
        ipa_name = Path(ipa_files[0]).name
        report_path, report = verified_ipa_report(z, ipa_name)
        expected_size = report.get("output_ipa_size_bytes", report.get("ipa_size_bytes"))
        expected_sha = report.get("output_ipa_sha256", report.get("ipa_sha256"))
        require(expected_size and int(expected_size) > 100 * 1024 * 1024,
                "Relatório indica IPA truncada ou sem tamanho")
        require(z.getinfo(ipa_files[0]).file_size == int(expected_size),
                "IPA e relatório divergem em tamanho")
        if expected_sha:
            require(bool(re.fullmatch(r"[0-9a-f]{64}", str(expected_sha).lower())),
                    "SHA-256 de IPA inválido no relatório")
        require(report.get("romfs_in_ipa") is not True and
                report.get("external_romfs_aoc_unchanged") is not False,
                "Artefato não comprova pacote thin com RomFS externa")
        framework = f"DmGame{TITLE_ID}.framework"
        target = work / ipa_name
        with z.open(ipa_files[0]) as inp, target.open("wb") as out:
            shutil.copyfileobj(inp, out, length=8 * 1024 * 1024)

    # Inspect the actual IPA: new successful shader builds may use a different
    # hash-named image or size. Never guess an old shader filename or length.
    shader = dict(report.get("shader_payload") or {})
    if not shader.get("ipa_path") or not shader.get("size_bytes"):
        with zipfile.ZipFile(target) as inner:
            prefix = f"Payload/DmShell.app/Frameworks/{framework}/"
            matches = [m for m in inner.infolist()
                       if m.filename.startswith(prefix + "msl/")
                       and m.filename.endswith(".img")
                       and m.file_size > 64 * 1024 * 1024]
            require(len(matches) == 1,
                    "Não encontrei exatamente uma imagem Metal de shaders válida na IPA")
            shader = {"ipa_path": matches[0].filename.removeprefix(
                           "Payload/DmShell.app/"),
                      "size_bytes": matches[0].file_size}
    validate_report = {"framework": framework, "shader_payload": shader}
    sha, _ = hashes(target)
    reject_confirmed_device_crash(rid, sha)
    reject_user_rejected_unverified(rid, sha)
    require(target.stat().st_size == int(expected_size), "IPA incompleta")
    require(not expected_sha or sha == str(expected_sha).lower(),
            "SHA-256 da IPA difere do relatório de build")
    validation = validate_ipa(target, validate_report, verify_crc=True)
    require(validation["fps"] == [30, 60] and validation["swap_ab"],
            "Pacote sem o menu FPS 30/60 e inversão A/B")
    print(f"[Fairy2iOS] IPA interna real: {ipa_name} ({target.stat().st_size:,} B), "
          f"SHA-256 {sha}", flush=True)

    print("[Fairy2iOS] 4/4: Enviando a IPA extraída ao Google Drive/fairy2/ipa...",
          flush=True)
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    game_folder = drive.files().get(fileId=DRIVE_GAME_FOLDER,
                                   supportsAllDrives=True,
                                   fields="id,name,mimeType,trashed").execute()
    require(game_folder.get("name") == "fairy2" and
            game_folder.get("mimeType") == "application/vnd.google-apps.folder" and
            not game_folder.get("trashed"), "Pasta Drive fairy2 incorreta")
    folders = [x for x in children(drive, DRIVE_GAME_FOLDER)
               if x.get("name") == "ipa" and
               x.get("mimeType") == "application/vnd.google-apps.folder"]
    require(len(folders) <= 1, "Pastas /ipa duplicadas no Drive")
    folder = (folders[0]["id"] if folders else
              drive.files().create(body={"name": "ipa", "parents": [DRIVE_GAME_FOLDER],
                                         "mimeType": "application/vnd.google-apps.folder"},
                                   fields="id", supportsAllDrives=True).execute()["id"])
    dest_name = f"Fairy2iOS-run{rid}-{ipa_name}"
    uploaded = upload(drive, target, folder, dest_name)
    provenance = {
        "project": BRANCH, "title_id": TITLE_ID, "run_id": rid,
        "run_url": f"https://github.com/{REPO}/actions/runs/{rid}",
        "run_commit": run["head_sha"], "artifact_id": artifact["id"],
        "artifact_name": artifact["name"], "artifact_zip_sha256": zip_sha,
        "artifact_digest": expected_zip_sha, "report_filename": report_path,
        "ipa_name": dest_name, "ipa_sha256": sha,
        "ipa_size": target.stat().st_size, "drive_file_id": uploaded["id"],
        "device_tested": False, "gameplay_fix_claimed": False,
        "build_succeeded": True, "runtime_status": "NOT_DEVICE_VERIFIED",
        "ipa_validation": validation, "build_report": report,
    }
    prov = work / f"{dest_name}-provenance.json"
    prov.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    upload(drive, prov, folder, prov.name)
    print(f"[Fairy2iOS] Concluído: {dest_name}\n"
          f"Drive: https://drive.google.com/drive/folders/{folder}\n"
          f"Actions: {provenance['run_url']}\n"
          "AVISO: build bem-sucedido não significa jogo funcionando no iPhone.",
          flush=True)
    return provenance

def main():
    """Always discover newest valid Fairy2iOS IPA across successful branch runs."""
    return transfer_latest_successful_ipa()


if __name__ == "__main__":
    main()
