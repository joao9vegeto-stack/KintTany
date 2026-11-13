#!/usr/bin/env python3
"""macOS Actions build stage for HookLink2iOS."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient.discovery import build

BRANCH="HookLink2iOS"
TITLE_ID="0400486024DEC000"
VERSION=131072
ENGINE_PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
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
    if not raw:
        die("Secret GOOGLE_SERVICE_ACCOUNT_JSON ausente; configure a mesma credencial de Drive usada pelo workflow Link2iOS.")
    try:
        info=json.loads(raw)
        creds=service_account.Credentials.from_service_account_info(
            info,scopes=["https://www.googleapis.com/auth/drive"])
    except Exception as exc:
        die(f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {exc}")
    return build("drive","v3",credentials=creds,cache_discovery=False), AuthorizedSession(creds)

def download_verified(drive,session,record,destination):
    """Resumable Drive download. A broken response resumes from the exact byte already written."""
    destination.parent.mkdir(parents=True,exist_ok=True)
    meta=drive.files().get(fileId=record["id"],fields="id,name,size,md5Checksum",
        supportsAllDrives=True).execute(num_retries=5)
    expected=int(record["size"])
    if int(meta.get("size",-1))!=expected: die(f"Tamanho no Drive diverge para {record['name']}.")
    part=destination.with_name(destination.name+".part")
    if part.exists() and part.stat().st_size>expected:
        part.unlink()
    url=f"https://www.googleapis.com/drive/v3/files/{record['id']}?alt=media&supportsAllDrives=true"
    failures=0
    last_report=0
    range_bytes=512*1024*1024
    while not part.exists() or part.stat().st_size<expected:
        offset=part.stat().st_size if part.exists() else 0
        end=min(offset+range_bytes-1,expected-1)
        headers={"Range":f"bytes={offset}-{end}"}
        before=offset
        try:
            with session.get(url,headers=headers,stream=True,timeout=(60,240)) as response:
                if response.status_code==200 and offset>0:
                    # If the endpoint ignores Range, restart safely from byte zero.
                    part.unlink(missing_ok=True)
                    offset=0
                    end=expected-1
                    expected_chunk=expected
                    mode="wb"
                elif response.status_code==206:
                    content_range=response.headers.get("Content-Range","")
                    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",content_range)
                    if not match:
                        die(f"Content-Range inválido para {record['name']}: {content_range!r}")
                    range_start,range_end,range_total=map(int,match.groups())
                    if range_start!=offset or range_total!=expected or range_end<range_start or range_end>end:
                        die(f"Content-Range inconsistente para {record['name']}: {content_range!r}")
                    expected_chunk=range_end-range_start+1
                    mode="ab" if offset else "wb"
                elif response.status_code==200 and offset==0:
                    expected_chunk=expected
                    mode="wb"
                else:
                    response.raise_for_status()
                    die(f"HTTP inesperado {response.status_code} no download de {record['name']}.")
                written=0
                with part.open(mode) as out:
                    for block in response.iter_content(chunk_size=8*1024*1024):
                        if not block: continue
                        out.write(block)
                        written+=len(block)
                        total_now=offset+written
                        if total_now-last_report>=1024*1024*1024 or total_now==expected:
                            print(f"Drive → Actions {record['name']}: {total_now/expected*100:.1f}% ({total_now:,}/{expected:,} bytes)",flush=True)
                            last_report=total_now
                        if written>expected_chunk:
                            die(f"Drive enviou dados além do intervalo pedido para {record['name']}.")
                if written!=expected_chunk:
                    raise IOError(f"Resposta incompleta de {record['name']}: {written:,}/{expected_chunk:,} bytes.")
            failures=0
        except requests.HTTPError as exc:
            status=exc.response.status_code if exc.response is not None else 0
            if status not in (408,429,500,502,503,504):
                raise
            failures+=1
            print(f"[HookLink2iOS] Drive HTTP {status}; tentativa retomável {failures}/20.",flush=True)
        except (requests.exceptions.RequestException,OSError,IOError) as exc:
            now=part.stat().st_size if part.exists() else 0
            failures=0 if now>before else failures+1
            print(f"[HookLink2iOS] Conexão interrompida em {now:,}/{expected:,} bytes; retomando ({failures}/20): {type(exc).__name__}: {exc}",flush=True)
        if failures>=20:
            die(f"Download de {record['name']} falhou após 20 tentativas retomáveis.")
        if failures:
            delay=min(60,2**min(failures,6))
            print(f"[HookLink2iOS] Nova tentativa em {delay}s.",flush=True)
            time.sleep(delay)
    if part.stat().st_size!=expected:
        die(f"Tamanho local incorreto para {record['name']}: {part.stat().st_size:,}/{expected:,}.")
    sha=digest(part,"sha256"); md5=digest(part,"md5")
    if sha.lower()!=record["sha256"].lower():
        part.unlink(missing_ok=True); die(f"SHA-256 divergente: {record['name']}.")
    if record.get("md5") and md5.lower()!=record["md5"].lower():
        part.unlink(missing_ok=True); die(f"MD5 divergente: {record['name']}.")
    if meta.get("md5Checksum") and md5.lower()!=meta["md5Checksum"].lower():
        part.unlink(missing_ok=True); die(f"MD5 do Google Drive divergente: {record['name']}.")
    part.replace(destination)
    print(f"VERIFIED {record['name']}: {expected:,} bytes | SHA256 {sha}",flush=True)

def patch_nxnative_release_nup_after_extract(engine):
    """Free the verified 25.6 GB input NUP after nxnative has extracted main game + DLC."""
    script=engine/"scripts/build_ipa_from_nsp.py"
    source=script.read_text(encoding="utf-8")
    marker="    # HookLink2iOS: release the source NUP after extract_aoc; no later stage reads it.\n"
    if marker in source:
        return
    anchor="    aoc = extract_aoc(nx, keys, repo, work, app, fam, logs)\n"
    if source.count(anchor)!=1:
        die("Não foi possível localizar de forma única a etapa final de extração do NUP no builder fixado.")
    injection=anchor+marker+"""    if fam.get('nup') is not None:
        _hooklink_nup = fam['nup']
        _hooklink_nup_path = _hooklink_nup.path
        _hooklink_nup.close()
        fam['nup'] = None
        _hooklink_nup_path.unlink()
        say(f'HookLink2iOS: NUP de entrada removido após extração validada ({_hooklink_nup_path.name}); {shutil.disk_usage(work).free / 2**30:.1f} GiB livres para shaders/Metal.')
