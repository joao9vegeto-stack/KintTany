"""Apply the US/Asia LayeredFS translation to the actual indexed RomFS before shader discovery."""
import hashlib, json, os, shutil, stat, zipfile
from pathlib import Path, PurePosixPath

ASIA="0100B8E016F76000"
USA="010056B015FE8000"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as inp:
        for chunk in iter(lambda:inp.read(8<<20),b""): h.update(chunk)
    return h.hexdigest()

def mod_files(z):
    result={}
    roots=set()
    for member in z.infolist():
        name=member.filename.replace("\\","/")
        if name.startswith("/") or any(x==".." for x in name.split("/")) or (member.external_attr>>16)&0o170000==stat.S_IFLNK:
            raise ValueError("Unsafe ZIP path")
        parts=PurePosixPath(name).parts
        ids=[i for i,x in enumerate(parts) if x.upper() in (ASIA,USA)]
        if not ids: continue
        i=ids[-1]
        if len(parts)<=i+1: continue
        if parts[i+1].lower()=="exefs" and not member.is_dir():
            raise ValueError("Translation contains ExeFS modifications; manual audit required")
        if parts[i+1].lower()!="romfs" or member.is_dir(): continue
        roots.add(parts[i].upper())
        rel="/".join(parts[i+2:])
        if not rel or rel in result: raise ValueError("Duplicate/empty translation member: "+rel)
        result[rel]=member
    if len(roots)!=1 or not result:
        raise ValueError("Expected exactly one Asia or USA Title ID / romfs subtree")
    return result,next(iter(roots))

def apply_translation(directory,archive,title,version):
    import romfs_image as ri
    directory=Path(directory); archive=Path(archive)
    if title!=USA or version!="v131072": raise ValueError("Translation version/title mismatch")
    image=directory/"RomFS.img"
    identity=directory/"RomFS.img.id"
    original=directory/"RomFS.original.img"
    original_id=directory/"RomFS.original.img.id"
    report_path=directory/"translation-report.json"
    zip_hash=sha256(archive)
    if report_path.is_file() and original.is_file() and image.is_file() and identity.is_file():
        old=json.loads(report_path.read_text())
        if old.get("zip_sha256")==zip_hash and old.get("sha256")==sha256(image) and old.get("sha256")==json.loads(identity.read_text()).get("sha256"):
            return old
    if not original.exists():
        image.replace(original)
        if identity.exists(): shutil.copy2(identity,original_id)
    elif not original_id.exists():
        raise RuntimeError("Original RomFS metadata absent")
    with zipfile.ZipFile(archive) as z:
        mods,source_title=mod_files(z)
        index=ri.read_index(original)
        original_files={k:v for k,v in index.items() if not v[0]}
        unknown=set(mods)-set(original_files)
        if unknown: raise ValueError("Translation contains paths absent from US RomFS: "+str(sorted(unknown)[:20]))
        if shutil.disk_usage(directory).free < original.stat().st_size+sum(x.file_size for x in mods.values()):
            raise RuntimeError("Insufficient space to rebuild translated RomFS")
        # Preserve directory layout, filenames and every unmodified byte.
        children={}
        for path,(isdir,off,size) in index.items():
            parent,_,name=path.rpartition("/")
            children.setdefault(parent,[]).append((name,path,isdir))
        entries=[[b"","",True,0,0]]
        i=0
        while i<len(entries):
            _,path,isdir,_,_=entries[i]
            if isdir:
                kids=sorted(children.get(path,[]),key=lambda x:x[0].encode())
                entries[i][3:]=[len(entries),len(kids)]
                entries.extend([[name.encode(),p,d,0,0] for name,p,d in kids])
            i+=1
        changed={}
        with original.open("rb") as inp:
            def copy(path,out):
                if path in mods:
                    member=mods[path]; h=hashlib.sha256(); total=0
                    with z.open(member) as source:
                        for block in iter(lambda:source.read(8<<20),b""):
                            out.write(block); h.update(block); total+=len(block)
                    if total!=member.file_size: raise ValueError("Translation member truncated")
                    changed[path]={"bytes":total,"sha256":h.hexdigest()}
                    return total
                _,off,size=original_files[path]
                inp.seek(off); left=size
                while left:
                    block=inp.read(min(left,8<<20))
                    if not block: raise ValueError("Original RomFS truncated")
                    out.write(block); left-=len(block)
                return size
            partial=Path(ri.write(entries,str(image),copy))
        new_index=ri.read_index(partial)
        if set(new_index)!=set(index): raise ValueError("RomFS inventory changed")
        with partial.open("rb") as inp:
            for path,record in changed.items():
                _,off,size=new_index[path]
                inp.seek(off); h=hashlib.sha256(); left=size
                while left:
                    block=inp.read(min(left,8<<20))
                    if not block: raise ValueError("Repacked translation truncated")
                    h.update(block); left-=len(block)
                if size!=record["bytes"] or h.hexdigest()!=record["sha256"]: raise ValueError("Translation verification failed")
        digest=sha256(partial)
        meta=json.loads(original_id.read_text())
        meta.update(bytes=partial.stat().st_size,sha256=digest,title=title.lower(),version=version)
        partial.replace(image)
        identity.write_text(json.dumps(meta,indent=2)+"\n")
        report={"title_id":title,"version":version,"language":"pt-BR","source_title":source_title,"zip_sha256":zip_hash,"sha256":digest,"file_count":len(changed),"files":changed}
        report_path.write_text(json.dumps(report,indent=2)+"\n")
        # Cached shader source survey must reflect the translated image.
        for name in ("RomFS.img.sources","RomFS.img.formats"):
            (directory/name).unlink(missing_ok=True)
        print("Tradução PT-BR aplicada e verificada:",len(changed),"arquivos",flush=True)
        return report
