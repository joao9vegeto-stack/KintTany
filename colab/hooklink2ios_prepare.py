#!/usr/bin/env python3
"""Linux/Colab intake + RomFS preparation for HookLink2iOS."""
from __future__ import annotations
import base64, email.message, hashlib, json, os, re, shutil, subprocess, sys, time, uuid, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit
import requests
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "HookLink2iOS"
WORKFLOW_NAME = "HookLink2iOS Ocarina native build"
HANDOFF = "hooklink2ios/handoff.json"
WORKFLOW_NAME = "HookLink2iOS Ocarina native build"
ENGINE = "https://github.com/dsi-hub/nxnative.git"
ENGINE_PIN = "cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
TITLE_ID = "0400486024DEC000"
VERSION = 131072
GPU = "g18p"  # iPhone 17 / 17 Pro A19 family; change only after validating the target GPU.
CHUNK = 64 * 1024 * 1024
FOLDER = "application/vnd.google-apps.folder"

def run(cmd, cwd=None):
    print("[HookLink2iOS] $", " ".join(map(str, cmd)), flush=True)
    p = subprocess.run(list(map(str,cmd)), cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace")
    print(p.stdout, end="", flush=True)
    if p.returncode:
        raise RuntimeError(f"Comando falhou ({p.returncode}): {cmd[0]}")
    return p.stdout

def file_hashes(path):
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(16*1024*1024),b""):
            sha.update(block); md5.update(block); size += len(block)
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
        spaces="drive",pageSize=100,fields="files(id,name)",supportsAllDrives=True,
        includeItemsFromAllDrives=True).execute(num_retries=5)
    if res.get("files"): return res["files"][0]
    return drive.files().create(body={"name":name,"mimeType":FOLDER,"parents":[parent]},
        fields="id,name",supportsAllDrives=True).execute(num_retries=5)

def upload(drive,path,parent,name,app_properties=None,description=None):
    h=file_hashes(path)
    body={"name":name,"parents":[parent]}
    if app_properties: body["appProperties"]={str(k):str(v) for k,v in app_properties.items()}
    if description: body["description"]=description[:25000]
    media=MediaFileUpload(str(path),mimetype="application/octet-stream",chunksize=CHUNK,resumable=True)
    req=drive.files().create(body=body,media_body=media,
        fields="id,name,size,md5Checksum,webViewLink,description,appProperties",supportsAllDrives=True)
    item=None
    while item is None:
        status,item=req.next_chunk(num_retries=8)
        if status: print(f"[HookLink2iOS] Drive upload {name}: {status.progress()*100:.1f}%",flush=True)
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

def set_github_actions_secret(token, secret_name, secret_value):
    """Encrypt a temporary OAuth credential and store it as a repository Actions secret."""
    from nacl.public import PublicKey, SealedBox
    headers=github_headers(token)
    base=f"https://api.github.com/repos/{REPO}/actions/secrets"
    key_response=requests.get(base+"/public-key",headers=headers,timeout=(30,90))
    if key_response.status_code in (401,403):
        raise PermissionError(
            "O PAT não tem acesso para gravar Secrets do GitHub. "
            "Adicione 'Secrets: Read and write' (Secrets: write) ao Fine-grained PAT "
            "restrito a este repositório e execute novamente."
        )
    key_response.raise_for_status()
    key=key_response.json()
    encrypted=SealedBox(PublicKey(base64.b64decode(key["key"]))).encrypt(secret_value.encode("utf-8"))
    payload={"encrypted_value":base64.b64encode(encrypted).decode("ascii"),"key_id":key["key_id"]}
    response=requests.put(f"{base}/{secret_name}",headers=headers,json=payload,timeout=(30,90))
    if response.status_code not in (201,204):
        raise RuntimeError(f"Não foi possível configurar o secret temporário {secret_name}: HTTP {response.status_code}: {response.text[:600]}")
    print(f"[HookLink2iOS] Secret temporário {secret_name} configurado (valor criptografado no GitHub).")

def delete_github_actions_secret(token, secret_name):
    """Delete the temporary OAuth secret after the Actions run is finished."""
    response=requests.delete(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{secret_name}",
        headers=github_headers(token),timeout=(30,90))
    if response.status_code not in (204,404):
        raise RuntimeError(f"Não foi possível apagar secret temporário {secret_name}: HTTP {response.status_code}: {response.text[:500]}")
    print(f"[HookLink2iOS] Secret temporário {secret_name} removido do repositório.")

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
    parent=drive.files().get(fileId=drive_parent_folder_id,fields="id,mimeType",supportsAllDrives=True).execute()
    if parent.get("mimeType")!=FOLDER: raise ValueError("DRIVE_FOLDER_ID não é uma pasta.")
    project=ensure_folder(drive,drive_parent_folder_id,"HookLink2iOS")
    inputs=ensure_folder(drive,project["id"],"Inputs")
    cached=find_cached_nup(drive,inputs["id"],key)
    nup=inp/"game.nup"; archive=None; archive_extracted=False; source_filename=""
    if cached:
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
        "builder":{"platform":"ios","romfs_mode":"separate","runner":"macos-26","xcode":"27.2"},
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
    return {"handoff":h,"commit_sha":commits[0]["sha"],
        "commit_url":f"https://github.com/{REPO}/commit/{commits[0]['sha']}",
        "actions_url":f"https://github.com/{REPO}/actions"}

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

