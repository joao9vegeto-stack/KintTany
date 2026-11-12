#!/usr/bin/env python3
"""Linux/Colab intake + RomFS preparation for HookLink2iOS."""
from __future__ import annotations
import base64, hashlib, json, os, re, shutil, subprocess, sys, time, uuid
from pathlib import Path, PurePosixPath
import requests
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

REPO = "joao9vegeto-stack/KintTany"
BRANCH = "HookLink2iOS"
HANDOFF = "hooklink2ios/handoff.json"
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
    name = Path(name).name.strip()
    if not name or name in (".",".."): raise ValueError("Nome de arquivo inválido.")
    return re.sub(r"[^A-Za-z0-9._ -]","_",name)

def download_url(url, dst):
    if not url.startswith("https://"): raise ValueError("A origem precisa usar HTTPS.")
    dst.parent.mkdir(parents=True,exist_ok=True)
    part = dst.with_name(dst.name+".part")
    total = last = 0
    try:
        with requests.get(url,stream=True,allow_redirects=True,timeout=(30,180),
                          headers={"User-Agent":"HookLink2iOS-Colab/1.0","Accept-Encoding":"identity"}) as r:
            r.raise_for_status()
            expected = int(r.headers.get("content-length") or 0)
            with part.open("wb") as out:
                for block in r.iter_content(8*1024*1024):
                    if not block: continue
                    out.write(block); total += len(block)
                    if total-last >= 512*1024*1024:
                        print(f"[HookLink2iOS] Download {total:,}/{expected or '?'} bytes",flush=True); last=total
        if total < 4: raise ValueError("Download vazio/incompleto.")
        part.replace(dst)
    except Exception:
        part.unlink(missing_ok=True); raise

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

def upload(drive,path,parent,name):
    h=file_hashes(path)
    media=MediaFileUpload(str(path),mimetype="application/octet-stream",chunksize=CHUNK,resumable=True)
    req=drive.files().create(body={"name":name,"parents":[parent]},media_body=media,
        fields="id,name,size,md5Checksum,webViewLink",supportsAllDrives=True)
    item=None
    while item is None:
        status,item=req.next_chunk(num_retries=8)
        if status: print(f"[HookLink2iOS] Drive upload {name}: {status.progress()*100:.1f}%",flush=True)
    if int(item.get("size",-1))!=h["size"] or str(item.get("md5Checksum","")).lower()!=h["md5"]:
        raise RuntimeError(f"Upload Drive falhou na verificação: {name}")
    return {"id":item["id"],"name":name,**h,"web_view_url":item.get("webViewLink")}

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

