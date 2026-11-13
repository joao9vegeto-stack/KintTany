#!/usr/bin/env python3
"""Finish HookLink2iOS on macOS from the Colab-prepared nxnative workspace."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account
from googleapiclient.discovery import build

BRANCH="HookLink2iOS"
TITLE_ID="0400486024DEC000"
VERSION=131072
ENGINE_PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
IOS_DEPLOYMENT_TARGET="26.0"


def die(message):
    raise RuntimeError(message)


def digest(path,algo="sha256"):
    h=hashlib.new(algo)
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(16*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def drive_client():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON","").strip()
    if not raw: die("Secret GOOGLE_SERVICE_ACCOUNT_JSON ausente.")
    try:
        info=json.loads(raw)
        creds=service_account.Credentials.from_service_account_info(
            info,scopes=["https://www.googleapis.com/auth/drive"])
    except Exception as exc:
        die(f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {exc}")
    return build("drive","v3",credentials=creds,cache_discovery=False),AuthorizedSession(creds)


def download_verified(drive,session,record,destination):
    """Resumable, range-based Drive download with size and SHA/MD5 validation."""
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    meta=drive.files().get(fileId=record["id"],fields="id,name,size,md5Checksum",
        supportsAllDrives=True).execute(num_retries=5)
    expected=int(record["size"])
    if int(meta.get("size",-1))!=expected: die(f"Tamanho no Drive diverge para {record['name']}.")
    part=destination.with_name(destination.name+".part")
    if part.exists() and part.stat().st_size>expected: part.unlink()
    url=f"https://www.googleapis.com/drive/v3/files/{record['id']}?alt=media&supportsAllDrives=true"
    failures=0; last_report=0; range_bytes=512*1024*1024
    while not part.exists() or part.stat().st_size<expected:
        offset=part.stat().st_size if part.exists() else 0
        end=min(offset+range_bytes-1,expected-1)
        try:
            with session.get(url,headers={"Range":f"bytes={offset}-{end}"},
                             stream=True,timeout=(60,240)) as response:
                if response.status_code==206:
                    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",response.headers.get("Content-Range",""))
                    if not match: die(f"Content-Range inválido para {record['name']}.")
                    first,last,total=map(int,match.groups())
                    if first!=offset or total!=expected or last<first or last>end:
                        die(f"Content-Range inconsistente para {record['name']}.")
                    expected_chunk=last-first+1; mode="ab" if offset else "wb"
                elif response.status_code==200 and offset==0:
                    expected_chunk=expected; mode="wb"
                elif response.status_code==200 and offset>0:
                    part.unlink(missing_ok=True); offset=0
                    expected_chunk=expected; mode="wb"
                else:
                    response.raise_for_status()
                    die(f"HTTP {response.status_code} inesperado no Drive.")
                written=0
                with part.open(mode) as out:
                    for block in response.iter_content(8*1024*1024):
                        if not block: continue
                        out.write(block); written+=len(block)
                        done=offset+written
                        if done-last_report>=1024**3 or done==expected:
                            print(f"[HookLink2iOS] Drive {record['name']}: {done/expected*100:.1f}% ({done:,}/{expected:,})",flush=True)
                            last_report=done
                        if written>expected_chunk: die(f"Drive excedeu o intervalo solicitado para {record['name']}.")
                if written!=expected_chunk: raise IOError(f"Bloco incompleto: {written:,}/{expected_chunk:,}.")
            failures=0
        except requests.HTTPError as exc:
            status=exc.response.status_code if exc.response is not None else 0
            if status not in (408,429,500,502,503,504): raise
            failures+=1
        except (requests.RequestException,OSError,IOError) as exc:
            failures+=1
            print(f"[HookLink2iOS] Download interrompido; retomando: {type(exc).__name__}: {exc}",flush=True)
        if failures>=20: die(f"Download Drive falhou após 20 tentativas: {record['name']}.")
        if failures: time.sleep(min(60,2**min(failures,6)))
    if part.stat().st_size!=expected: die(f"Tamanho local incorreto para {record['name']}.")
    sha=digest(part); md5=digest(part,"md5")
    if sha.lower()!=record["sha256"].lower(): part.unlink(missing_ok=True); die(f"SHA-256 divergente: {record['name']}.")
    if record.get("md5") and md5.lower()!=record["md5"].lower(): part.unlink(missing_ok=True); die(f"MD5 divergente: {record['name']}.")
    if meta.get("md5Checksum") and md5.lower()!=meta["md5Checksum"].lower(): part.unlink(missing_ok=True); die(f"MD5 do Drive divergente: {record['name']}.")
    part.replace(destination)
    print(f"[HookLink2iOS] VERIFIED {record['name']}: {expected:,} bytes | SHA-256 {sha}",flush=True)


def extract_verified_archive(archive,destination):
    """Safely unpack the Colab tar.zst prepared workspace."""
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    proc=subprocess.Popen(["zstd","-dc",str(archive)],stdout=subprocess.PIPE)
    if proc.stdout is None: die("Não foi possível iniciar zstd.")
    try:
        with tarfile.open(fileobj=proc.stdout,mode="r|") as tar:
            for member in tar:
                rel=PurePosixPath(member.name)
                if rel.is_absolute() or ".." in rel.parts:
                    die(f"Caminho inseguro no workspace: {member.name}")
                target=destination.joinpath(*[p for p in rel.parts if p not in ("",".")])
                if member.isdir():
                    target.mkdir(parents=True,exist_ok=True); continue
                if not member.isfile():
                    die(f"Tipo de entrada não permitido no workspace: {member.name}")
                target.parent.mkdir(parents=True,exist_ok=True)
                src=tar.extractfile(member)
                if src is None: die(f"Não foi possível ler {member.name}.")
                with src,target.open("wb") as out: shutil.copyfileobj(src,out,16*1024*1024)
    finally:
        proc.stdout.close()
    if proc.wait()!=0: die("Falha ao descompactar workspace tar.zst.")


def preflight_hooklink_engine(engine):
    profile=engine/"dm/games"/TITLE_ID
    game=profile/"game.tsv"
    if not game.is_file(): die(f"Perfil nxnative ausente: {game}")
    values={}
    for line in game.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "\t" in line:
            key,value=line.split("\t",1); values[key]=value
    expected={"title_id":TITLE_ID,"program_id":TITLE_ID,"package":f"v{VERSION}","pso_mtl4":"on"}
    for key,value in expected.items():
        if values.get(key)!=value: die(f"Perfil Ocarina divergente em {key}: esperado {value!r}, recebido {values.get(key)!r}.")
    for name,minimum in (("shader_pairs.tsv",1000),("pso_pairs.tsv",1000)):
        path=profile/name
        if not path.is_file(): die(f"Tabela de shaders ausente: {path}")
        rows=sum(1 for line in path.open(encoding="utf-8") if line.strip() and not line.startswith("#"))
        if rows<minimum: die(f"{name}: apenas {rows} entradas.")
        print(f"[HookLink2iOS] {name}: {rows:,} entradas.",flush=True)
    lock=(engine/"dm/gfx/tools/dmsh_chain.lock")
    if not lock.is_file(): die("dmsh_chain.lock ausente.")
    lock_fields={}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if "\t" in line and not line.startswith("#"):
            key,value=line.split("\t",1); lock_fields[key]=value
    for key in ("metal_macosx","metal_iphoneos","dmsh_xlate","xlate_source","spirv_cross"):
        if not lock_fields.get(key): die(f"Fingerprint {key} ausente em dmsh_chain.lock.")
    project=(engine/"dm/ios/project.yml")
    if not project.is_file(): die("Projeto Xcode DmIOS ausente.")
    project_text=project.read_text(encoding="utf-8")
    if not re.search(r'^\s+iOS:\s*["\']26\.0["\']\s*$',project_text,re.M):
        die("O projeto DmIOS não declara deploymentTarget iOS 26.0.")
    print("[HookLink2iOS] Projeto iOS 26.0, perfil e cadeia Metal conferidos.",flush=True)


def load_builder(engine):
    for path in (engine/"dm/tools",engine/"dm/games",engine/"dm/gfx/tools",engine/"scripts"):
        sys.path.insert(0,str(path))
    script=engine/"scripts/build_ipa_from_nsp.py"
    spec=importlib.util.spec_from_file_location("hooklink2ios_nxnative_builder",script)
    if spec is None or spec.loader is None: die(f"Builder nxnative ausente: {script}")
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    import game as game_profiles
    import nacp
    import profile_guess as pg
    module.gamemod=game_profiles; module.nacp=nacp; module.pg=pg
    return module,game_profiles,nacp,pg


def audit_ipa(ipa,romfs_identity,expected_chain):
    import zipfile
    with zipfile.ZipFile(ipa,"r") as archive:
        names=set(archive.namelist())
        app="Payload/DmIOS.app/"
        required=(app+"Info.plist",app+"DmIOS",app+"romfs.id")
        missing=[p for p in required if p not in names]
        if missing: die("IPA incompleta; faltam: "+", ".join(missing))
        msl=[p for p in names if p.startswith(app+"msl/b-") and p.endswith(".img")]
        if not any(Path(p).name==f"b-{expected_chain}.img" for p in msl):
            die(f"IPA não contém a biblioteca Metal b-{expected_chain}.img.")
        pso=[p for p in names if p.startswith(app+"pso/") and p.endswith(".mtl4a")]
        if pso: die("GPU none: arquivo PSO offline inesperado: "+", ".join(pso))
        plist=plistlib.loads(archive.read(app+"Info.plist"))
        minimum=str(plist.get("MinimumOSVersion",""))
        if minimum!=IOS_DEPLOYMENT_TARGET:
            die(f"IPA exige iOS {minimum}; o alvo exigido é iOS {IOS_DEPLOYMENT_TARGET}.")
        marker=archive.read(app+"romfs.id").decode("utf-8","replace").strip()
        marker_fields=dict(item.split("=",1) for item in marker.split()[1:] if "=" in item)
        identity_fields=dict(item.split("=",1) for item in str(romfs_identity).split()[1:] if "=" in item)
        if marker_fields.get("size")!=identity_fields.get("size") or marker_fields.get("index")!=identity_fields.get("index"):
            die("Marcador romfs.id da IPA não corresponde ao RomFS externo verificado.")
        msl_records=[{"name":p,"size":archive.getinfo(p).file_size} for p in sorted(msl)]
        return {"app_root":app.rstrip("/"),"minimum_os_version":minimum,
                "msl_files":msl_records,"pso_archive":None,"gpu_mode":"none",
                "romfs_marker":marker}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--handoff",type=Path,required=True)
    ap.add_argument("--engine",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if os.environ.get("GITHUB_REF")!=f"refs/heads/{BRANCH}": die(f"Branch recusada: {os.environ.get('GITHUB_REF')!r}")
    h=json.loads(args.handoff.read_text(encoding="utf-8"))
    if h.get("schema")!=3 or h.get("project")!="HookLink2iOS" or h.get("branch")!=BRANCH:
        die("Handoff não pertence ao novo pipeline preparado do HookLink2iOS.")
    if h.get("title_id")!=TITLE_ID or h.get("package_version_number")!=VERSION:
        die("Title ID/update do handoff incorretos.")
    if h.get("engine",{}).get("commit")!=ENGINE_PIN: die("Pin nxnative divergente.")
    if h.get("gpu_arch")!="none": die("HookLink segue Link2iOS: GPU none, sem arquivo PSO offline.")
    if h.get("builder",{}).get("iphoneos_deployment_target")!=IOS_DEPLOYMENT_TARGET:
        die("Handoff não fixa deployment target iOS 26.0.")
    for key in ("nup","work_archive","romfs","resolution_overlay"):
        record=h.get(key,{})
        if not record.get("id") or int(record.get("size",0))<=0 or not re.fullmatch(r"[0-9a-f]{64}",record.get("sha256","")):
            die(f"Registro {key} inválido no handoff.")
    if h.get("prepared",{}).get("engine_pin")!=ENGINE_PIN:
        die("Manifest Colab não foi preparado com o pin nxnative esperado.")
    sha=subprocess.check_output(["git","-C",str(args.engine),"rev-parse","HEAD"],text=True).strip()
    if sha!=ENGINE_PIN: die(f"Checkout nxnative divergente: {sha}")
    preflight_hooklink_engine(args.engine)

    rt=Path(os.environ.get("RUNNER_TEMP","/tmp"))
    work=rt/"hooklink2ios-work"; incoming=rt/"hooklink2ios-input"
    shutil.rmtree(work,ignore_errors=True); shutil.rmtree(incoming,ignore_errors=True)
    work.mkdir(parents=True); incoming.mkdir(parents=True)
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    drive,session=drive_client()

    # This is the key Link2iOS parity: Actions downloads the prepared workspace,
    # the standalone RomFS and the overlay. It never downloads the original NUP.
    archive=incoming/"hooklink2ios-work.tar.zst"
    download_verified(drive,session,h["work_archive"],archive)
    print("[HookLink2iOS] Restaurando workspace que já contém extração, rewrite AArch64 e shader split do Colab.")
    extract_verified_archive(archive,work)
    archive.unlink()
    prep_path=work/"hooklink2ios-linux-prep.json"
    if not prep_path.is_file(): die("Manifest hooklink2ios-linux-prep.json ausente no workspace.")
    prep=json.loads(prep_path.read_text(encoding="utf-8"))
    for key in ("project","title_id","package_version","engine_pin","shader_package_key","shader_chain","modules","romfs_relative_path"):
        if prep.get(key)!=h.get("prepared",{}).get(key):
            die(f"Handoff e workspace divergem em {key}.")
    if prep.get("project")!="HookLink2iOS" or prep.get("title_id")!=TITLE_ID or prep.get("package_version")!=f"v{VERSION}":
        die("Workspace preparado pertence a outro jogo ou update.")
    if prep.get("engine_pin")!=ENGINE_PIN: die("Workspace foi preparado por outro commit nxnative.")
    version_dir=work/"extract"/f"v{VERSION}"
    romfs=version_dir/"RomFS.img"
    if romfs.exists(): die("Workspace archive não deveria conter RomFS.img; o arquivo deve ser restaurado separadamente.")
    download_verified(drive,session,h["romfs"],romfs)
    overlay=out/"res_overlay"/"Pack"/"Bootup.Nin_Ounce_NVN2.pack.zs"
    download_verified(drive,session,h["resolution_overlay"],overlay)
    if int(romfs.stat().st_size)!=int(h["romfs"]["size"]): die("RomFS restaurado tem tamanho divergente.")
    if digest(romfs).lower()!=h["romfs"]["sha256"].lower(): die("SHA-256 do RomFS restaurado diverge do Colab.")
    identity=subprocess.check_output(
        [sys.executable,str(args.engine/"dm/tools/romfs_image.py"),"--identity",
         str(romfs),TITLE_ID,f"v{VERSION}",ENGINE_PIN],text=True).strip().splitlines()[-1]
    if identity!=h["romfs"].get("identity") or identity!=prep.get("romfs_identity"):
        die("Identidade do RomFS restaurado diverge do handoff/manifest Colab.")

    builder,game_profiles,nacp,pg=load_builder(args.engine)
    profile=game_profiles.by_title(int(TITLE_ID,16))
    if profile is None or str(profile.get("package") or "")!=f"v{VERSION}":
        die("Perfil Ocarina ausente ou update não registrado.")
    exefs=version_dir/"ExeFS"; patched=work/f"patched_v{VERSION}"
    shader_pkg=work/"shader"/"pkg"
    if not (exefs/"main").is_file() or not (patched/"main.patched.bin").is_file():
        die("Workspace não contém ExeFS e rewrite AArch64 completos.")
    modules=profile.modules_in(exefs)
    if modules!=prep.get("modules"): die("Módulos extraídos divergem do manifest Colab.")
    for name in modules:
        if not (patched/f"{name}.patched.bin").is_file() or not (patched/f"{name}.fixups.tsv").is_file():
            die(f"Rewrite/fixups ausentes para {name}.")
    if not shader_pkg.is_dir() or builder.package_key(shader_pkg)!=prep["shader_package_key"]:
        die("Conteúdo shader/pkg diverge da chave produzida no Colab.")

    logs=work/"logs"; logs.mkdir(parents=True,exist_ok=True)
    (work/"tmp").mkdir(parents=True,exist_ok=True)
    (work/"ipa").mkdir(parents=True,exist_ok=True)
    py=sys.executable
    env=builder.tool_env()
    env.setdefault("USER",os.environ.get("USER") or "runner")
    builder.configure_dotnet(env)
    env.update({"DM_GAME":TITLE_ID,"DM_ROOT":str(work),"WORK":str(work/"tmp"),
                "IOS_PULL":"1","IPHONEOS_DEPLOYMENT_TARGET":IOS_DEPLOYMENT_TARGET,"J":"1"})
    xlate=args.engine/"dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate"
    builder.PROG.mode="lines"; builder.PROG.plan(3)
    builder.check_prereqs(env,xlate,mac=False)
    builder.check_metal(py,args.engine,env)
    builder.chain_header(py,args.engine,env,logs)
    actual_chain=builder.chain_of(args.engine)
    if actual_chain!=prep["shader_chain"]: die("Shader chain no Actions difere daquela usada no split Colab.")

    romfs_source=builder.rfs.source(version_dir)
    facts=pg.build_sources(exefs,romfs_source,modules)
    if facts["graphics"][0]!="nvn": die(f"Graphics API inesperada para Ocarina: {facts['graphics'][0]}.")
    for flag in ("glslc_capture","vk_capture","gl_capture","ue_decode","oodle_packs","ue_legacy"):
        if facts.get(flag,(False,""))[0]:
            die(f"Ocarina exige etapa de captura/decoder não preparada no Colab: {flag}.")

    gpu=builder.ios_gpus("none",profile)
    if gpu!="none": die(f"Seleção GPU inesperada: {gpu}.")
    pull=builder.ios_wants_pulling(profile,gpu,False,env)
    if not pull: die("As bibliotecas iOS Metal de pulling são necessárias e não podem ser omitidas.")
    print("[HookLink2iOS] Compilando bibliotecas Metal iOS sobre o shader split validado do Colab...")
    ios_msl=builder.build_shaders(
        py,args.engine,work/"shader",xlate,env,logs,profile,
        pkg_key=prep["shader_package_key"],mac=False,seen=None,pull=pull)
    chain_lib=ios_msl/f"b-{actual_chain}"
    if not (chain_lib.is_dir() or Path(str(chain_lib)+".img").is_file()):
        die(f"Biblioteca Metal iOS ausente: {chain_lib}.")

    base_candidates=sorted(p for p in (work/"extract").iterdir()
                           if p.is_dir() and p.name.startswith("v") and p.name!="v"+str(VERSION))
    base_dir=next((p for p in base_candidates if (p/"control.nacp").is_file()),None)
    if base_dir is None: base_dir=version_dir
    control=builder.languages_control(version_dir,base_dir)
    app_name=nacp.name(base_dir/"control.nacp") or profile.get("name") or "Ocarina of Time"
    app_version=nacp.version(version_dir/"control.nacp") or "1.0"
    language=builder.game_language("en-US",False,nacp.languages(control))
    icon,stand_in=builder.app_icon(None,None,version_dir,base_dir)
    bundle_id=f"org.nxnative.{TITLE_ID.lower()}"
    aoc=work/"aoc"; aoc_dir=str(aoc) if aoc.is_dir() and any(aoc.iterdir()) else ""
    env_file=Path("hooklink/Resources/presets/iphone.env").resolve()
    entitlements=Path("hooklink/Resources/presets/entitlements.plist").resolve()
    if not env_file.is_file() or not entitlements.is_file(): die("Preset iPhone/entitlements HookLink ausentes.")
    ipa=out/"OcarinaOfTime-HookLink2iOS.ipa"
    ipa_env=dict(env,GAME=TITLE_ID,W=str(work/"ipa"),PATCHED=str(patched),ROMFS=str(romfs),
        MSL_IOS=str(ios_msl),GFXAPI="nvn",FONT_PY=py,DM_DISPLAY_NAME=app_name,
        DM_BUNDLE_ID=bundle_id,AOC=aoc_dir,DM_XCODE_DERIVED_DATA=str(work/"xcode-derived-data"),
        DM_TEAM_ID="0000000000",DM_LANG=language,CONTROL=str(control),DM_SHOW_FPS="1",
        DM_PSO_GPUS="none",DM_COPY_ROMFS="NO",DM_ENV_FILE=str(env_file),
        DM_ENTITLEMENTS=str(entitlements),IPHONEOS_DEPLOYMENT_TARGET=IOS_DEPLOYMENT_TARGET)
    if app_version: ipa_env["DM_APP_VERSION"]=app_version
    if icon: ipa_env["DM_ICON"]=str(icon)
    else: print("[HookLink2iOS] NUP/profile sem ícone próprio; o app usará ícone neutro.",flush=True)
    if aoc_dir: print("[HookLink2iOS] DLC/AOC validado será mantido junto ao app.",flush=True)

    print("[HookLink2iOS] Finalizando IPA nativa com o builder simplificado HookLink/nxnative (iOS 26.0, GPU none)...",flush=True)
    subprocess.run(["bash",str(args.engine/"dm/ios/tools/build_ipa.sh"),str(ipa)],
                   cwd=args.engine,env=ipa_env,check=True)
    if not ipa.is_file() or not ipa.stat().st_size: die("build_ipa.sh terminou sem IPA.")
    contents=audit_ipa(ipa,identity,actual_chain)
    report={
        "project":"HookLink2iOS","branch":BRANCH,"commit":os.environ.get("GITHUB_SHA"),
        "run_id":os.environ.get("GITHUB_RUN_ID"),"title_id":TITLE_ID,
        "package_version":f"v{VERSION}","engine_commit":ENGINE_PIN,
        "gpu_arch":"none","romfs_mode":"separate",
        "iphoneos_deployment_target":IOS_DEPLOYMENT_TARGET,
        "nup_source":{"name":h["nup"]["name"],"size":int(h["nup"]["size"]),
            "sha256":h["nup"]["sha256"],"downloaded_in_actions":False},
        "work_archive":{"name":h["work_archive"]["name"],"size":int(h["work_archive"]["size"]),
            "sha256":h["work_archive"]["sha256"],"verified":True},
        "prepared":{"shader_package_key":prep["shader_package_key"],
            "shader_chain":actual_chain,"modules":modules,
            "stages":prep["prepared_stages"]},
        "ipa":{"name":ipa.name,"size":ipa.stat().st_size,"sha256":digest(ipa),"contents":contents},
        "romfs":{"name":"romfs.img","size":romfs.stat().st_size,"sha256":digest(romfs),
            "identity":identity,"source":"Colab-prepared; external to IPA"},
        "resolution_overlay":{"name":overlay.name,"size":overlay.stat().st_size,
            "sha256":digest(overlay)},
    }
    (out/"build-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("[HookLink2iOS] IPA auditada: iOS 26.0, biblioteca Metal presente, sem PSO offline e sem RomFS embutido.",flush=True)
    print("HOOKLINK2IOS_BUILD_OK",flush=True)
    print(f"IPA={ipa} BYTES={ipa.stat().st_size}",flush=True)


if __name__=="__main__":
    main()