"""
    script.write_text(source.replace(anchor,injection),encoding="utf-8")
    if marker not in script.read_text(encoding="utf-8"):
        die("Patch de liberação do NUP não foi persistido.")

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
    gpu=h.get("gpu_arch")
    if gpu!="g18p": die(f"GPU incompatível com o perfil iPhone 17 Pro do HookLink: {gpu!r}")
    sha=subprocess.check_output(["git","-C",str(args.engine),"rev-parse","HEAD"],text=True).strip()
    if sha!=ENGINE_PIN: die(f"Checkout nxnative divergente: {sha}")
    if any(k not in h for k in ("nup","romfs","resolution_overlay","drive")): die("Handoff incompleto.")
    if int(h["nup"]["size"]) < 20 * 1024**3:
        die("NUP menor que o esperado para o build HookLink; abortando antes de qualquer transferência.")
    for key in ("nup","romfs","resolution_overlay"):
        record=h[key]
        if not record.get("id") or int(record.get("size",0))<=0:
            die(f"Registro {key} inválido no handoff.")
        if len(record.get("sha256",""))!=64:
            die(f"SHA-256 ausente/inválido em {key}.")
    rt=Path(os.environ.get("RUNNER_TEMP","/tmp"))
    work=rt/"hooklink2ios-work"; incoming=rt/"hooklink2ios-input"
    shutil.rmtree(work,ignore_errors=True); shutil.rmtree(incoming,ignore_errors=True)
    work.mkdir(parents=True); incoming.mkdir(parents=True)
    out=args.output; out.mkdir(parents=True,exist_ok=True)
    drive,drive_session=drive_client()
    nup=incoming/"game.nup"
    # The pinned nxnative builder creates extract/v131072/RomFS.img directly from the NUP.
    # Do not download the separate 26 GB Drive copy a second time.
    romfs=work/"extract"/f"v{VERSION}"/"RomFS.img"
    overlay=out/"res_overlay"/"Pack"/"Bootup.Nin_Ounce_NVN2.pack.zs"
    download_verified(drive,drive_session,h["nup"],nup)
    download_verified(drive,drive_session,h["resolution_overlay"],overlay)

    patch_nxnative_release_nup_after_extract(args.engine)
    env_file=Path("hooklink/Resources/presets/iphone.env").resolve()
    entitlements=Path("hooklink/Resources/presets/entitlements.plist").resolve()
    if not env_file.is_file() or not entitlements.is_file(): die("Preset iOS/entitlements HookLink ausentes.")
    os.environ["DM_ENTITLEMENTS"]=str(entitlements)
    ipa=out/"OcarinaOfTime-HookLink2iOS.ipa"
    cmd=[sys.executable,"-I",str(args.engine/"scripts/build_ipa_from_nsp.py"),str(nup),
        "--platform","ios","--package",f"v{VERSION}","--romfs","separate","--allow-damaged",
        "--gpu",gpu,"--env-file",str(env_file),
        "--work-dir",str(work),"--app-name","Ocarina of Time","-o",str(ipa)]
    print("[HookLink2iOS] Build Xcode/Metal iniciado; --romfs separate mantém o RomFS fora da IPA.",flush=True)
    subprocess.run(cmd,cwd=args.engine,env=os.environ.copy(),check=True)
    if not ipa.is_file() or not ipa.stat().st_size: die("Builder terminou sem gerar IPA.")
    if not romfs.is_file() or romfs.stat().st_size!=int(h["romfs"]["size"]):
        die("RomFS criado pelo builder difere do tamanho validado no Colab.")
    romfs_sha=digest(romfs,"sha256")
    if romfs_sha.lower()!=h["romfs"]["sha256"].lower():
        die("SHA-256 do RomFS criado no Actions difere do RomFS previamente validado no Colab.")
    romfs_identity=subprocess.check_output(
        [sys.executable,str(args.engine/"dm/tools/romfs_image.py"),"--identity",
         str(romfs),TITLE_ID,f"v{VERSION}",ENGINE_PIN],text=True).strip().splitlines()[-1]
    if romfs_identity!=h["romfs"].get("identity"):
        die("Identidade do RomFS criado no Actions difere do handoff validado no Colab.")

    report={"project":"HookLink2iOS","branch":BRANCH,"commit":os.environ.get("GITHUB_SHA"),
        "run_id":os.environ.get("GITHUB_RUN_ID"),"title_id":TITLE_ID,"package_version":f"v{VERSION}",
        "engine_commit":sha,"gpu_arch":gpu,"romfs_mode":"separate",
        "nup_source":{"size":int(h["nup"]["size"]),"sha256":h["nup"]["sha256"],
                      "deleted_after_extract":True},
        "ipa":{"name":ipa.name,"size":ipa.stat().st_size,"sha256":digest(ipa,"sha256")},
        "romfs":{"name":"romfs.img","size":romfs.stat().st_size,"sha256":romfs_sha,
                 "identity":romfs_identity,"source":"repacked-from-verified-nup"},
        "resolution_overlay":{"name":overlay.name,"size":overlay.stat().st_size,
                              "sha256":digest(overlay,"sha256")}}
    report_path=out/"build-report.json"
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("[HookLink2iOS] IPA/overlay/report ficam no artifact do Actions; o Colab os transfere ao Drive via OAuth após validar o artifact.",flush=True)
    print("HOOKLINK2IOS_BUILD_OK",flush=True)
    print(f"IPA={ipa} BYTES={ipa.stat().st_size}",flush=True)

if __name__=="__main__": main()
