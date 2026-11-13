#!/usr/bin/env python3
"""Linux/Colab intake + RomFS preparation for HookLink2iOS."""
from __future__ import annotations
import base64, email.message, hashlib, json, os, re, shutil, subprocess, sys, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit
import requests
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "HookLink2iOS"
WORKFLOW_NAME = "HookLink2iOS Ocarina native build"
HANDOFF = "hooklink2ios/handoff.json"
WORKFLOW_NAME = "HookLink2iOS Ocarina native build"
ENGINE = "https://github.com/dsi-hub/nxnative.git"
ENGINE_PIN = "cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
TITLE_ID = "0400486024DEC000"
VERSION = 131072
GPU = "g18p"  # HookLink documented offline Metal pipeline archive for A19 / iPhone 17 Pro.
CHUNK = 64 * 1024 * 1024
FOLDER = "application/vnd.google-apps.folder"

def drive_execute(request, label="Google Drive API", retries=12):
    """Retry transient Drive API failures (429/5xx) with exponential backoff."""
    for attempt in range(retries + 1):
        try:
            return request.execute(num_retries=0)
        except HttpError as exc:
            status=int(getattr(exc.resp, "status", 0) or 0)
            if status not in (408, 429, 500, 502, 503, 504) or attempt >= retries:
                raise
            delay=min(90, 2 ** min(attempt + 1, 6))
            print(f"[HookLink2iOS] {label}: HTTP {status}; nova tentativa "
                  f"{attempt + 1}/{retries} em {delay}s.", flush=True)
            time.sleep(delay)
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError) as exc:
            if attempt >= retries:
                raise
            delay=min(90, 2 ** min(attempt + 1, 6))
            print(f"[HookLink2iOS] {label}: conexão instável; nova tentativa "
                  f"{attempt + 1}/{retries} em {delay}s ({type(exc).__name__}).", flush=True)
            time.sleep(delay)