def prepare(*,source_url="",source_filename="",source_drive_id="",drive_parent_folder_id,
            drive,github_token,repo_root,work_root=Path("/content/hooklink2ios-work")):
    if sys.version_info<(3,12): raise RuntimeError("Python 3.12+ obrigatório.")
    if bool(source_url)==bool(source_drive_id): raise ValueError("Informe somente URL HTTPS ou ID de arquivo do Drive.")
    request_id=str(uuid.uuid4()); inp=work_root/"input"; extracted=work_root/"unpacked"
    engine=work_root/"nxnative"; build=work_root/"linux-build"
    inp.mkdir(parents=True,exist_ok=True); work_root.mkdir(parents=True,exist_ok=True)
    if source_drive_id:
        tmp=inp/"source.download"; actual=download_drive_source(drive,source_drive_id,tmp)
        source=inp/safe_name(actual); source.unlink(missing_ok=True); tmp.rename(source)
    else:
        source=inp/safe_name(source_filename or "game.nup"); download_url(source_url,source)
    print(f"[HookLink2iOS] Origem recebida: {source.name} ({source.stat().st_size:,} bytes)")
    if source.suffix.lower()==".nup": nup=source; archive=None
    elif source.suffix.lower() in (".rar",".zip",".7z",".tar",".tgz",".gz",".xz"):
        nup=extract_archive(source,extracted); archive=source
    else: raise ValueError(f"Formato {source.suffix} não suportado.")
    clone_engine(engine)
    out=run([sys.executable,engine/"scripts/pack_nup.py",nup,"--version",str(VERSION),
             "--work-dir",build],cwd=engine)
    if f"{TITLE_ID} version {VERSION}" not in out:
        raise ValueError("O NUP não corresponde ao Title ID/update esperado; interrompi antes do upload.")
    romfs=build/"extract"/f"v{VERSION}"/"RomFS.img"
    if not romfs.is_file() or not romfs.stat().st_size: raise RuntimeError("RomFS.img não foi criado.")
    identity=run([sys.executable,engine/"dm/tools/romfs_image.py","--identity",romfs,
                  TITLE_ID,f"v{VERSION}",ENGINE_PIN]).strip().splitlines()[-1]
    overlay=work_root/"res_overlay"/"Pack"/"Bootup.Nin_Ounce_NVN2.pack.zs"
    overlay.parent.mkdir(parents=True,exist_ok=True)
    run([sys.executable,repo_root/"hooklink/Resources/tools/hl_resolution.py",
         engine,romfs,overlay,"0.75","95"])
    if not overlay.is_file() or not overlay.stat().st_size: raise RuntimeError("Overlay não foi gerado.")
    if archive:
        archive.unlink(missing_ok=True)
        print("[HookLink2iOS] Arquivo compactado removido após NUP e RomFS validados.")
    parent=drive.files().get(fileId=drive_parent_folder_id,fields="id,mimeType",supportsAllDrives=True).execute()
    if parent.get("mimeType")!=FOLDER: raise ValueError("DRIVE_PARENT_FOLDER_ID não é uma pasta.")
    project=ensure_folder(drive,drive_parent_folder_id,"HookLink2iOS")
    runfolder=drive.files().create(body={"name":f"HookLink2iOS-{request_id}","mimeType":FOLDER,"parents":[project["id"]]},
        fields="id,name,webViewLink",supportsAllDrives=True).execute()
    print("[HookLink2iOS] Enviando NUP, RomFS e overlay ao Drive.")
    nup_item=upload(drive,nup,runfolder["id"],"game.nup")
    romfs_item=upload(drive,romfs,runfolder["id"],"romfs.img")
    overlay_item=upload(drive,overlay,runfolder["id"],"Bootup.Nin_Ounce_NVN2.pack.zs")
    handoff={"schema":1,"project":"HookLink2iOS","branch":BRANCH,"request_id":request_id,
        "title_id":TITLE_ID,"package_version":f"v{VERSION}","package_version_number":VERSION,
        "gpu_arch":GPU,"engine":{"repository":ENGINE,"branch":"hooklink","commit":ENGINE_PIN},
        "source":{"filename":source.name,"archive_extracted":archive is not None,
                  "archive_deleted_after_extraction":archive is not None},
        "drive":{"parent_folder_id":drive_parent_folder_id,"project_folder_id":project["id"],
                 "run_folder_id":runfolder["id"],"run_folder_url":runfolder.get("webViewLink")},
        "nup":nup_item,"romfs":{**romfs_item,"identity":identity},"resolution_overlay":overlay_item,
        "builder":{"platform":"ios","romfs_mode":"separate","runner":"macos-26","xcode":"27.2"},
        "created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    pushed=publish(github_token,handoff)
    print("[HookLink2iOS] Preparação Linux concluída.")
    print("NUP:",nup_item["id"],nup_item["size"],"bytes")
    print("RomFS:",romfs_item["id"],romfs_item["size"],"bytes")
    print("Actions:",pushed["actions_url"])
    return {"handoff":handoff,"github":pushed}

if __name__=="__main__":
    print("Importe prepare() pelo notebook Colab e forneça sua própria origem de dump.")
