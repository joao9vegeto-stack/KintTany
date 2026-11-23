#!/usr/bin/env python3
"""A19 Pro Metal 4 offline pipeline archive from the proven original IPA.

Does not rewrite the game, decode NSP/NUP, or retranslate/recompile existing Metal shaders.
Metal metal-tt links PSO descriptions against the existing .metallib libraries.
"""
from __future__ import annotations
import argparse, hashlib, json, plistlib, shutil, subprocess, sys, zipfile
from pathlib import Path

TITLE="0400486024DEC000"
ENGINE_PIN="cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
APP="Payload/DmIOS.app/"
BLOCK=16*1024*1024

def die(msg): raise SystemExit("[HookLink2iOS PSO] "+msg)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(BLOCK),b""):h.update(b)
    return h.hexdigest()

def execute(argv):
    print("+", " ".join(map(str,argv)),flush=True)
    subprocess.run([str(x) for x in argv],check=True)

def extract(z,name,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with z.open(name) as f,path.open("wb") as out:
        shutil.copyfileobj(f,out,BLOCK)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True,type=Path)
    ap.add_argument("--engine",required=True,type=Path)
    ap.add_argument("--work",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--script-only",action="store_true")
    a=ap.parse_args()
    engine=a.engine.resolve()
    actual=subprocess.check_output(["git","-C",str(engine),"rev-parse","HEAD"],text=True).strip()
    if actual!=ENGINE_PIN:die("pinned old engine required, got "+actual)
    if a.source.stat().st_size<1_000_000_000:die("source IPA too small")
    work,out=a.work.resolve(),a.output.resolve()
    work.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.source) as z:
        marker=z.read(APP+"romfs.id").decode("utf-8","replace").strip()
        fields=dict(p.split("=",1) for p in marker.split()[1:] if "=" in p)
        if (not marker.startswith("DMROMFSID1 ") or fields.get("title")!=TITLE
            or fields.get("size")!="26247576430" or fields.get("index")!="b6a3def414e47ca5"):
            die("IPA RomFS differs from the validated original handoff")
        plist=plistlib.loads(z.read(APP+"Info.plist"))
        if str(plist.get("MinimumOSVersion"))!="26.0":die("expected iOS 26")
        import re
        images=[x for x in z.namelist() if re.fullmatch(r"Payload/DmIOS\.app/msl/b-[^/]+\.img(?:\.[0-9]+)?",x)]
        if not images:die("missing NVN/Metal image")
        stems={x.rsplit(".img",1)[0]+".img" for x in images}
        if len(stems)!=1:die("multiple NVN/Metal image chains; aborting")
        stem=stems.pop()
        if images==[stem]:
            ordered=[stem]
        else:
            bypart={}
            for x in images:
                suffix=x[len(stem):]
                if not suffix.startswith(".") or not suffix[1:].isdigit() or x==stem:
                    die("unexpected mixed Metal image part: "+x)
                bypart[int(suffix[1:])]=x
            if len(bypart)!=len(images) or set(bypart)!=set(range(len(images))) or len(images)<2:
                die("missing/duplicate split Metal image part")
            ordered=[bypart[i] for i in range(len(images))]
        dest=work/"msl"/Path(stem).name
        target_size=sum(z.getinfo(x).file_size for x in ordered)
        if not dest.exists() or dest.stat().st_size!=target_size:
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_suffix(".img.partial")
            with temp.open("wb") as out:
                for image in ordered:
                    with z.open(image) as part:
                        shutil.copyfileobj(part,out,BLOCK)
            if temp.stat().st_size!=target_size:
                temp.unlink(missing_ok=True)
                die("Metal image reassembled incorrectly")
            temp.replace(dest)
        print("[HookLink2iOS PSO] extracted unchanged Metal image; split parts:",len(ordered),"bytes:",target_size,flush=True)
        pairs={}
        for name in ("shader_pairs.tsv","pso_pairs.tsv","shader_map.tsv","pso_manifest.tsv"):
            member=APP+"dm/"+name
            if member not in z.namelist():die("source IPA missing "+name)
            path=work/"tables"/name
            extract(z,member,path)
            same=engine/"dm"/"games"/TITLE/name
            if not same.is_file() or same.read_bytes()!=path.read_bytes():
                die("profile table is not identical to the pinned original engine: "+name)
            pairs[name]=path
    sys.path.insert(0,str(engine/"dm"/"tools"))
    import shader_lib
    if shader_lib.left_out_pulling(dest):
        die("original IPA lacks pulling vertex Metal libraries; full shader build would be required")
    command=[sys.executable,engine/"dm"/"gfx"/"tools"/"pso_offline.py",
             "--msl",dest.with_suffix(""),"--out",out,"--work",work/"psowork",
             "--pairs",pairs["shader_pairs.tsv"],"--pairs",pairs["pso_pairs.tsv"],
             "--shader-map",pairs["shader_map.tsv"],"--manifest",pairs["pso_manifest.tsv"],
             "--depth","gl","--gpu","g18p","--platform","ios","--os-min","26.0",
             "--batch-size","400","--jobs","1"]
    execute(command+["--script-only"])
    plan=json.loads((work/"psowork"/"bases.mtl4-json").read_text(encoding="utf-8"))
    desc=plan["pipeline_descriptors"]
    render=len(desc.get("render_pipeline_descriptors",[]))
    compute=len(desc.get("compute_pipeline_descriptors",[]))
    print(f"[HookLink2iOS PSO] plan: {render} GPU render pipelines, {compute} compute pipelines",flush=True)
    if render<10:die("not enough safe pipeline bases in the original shader libraries")
    if a.script_only:return
    execute(command)
    archive=out/"applegpu_g18p.mtl4a"
    stamp=out/"prebuilt.tsv"
    if not archive.is_file() or archive.stat().st_size<1024 or not stamp.is_file():
        die("A19 Pro PSO artifact incomplete")
    report={"project":"HookLink2iOS","gpu":"applegpu_g18p",
            "source_engine":ENGINE_PIN,"source_ipa_sha256":digest(a.source),
            "psos_render":render,"psos_compute":compute,
            "archive_size":archive.stat().st_size,"archive_sha256":digest(archive),
            "metal_shaders_recompiled":False,"game_rewritten":False,
            "ios_minimum":"26.0"}
    (out/"pso-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)
    print("HOOKLINK2IOS_PSO_OK",flush=True)

if __name__=="__main__":main()
