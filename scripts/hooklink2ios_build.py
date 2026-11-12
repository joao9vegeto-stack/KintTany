#!/usr/bin/env python3
"""macOS Actions build stage for HookLink2iOS."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

BRANCH="HookLink2iOS"
TITLE_ID="0400486024DEC000"
VERSION=131072
ENGINE_PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
FOLDER="application/vnd.google-apps.folder"
CHUNK=64*1024*1024

def digest(path,algo):
    h=hashlib.new(algo)
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(16*1024*1024),b""): h.update(block)
    return h.hexdigest()

def die(message):
    raise RuntimeError(message)

def drive_client():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON","").strip()
    if not raw: die("Secret GOOGLE_SERVICE_ACCOUNT_JSON não configurado no repositório.")
    creds=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive","v3",credentials=creds,cache_discovery=False)

def download_verified(drive,record,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    meta=drive.files().get(fileId=record["id"],fields="id,name,size,md5Checksum",
        supportsAllDrives=True).execute(num_retries=5)
    expected=int(record["size"])
    if int(meta.get("size",-1))!=expected: die(f"Tamanho no Drive diverge para {record['name']}.")
    part=destination.with_name(destination.name+".part")
    req=drive.files().get_media(fileId=record["id"],supportsAllDrives=True)
    with part.open("wb") as out:
        dl=MediaIoBaseDownload(out,req,chunksize=CHUNK); done=False
        while not done:
            status,done=dl.next_chunk(num_retries=8)
            if status: print(f"Drive → Actions {record['name']}: {status.progress()*100:.1f}%",flush=True)
    if part.stat().st_size!=expected:
        part.unlink(missing_ok=True); die(f"Download incompleto: {record['name']}.")
    sha=digest(part,"sha256"); md5=digest(part,"md5")
    if sha.lower()!=record["sha256"].lower():
        part.unlink(missing_ok=True); die(f"SHA-256 divergente: {record['name']}.")
    if record.get("md5") and md5.lower()!=record["md5"].lower():
        part.unlink(missing_ok=True); die(f"MD5 divergente: {record['name']}.")
    if meta.get("md5Checksum") and md5.lower()!=meta["md5Checksum"].lower():
        part.unlink(missing_ok=True); die(f"MD5 do Google Drive divergente: {record['name']}.")
    part.replace(destination)
    print(f"VERIFIED {record['name']}: {expected:,} bytes | SHA256 {sha}",flush=True)

def ensure_folder(drive,parent,name):
    qname=name.replace("'","\\'")
    res=drive.files().list(q=f"'{parent}' in parents and name = '{qname}' and mimeType = '{FOLDER}' and trashed = false",
        spaces="drive",pageSize=100,fields="files(id,name)",supportsAllDrives=True,
        includeItemsFromAllDrives=True).execute(num_retries=5)
    if res.get("files"): return res["files"][0]
    return drive.files().create(body={"name":name,"mimeType":FOLDER,"parents":[parent]},
        fields="id,name",supportsAllDrives=True).execute(num_retries=5)

def upload_drive(drive,path,parent,name):
    size=path.stat().st_size; md5=digest(path,"md5")
    media=MediaFileUpload(str(path),mimetype="application/octet-stream",chunksize=CHUNK,resumable=True)
    req=drive.files().create(body={"name":name,"parents":[parent]},media_body=media,
        fields="id,name,size,md5Checksum,webViewLink",supportsAllDrives=True)
    item=None
    while item is None:
        status,item=req.next_chunk(num_retries=8)
        if status: print(f"Actions → Drive {name}: {status.progress()*100:.1f}%",flush=True)
    if int(item.get("size",-1))!=size or str(item.get("md5Checksum","")).lower()!=md5:
        die(f"Upload ao Drive não passou na verificação: {name}")
    return {"id":item["id"],"name":name,"size":size,"md5":md5,"url":item.get("webViewLink")}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--handoff",type=Path,required=True)
    ap.add_argument("--engine",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if os.environ.get("GITHUB_REF")!=f"refs/heads/{BRANCH}": die(f"Branch recusada: {os.environ.get('GITHUB_REF')!r}")
    h=json.loads(args.handoff.read_text(encoding="utf-8"))
    if h.get("project")!="HookLink2iOS" or h.get("branch")!=BRANCH: die("Handoff não pertence a HookLink2iOS.")
    if h.get("title_id")!=TITLE_ID or h.get("package_version_number")!=VERSION: die("Title ID/update do handoff incorretos.")
    if h.get("engine",{}).get("commit")!=ENGINE_PIN: die("Pin nxnative do handoff divergente.")
    sha=subprocess.check_output(["git","-C",str(args.engine),"rev-parse","HEAD"],text=True).strip()
    if sha!=ENGINE_PIN: die(f"Checkout nxnative divergente: {sha}")
    if any(k not in h for k in ("nup","romfs","resolution_overlay","drive")): die("Handoff incompleto.")
    rt=Path(os.environ.get("RUNNER_TEMP","/tmp"))
    work=rt/"hooklink2ios-work"; incoming=rt/"hooklink2ios-input"
    shutil.rmtree(work,ignore_errors=True); shutil.rmtree(incoming,ignore_errors=True)
    work.mkdir(parents=True); incoming.mkdir(parents=True)
    out=args.output; out.mkdir(parents=True,exist_ok=True)
    drive=drive_client()
    nup=incoming/"game.nup"
    romfs=work/"extract"/f"v{VERSION}"/"RomFS.img"
    overlay=out/"res_overlay"/"Pack"/"Bootup.Nin_Ounce_NVN2.pack.zs"
    download_verified(drive,h["nup"],nup)
    download_verified(drive,h["romfs"],romfs)
    download_verified(drive,h["resolution_overlay"],overlay)

    env_file=Path("hooklink/Resources/presets/iphone.env").resolve()
    entitlements=Path("hooklink/Resources/presets/entitlements.plist").resolve()
    if not env_file.is_file() or not entitlements.is_file(): die("Preset iOS/entitlements HookLink ausentes.")
    os.environ["DM_ENTITLEMENTS"]=str(entitlements)
    ipa=out/"OcarinaOfTime-HookLink2iOS.ipa"
    cmd=[sys.executable,str(args.engine/"scripts/build_ipa_from_nsp.py"),str(nup),
        "--platform","ios","--romfs","separate","--allow-damaged",
        "--gpu",h.get("gpu_arch","g18p"),"--env-file",str(env_file),
        "--work-dir",str(work),"--app-name","Ocarina of Time","-o",str(ipa)]
    print("[HookLink2iOS] Build Xcode/Metal iniciado; --romfs separate mantém o RomFS fora da IPA.",flush=True)
    subprocess.run(cmd,cwd=args.engine,env=os.environ.copy(),check=True)
    if not ipa.is_file() or not ipa.stat().st_size: die("Builder terminou sem gerar IPA.")

    report={"project":"HookLink2iOS","branch":BRANCH,"commit":os.environ.get("GITHUB_SHA"),
        "run_id":os.environ.get("GITHUB_RUN_ID"),"title_id":TITLE_ID,"package_version":f"v{VERSION}",
        "engine_commit":sha,"gpu_arch":h.get("gpu_arch","g18p"),"romfs_mode":"separate",
        "ipa":{"name":ipa.name,"size":ipa.stat().st_size,"sha256":digest(ipa,"sha256")},
        "romfs":{"name":"romfs.img","size":romfs.stat().st_size,"sha256":digest(romfs,"sha256"),
                 "identity":h["romfs"].get("identity")},
        "resolution_overlay":{"name":overlay.name,"size":overlay.stat().st_size,
                              "sha256":digest(overlay,"sha256")}}
    report_path=out/"build-report.json"
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    try:
        dest=ensure_folder(drive,h["drive"]["run_folder_id"],
            f"actions-run-{os.environ.get('GITHUB_RUN_NUMBER','manual')}")
        report["drive_upload"]={"folder_id":dest["id"],
            "ipa":upload_drive(drive,ipa,dest["id"],ipa.name),
            "overlay":upload_drive(drive,overlay,dest["id"],overlay.name)}
        # Upload a report after adding IPA/overlay Drive IDs so report contains links.
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        report["drive_upload"]["report"]=upload_drive(drive,report_path,dest["id"],report_path.name)
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print("[HookLink2iOS] IPA/overlay/report enviados ao Google Drive.",flush=True)
    except Exception as e:
        report["drive_upload_warning"]=str(e)[:1000]
        report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(f"::warning::Upload ao Drive falhou; o artifact do Actions será mantido. {e}",flush=True)
    print("HOOKLINK2IOS_BUILD_OK",flush=True)
    print(f"IPA={ipa} BYTES={ipa.stat().st_size}",flush=True)

if __name__=="__main__": main()