def run(cmd, cwd=None):
    print("[HookLink2iOS] $", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(list(map(str,cmd)), cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace")
    print(p.stdout, end="", flush=True)
    if p.returncode:
        raise RuntimeError(f"Comando falhou ({p.returncode}): {cmd[0]}")
    return p.stdout

def file_hashes(path):
    path=Path(path)
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    total=path.stat().st_size
    last_report=0
    print(f"[HookLink2iOS] Calculando SHA-256/MD5: {path.name} ({total:,} bytes)",flush=True)
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(16*1024*1024),b""):
            sha.update(block); md5.update(block); size += len(block)
            if size-last_report >= 1024*1024*1024 or size==total:
                print(f"[HookLink2iOS] Hash {path.name}: {size/total*100:.1f}% ({size:,}/{total:,} bytes)",flush=True)
                last_report=size
    return {"size":size,"sha256":sha.hexdigest(),"md5":md5.hexdigest()}

def safe_name(name):
    name = Path(unquote(str(name))).name.strip()
    if not name or name in (".",".."): raise ValueError("Nome de arquivo inválido.")
    return re.sub(r"[^A-Za-z0-9._ -]","_",name)

def source_key(url):
    parsed=urlsplit(url.strip())
    if parsed.scheme.lower()!="https" or not parsed.netloc or not parsed.path:
        raise ValueError("Forneça uma URL HTTPS completa.")
    stable=f"https://{parsed.netloc.lower()}{parsed.path}"
    return hashlib.sha256(stable.encode()).hexdigest()

def download_url(url, dst):
    if not url.startswith("https://"): raise ValueError("A origem precisa usar HTTPS.")
    dst.parent.mkdir(parents=True,exist_ok=True)
    part=dst.with_name(dst.name+".part"); total=last=0
    with requests.get(url,stream=True,allow_redirects=True,timeout=(30,180),
        headers={"User-Agent":"HookLink2iOS-Colab/2.0","Accept-Encoding":"identity"}) as r:
        r.raise_for_status()
        disposition=r.headers.get("Content-Disposition","")
        if not disposition:
            disposition=parse_qs(urlsplit(url).query).get("response-content-disposition",[""])[0]
        msg=email.message.Message()
        if disposition: msg["content-disposition"]=disposition
        filename=msg.get_filename() or Path(unquote(urlsplit(url).path)).name
        filename=safe_name(filename)
        target=dst.parent/filename
        expected=int(r.headers.get("content-length") or 0)
        with part.open("wb") as out:
            for block in r.iter_content(8*1024*1024):
                if not block: continue
                out.write(block); total+=len(block)
                if total-last>=512*1024*1024:
                    print(f"[HookLink2iOS] Download {total:,}/{expected or '?'} bytes",flush=True); last=total
        if total<4 or (expected and total!=expected):
            raise ValueError(f"Download incompleto: {total:,}/{expected or '?'} bytes.")
    part.replace(target)
    h=file_hashes(target)
    print(f"[HookLink2iOS] Download concluído: {filename} | {h['size']:,} bytes | SHA-256 {h['sha256']}")
    return target,filename,h

def download_drive_source(drive, file_id, dst):
    meta = drive.files().get(fileId=file_id,fields="id,name,size,mimeType",supportsAllDrives=True).execute()
    if meta.get("mimeType")==FOLDER: raise ValueError("O ID aponta para uma pasta, não um arquivo.")
    part=dst.with_name(dst.name+".part"); dst.parent.mkdir(parents=True,exist_ok=True)
    req=drive.files().get_media(fileId=file_id,supportsAllDrives=True)
    with part.open("wb") as out:
        dl=MediaIoBaseDownload(out,req,chunksize=CHUNK); done=False
        while not done:
            status,done=dl.next_chunk(num_retries=8)
            if status: print(f"[HookLink2iOS] Drive download {status.progress()*100:.1f}%",flush=True)
    if int(meta.get("size") or 0) and part.stat().st_size != int(meta["size"]):
        part.unlink(missing_ok=True); raise ValueError("Tamanho do arquivo no Drive não confere.")
    part.replace(dst)
    return meta["name"]

def extract_archive(archive,dest):
    if not shutil.which("bsdtar"): raise RuntimeError("bsdtar ausente; instale libarchive-tools no Colab.")
    listing=run(["bsdtar","-tf",archive])
    entries=[x.strip() for x in listing.splitlines() if x.strip()]
    if not entries: raise ValueError("Arquivo compactado vazio.")
    for raw in entries:
        norm=raw.replace("\\","/")
        member=PurePosixPath(norm)
        if member.is_absolute() or re.match(r"^[A-Za-z]:",norm) or ".." in member.parts:
            raise ValueError(f"Caminho inseguro no arquivo: {raw}")
    verbose=run(["bsdtar","-tvf",archive])
    for line in verbose.splitlines():
        mode=line.split(maxsplit=1)[0] if line.split() else ""
        if mode.startswith(("l","h")): raise ValueError("Arquivo contém link simbólico/duro; extração recusada.")
    shutil.rmtree(dest,ignore_errors=True); dest.mkdir(parents=True)
    run(["bsdtar","-xf",archive,"-C",dest])
    nups=sorted(p for p in dest.rglob("*") if p.is_file() and p.suffix.lower()==".nup")
    if len(nups)!=1:
        raise ValueError(f"Esperado exatamente um NUP no arquivo; encontrados {len(nups)}.")
    return nups[0]

def clone_engine(dest):
    shutil.rmtree(dest,ignore_errors=True); dest.parent.mkdir(parents=True,exist_ok=True)
    run(["git","init",dest]); run(["git","-C",dest,"remote","add","origin",ENGINE])
    run(["git","-C",dest,"fetch","--depth","1","origin",ENGINE_PIN])
    run(["git","-C",dest,"checkout","--detach","FETCH_HEAD"])
    sha=subprocess.check_output(["git","-C",dest,"rev-parse","HEAD"],text=True).strip()
    if sha!=ENGINE_PIN: raise RuntimeError(f"nxnative pin divergente: {sha}")

def ensure_folder(drive,parent,name):
    qname=name.replace("'","\\'")
    res=drive.files().list(q=f"'{parent}' in parents and name = '{qname}' and mimeType = '{FOLDER}' and trashed = false",
        spaces="drive",pageSize=100,fields="files(id,name,webViewLink)",supportsAllDrives=True,
        includeItemsFromAllDrives=True).execute(num_retries=5)
    if res.get("files"): return res["files"][0]
    return drive.files().create(body={"name":name,"mimeType":FOLDER,"parents":[parent]},
        fields="id,name,webViewLink",supportsAllDrives=True).execute(num_retries=5)

def upload(drive,path,parent,name,app_properties=None,description=None,precomputed_hashes=None):
    h=precomputed_hashes or file_hashes(path)
    body={"name":name,"parents":[parent]}
    if app_properties: body["appProperties"]={str(k):str(v) for k,v in app_properties.items()}
    if description: body["description"]=description[:25000]
    media=MediaFileUpload(str(path),mimetype="application/octet-stream",chunksize=CHUNK,resumable=True)
    req=drive.files().create(body=body,media_body=media,
        fields="id,name,size,md5Checksum,webViewLink,description,appProperties",supportsAllDrives=True)
    item=None
    failures=0
    while item is None:
        try:
            status,item=req.next_chunk(num_retries=8)
            failures=0
            if status: print(f"[HookLink2iOS] Drive upload {name}: {status.progress()*100:.1f}%",flush=True)
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError) as exc:
            failures += 1
            if failures > 12:
                raise RuntimeError(
                    f"Upload interrompido após {failures} tentativas; o arquivo local foi preservado: {path}"
                ) from exc
            delay=min(60, 2 ** min(failures, 6))
            print(f"[HookLink2iOS] Conexão Drive caiu durante {name}; retomando a sessão "
                  f"({failures}/12) em {delay}s...", flush=True)
            time.sleep(delay)
    if int(item.get("size",-1))!=h["size"] or str(item.get("md5Checksum","")).lower()!=h["md5"]:
        raise RuntimeError(f"Upload Drive falhou na verificação: {name}")
    return {"id":item["id"],"name":name,**h,"web_view_url":item.get("webViewLink")}

