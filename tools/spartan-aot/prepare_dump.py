#!/usr/bin/env python3
"""Prepare the supplied PS4 dump for the gow3-macos-arm64 AOT pipeline.

This performs container validation and plaintext SELF reconstruction only. It
never decrypts SELF entries and refuses encrypted/compressed payloads.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, struct, zipfile
from pathlib import Path

MAX_ELF = 512 * 1024 * 1024
SELF_MAGICS = (b"\x4f\x15\x3d\x1d", b"SCE\0")

def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]
def u64(b, o): return struct.unpack_from("<Q", b, o)[0]
def sha256(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def safe_extract(zf, dest):
    root=dest.resolve()
    for info in zf.infolist():
        name=info.filename.replace("\\","/")
        target=(dest/name).resolve()
        if not target.is_relative_to(root): raise ValueError(f"ZIP path traversal: {info.filename}")
        if info.flag_bits & 1: raise ValueError(f"ZIP entry encrypted: {info.filename}")
        if info.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with zf.open(info) as src, open(target,"wb") as out: shutil.copyfileobj(src,out)

def find_file(root, basename):
    hits=[p for p in root.rglob("*") if p.is_file() and p.name.lower()==basename.lower()]
    if len(hits)!=1: raise ValueError(f"Esperado exatamente um {basename}; encontrados: {len(hits)}")
    return hits[0]

def reconstruct_self(data: bytes) -> tuple[bytes,dict]:
    if data[:4]==b"\x7fELF":
        return data, {"format":"ELF64 x86-64 (input already ELF)","segments":0}
    if data[:4] not in SELF_MAGICS or len(data)<0x20: raise ValueError("eboot.bin não é ELF nem SELF PS4 reconhecido")
    header_size=u16(data,0x0c); declared=u64(data,0x10); count=u16(data,0x18)
    if not 0<count<=1024: raise ValueError("SELF entry count inválido")
    table_end=0x20+count*0x20
    if table_end>len(data) or header_size<table_end or header_size>len(data) or not header_size<=declared<=len(data):
        raise ValueError("SELF entry table/header size inválido")
    entries=[]
    for i in range(count):
        o=0x20+i*0x20
        props,off,stored,unpacked=struct.unpack_from("<QQQQ",data,o)
        if off+stored>declared: raise ValueError(f"SELF entry {i} ultrapassa o arquivo")
        ent={"i":i,"props":props,"off":off,"stored":stored,"unpacked":unpacked,
             "encrypted":bool(props&(1<<1)),"compressed":bool(props&(1<<3)),
             "blocks":bool(props&(1<<11)),"seg":(props>>20)&0xffff}
        entries.append(ent)
    # SELF entries are payload extents, not a reliable program-header index.
    # Match them to ELF program headers by the declared payload size, as the
    # established PS4 unfself layout does. The previous segment-index mapping
    # incorrectly treated the HAS_META bit as a 16-bit segment number.
    elf_off=-1
    for pos in range(table_end,min(len(data)-64,0x10000)+1):
        if data[pos:pos+4]!=b"\x7fELF": continue
        if data[pos+4:pos+7]!=b"\x02\x01\x01" or u16(data,pos+18)!=0x3e: continue
        phoff=u64(data,pos+32); es=u16(data,pos+54); n=u16(data,pos+56)
        if es>=56 and 0<n<=1024 and pos+phoff+es*n<=len(data): elf_off=pos; break
    if elf_off<0: raise ValueError("ELF interno não encontrado no SELF")
    phoff=u64(data,elf_off+32); es=u16(data,elf_off+54); n=u16(data,elf_off+56)
    phstart=elf_off+phoff; phend=phstart+es*n
    if phend>len(data): raise ValueError("Program header table inválida")
    ph=[]
    outsize=64+es*n
    for i in range(n):
        o=phstart+i*es; typ=u32(data,o); off=u64(data,o+8); fs=u64(data,o+32); ms=u64(data,o+40)
        if typ==1 and fs>ms: raise ValueError("PT_LOAD filesz > memsz")
        if fs:
            if off+fs>MAX_ELF: raise ValueError("ELF reconstruído excede 512 MiB")
            outsize=max(outsize,off+fs)
        ph.append({"i":i,"type":typ,"off":off,"fs":fs})
    out=bytearray(outsize); out[:64]=data[elf_off:elf_off+64]
    out[64:64+es*n]=data[phstart:phend]
    used=set(); mapped=[]
    # The SELF table is followed by version/certification data. Some ELF
    # metadata program headers (notably PT_SCE_COMMENT) are backed by this
    # trailing extent rather than a normal segment-table entry.
    tail_off=max((e["off"]+e["stored"] for e in entries), default=header_size)
    payloads=[]
    for e in entries:
        payloads.append({**e,"payload":data[e["off"]:e["off"]+e["stored"]]})
    if tail_off < len(data):
        payloads.append({"i":-1,"off":tail_off,"stored":len(data)-tail_off,
                         "unpacked":len(data)-tail_off,"encrypted":False,
                         "compressed":False,"payload":data[tail_off:]})
    def covered(h): return any(a<=h["off"] and b>=h["off"]+h["fs"] for a,b in mapped)
    def place(h, payload):
        if len(payload)!=h["fs"]: raise ValueError(f"Tamanho incompatível no segmento {h['i']}")
        out[h["off"]:h["off"]+h["fs"]]=payload; mapped.append((h["off"],h["off"]+h["fs"]))
    def place_entry(h):
        candidates=[e for e in payloads if e["i"] not in used and
                    (e["stored"]==h["fs"] or e["unpacked"]==h["fs"])]
        usable=[e for e in candidates if not e["encrypted"] and not e["compressed"]]
        if usable:
            e=usable[0]
            place(h,e["payload"][:h["fs"]]); used.add(e["i"]); return
        if candidates:
            e=candidates[0]
            reason="criptografada" if e["encrypted"] else "compactada"
            raise ValueError(f"SELF entry {e['i']} para segmento {h['i']} está {reason}; não é seguro reconstruir sem descriptografia/descompressão")
        start=elf_off+h["off"]; end=start+h["fs"]
        if end<=len(data): place(h,data[start:end]); return
        sizes=sorted({e["stored"] for e in payloads if e["i"] not in used})
        raise ValueError(f"Sem payload SELF de tamanho 0x{h['fs']:x} para program header {h['i']}; tamanhos disponíveis: {sizes[:24]}")
    for h in ph:
        if h["fs"] and not covered(h): place_entry(h)
    for h in ph:
        if h["fs"] and not covered(h): raise ValueError(f"Segmento {h['i']} não foi reconstruído")
    return bytes(out),{"format":"PS4 SELF -> ELF64 x86-64","program_headers":n,
                       "pt_load":sum(1 for h in ph if h["type"]==1 and h["fs"]),
                       "elf_bytes":len(out),"self_entries":count,"mapping":"SELF payload extents matched to ELF program headers by exact file size"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--eboot",required=True); ap.add_argument("--assets-zip",required=True); ap.add_argument("--out",required=True)
    a=ap.parse_args(); eboot=Path(a.eboot); archive=Path(a.assets_zip); out=Path(a.out)
    if not eboot.is_file() or not archive.is_file(): raise SystemExit("eboot.bin ou G3.zip ausente")
    if out.exists(): shutil.rmtree(out)
    game=out/"game"; game.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zf: safe_extract(zf,game)
    param=find_file(game,"param.sfo")
    psf=param.read_bytes()
    if not psf.startswith(b"\0PSF"): raise ValueError("param.sfo sem magic PSF")
    module_records=[]
    for name in ("libc.prx","libSceFios2.prx"):
        p=find_file(game,name)
        raw=p.read_bytes()
        try:
            module_elf,module_meta=reconstruct_self(raw)
        except Exception as exc:
            raise ValueError(f"{name}: magic={raw[:16].hex()} bytes={len(raw)}; ELF plaintext indisponível: {exc}") from exc
        target=game/"sce_module"/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(module_elf)
        module_records.append({"name":name,"path":"game/sce_module/"+name,
          "input_bytes":len(raw),"input_magic":raw[:16].hex(),
          "output_bytes":len(module_elf),"sha256":hashlib.sha256(module_elf).hexdigest(),**module_meta})
    target_sfo=game/"sce_sys"/"param.sfo"; target_sfo.parent.mkdir(parents=True,exist_ok=True)
    if param.resolve()!=target_sfo.resolve(): shutil.copy2(param,target_sfo)
    elf,meta=reconstruct_self(eboot.read_bytes())
    elf_path=game/"eboot.bin"; elf_path.write_bytes(elf)
    manifest={"eboot":{"path":str(eboot),"bytes":eboot.stat().st_size,"sha256":sha256(eboot)},
      "assets_zip":{"path":str(archive),"bytes":archive.stat().st_size,"sha256":sha256(archive)},
      "prepared_elf":{"path":"game/eboot.bin","bytes":len(elf),"sha256":hashlib.sha256(elf).hexdigest(),**meta},
      "validated_modules":module_records,
      "param_sfo":"game/sce_sys/param.sfo"}
    (out/"input-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))
if __name__=="__main__":
    try: main()
    except Exception as exc: raise SystemExit(f"prepare_dump: {exc}")