def transfer_actions_artifact_to_drive(*,github_token,expected_commit,drive,run_folder_id):
    info=wait_for_actions_artifact(github_token=github_token,expected_commit=expected_commit)
    artifact=info["artifact"]; run_data=info["run"]
    url=f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip"
    work=Path("/content/hooklink2ios-artifact-transfer"); work.mkdir(parents=True,exist_ok=True)
    zip_path=work/"artifact.zip"; part=zip_path.with_suffix(".part"); total=0
    r=requests.get(url,headers=info["headers"],stream=True,allow_redirects=True,timeout=(30,180)); r.raise_for_status()
    with r:
        with part.open("wb") as out:
            for block in r.iter_content(8*1024*1024):
                if block: out.write(block); total+=len(block)
    expected_size=int(artifact.get("size_in_bytes") or 0)
    if expected_size and total!=expected_size: part.unlink(missing_ok=True); raise RuntimeError("ZIP do artifact incompleto.")
    zip_sha=file_hashes(part)["sha256"]; digest=str(artifact.get("digest") or "").split(":",1)[-1].lower()
    if digest and zip_sha.lower()!=digest: part.unlink(missing_ok=True); raise RuntimeError("Digest do ZIP diverge do GitHub.")
    part.replace(zip_path)
    dest=work/"extracted"; shutil.rmtree(dest,ignore_errors=True); dest.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        members=z.infolist()
        for m in members:
            path=PurePosixPath(m.filename)
            if path.is_absolute() or ".." in path.parts: raise ValueError("Caminho inseguro no artifact.")
        ipa=[m for m in members if m.filename.lower().endswith(".ipa")]
        report=[m for m in members if PurePosixPath(m.filename).name=="build-report.json"]
        overlays=[m for m in members if PurePosixPath(m.filename).name=="Bootup.Nin_Ounce_NVN2.pack.zs"]
        if len(ipa)!=1 or len(report)!=1 or len(overlays)!=1: raise RuntimeError("Artifact não contém IPA/report/overlay únicos.")
        paths={}
        for m in (ipa[0],report[0],overlays[0]):
            p=dest/PurePosixPath(m.filename).name
            with z.open(m) as src,p.open("wb") as out: shutil.copyfileobj(src,out,8*1024*1024)
            paths[p.name]=p
    report_data=json.loads(paths["build-report.json"].read_text())
    ih=file_hashes(paths[ipa[0].filename.split("/")[-1]])
    if report_data.get("project")!="HookLink2iOS" or report_data.get("branch")!=BRANCH: raise RuntimeError("Proveniência do build-report incorreta.")
    if int(report_data.get("ipa",{}).get("size",-1))!=ih["size"] or report_data.get("ipa",{}).get("sha256","").lower()!=ih["sha256"]: raise RuntimeError("Hash/tamanho da IPA diverge do build-report.")
    provenance=f"HookLink2iOS | branch={BRANCH} | commit={expected_commit} | run_id={run_data['id']} | artifact={artifact['name']} | run_url={run_data.get('html_url')}"
    ipa_item=upload(drive,paths[ipa[0].filename.split("/")[-1]],run_folder_id,"OcarinaOfTime-HookLink2iOS.ipa",description=provenance)
    upload(drive,paths[overlays[0].filename.split("/")[-1]],run_folder_id,"Bootup.Nin_Ounce_NVN2.pack.zs",description=provenance)
    upload(drive,paths["build-report.json"],run_folder_id,"build-report.json",description=provenance)
    remote=drive.files().get(fileId=ipa_item["id"],fields="id,name,size,md5Checksum,webViewLink,description",supportsAllDrives=True).execute()
    if int(remote.get("size",-1))!=ih["size"] or remote.get("md5Checksum","").lower()!=ih["md5"] or remote.get("description")!=provenance: raise RuntimeError("IPA no Drive falhou na verificação final.")
    zip_path.unlink(missing_ok=True)
    return {"run":run_data,"artifact":artifact,"ipa":remote,"ipa_sha256":ih["sha256"],
        "commit_sha":expected_commit,"run_url":run_data.get("html_url"),
        "commit_url":f"https://github.com/{REPO}/commit/{expected_commit}"}

if __name__=="__main__":
    print("Importe prepare() pelo notebook Colab e cole uma URL HTTPS de NUP/arquivo compactado.")
