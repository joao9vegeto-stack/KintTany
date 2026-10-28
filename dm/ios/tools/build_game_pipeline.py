import os, sys, re, struct, shutil, subprocess, lz4.block
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import *

rt  = Path(os.environ["RUNNER_TEMP"]).resolve()
kit = rt / "kit"
exefs   = kit / "ExeFS"
romfs   = kit / "RomFS"
romfs.mkdir(parents=True, exist_ok=True)
manifest = kit / "romfs_manifest.tsv"

# ── 1. TitleID ──────────────────────────────────────────────────────────────
tid_str   = "010035F022078000"
npdm_file = exefs / "main.npdm"
if npdm_file.exists():
    npdm    = npdm_file.read_bytes()
    aci0    = struct.unpack_from("<I", npdm, 0x70)[0]
    tid     = struct.unpack_from("<Q", npdm, aci0 + 0x10)[0]
    tid_str = f"{tid:016X}"
print(f"=== TitleID detectado: {tid_str} ===", flush=True)

# ── 2. Nome e versão ─────────────────────────────────────────────────────────
game_title = f"SwitchGame_{tid_str}"
game_ver   = "1.0"
nacp_files = list(kit.rglob("*.nacp"))
if nacp_files:
    nacp_path = nacp_files[0]
    try:
        res_name = subprocess.run(
            ["python3", "dm/tools/nacp.py", str(nacp_path)],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        if res_name:
            game_title = res_name
    except Exception:
        pass
    try:
        res_ver = subprocess.run(
            ["python3", "dm/tools/nacp.py", "--version", str(nacp_path)],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        if res_ver:
            game_ver = res_ver
    except Exception:
        pass
elif tid_str == "010035F022078000":
    game_title = "DRAGON BALL: Sparking! ZERO"

safe_name    = re.sub(r"[^A-Za-z0-9]+", "_", game_title).strip("_") or tid_str
ipa_filename = f"{safe_name}.ipa"
print(f"=== Jogo: '{game_title}' v{game_ver} -> {ipa_filename} ===", flush=True)

games_dir   = Path("dm/games").resolve()
game_py     = games_dir / "game.py"
sample_tsvs = sorted(games_dir.glob("*/game.tsv"))

# ── 3. Módulos NSO ───────────────────────────────────────────────────────────
order = ["main","subsdk0","subsdk1","subsdk2","subsdk3","subsdk4",
         "subsdk5","subsdk6","subsdk7","subsdk8","subsdk9","sdk"]
mods = []
for m in order:
    p = exefs / m
    if p.is_file() and p.read_bytes()[:4] == b"NSO0":
        mods.append(m)
for p in sorted(exefs.iterdir()):
    if p.is_file() and p.name not in mods and p.name not in ("main.npdm","rtld") \
       and p.read_bytes()[:4] == b"NSO0":
        mods.append(p.name)
print(f"=== Módulos NSO (sem rtld): {mods} ===", flush=True)

# ── 4. Descomprime main (NSO format correto) ─────────────────────────────────
main_bytes = (exefs / "main").read_bytes()
main_bid   = main_bytes[0x40:0x50].hex()
print(f"=== Build ID: {main_bid} ===", flush=True)

# Header NSO real:
# 0x0C = flags (bit i = segmento i está comprimido)
# Segmento i começa em 0x10 + i*0x10:
#   +0x00 = file_offset (u32)
#   +0x04 = mem_offset  (u32)
#   +0x08 = decomp_size (u32)  ← tamanho DESCOMPRIMIDO
#   +0x0C = align/extra (u32)  ← ignorar
# Tamanhos comprimidos ficam em 0x60 + i*4

flags = struct.unpack_from("<I", main_bytes, 0x0C)[0]

segs = []
for i in range(3):
    base = 0x10 + i * 0x10
    file_off  = struct.unpack_from("<I", main_bytes, base + 0x00)[0]
    mem_off   = struct.unpack_from("<I", main_bytes, base + 0x04)[0]
    decomp_sz = struct.unpack_from("<I", main_bytes, base + 0x08)[0]
    segs.append((file_off, mem_off, decomp_sz))

csz = struct.unpack_from("<III", main_bytes, 0x60)

# Diagnóstico
for i, (fo, mo, sz) in enumerate(segs):
    print(f"  seg[{i}]: file_off=0x{fo:x} mem_off=0x{mo:x} "
          f"mem_sz=0x{sz:x} csz=0x{csz[i]:x} compressed={(flags>>i)&1}", flush=True)

# Valida que os offsets fazem sentido
if segs[0][0] < 0x100:
    print("[patch] FATAL: file_off do seg[0] invalido — header NSO corrompido ou formato inesperado")
    sys.exit(1)

# Monta imagem descomprimida
img_size = max(mo + sz for (fo, mo, sz) in segs)
img = bytearray(img_size)

for i, (fo, mo, sz) in enumerate(segs):
    comp_sz = csz[i]
    raw = main_bytes[fo : fo + comp_sz]
    if (flags >> i) & 1:
        raw = lz4.block.decompress(raw, uncompressed_size=sz)
    if len(raw) < sz:
        print(f"[patch] AVISO: seg[{i}] raw={len(raw):#x} < sz={sz:#x}, padding com zeros")
        raw = raw + bytes(sz - len(raw))
    img[mo : mo + sz] = raw[:sz]

print(f"=== Imagem descomprimida: {img_size:#x} bytes ===", flush=True)

# Disassembla
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True
insns_all = list(md.disasm(bytes(img), 0))
print(f"=== Instruções disassembladas: {len(insns_all)} ===", flush=True)

if len(insns_all) < 1000:
    print(f"[patch] FATAL: apenas {len(insns_all)} instrucoes — imagem invalida")
    sys.exit(1)

by_addr = {i.address: i for i in insns_all}

# ── Detector dinâmico pela vtable 0x92fa000 ──────────────────────────────────
VTABLE_PAGE = 0x92fa000 & ~0xFFF   # página base do adrp
NOP_WORD    = b"\x1f\x20\x03\xd5"

def sign_extend(v, bits):
    s = 1 << (bits - 1)
    return (v & (s - 1)) - (v & s)

def decode_bl(word, pc):
    if (word & 0xFC000000) != 0x94000000:
        return None
    return pc + sign_extend((word & 0x03FFFFFF) << 2, 28)

def rnum(name):
    if not name:
        return None
    m2 = re.fullmatch(r"[xw](\d+)", name.lower())
    return int(m2.group(1)) if m2 and int(m2.group(1)) <= 30 else None

insns_all = list(md.disasm(bytes(img), 0))
by_addr   = {i.address: i for i in insns_all}
print(f"=== Instruções disassembladas: {len(insns_all)} ===", flush=True)

# Acha construtor: adrp -> vtable_page, add, str xVT,[xThis]
ctor_candidates = []
for idx, insn in enumerate(insns_all):
    if insn.mnemonic != "adrp" or len(insn.operands) < 2:
        continue
    dst = rnum(insn.reg_name(insn.operands[0].reg))
    if dst is None or insn.operands[1].imm != VTABLE_PAGE:
        continue
    tracked = dst
    for j in range(idx + 1, min(idx + 16, len(insns_all))):
        ii = insns_all[j]
        if ii.mnemonic == "str" and len(ii.operands) >= 2:
            src  = rnum(ii.reg_name(ii.operands[0].reg))
            base = rnum(ii.reg_name(ii.operands[1].mem.base))
            if src == tracked and base is not None:
                func_start = insn.address
                for k in range(idx, max(-1, idx - 256), -1):
                    kk = insns_all[k]
                    if kk.mnemonic == "stp":
                        ops = [kk.reg_name(o.reg).lower() if o.type == ARM64_OP_REG else "" for o in kk.operands]
                        if "x29" in ops and "x30" in ops:
                            func_start = kk.address
                            break
                ctor_candidates.append({"func": func_start, "this_reg": base,
                                        "score": 100 - min(abs(ii.operands[1].mem.disp), 32)})
                break

if not ctor_candidates:
    print("[patch] FATAL: construtor nao encontrado pela vtable"); sys.exit(1)

ctor_candidates.sort(key=lambda x: (-x["score"], x["func"]))
ctor = ctor_candidates[0]
print(f"=== Construtor: func=0x{ctor['func']:x} this_reg=x{ctor['this_reg']} ===", flush=True)

# Acha BL que chama o construtor
bls = []
for off in range(0, len(img) - 4, 4):
    w = struct.unpack_from("<I", img, off)[0]
    t = decode_bl(w, off)
    if t is not None and ctor["func"] <= t <= ctor["func"] + 0x40:
        bls.append(off)

if not bls:
    print("[patch] FATAL: nenhum BL para o construtor"); sys.exit(1)

best_cut = None
best_score = -1
for bl in bls:
    obj_reg = ctor["this_reg"]
    score   = 0
    for a in range(max(0, bl - 0x80), bl, 4):
        ii = by_addr.get(a)
        if not ii:
            continue
        if ii.mnemonic == "mov" and len(ii.operands) >= 2:
            d = rnum(ii.reg_name(ii.operands[0].reg))
            s = rnum(ii.reg_name(ii.operands[1].reg))
            if d == 0 and s is not None:
                obj_reg = s
                score  += 50 + (25 if s in range(19, 29) else 0)
                break
    score += 12 if obj_reg in (19, 28) else 0
    if score > best_score:
        best_score = score
        best_cut   = {"cut": bl, "obs": bl + 4, "obj_reg": obj_reg, "ctor": ctor["func"]}

cut_addr      = best_cut["cut"]
obs_addr      = best_cut["obs"]
cut_orig_hex  = img[cut_addr:cut_addr+4].hex()
obs_orig_word = f"{struct.unpack_from('<I', img, obs_addr)[0]:08x}"
print(f"=== CUT=0x{cut_addr:x} ({cut_orig_hex}) OBS=0x{obs_addr:x} ({obs_orig_word}) OBJ_REG=x{best_cut['obj_reg']} ===", flush=True)

# ── 5. Resto do pipeline (idêntico ao original) ───────────────────────────────
def dump(lo, hi, tag):
    print(f"=== [{tag}] 0x{lo:x}..0x{hi:x} ===", flush=True)
    for i2 in md.disasm(bytes(img[lo:hi]), lo):
        print(f"  0x{i2.address:x}:\t{i2.mnemonic}\t{i2.op_str}\t[{i2.bytes.hex()}]")

dump(0x1eb0cc0, 0x1eb0d80, "PC main+0x1eb0d40")
dump(0x1e5bb60, 0x1e5bbe0, "LR main+0x1e5bbbc")
dump(0x1e4e840, 0x1e4e8a0, "BT main+0x1e4e87c")
dump(0x1eab040, 0x1eab0a0, "BT main+0x1eab078")

alt_vt = 0x8ecc1a8
if alt_vt + 16 * 8 <= len(img):
    alt_slots = [struct.unpack_from("<Q", img, alt_vt + k * 8)[0] for k in range(16)]
    print(f"=== Vtable alternativa 0x{alt_vt:x}: {[hex(s) for s in alt_slots]} ===", flush=True)

ro_lo, ro_hi  = segs[1][1], segs[1][1] + segs[1][2]
rodata        = bytes(img[ro_lo:ro_hi])
has_ansimalloc = ("ansimalloc".encode("utf-16-le") in rodata) or (b"ansimalloc" in rodata)
has_binned2    = ("binned2".encode("utf-16-le") in rodata)
print(f"=== ansimalloc={has_ansimalloc} binned2={has_binned2} ===", flush=True)

vtable_addr = 0x92fa000
prof_dir    = games_dir / tid_str
prof_dir.mkdir(parents=True, exist_ok=True)

need_repatch = False
ue_layout    = "UE5"

if vtable_addr + 26 * 8 <= len(img):
    slot4_fn = struct.unpack_from("<Q", img, vtable_addr + 4 * 8)[0]
    if slot4_fn < len(img):
        s4_asm = " ; ".join(f"{i.mnemonic} {i.op_str}" for i in md.disasm(bytes(img[slot4_fn:slot4_fn+32]), slot4_fn))
        if "#0x18" in s4_asm:
            ue_layout = "UE4_27"

print(f"=== Layout: {ue_layout} | cut=0x{cut_addr:x} | obs=0x{obs_addr:x} ===", flush=True)

patches_py = prof_dir / "patches.py"
patches_py.write_text(
    "# Auto-generated FMallocBinned3 (37 GB) replacement patch\n"
    "CUTS = {\n"
    f"    '{main_bid}': [\n"
    f"        (0x{cut_addr:x}, '{cut_orig_hex}', '1f2003d5', 'GCreateMalloc: bl FMallocBinned3 constructor -> nop'),\n"
    "    ],\n"
    "}\n"
    "OBS = {\n"
    f"    '{main_bid}': [\n"
    f"        (0x{obs_addr:x}, {best_cut['obj_reg']}, '{obs_orig_word}', 'GCreateMalloc: install the host vtable before use'),\n"
    "    ],\n"
    "}\n",
    encoding="utf-8"
)

uemalloc_c = Path("dm/host/hle_uemalloc.c")
if uemalloc_c.exists():
    uetxt = uemalloc_c.read_text(encoding="utf-8")
    print("=== hle_uemalloc.c original ===", flush=True)
    print(uetxt, flush=True)
    if main_bid not in uetxt:
        new_entry  = f'    {{ "{main_bid}", "{game_title}", {ue_layout}, 0, 0x{vtable_addr:x}, 0x{cut_addr:x} }},\n'
        target_hdr = "static const struct { const char *build, *what; int layout; uint64_t obj, vtable, cut; } k_ue[] = {\n"
        uetxt = uetxt.replace(target_hdr, target_hdr + new_entry)
        # Usa obj_reg detectado dinamicamente
        obj_reg_n = best_cut["obj_reg"]
        uetxt = re.sub(
            r'uint64_t obj = regs\[\d+\];',
            f'uint64_t obj = (regs[{obj_reg_n}] > 0x100000000ULL) ? regs[{obj_reg_n}] : '
            f'((regs[19] > 0x100000000ULL) ? regs[19] : '
            f'((regs[20] > 0x100000000ULL) ? regs[20] : regs[0]));',
            uetxt
        )
        uemalloc_c.write_text(uetxt, encoding="utf-8")
        print("=== Build ID registrado em hle_uemalloc.c ===", flush=True)
        need_repatch = True

# ── 6. game.tsv ──────────────────────────────────────────────────────────────
marker = "romfs_marker.bin"
if manifest.exists():
    for line in manifest.read_text(errors="ignore").splitlines():
        if line.strip() and not line.startswith("#"):
            first_col = line.split("\t")[0].lstrip("/")
            if first_col:
                marker = first_col
                break

game_tsv = prof_dir / "game.tsv"
ref_kv   = {}
for stsv in sample_tsvs:
    if stsv.parent.name != tid_str:
        for line in stsv.read_text(errors="ignore").splitlines():
            if "\t" in line and not line.startswith("#"):
                k, v = line.split("\t", 1)
                ref_kv.setdefault(k.strip(), v.strip())
        break

kv = {
    "name":         game_title,
    "program_id":   tid_str,
    "title_id":     tid_str,
    "bundle_id":    f"org.nxnative.{tid_str.lower()}",
    "build":        f"v0\t{game_ver}\tmain={main_bid}",
    "version":      game_ver,
    "package":      "v0",
    "ipa":          ipa_filename,
    "modules":      " ".join(mods),
    "romfs_marker": marker,
    "gfx_api":      "nvn",
    "app_category": "public.app-category.games",
    "orientation":  "landscape",
    "mem_reserve":  "0xF0000000",
    "mem_alias":    "0xC8000000",
    "mem_stack":    "0x10000000",
    "app_pool":     "0xCD500000",
    "sys_resource": "0x2800000",
    "fps_target":   "60",
    "pad_layout":   "full",
    "game_args":    "-SwitchVirtualAddressSpaceSize=2048" + (" -ansimalloc" if has_ansimalloc else ""),
}
skip_keys = {"patches","hooks","vulkan_shaders","gl_shaders","trinity_packs",
             "feedback_snap","shader_versions","shader_groups","shader_note",
             "pso_mtl4","game_env","build"}
for rk, rv in ref_kv.items():
    if rk not in kv and rk not in skip_keys and not rk.startswith("subsdk") \
       and rk not in ("rtld","main","sdk"):
        kv[rk] = rv

game_tsv.write_text("\n".join(f"{k}\t{v}" for k, v in kv.items()) + "\n", encoding="utf-8")
print(f"=== game_args: {kv['game_args']} ===", flush=True)

gpy_txt = game_py.read_text(encoding="utf-8")
if "return ''" not in gpy_txt:
    gpy_txt = re.sub(
        r"if default is None:\s+raise KeyError\([^\)]+\)",
        "if default is None: return ''",
        gpy_txt
    )
    game_py.write_text(gpy_txt, encoding="utf-8")

marker_path = romfs / marker
marker_path.parent.mkdir(parents=True, exist_ok=True)
if not marker_path.exists():
    marker_path.write_bytes(b"DUMMY_ROMFS_MARKER")

# ── 7. Dirs de trabalho ───────────────────────────────────────────────────────
work          = rt / f"{tid_str}-work"
patched       = work / "build" / "patched_v0"
msl_ios_base  = work / "build" / "ios" / "dmsh_b"
data_v0       = work / "data" / "v0"
for d in (patched, msl_ios_base, data_v0):
    d.mkdir(parents=True, exist_ok=True)

chain_h     = Path("dm/gfx/nvn/dmsh_chain.h")
chain_stamp = "157e1b96c8da"
if chain_h.exists():
    m_ch = re.search(r'#define\s+DMSH_CHAIN\s+"([^"]+)"', chain_h.read_text(errors="ignore"))
    if m_ch:
        chain_stamp = m_ch.group(1)
b_dir = msl_ios_base / f"b-{chain_stamp}"
b_dir.mkdir(parents=True, exist_ok=True)

# ── 8. Cache ──────────────────────────────────────────────────────────────────
cache_root   = Path("/Users/runner/patched_cache")
cache_dir    = cache_root / tid_str
cache_dir.mkdir(parents=True, exist_ok=True)

# Invalida cache se CUT mudou
import hashlib, json
stamp_file = cache_root / "uemalloc_cut_stamp.json"
stamp = {"sha256": hashlib.sha256(main_bytes).hexdigest(),
         "cut": cut_addr, "obs": obs_addr, "obj_reg": best_cut["obj_reg"]}
old_stamp = None
if stamp_file.exists():
    try:    old_stamp = json.loads(stamp_file.read_text())
    except: pass
if old_stamp != stamp:
    print("=== Stamp mudou — invalidando cache ===", flush=True)
    for p in cache_root.glob("*"):
        if p.is_dir(): shutil.rmtree(p)
        elif p.name != ".DS_Store": p.unlink(missing_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True))

cached_files = [f for f in cache_dir.iterdir() if f.name != ".DS_Store"]
if len(cached_files) >= len(mods):
    print(f"=== [CACHE HIT] Restaurando de {cache_dir} ===", flush=True)
    shutil.copytree(cache_dir, patched, dirs_exist_ok=True)
    for rtld_f in patched.glob("rtld*"):
        if rtld_f.is_file(): rtld_f.unlink()
    cuts_file = patched / "main.cuts.tsv"
    if need_repatch and (not cuts_file.exists() or cuts_file.stat().st_size == 0):
        print("=== Re-patch do main (CUT mudou) ===", flush=True)
        subprocess.run(["python3","dm/tools/patch_nso.py",str(exefs/"main"),str(patched),"main"], check=True)
        shutil.copytree(patched, cache_dir, dirs_exist_ok=True)
else:
    for m in mods:
        print(f"=== Reescrevendo NSO: {m} ===", flush=True)
        subprocess.run(["python3","dm/tools/patch_nso.py",str(exefs/m),str(patched),m], check=True)
    shutil.copytree(patched, cache_dir, dirs_exist_ok=True)

if (exefs / "main.npdm").exists():
    dst_npdm = patched / "main.npdm"
    if (exefs / "main.npdm").resolve() != dst_npdm.resolve():
        shutil.copy2(exefs / "main.npdm", dst_npdm)

for nacp in nacp_files:
    for dst_nacp in (data_v0 / "control.nacp", romfs.parent / "control.nacp"):
        if nacp.resolve() != dst_nacp.resolve():
            shutil.copy2(nacp, dst_nacp)
    break

subprocess.run(["make","-s","-C","dm/host","game_profile",f"GAME={tid_str}"], check=True)

# ── 9. Build IPA ──────────────────────────────────────────────────────────────
out_ipa = rt / ipa_filename
env     = os.environ.copy()
env.update({
    "GAME":            tid_str,
    "W":               str(work),
    "PATCHED":         str(patched),
    "ROMFS":           str(romfs),
    "MSL_IOS":         str(msl_ios_base),
    "DM_DISPLAY_NAME": game_title,
    "DM_APP_VERSION":  game_ver,
    "CHAIN_STAMP":     chain_stamp,
    "AOC":             str(kit / "aoc") if (kit / "aoc").is_dir() else "",
})
subprocess.run(["bash","-x","dm/ios/tools/build_ipa.sh",str(out_ipa)], env=env, check=True)
(rt / "last_ipa_name.txt").write_text(safe_name, encoding="utf-8")
print(f"=== SUCESSO! IPA: {out_ipa} ===", flush=True)
