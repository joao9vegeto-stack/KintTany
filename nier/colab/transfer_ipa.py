"""Retrieve only the latest successful Nier2iOS IPA, verify, and upload to Drive."""
import hashlib, json, os, re, time, zipfile
from pathlib import Path
import requests
from run_colab import drive_api, list_children, create_folder, upload_drive_file
REPO="joao9vegeto-stack/KintTany"
TITLE="010056B015FE8000"
FOLDER="11udbko06i5QvX930AiwR-VQ8Lu0bP39E"
CHUNK=64*1024*1024
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(8<<20),b""): h.update(b)
    return h.hexdigest()
def transfer(token):
    headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    api_url="https://api.github.com/repos/"+REPO
    def get(path,**kwargs):
        r=requests.get(api_url+path,headers=headers,timeout=60,**kwargs);r.raise_for_status();return r
    runs=get("/actions/workflows/nier.yml/runs",params={"branch":"Nier2iOS","status":"success","per_page":100}).json()["workflow_runs"]
    if not runs: raise RuntimeError("Ainda não existe build Nier2iOS bem-sucedido.")
    runs.sort(key=lambda x:(x["updated_at"],x["id"]),reverse=True)
    run=runs[0]
    arts=get(f"/actions/runs/{run['id']}/artifacts",params={"per_page":100}).json()["artifacts"]
    valid=[a for a in arts if a["name"]==f"Nier2iOS-NieRAutomata-{run['run_number']}" and not a["expired"]]
    if len(valid)!=1: raise RuntimeError("O último build não tem exatamente um artefato IPA disponível.")
    art=valid[0]; size=art["size_in_bytes"]; digest=art.get("digest","")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}",digest): raise RuntimeError("GitHub não informou SHA-256 do artefato.")
    work=Path("/content/nier-transfer")/str(art["id"]);work.mkdir(parents=True,exist_ok=True)
    archive=work/"artifact.zip"; partial=work/"artifact.zip.part"
    if not archive.exists() or archive.stat().st_size!=size or sha(archive)!=digest[7:]:
        if partial.exists() and partial.stat().st_size>size: partial.unlink()
        done=partial.stat().st_size if partial.exists() else 0
        while done<size:
            end=min(size,done+CHUNK)-1
            for attempt in range(5):
                try:
                    red=get(f"/actions/artifacts/{art['id']}/zip",allow_redirects=False)
                    url=red.headers["Location"]
                    with requests.get(url,headers={"Range":f"bytes={done}-{end}","Accept-Encoding":"identity"},stream=True,timeout=(30,180)) as resp:
                        if resp.status_code!=206 or resp.headers.get("Content-Range")!=f"bytes {done}-{end}/{size}": raise RuntimeError("Range inválido")
                        with partial.open("ab") as out:
                            for b in resp.iter_content(1<<20):out.write(b)
                    if partial.stat().st_size!=end+1:raise RuntimeError("Range incompleto")
                    break
                except Exception:
                    if partial.exists():
                        with partial.open("r+b") as out:out.truncate(done)
                    if attempt==4:raise
                    time.sleep(2**attempt)
            done=end+1;print(f"GitHub → Colab: {done/size:.1%} ({done/2**30:.2f} GiB)",flush=True)
        if sha(partial)!=digest[7:]:
            partial.unlink();raise RuntimeError("SHA-256 do artefato divergente")
        partial.replace(archive)
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        ipas=[n for n in names if n.endswith(".ipa") and not n.endswith("/")]
        reports=[n for n in names if Path(n).name=="build-report.json"]
        if len(ipas)!=1 or len(reports)!=1:raise RuntimeError("Artefato ambíguo")
        report=json.loads(z.read(reports[0]))
        if (report.get("project"),report.get("title_id"),report.get("package_version"),report.get("github_sha"))!=("Nier2iOS",TITLE,"v131072",run["head_sha"]):raise RuntimeError("Proveniência incompatível")
        if report.get("translation",{}).get("file_count",0)<1:raise RuntimeError("Tradução ausente")
        ipa=work/"Nier2iOS-NieRAutomata.ipa"
        with z.open(ipas[0]) as inp,ipa.open("wb") as out:
            for b in iter(lambda:inp.read(8<<20),b""):out.write(b)
    if ipa.stat().st_size!=report["ipa_size_bytes"] or sha(ipa)!=report["ipa_sha256"]:raise RuntimeError("IPA divergente do relatório")
    with zipfile.ZipFile(ipa) as z:
        prefix=f"Payload/DmShell.app/Frameworks/DmGame{TITLE}.framework/"
        names=z.namelist()
        assert "Payload/DmShell.app/DmShell" in names
        assert prefix+"game.manifest.json" in names
        manifest=json.loads(z.read(prefix+"game.manifest.json"))
        assert manifest["title_id"].upper()==TITLE and prefix+manifest["framework_executable"] in names
        config=json.loads(z.read(prefix+"dm/launcher.json"))
        assert any(s.get("env")=="DM_NIER_TRANSLATION" for s in config["settings"])
        assert not any(n.lower().endswith(("/romfs.img",".xci",".nsp","/prod.keys")) or "/aoc/" in n.lower() for n in names)
        assert z.testzip() is None
    drive=drive_api()
    dirs=[x for x in list_children(drive,FOLDER) if x["name"]=="ipa" and x.get("mimeType")=="application/vnd.google-apps.folder"]
    if len(dirs)>1:raise RuntimeError("Pasta ipa ambígua")
    folder=dirs[0]["id"] if dirs else create_folder(drive,"ipa",FOLDER)
    name=f"Nier2iOS-run{run['id']}-{report['ipa_sha256'][:12]}.ipa"
    result=upload_drive_file(drive,ipa,folder,name)
    print("IPA verificada:",result,"\nRun:",run["id"],"Commit:",run["head_sha"],flush=True)
    return result
