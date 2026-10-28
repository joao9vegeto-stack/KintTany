import os, sys, re, struct, shutil, subprocess, json, hashlib, bisect, array
from pathlib import Path

try:
    import lz4.block
except ImportError:
    subprocess.run([sys.executable,"-m","pip","install","--break-system-packages","lz4"], check=True)
    import lz4.block

def fatal(msg):
    print(f"[patch] FATAL: {msg}", flush=True)
    sys.exit(1)

# ── Paths base ────────────────────────────────────────────────────────────────
rt       = Path(os.environ["RUNNER_TEMP"]).resolve()
kit      = rt / "kit"
exefs    = kit / "ExeFS"
romfs    = kit / "RomFS"
romfs.mkdir(parents=True, exist_ok=True)
manifest = kit / "romfs_manifest.tsv"

# ─────────────────────────────────────────────────────────────────────────────
# 1. TitleID
# ─────────────────────────────────────────────────────────────────────────────
tid_str   = "010035F022078000"
npdm_file = exefs / "main.npdm"
if npdm_file.exists():
    npdm    = npdm_file.read_bytes()
    aci0    = struct.unpack_from("<I", npdm, 0x70)[0]
    tid     = struct.unpack_from("<Q", npdm, aci0 + 0x10)[0]
    tid_str = f"{tid:016X}"
