#!/usr/bin/env python3
"""Rebuild the X3 host from the verified successful 4.0 IPA, never retranslate guest shaders."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import hooklink2ios_native_relink as native
import hooklink2ios_perf_repack as repack
import hooklink2ios_v4_build as v4
import hooklink2ios_x3_recovery as recovery

RUN="45214405727"
SOURCE_HEAD="c2aa86b2172ad337e811ff2c43ca695c59d55ff4"
CHAIN="b6112b954691"
PREFIX="Payload/DmIOS.app/"

def require(value,message):
    if not value:
        raise RuntimeError(message)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",type=Path,required=True)
    p.add_argument("--engine",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    require(sys.platform=="darwin","native iOS host relink requires macOS")
    require(os.environ.get("GITHUB_REF")=="refs/heads/HookLink2iOS","wrong branch")
    v4.verify_v4_engine(a.engine)
    report_files=list(a.artifact.rglob("build-report.json"))
    ipas=list(a.artifact.rglob("*.ipa"))
    require(len(report_files)==1 and len(ipas)==1,"source artifact does not have exactly one IPA and report")
    report=json.loads(report_files[0].read_text())
    source=ipas[0]
    require(str(report.get("run_id"))==RUN and report.get("commit")==SOURCE_HEAD,"wrong source build")
    require(report.get("engine_commit")==v4.UPSTREAM_PIN and report.get("hooklink_release")=="4.0","wrong X3 engine/release")
    require(report.get("shader_chain")==CHAIN and report.get("original_1_8_shader_image_reused") is False,"wrong shader chain")
    require(report.get("gpu_arch")=="none" and report.get("romfs_mode")=="separate","source is not thin")
    require(native.sha256(source)==report["ipa"]["sha256"] and source.stat().st_size==report["ipa"]["size"],"source IPA hash/size mismatch")
    a.output.mkdir(parents=True,exist_ok=True)
    work=a.output.parent/"host-work"
    work.mkdir(parents=True,exist_ok=True)
    original=work/"original-DmIOS"
    origdm=work/"original_dm"; origdm.mkdir(exist_ok=True)
    patches=work/"original_rewritten"; patches.mkdir(exist_ok=True)
    with zipfile.ZipFile(source) as z:
        marker,images=repack.audit(z)
        require(marker==report["ipa"]["contents"]["romfs_marker"],"source RomFS marker differs from report")
        require(all("/msl/b-"+CHAIN+".img" in name for name in images),"source contains another shader image")
        plist=plistlib.loads(z.read(PREFIX+"Info.plist"))
        native.extract_member(z,PREFIX+"DmIOS",original,1_500_000_000)
        for info in z.infolist():
            if info.filename.startswith(PREFIX+"dm/") and not info.is_dir():
                rel=info.filename[len(PREFIX+"dm/"):]
                require(rel and ".." not in Path(rel).parts and "\\" not in rel,"bad source resource path")
                native.extract_member(z,info.filename,origdm/rel,256*1024*1024)
        guest=native.extract_guest_sections(original,source,z,patches)
    changes=recovery.apply(a.engine)
    print("X3 source changes:",changes,flush=True)
    executable,buildlog,checked=native.generate_and_build(a.engine,work,patches,plist,original)
    output=a.output/"OcarinaOfTime-HookLink2iOS-X3-Recovery.ipa"
    internal=a.output/"repack-report.json"
    # Do not lock the launcher: all modes remain selectable. Stop full pair scanning
    # by default, retain the original prewarm manifest and all existing graphics controls.
    repack.PRESETS={"x3-recovery":{"DM_FRAME_MODE":"1","DM_FPS_TARGET":"30","DM_FRAMEGEN":"0","DM_PSO_PREBUILD":"0"}}
    sys.argv=["hooklink2ios_perf_repack.py","--source",str(source),"--replacement-executable",str(executable),"--preset","x3-recovery","--output",str(output),"--report",str(internal)]
    repack.main()
    audit=json.loads(internal.read_text())
    audit["native_host_relinked"]["source"]="pinned original X3 host with source-level recovery patch"
    internal.write_text(json.dumps(audit,indent=2)+"\n")
    with zipfile.ZipFile(output) as z:
        newmarker,newimages=repack.audit(z)
        require(newmarker==marker and newimages==images,"RomFS or Metal image changed")
        contents=report["ipa"]["contents"].copy()
        contents["romfs_marker"]=newmarker
    report.update(commit=os.environ["GITHUB_SHA"],run_id=os.environ["GITHUB_RUN_ID"],
                  native_recovery={"source_run":RUN,"source_commit":SOURCE_HEAD,"source_ipa_sha256":native.sha256(source),
                  "changes":changes,"guest_section_hashes_verified":checked,"shader_images_preserved":True,
                  "original_game_shaders_recompiled":False,"game_code_rewritten":False,
                  "native_executable_sha256":audit["native_host_relinked"]["signed_executable_sha256"]},
                  ipa={"name":output.name,"size":output.stat().st_size,"sha256":native.sha256(output),"contents":contents})
    (a.output/"build-report.json").write_text(json.dumps(report,indent=2)+"\n")
    overlays=list(a.artifact.rglob("Bootup.Nin_Ounce_NVN2.pack.zs"))
    require(len(overlays)==1 and native.sha256(overlays[0])==report["resolution_overlay"]["sha256"],"verified overlay missing")
    dst=a.output/"res_overlay/Pack";dst.mkdir(parents=True,exist_ok=True)
    shutil.copy2(overlays[0],dst/overlays[0].name)
    print("HOOKLINK2IOS_X3_RECOVERY_HOST_ONLY_OK",output.stat().st_size,report["ipa"]["sha256"],flush=True)

if __name__=="__main__":
    main()