def list_children(drive,folder_id):
    out=[]; token=None
    while True:
        res=drive.files().list(q=f"'{folder_id}' in parents and trashed = false",
            spaces="drive",pageSize=100,pageToken=token,
            fields="nextPageToken,files(id,name,size,md5Checksum,appProperties,webViewLink)",
            supportsAllDrives=True,includeItemsFromAllDrives=True).execute(num_retries=5)
        out.extend(res.get("files",[])); token=res.get("nextPageToken")
        if not token: return out

def find_cached_nup(drive,folder_id,key):
    matches=[x for x in list_children(drive,folder_id)
        if (x.get("appProperties") or {}).get("hooklink2ios_source_key")==key
        and x.get("name","").lower().endswith(".nup")]
    return matches[0] if matches else None

def download_verified_nup(drive,record,destination):
    meta=drive.files().get(fileId=record["id"],fields="id,name,size,md5Checksum",supportsAllDrives=True).execute()
    part=destination.with_name(destination.name+".part")
    req=drive.files().get_media(fileId=record["id"],supportsAllDrives=True)
    with part.open("wb") as out:
        dl=MediaIoBaseDownload(out,req,chunksize=CHUNK); done=False
        while not done:
            status,done=dl.next_chunk(num_retries=8)
            if status: print(f"[HookLink2iOS] Drive → Colab {record['name']}: {status.progress()*100:.1f}%",flush=True)
    h=file_hashes(part)
    expected=(record.get("appProperties") or {}).get("hooklink2ios_nup_sha256","")
    if int(meta.get("size",-1))!=h["size"] or (expected and h["sha256"]!=expected):
        part.unlink(missing_ok=True); raise RuntimeError("NUP no Drive falhou na verificação SHA/size.")
    part.replace(destination)
    return {"id":record["id"],"name":record["name"],**h,"web_view_url":record.get("webViewLink")}

def publish(token,handoff):
    if not token: raise ValueError("GitHub PAT obrigatório.")
    url=f"https://api.github.com/repos/{REPO}/contents/{HANDOFF}"
    headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json",
             "X-GitHub-Api-Version":"2022-11-28","User-Agent":"HookLink2iOS-Colab"}
    old=requests.get(url,params={"ref":BRANCH},headers=headers,timeout=60)
    body={"message":f"HookLink2iOS handoff {handoff['request_id']}",
        "content":base64.b64encode(json.dumps(handoff,indent=2).encode()).decode(),"branch":BRANCH}
    if old.status_code==200: body["sha"]=old.json()["sha"]
    elif old.status_code!=404: raise RuntimeError(f"Não foi possível ler handoff atual (HTTP {old.status_code}).")
    r=requests.put(url,headers=headers,json=body,timeout=60)
    if r.status_code not in (200,201): raise RuntimeError(f"GitHub recusou handoff (HTTP {r.status_code}): {r.text[:500]}")
    c=r.json().get("commit",{})
    return {"commit_sha":c.get("sha"),"commit_url":c.get("html_url"),
            "actions_url":f"https://github.com/{REPO}/actions"}