print(f"=== TitleID detectado: {tid_str} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Nome e versão
# ─────────────────────────────────────────────────────────────────────────────
game_title = f"SwitchGame_{tid_str}"
game_ver   = "1.0"
nacp_files = list(kit.rglob("*.nacp"))

if nacp_files:
    nacp_path = nacp_files[0]
    try:
        res = subprocess.run(["python3","dm/tools/nacp.py",str(nacp_path)],
                             capture_output=True, text=True, check=True)
        if res.stdout.strip():
            game_title = res.stdout.strip()
    except Exception:
        pass
    try:
        res = subprocess.run(["python3","dm/tools/nacp.py","--version",str(nacp_path)],
                             capture_output=True, text=True, check=True)
        if res.stdout.strip():
            game_ver = res.stdout.strip()
    except Exception:
        pass
elif tid_str == "010035F022078000":
    game_title = "DRAGON BALL: Sparking! ZERO"

safe_name    = re.sub(r"[^A-Za-z0-9]+","_", game_title).strip("_") or tid_str
ipa_filename = f"{safe_name}.ipa"
print(f"=== Jogo: '{game_title}' v{game_ver} -> {ipa_filename} ===", flush=True)

games_dir   = Path("dm/games").resolve()
game_py     = games_dir / "game.py"
sample_tsvs = sorted(games_dir.glob("*/game.tsv"))

# ─────────────────────────────────────────────────────────────────────────────
# 3. Módulos NSO
# ─────────────────────────────────────────────────────────────────────────────
order = ["main","subsdk0","subsdk1","subsdk2","subsdk3","subsdk4",
         "subsdk5","subsdk6","subsdk7","subsdk8","subsdk9","sdk"]
mods = []
for m in order:
    p = exefs / m
    if p.is_file() and p.read_bytes()[:4] == b"NSO0":
        mods.append(m)
for p in sorted(exefs.iterdir()):
    if p.is_file() and p.name not in mods \
       and p.name not in ("main.npdm","rtld") \
       and p.read_bytes()[:4] == b"NSO0":
        mods.append(p.name)
print(f"=== Módulos NSO (sem rtld): {mods} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 4. Descomprime o NSO main (autocontido; esta etapa já funcionava nos logs)
# ─────────────────────────────────────────────────────────────────────────────
main_bytes = (exefs / "main").read_bytes()
if main_bytes[:4] != b"NSO0":
    fatal(f"magic invalido {main_bytes[:4]!r}")

flags    = struct.unpack_from("<I", main_bytes, 0x0C)[0]
main_bid = main_bytes[0x40:0x50].hex()
use_zstd = bool(flags & (1 << 7))
print(f"=== Build ID: {main_bid} ===", flush=True)
print(f"=== flags: 0x{flags:02x} | compressao: {'zstd' if use_zstd else 'lz4-block'} ===", flush=True)

stored  = [struct.unpack_from("<III", main_bytes, 0x10 + i * 0x10) for i in range(3)]  # (file_off, mem_off, size)
csz_hdr = struct.unpack_from("<III", main_bytes, 0x60)
csz     = [csz_hdr[i] if (flags >> i) & 1 else stored[i][2] for i in range(3)]
seg_names = ["text", "rodata", "data"]

for i, ((fo, mo, sz), c) in enumerate(zip(stored, csz)):
    print(f"  .{seg_names[i]}: file_off=0x{fo:x} mem_off=0x{mo:x} "
          f"decomp_sz=0x{sz:x} comp_sz=0x{c:x} compressed={(flags>>i)&1}", flush=True)

img_size = stored[2][1] + stored[2][2]
img = bytearray(img_size)
for i, ((fo, mo, sz), c) in enumerate(zip(stored, csz)):
    raw = main_bytes[fo:fo + c]
    if (flags >> i) & 1:
        try:
            if use_zstd:
                import zstandard as zstd
                raw = zstd.ZstdDecompressor().decompress(raw, max_output_size=sz)
            else:
                raw = lz4.block.decompress(raw, uncompressed_size=sz)
        except Exception as e:
            fatal(f"descompressao seg[{i}] .{seg_names[i]}: {e} | bytes: {main_bytes[fo:fo+16].hex()}")
    if len(raw) != sz:
        fatal(f"seg[{i}] .{seg_names[i]} descomprimiu {len(raw):#x} bytes, esperado {sz:#x}")
    img[mo:mo + sz] = raw
    print(f"  seg[{i}] .{seg_names[i]} ok -> mem[0x{mo:x}..0x{mo+sz:x}]", flush=True)
print(f"=== Imagem descomprimida: 0x{img_size:x} bytes ===", flush=True)

text_lo = stored[0][1]
text_sz = stored[0][2]
text_hi = text_lo + text_sz
ro_lo, ro_sz = stored[1][1], stored[1][2]

# ─────────────────────────────────────────────────────────────────────────────
# 5. Varredura do .text por palavras de 32 bits (SEM Capstone)
#    O Capstone.disasm() PARA na 1a palavra invalida (dado em literal pool),
#    por isso so cobria ~55 KB de 90 MB. Aqui lemos todas as palavras.
# ─────────────────────────────────────────────────────────────────────────────
mod0_ptr = struct.unpack_from("<I", img, text_lo + 4)[0]
if bytes(img[text_lo + mod0_ptr: text_lo + mod0_ptr + 4]) != b"MOD0":
    fatal(f"MOD0 nao encontrado em 0x{mod0_ptr:x}")
code_start = (text_lo + mod0_ptr + 0x28 + 3) & ~3
print(f"=== MOD0 em 0x{mod0_ptr:x} | primeiro codigo em 0x{code_start:x} ===", flush=True)
print(f"=== bytes em 0x{code_start:x}: {bytes(img[code_start:code_start+16]).hex()} ===", flush=True)

words = array.array("I")
words.frombytes(bytes(img[text_lo:text_hi]))
if sys.byteorder == "big":
    words.byteswap()
nwords = len(words)

adrps = []   # (addr, pagina_alvo, rd)
bls   = []   # (addr, destino)
for i, w in enumerate(words):
    if (w & 0x9f000000) == 0x90000000:
        imm = (((w >> 5) & 0x7ffff) << 2) | ((w >> 29) & 3)
        if imm & 0x100000:
            imm -= 0x200000
        pc = text_lo + i * 4
        adrps.append((pc, (pc & ~0xfff) + (imm << 12), w & 31))
    elif (w >> 26) == 0x25:
        imm = w & 0x3ffffff
        if imm & 0x2000000:
            imm -= 0x4000000
        pc = text_lo + i * 4
        bls.append((pc, pc + imm * 4))
print(f"=== Palavras: {nwords} | adrp: {len(adrps)} | bl: {len(bls)} ===", flush=True)
if len(adrps) < 1000 or len(bls) < 1000:
    fatal("poucos adrp/bl no .text; imagem suspeita")

def word_at(addr):
    return words[(addr - text_lo) // 4]

def qword_at(addr):
    return struct.unpack_from("<Q", img, addr)[0]

def in_text(v):
    return code_start <= v < text_hi

# Tabela de funcoes via eh_frame_hdr (como em nso_fnmap.py do nxnative)
func_starts = []
try:
    ehs = mod0_ptr + struct.unpack_from("<i", img, mod0_ptr + 16)[0]
    _v, penc, cenc, tenc = img[ehs:ehs + 4]
    if (penc, cenc, tenc) != (0x1b, 0x03, 0x3b):
        raise ValueError(f"encodings {penc:#x} {cenc:#x} {tenc:#x}")
    nfde = struct.unpack_from("<I", img, ehs + 8)[0]
    for k in range(nfde):
        loc, _fde = struct.unpack_from("<ii", img, ehs + 12 + k * 8)
        a = ehs + loc
        if code_start <= a < text_hi:
            func_starts.append(a)
    func_starts = sorted(set(func_starts))
    print(f"=== eh_frame_hdr: {len(func_starts)} funcoes ===", flush=True)
except Exception as e:
    func_starts = []
    print(f"  [warn] eh_frame_hdr indisponivel ({e}); usando heuristica de prologo", flush=True)

def heuristic_start(addr):
    i = (addr - text_lo) // 4
    for k in range(i, max(-1, i - 1024), -1):
        w = words[k]
        if (w & 0xffc07fff) in (0xa9007bfd, 0xa9807bfd, 0xa8807bfd):   # stp x29, x30, ...
            s = k
            while s - 1 >= 0:
                p = words[s - 1]
                if (p & 0xff0003ff) == 0xd10003ff or (p & 0xff800000) in (0xa9000000, 0xa9800000):
                    s -= 1
                else:
                    break
            return text_lo + s * 4
    return addr

def func_of(addr):
    if func_starts:
        i = bisect.bisect_right(func_starts, addr) - 1
        if i >= 0 and addr - func_starts[i] < 0x100000:
            return func_starts[i]
    return heuristic_start(addr)

def adrp_add_targets(page_set):
    """pares adrp + add imm (ate 8 palavras depois) cujo alvo cai nas paginas dadas"""
    out = []
    for pc, page, rd in adrps:
        if page not in page_set:
            continue
        bi = (pc - text_lo) // 4
        for j in range(bi + 1, min(bi + 9, nwords)):
            v = words[j]
            if (v & 0xffc00000) == 0x91000000 and ((v >> 5) & 31) == rd:
                out.append((pc, text_lo + j * 4, page + ((v >> 10) & 0xfff), v & 31))
                break
    return out

def find_all(needle, lo, hi, align=1):
    out, p = [], lo
    while True:
        p = img.find(needle, p, hi)
        if p < 0:
            break
        if p % align == 0:
            out.append(p)
        p += 1
    return out

# ─────────────────────────────────────────────────────────────────────────────
# 6. Detector da vtable FMallocBinned3 -> construtor -> CUT / OBS
# ─────────────────────────────────────────────────────────────────────────────
# Layouts do FMalloc (de dm/host/hle_uemalloc.c): indice do slot GetDescriptiveName
LAYOUT_SLOT = {"UE5": 22, "UE4_27": 19, "UE5_6": 26}

# 6a. string "Binned3" (retorno de GetDescriptiveName) em ASCII / UTF-16 / UTF-32
str_addrs = []
for enc, step in (("ascii", 1), ("utf-16-le", 2), ("utf-32-le", 4)):
    needle = "Binned3\0".encode(enc)
    for p in find_all(needle, text_hi, img_size, step):
        prev = bytes(img[p - step:p]) if p - step >= 0 else bytes(step)
        if prev[:1].isalnum() and prev[1:] == bytes(step - 1):
            continue   # faz parte de uma string maior (ex.: FMallocBinned3)
        str_addrs.append(p)
        ctx = bytes(img[max(0, p - 12):p + 24])
        print(f"  [str] 'Binned3' {enc} em 0x{p:x} ctx={ctx!r}", flush=True)
if not str_addrs:
    fatal("string 'Binned3' (inicio de string) nao encontrada no binario")

# 6b. funcoes que referenciam a string = candidatas a GetDescriptiveName
str_set = set(str_addrs)
refs_str = adrp_add_targets({a & ~0xfff for a in str_addrs})
getdesc = set()
for apc, _addc, tgt, _reg in refs_str:
    if tgt in str_set:
        getdesc.add(func_of(apc))
        getdesc.add(apc)
        print(f"  [ref] string referenciada em 0x{apc:x} (funcao 0x{func_of(apc):x})", flush=True)
if not getdesc:
    fatal("nenhuma funcao referencia a string 'Binned3'")

# 6c. ponteiro da funcao na vtable -> base da vtable para cada layout
combos = set()
for fn_c in sorted(getdesc):
    for slot_addr in find_all(struct.pack("<Q", fn_c), text_hi, img_size, 8):
        for lay, idx in LAYOUT_SLOT.items():
            base = slot_addr - idx * 8
            if base < text_hi:
                continue
            cnt = 0
            while base + cnt * 8 + 8 <= img_size and in_text(qword_at(base + cnt * 8)):
                cnt += 1
            if cnt > idx:
                combos.add((lay, base, cnt))
print(f"=== Combinacoes vtable/layout candidatas: {len(combos)} ===", flush=True)
if not combos:
    fatal("GetDescriptiveName nao aparece em nenhuma vtable")

# 6d. so vale a base referenciada por adrp+add no .text
bases = {b for (_l, b, _c) in combos}
refs_vt = adrp_add_targets({b & ~0xfff for b in bases})
refs_by_base = {}
for r in refs_vt:
    if r[2] in bases:
        refs_by_base.setdefault(r[2], []).append(r)

chosen = None
for lay, base, cnt in sorted(combos, key=lambda x: x[1]):
    if base not in refs_by_base:
        continue
    slot0, slot1 = qword_at(base), qword_at(base + 8)
    ctors, any_ref = {}, set()
    for apc, addc, _tgt, reg in refs_by_base[base]:
        fn_r = func_of(apc)
        if fn_r in (slot0, slot1):
            continue   # destrutores
        any_ref.add(fn_r)
        ai = (addc - text_lo) // 4
        for j in range(ai + 1, min(ai + 17, nwords)):
            v = words[j]
            if (v & 0xffc00000) == 0xf9000000 and (v & 31) == reg and ((v >> 10) & 0xfff) * 8 <= 32:
                ctors[fn_r] = (v >> 5) & 31
                break
    cand = ctors if ctors else {f: 0 for f in any_ref}
    print(f"  [vtable] layout={lay} base=0x{base:x} slots_texto={cnt} "
          f"construtores={[hex(c) for c in cand]}", flush=True)
    if not cand:
        continue
    cand_set = set(cand)
    sites = [pc for pc, t in bls if t in cand_set]
    if not sites:
        sites = [pc for pc, t in bls if any(c <= t <= c + 0x40 for c in cand_set)]
    print(f"           chamadas (bl) ao construtor: {[hex(s) for s in sites]}", flush=True)
    if sites:
        chosen = (lay, base, cand, sites)
        break

if not chosen:
    fatal("vtable achada, mas nenhum construtor com bl chamador (veja as linhas [vtable] acima)")

ue_layout, vtable_addr, ctor_map, call_sites = chosen
print(f"=== vtable FMallocBinned3: 0x{vtable_addr:x} | layout {ue_layout} ===", flush=True)

best, best_score = None, -1
for bl in sorted(call_sites):
    obj_reg, score = 19, 0
    bi = (bl - text_lo) // 4
    for k in range(bi - 1, max(-1, bi - 33), -1):
        w = words[k]
        if (w & 0xffe0ffff) == 0xaa0003e0:       # mov x0, xN
            obj_reg = (w >> 16) & 31
            score += 50 + (25 if 19 <= obj_reg <= 28 else 0)
            break
    score += 12 if obj_reg in (19, 28) else 0
    print(f"  [cut?] bl=0x{bl:x} obj_reg=x{obj_reg} score={score}", flush=True)
    if score > best_score:
        best_score, best = score, (bl, obj_reg)

cut_addr, obj_reg_n = best
obs_addr      = cut_addr + 4
cut_orig_hex  = bytes(img[cut_addr:cut_addr + 4]).hex()
obs_orig_word = f"{struct.unpack_from('<I', img, obs_addr)[0]:08x}"
print(f"=== CUT=0x{cut_addr:x} ({cut_orig_hex}) OBS=0x{obs_addr:x} ({obs_orig_word}) "
      f"OBJ_REG=x{obj_reg_n} ===", flush=True)

has_ansimalloc = False
ro_bytes = bytes(img[ro_lo:ro_lo + ro_sz])
if b"ansimalloc" in ro_bytes or "ansimalloc".encode("utf-16-le") in ro_bytes:
    has_ansimalloc = True
del ro_bytes
print(f"=== Layout: {ue_layout} | ansimalloc={has_ansimalloc} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 7. patches.py e hle_uemalloc.c
# ─────────────────────────────────────────────────────────────────────────────
prof_dir = games_dir / tid_str
prof_dir.mkdir(parents=True, exist_ok=True)

patches_py = prof_dir / "patches.py"
patches_py.write_text(
    "# Auto-generated — FMallocBinned3 patch\n"
    "CUTS = {\n"
    f"    '{main_bid}': [\n"
    f"        (0x{cut_addr:x}, '{cut_orig_hex}', '1f2003d5',\n"
    f"         'GCreateMalloc: bl FMallocBinned3 -> nop'),\n"
    "    ],\n"
    "}\n"
    "OBS = {\n"
    f"    '{main_bid}': [\n"
    f"        (0x{obs_addr:x}, {obj_reg_n}, '{obs_orig_word}',\n"
    f"         'GCreateMalloc: install host vtable'),\n"
    "    ],\n"
    "}\n",
    encoding="utf-8"
)

need_repatch = False
uemalloc_c   = Path("dm/host/hle_uemalloc.c")
if uemalloc_c.exists():
    uetxt = uemalloc_c.read_text(encoding="utf-8")
    if main_bid not in uetxt:
        new_entry  = (f'    {{ "{main_bid}", "{game_title}", {ue_layout}, '
                      f'0, 0x{vtable_addr:x}, 0x{cut_addr:x} }},\n')
        target_hdr = ('static const struct { const char *build, *what; '
                      'int layout; uint64_t obj, vtable, cut; } k_ue[] = {\n')
        uetxt = uetxt.replace(target_hdr, target_hdr + new_entry)
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

# ─────────────────────────────────────────────────────────────────────────────
# 8. game.tsv
# ─────────────────────────────────────────────────────────────────────────────
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
    "game_args":    ("-SwitchVirtualAddressSpaceSize=2048"
                     + (" -ansimalloc" if has_ansimalloc else "")),
}
skip_keys = {"patches","hooks","vulkan_shaders","gl_shaders","trinity_packs",
             "feedback_snap","shader_versions","shader_groups","shader_note",
             "pso_mtl4","game_env","build"}
for rk, rv in ref_kv.items():
    if rk not in kv and rk not in skip_keys \
       and not rk.startswith("subsdk") \
       and rk not in ("rtld","main","sdk"):
        kv[rk] = rv

game_tsv.write_text(
    "\n".join(f"{k}\t{v}" for k, v in kv.items()) + "\n",
    encoding="utf-8"
)
print(f"=== game_args: {kv['game_args']} ===", flush=True)

if game_py.exists():
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

# libera memoria antes do build
del words, adrps, bls, img

# ─────────────────────────────────────────────────────────────────────────────
# 9. Dirs de trabalho
# ─────────────────────────────────────────────────────────────────────────────
work         = rt / f"{tid_str}-work"
patched      = work / "build" / "patched_v0"
msl_ios_base = work / "build" / "ios" / "dmsh_b"
data_v0      = work / "data" / "v0"
for d in (patched, msl_ios_base, data_v0):
    d.mkdir(parents=True, exist_ok=True)

chain_h     = Path("dm/gfx/nvn/dmsh_chain.h")
chain_stamp = "157e1b96c8da"
if chain_h.exists():
    m_ch = re.search(r'#define\s+DMSH_CHAIN\s+"([^"]+)"',
                     chain_h.read_text(errors="ignore"))
    if m_ch:
        chain_stamp = m_ch.group(1)

b_dir = msl_ios_base / f"b-{chain_stamp}"
b_dir.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# 10. Cache com stamp
# ─────────────────────────────────────────────────────────────────────────────
cache_root = Path("/Users/runner/patched_cache")
cache_dir  = cache_root / tid_str
cache_dir.mkdir(parents=True, exist_ok=True)

stamp_file = cache_root / "uemalloc_cut_stamp.json"
stamp = {
    "sha256":  hashlib.sha256(main_bytes).hexdigest(),
    "cut":     cut_addr,
    "obs":     obs_addr,
    "obj_reg": obj_reg_n,
}
old_stamp = None
if stamp_file.exists():
    try:
        old_stamp = json.loads(stamp_file.read_text())
    except Exception:
        pass

if old_stamp != stamp:
    print("=== Stamp mudou — invalidando cache ===", flush=True)
    for p in cache_root.glob("*"):
        if p.is_dir():
            shutil.rmtree(p)
        elif p.name != ".DS_Store":
            p.unlink(missing_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

stamp_file.write_text(json.dumps(stamp, indent=2, sort_keys=True))

cached_files = [f for f in cache_dir.iterdir() if f.name != ".DS_Store"]
if len(cached_files) >= len(mods):
    print(f"=== [CACHE HIT] Restaurando de {cache_dir} ===", flush=True)
    shutil.copytree(cache_dir, patched, dirs_exist_ok=True)
    for rtld_f in patched.glob("rtld*"):
        if rtld_f.is_file():
            rtld_f.unlink()
    cuts_file = patched / "main.cuts.tsv"
    if need_repatch and (not cuts_file.exists() or cuts_file.stat().st_size == 0):
        print("=== Re-patch do main (CUT mudou) ===", flush=True)
        subprocess.run(
            ["python3","dm/tools/patch_nso.py",
             str(exefs/"main"), str(patched), "main"],
            check=True
        )
        shutil.copytree(patched, cache_dir, dirs_exist_ok=True)
else:
    for m in mods:
        print(f"=== Reescrevendo NSO: {m} ===", flush=True)
        subprocess.run(
            ["python3","dm/tools/patch_nso.py",
             str(exefs/m), str(patched), m],
            check=True
        )
    shutil.copytree(patched, cache_dir, dirs_exist_ok=True)

if (exefs / "main.npdm").exists():
    dst_npdm = patched / "main.npdm"
    if (exefs / "main.npdm").resolve() != dst_npdm.resolve():
        shutil.copy2(exefs / "main.npdm", dst_npdm)

for nacp in nacp_files:
    for dst_nacp in (data_v0/"control.nacp", romfs.parent/"control.nacp"):
        if nacp.resolve() != dst_nacp.resolve():
            shutil.copy2(nacp, dst_nacp)
    break

subprocess.run(
    ["make","-s","-C","dm/host","game_profile",f"GAME={tid_str}"],
    check=True
)

# ─────────────────────────────────────────────────────────────────────────────
# 11. Build IPA
# ─────────────────────────────────────────────────────────────────────────────
out_ipa = rt / ipa_filename
env = os.environ.copy()
env.update({
    "GAME":            tid_str,
    "W":               str(work),
    "PATCHED":         str(patched),
    "ROMFS":           str(romfs),
    "MSL_IOS":         str(msl_ios_base),
    "DM_DISPLAY_NAME": game_title,
    "DM_APP_VERSION":  game_ver,
    "CHAIN_STAMP":     chain_stamp,
    "AOC":             str(kit/"aoc") if (kit/"aoc").is_dir() else "",
})
subprocess.run(
    ["bash","-x","dm/ios/tools/build_ipa.sh", str(out_ipa)],
    env=env, check=True
)

(rt / "last_ipa_name.txt").write_text(safe_name, encoding="utf-8")
print(f"=== SUCESSO! IPA: {out_ipa} ===", flush=True)