def prepare(*,source_url,drive_parent_folder_id,drive,github_token,repo_root,
            work_root=Path("/content/hooklink2ios-work")):
    if sys.version_info<(3,12): raise RuntimeError("Python 3.12+ obrigatório.")
    key=source_key(source_url); request_id=str(uuid.uuid4())
    inp=work_root/"input"; extracted=work_root/"unpacked"
    engine=work_root/"nxnative"; build=work_root/"linux-build"
    inp.mkdir(parents=True,exist_ok=True); work_root.mkdir(parents=True,exist_ok=True)
    parent=drive_execute(drive.files().get(fileId=drive_parent_folder_id,fields="id,mimeType",supportsAllDrives=True), "consulta da pasta raiz")
    if parent.get("mimeType")!=FOLDER: raise ValueError("DRIVE_FOLDER_ID não é uma pasta.")
    project=ensure_folder(drive,drive_parent_folder_id,"HookLink2iOS")
    inputs=ensure_folder(drive,project["id"],"Inputs")
    cached=find_cached_nup(drive,inputs["id"],key)
    nup=inp/"game.nup"; archive=None; archive_extracted=False; source_filename=""
    # Recuperação local: se a sessão anterior caiu durante o upload, reutiliza o NUP
    # já extraído em /content e não baixa nem extrai novamente o arquivo de origem.
    local_sources=[p for p in inp.iterdir() if p.is_file() and p.name not in
        ("game.nup","game.nup.part") and not p.name.endswith(".part")]
    if nup.is_file() and nup.stat().st_size>0:
        source_filename=local_sources[0].name if local_sources else "recuperado-local.nup"
        archive_extracted = (
            Path(source_filename).suffix.lower() in
            (".rar", ".zip", ".7z", ".tar", ".tgz", ".gz", ".xz", ".bz2")
        )
        print(f"[HookLink2iOS] NUP LOCAL RECUPERADO: {nup.stat().st_size:,} bytes; sem download/extração.")
        nh=file_hashes(nup)
        cache_name=f"{Path(source_filename).stem[:55]}_{key[:10]}.nup"
        nup_item=upload(drive,nup,inputs["id"],cache_name,
            app_properties={"hooklink2ios_source_key":key,"hooklink2ios_nup_sha256":nh["sha256"],
                "hooklink2ios_source_filename":source_filename[:120],
                "hooklink2ios_archive_extracted":str(archive_extracted).lower()},
            description=f"HookLink2iOS input cache | source={source_filename} | key={key} | sha256={nh['sha256']}",
            precomputed_hashes=nh)
        for candidate in local_sources:
            candidate.unlink(missing_ok=True)
        print("[HookLink2iOS] NUP local persistido e verificado no Drive.")
    elif cached:
        print("[HookLink2iOS] CACHE HIT: NUP já está no Drive; ignorando o download externo.")
        nup_item=download_verified_nup(drive,cached,nup)
        source_filename=(cached.get("appProperties") or {}).get("hooklink2ios_source_filename",cached["name"])
        archive_extracted=(cached.get("appProperties") or {}).get("hooklink2ios_archive_extracted")=="true"
    else:
        source,source_filename,_=download_url(source_url,inp/"source")
        ext=Path(source_filename).suffix.lower()
        is_archive=ext in (".rar",".zip",".7z",".tar",".tgz",".gz",".xz",".bz2") or source_filename.lower().endswith((".tar.gz",".tar.xz",".tar.zst",".tar.bz2"))
        if ext==".nup":
            if source.resolve()!=nup.resolve(): shutil.copy2(source,nup)
        elif is_archive:
            extracted_nup=extract_archive(source,extracted)
            shutil.copy2(extracted_nup,nup); archive=source; archive_extracted=True
        else:
            raise ValueError(f"Formato {ext} não suportado; esperado .nup/.rar/.zip/.7z ou tar compactado.")
        nh=file_hashes(nup)
        cache_name=f"{Path(source_filename).stem[:55]}_{key[:10]}.nup"
        nup_item=upload(drive,nup,inputs["id"],cache_name,
            app_properties={"hooklink2ios_source_key":key,"hooklink2ios_nup_sha256":nh["sha256"],
                "hooklink2ios_source_filename":source_filename[:120],
                "hooklink2ios_archive_extracted":str(archive_extracted).lower()},
            description=f"HookLink2iOS input cache | source={source_filename} | key={key} | sha256={nh['sha256']}")
        # Keep the validated NUP on Drive; discard the source archive only after upload verification.
        if source.exists() and source.resolve()!=nup.resolve(): source.unlink()
        shutil.rmtree(extracted,ignore_errors=True)
        print("[HookLink2iOS] NUP persistido e verificado em HookLink2iOS/Inputs.")
    if not nup.is_file() or not nup.stat().st_size: raise RuntimeError("NUP ausente após download/cache.")
    clone_engine(engine)
    out=run([sys.executable,engine/"scripts/pack_nup.py",nup,"--version",str(VERSION),"--work-dir",build],cwd=engine)
    if f"{TITLE_ID} version {VERSION}" not in out: raise ValueError("Title ID/update não corresponde ao alvo; handoff cancelado.")
    romfs=build/"extract"/f"v{VERSION}"/"RomFS.img"
    if not romfs.is_file() or not romfs.stat().st_size: raise RuntimeError("RomFS.img não foi criado.")
    identity=run([sys.executable,engine/"dm/tools/romfs_image.py","--identity",romfs,TITLE_ID,f"v{VERSION}",ENGINE_PIN]).strip().splitlines()[-1]
    overlay=work_root/"res_overlay"/"Pack"/"Bootup.Nin_Ounce_NVN2.pack.zs"
    overlay.parent.mkdir(parents=True,exist_ok=True)
    run([sys.executable,repo_root/"hooklink/Resources/tools/hl_resolution.py",engine,romfs,overlay,"0.75","95"])
    if not overlay.is_file() or not overlay.stat().st_size: raise RuntimeError("Overlay não foi gerado.")
    runfolder=drive.files().create(body={"name":f"HookLink2iOS-{request_id}","mimeType":FOLDER,"parents":[project["id"]]},
        fields="id,name,webViewLink",supportsAllDrives=True).execute()
    romfs_item=upload(drive,romfs,runfolder["id"],"romfs.img")
    overlay_item=upload(drive,overlay,runfolder["id"],"Bootup.Nin_Ounce_NVN2.pack.zs")
    handoff={"schema":2,"project":"HookLink2iOS","branch":BRANCH,"request_id":request_id,
        "title_id":TITLE_ID,"package_version":f"v{VERSION}","package_version_number":VERSION,
        "gpu_arch":GPU,"engine":{"repository":ENGINE,"branch":"hooklink","commit":ENGINE_PIN},
        "source":{"filename":source_filename,"url_fingerprint":key,"archive_extracted":archive_extracted,
                  "archive_deleted_after_extraction":archive_extracted},
        "drive":{"parent_folder_id":drive_parent_folder_id,"project_folder_id":project["id"],
            "inputs_folder_id":inputs["id"],"run_folder_id":runfolder["id"],"run_folder_url":runfolder.get("webViewLink")},
        "nup":nup_item,"romfs":{**romfs_item,"identity":identity},"resolution_overlay":overlay_item,
        "builder":{"platform":"ios","romfs_mode":"separate","runner":"xcode-27","xcode":"27.2.0"},
        "created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    pushed=publish(github_token,handoff)
    print("[HookLink2iOS] Handoff publicado somente em HookLink2iOS; commit:",pushed["commit_sha"])
    return {"handoff":handoff,"github":pushed}

def github_headers(token):
    if not token: raise ValueError("GitHub PAT obrigatório.")
    return {"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28","User-Agent":"HookLink2iOS-Colab"}

def github_get(session,url,params=None):
    r=session.get(url,params=params,timeout=(30,120))
    if not r.ok: raise RuntimeError(f"GitHub API HTTP {r.status_code}: {r.text[:800]}")
    return r.json()

def recover_current_handoff(*,github_token,source_url):
    key=source_key(source_url); session=requests.Session(); session.headers.update(github_headers(github_token))
    url=f"https://api.github.com/repos/{REPO}/contents/{HANDOFF}"
    r=session.get(url,params={"ref":BRANCH},timeout=(30,90))
    if r.status_code==404: return None
    if not r.ok: raise RuntimeError(f"Leitura do handoff falhou: HTTP {r.status_code}: {r.text[:800]}")
    h=json.loads(base64.b64decode(r.json()["content"]).decode("utf-8"))
    if h.get("project")!="HookLink2iOS" or h.get("branch")!=BRANCH or h.get("source",{}).get("url_fingerprint")!=key: return None
    commits=github_get(session,f"https://api.github.com/repos/{REPO}/commits",
        {"sha":BRANCH,"path":HANDOFF,"per_page":1})
    if not commits: raise RuntimeError("Commit do handoff não foi encontrado.")
    handoff_commit=commits[0]["sha"]
    runs=github_get(session,f"https://api.github.com/repos/{REPO}/actions/runs",
        {"branch":BRANCH,"event":"push","per_page":100,"page":1}).get("workflow_runs",[])
    matching=[x for x in runs if x.get("head_sha")==handoff_commit
        and x.get("head_branch")==BRANCH and (
            str(x.get("path","")).endswith("hooklink2ios.yml")
            or WORKFLOW_NAME.lower() in str(x.get("name","")).lower()
        )]
    existing_run=sorted(matching,key=lambda x:x.get("id",0),reverse=True)[0] if matching else None
    return {"handoff":h,"commit_sha":handoff_commit,
        "commit_url":f"https://github.com/{REPO}/commit/{handoff_commit}",
        "actions_url":(existing_run or {}).get("html_url",f"https://github.com/{REPO}/actions"),
        "existing_run":existing_run}

def verify_handoff_drive_assets(drive,h):
    for key in ("nup","romfs","resolution_overlay"):
        rec=h[key]
        remote=drive.files().get(fileId=rec["id"],fields="id,size,md5Checksum",supportsAllDrives=True).execute()
        if int(remote.get("size",-1))!=int(rec["size"]): raise RuntimeError(f"{key} size diverge no Drive.")
        if rec.get("md5") and remote.get("md5Checksum","").lower()!=rec["md5"].lower(): raise RuntimeError(f"{key} MD5 diverge no Drive.")

def wait_for_actions_artifact(*,github_token,expected_commit,timeout_seconds=21600,poll_seconds=30):
    session=requests.Session(); session.headers.update(github_headers(github_token))
    url=f"https://api.github.com/repos/{REPO}/actions/runs"; deadline=time.time()+timeout_seconds; run_data=None
    while time.time()<deadline:
        payload=github_get(session,url,{"branch":BRANCH,"event":"push","per_page":100,"page":1})
        matches=[x for x in payload.get("workflow_runs",[]) if x.get("head_sha")==expected_commit
            and x.get("head_branch")==BRANCH and (
                str(x.get("path","")).endswith("hooklink2ios.yml")
                or WORKFLOW_NAME.lower() in str(x.get("name","")).lower()
            )]
        if matches:
            run_data=sorted(matches,key=lambda x:x.get("id",0),reverse=True)[0]
            print("[HookLink2iOS] Actions run",run_data["run_number"],run_data.get("status"),run_data.get("html_url"),flush=True)
            if run_data.get("status")=="completed": break
        else: print("[HookLink2iOS] Aguardando workflow do commit",expected_commit,flush=True)
        time.sleep(poll_seconds)
    if not run_data or run_data.get("status")!="completed": raise TimeoutError("Workflow não concluiu no limite de espera.")
    if run_data.get("conclusion")!="success": raise RuntimeError(f"Workflow {run_data.get('conclusion')}: {run_data.get('html_url')}")
    artifacts=github_get(session,run_data["artifacts_url"],{"per_page":100,"page":1}).get("artifacts",[])
    name=f"HookLink2iOS-Ocarina-{run_data['run_number']}"
    found=[x for x in artifacts if x.get("name")==name and not x.get("expired")]
    if len(found)!=1: raise RuntimeError(f"Artifact {name} ausente/expirado.")
    return {"run":run_data,"artifact":found[0],"headers":dict(session.headers)}

def download_artifact_zip_resumable(*,session,url,artifact,destination,chunk_bytes=512*1024*1024):
    """Download a GitHub artifact with byte-range resume, reacquiring signed redirects after failures."""
    expected=int(artifact.get("size_in_bytes") or 0)
    if expected<=0: raise RuntimeError("GitHub não informou o tamanho do artifact; download recusado.")
    raw_digest=str(artifact.get("digest") or "")
    expected_sha=raw_digest.split(":",1)[-1].lower()
    if not re.fullmatch(r"[0-9a-f]{64}",expected_sha):
        raise RuntimeError("GitHub não informou um SHA-256 válido para o artifact.")
    part=destination.with_name(destination.name+".part")
    if part.exists() and part.stat().st_size>expected: part.unlink()
    failures=0; last_report=0
    while not part.exists() or part.stat().st_size<expected:
        offset=part.stat().st_size if part.exists() else 0
        end=min(offset+chunk_bytes-1,expected-1)
        try:
            # Re-request the API redirect every chunk/retry; signed blob URLs can expire.
            redirect=session.get(url,headers={"Accept":"application/vnd.github+json"},
                allow_redirects=False,timeout=(30,120))
            if redirect.status_code in (301,302,303,307,308):
                blob_url=redirect.headers.get("Location")
                if not blob_url: raise RuntimeError("GitHub devolveu redirect de artifact sem Location.")
            elif redirect.status_code==200 and offset==0:
                blob_url=url
            else:
                redirect.raise_for_status()
                raise RuntimeError(f"Resposta inesperada da API de artifact: HTTP {redirect.status_code}.")
            headers={"Accept-Encoding":"identity","Range":f"bytes={offset}-{end}"}
            with requests.get(blob_url,headers=headers,stream=True,allow_redirects=True,
                              timeout=(30,240)) as response:
                if response.status_code==206:
                    content_range=response.headers.get("Content-Range","")
                    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",content_range)
                    if not match: raise RuntimeError(f"Content-Range inválido no artifact: {content_range!r}")
                    start,end_actual,total=map(int,match.groups())
                    if start!=offset or end_actual<start or end_actual>end or total!=expected:
                        raise RuntimeError(f"Content-Range inconsistente no artifact: {content_range!r}")
                    expected_chunk=end_actual-start+1
                    mode="ab" if offset else "wb"
                elif response.status_code==200 and offset==0:
                    expected_chunk=expected
                    mode="wb"
                elif response.status_code==200 and offset>0:
                    # A CDN ignored Range: safely restart from byte zero.
                    part.unlink(missing_ok=True)
                    offset=0; expected_chunk=expected; mode="wb"
                else:
                    response.raise_for_status()
                    raise RuntimeError(f"HTTP inesperado {response.status_code} no artifact.")
                written=0
                with part.open(mode) as out:
                    for block in response.iter_content(8*1024*1024):
                        if not block: continue
                        out.write(block); written+=len(block)
                        total_now=offset+written
                        if total_now-last_report>=1024*1024*1024 or total_now==expected:
                            print(f"[HookLink2iOS] Artifact GitHub: {total_now/expected*100:.1f}% "
                                  f"({total_now:,}/{expected:,} bytes)",flush=True)
                            last_report=total_now
                        if written>expected_chunk:
                            raise RuntimeError("CDN enviou mais bytes que o intervalo pedido.")
                if written!=expected_chunk:
                    raise IOError(f"Chunk do artifact incompleto: {written:,}/{expected_chunk:,} bytes.")
            failures=0
        except (requests.exceptions.RequestException,OSError,IOError) as exc:
            current=part.stat().st_size if part.exists() else 0
            failures=0 if current>offset else failures+1
            print(f"[HookLink2iOS] Artifact interrompido em {current:,}/{expected:,}; "
                  f"retomada {failures}/20 ({type(exc).__name__}: {exc})",flush=True)
        if failures>=20: raise RuntimeError("Artifact não pôde ser baixado após 20 tentativas retomáveis.")
        if failures:
            delay=min(60,2**min(failures,6))
            time.sleep(delay)
    if part.stat().st_size!=expected:
        raise RuntimeError(f"Tamanho final do artifact diverge: {part.stat().st_size:,}/{expected:,}.")
    actual_sha=file_hashes(part)["sha256"]
    if actual_sha.lower()!=expected_sha:
        part.unlink(missing_ok=True)
        raise RuntimeError("SHA-256 do ZIP diverge do digest publicado pelo GitHub.")
    part.replace(destination)
    print(f"[HookLink2iOS] Artifact verificado por SHA-256: {actual_sha}",flush=True)
    return {"path":destination,"size":expected,"sha256":actual_sha}

def transfer_actions_artifact_to_drive(*,github_token,expected_commit,handoff,drive,run_folder_id):
    info=wait_for_actions_artifact(github_token=github_token,expected_commit=expected_commit)
    artifact=info["artifact"]; run_data=info["run"]
    url=f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip"
    work=Path("/content/hooklink2ios-artifact-transfer"); work.mkdir(parents=True,exist_ok=True)
    zip_path=work/"artifact.zip"
    download_artifact_zip_resumable(
        session=requests.Session(),url=url,artifact=artifact,destination=zip_path
    )
    dest=work/"extracted"; shutil.rmtree(dest,ignore_errors=True); dest.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        members=z.infolist()
        for m in members:
            path=PurePosixPath(m.filename)
            if path.is_absolute() or ".." in path.parts: raise ValueError("Caminho inseguro no artifact.")
        ipa=[m for m in members if m.filename.lower().endswith(".ipa")]
        report=[m for m in members if PurePosixPath(m.filename).name=="build-report.json"]
        overlays=[m for m in members if PurePosixPath(m.filename).name=="Bootup.Nin_Ounce_NVN2.pack.zs"]
        if len(ipa)!=1 or len(report)!=1 or len(overlays)!=1:
            raise RuntimeError("Artifact não contém exatamente uma IPA, um relatório e um overlay.")
        paths={}
        for m in (ipa[0],report[0],overlays[0]):
            p=dest/PurePosixPath(m.filename).name
            with z.open(m) as src,p.open("wb") as out: shutil.copyfileobj(src,out,8*1024*1024)
            paths[p.name]=p
    report_data=json.loads(paths["build-report.json"].read_text())
    ih=file_hashes(paths[ipa[0].filename.split("/")[-1]])
    if report_data.get("project")!="HookLink2iOS" or report_data.get("branch")!=BRANCH:
        raise RuntimeError("Proveniência do build-report incorreta.")
    if report_data.get("commit")!=expected_commit or report_data.get("run_id")!=str(run_data["id"]):
        raise RuntimeError("Commit/run_id do build-report não correspondem ao Actions.")
    if report_data.get("title_id")!=handoff.get("title_id") or report_data.get("package_version")!=handoff.get("package_version"):
        raise RuntimeError("Title ID/versão do build-report divergem do handoff.")
    if report_data.get("engine_commit")!=handoff.get("engine",{}).get("commit"):
        raise RuntimeError("Pin nxnative no build-report diverge do handoff.")
    if report_data.get("gpu_arch")!="g18p" or report_data.get("romfs_mode")!="separate":
        raise RuntimeError("GPU/RomFS mode do build-report divergem do perfil HookLink iPhone 17.")
    if int(report_data.get("ipa",{}).get("size",-1))!=ih["size"] or report_data.get("ipa",{}).get("sha256","").lower()!=ih["sha256"]:
        raise RuntimeError("Hash/tamanho da IPA divergem do build-report.")
    records=report_data.get("romfs",{})
    if int(records.get("size",-1))!=int(handoff["romfs"]["size"]) or records.get("sha256","").lower()!=handoff["romfs"]["sha256"].lower():
        raise RuntimeError("RomFS no build-report diverge do arquivo validado no Colab.")
    if records.get("identity")!=handoff["romfs"].get("identity"):
        raise RuntimeError("Identidade RomFS no build-report diverge do handoff.")
    nup_record=report_data.get("nup_source",{})
    if int(nup_record.get("size",-1))!=int(handoff["nup"]["size"]) or nup_record.get("sha256","").lower()!=handoff["nup"]["sha256"].lower() or not nup_record.get("deleted_after_extract"):
        raise RuntimeError("Proveniência do NUP no build-report diverge do handoff.")
    overlay_record=report_data.get("resolution_overlay",{})
    if int(overlay_record.get("size",-1))!=int(handoff["resolution_overlay"]["size"]) or overlay_record.get("sha256","").lower()!=handoff["resolution_overlay"]["sha256"].lower():
        raise RuntimeError("Overlay no build-report diverge do handoff.")
    contents=report_data.get("ipa",{}).get("contents",{})
    if contents.get("pso_archive",{}).get("name")!="Payload/DmIOS.app/pso/applegpu_g18p.mtl4a" or not contents.get("msl_files"):
        raise RuntimeError("IPA reportada sem pipeline archive g18p ou biblioteca NVN/Metal.")
    build_folder=ensure_folder(drive,run_folder_id,
        f"actions-{run_data['run_number']}-{run_data['id']}")
    provenance=f"HookLink2iOS | branch={BRANCH} | commit={expected_commit} | run_id={run_data['id']} | artifact={artifact['name']} | run_url={run_data.get('html_url')}"
    ipa_item=upload(drive,paths[ipa[0].filename.split("/")[-1]],build_folder["id"],"OcarinaOfTime-HookLink2iOS.ipa",description=provenance)
    upload(drive,paths[overlays[0].filename.split("/")[-1]],build_folder["id"],"Bootup.Nin_Ounce_NVN2.pack.zs",description=provenance)
    upload(drive,paths["build-report.json"],build_folder["id"],"build-report.json",description=provenance)
    remote=drive.files().get(fileId=ipa_item["id"],fields="id,name,size,md5Checksum,webViewLink,description",supportsAllDrives=True).execute()
    if int(remote.get("size",-1))!=ih["size"] or remote.get("md5Checksum","").lower()!=ih["md5"] or remote.get("description")!=provenance:
        raise RuntimeError("IPA no Drive falhou na verificação final.")
    zip_path.unlink(missing_ok=True)
    return {"run":run_data,"artifact":artifact,"ipa":remote,"ipa_sha256":ih["sha256"],
        "drive_folder":build_folder,"commit_sha":expected_commit,"run_url":run_data.get("html_url"),
        "commit_url":f"https://github.com/{REPO}/commit/{expected_commit}"}

if __name__=="__main__":
    print("Importe prepare() pelo notebook Colab e cole uma URL HTTPS de NUP/arquivo compactado.")
