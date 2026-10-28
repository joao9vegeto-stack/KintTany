import os, sys, re, struct, shutil, subprocess, json, hashlib
from pathlib import Path

# ── Imports com fallback ──────────────────────────────────────────────────────
try:
    import lz4.block
except ImportError:
    subprocess.run([sys.executable,"-m","pip","install","--break-system-packages","lz4"], check=True)
    import lz4.block

try:
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    from capstone.arm64 import ARM64_OP_REG
except ImportError:
    subprocess.run([sys.executable,"-m","pip","install","--break-system-packages","capstone"], check=True)
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    from capstone.arm64 import ARM64_OP_REG

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
# 2. Nome e versão via .nacp
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
# 3. Módulos NSO (sem rtld)
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
# 4. Lê e descomprime main — spec oficial switchbrew.org/wiki/NSO0
# ─────────────────────────────────────────────────────────────────────────────
main_path  = exefs / "main"
main_bytes = main_path.read_bytes()

if main_bytes[:4] != b"NSO0":
    print(f"[patch] FATAL: magic invalido {main_bytes[:4]!r}")
    sys.exit(1)

flags    = struct.unpack_from("<I", main_bytes, 0x0C)[0]
main_bid = main_bytes[0x40:0x50].hex()   # 16 bytes = 32 hex chars
print(f"=== Build ID: {main_bid} ===", flush=True)
print(f"=== flags NSO: 0x{flags:02x} ===", flush=True)

# Offsets dos segmentos conforme spec:
#   text   -> 0x10(file) 0x14(mem) 0x18(decomp_sz)
#   rodata -> 0x20(file) 0x24(mem) 0x28(decomp_sz)
#   data   -> 0x30(file) 0x34(mem) 0x38(decomp_sz)
# Compressed sizes:
#   text=0x60  rodata=0x64  data=0x68
SEG_SPEC = [
    (0x10, 0x14, 0x18, 0x60, "text"),
    (0x20, 0x24, 0x28, 0x64, "rodata"),
    (0x30, 0x34, 0x38, 0x68, "data"),
]

segs = []
for (fo_off, mo_off, sz_off, csz_off, name) in SEG_SPEC:
    file_off  = struct.unpack_from("<I", main_bytes, fo_off)[0]
    mem_off   = struct.unpack_from("<I", main_bytes, mo_off)[0]
    decomp_sz = struct.unpack_from("<I", main_bytes, sz_off)[0]
    comp_sz   = struct.unpack_from("<I", main_bytes, csz_off)[0]
    segs.append((file_off, mem_off, decomp_sz, comp_sz, name))
    print(f"  .{name}: file_off=0x{file_off:x} mem_off=0x{mem_off:x} "
          f"decomp_sz=0x{decomp_sz:x} comp_sz=0x{comp_sz:x} "
          f"compressed={(flags >> SEG_SPEC.index((fo_off,mo_off,sz_off,csz_off,name))) & 1}",
          flush=True)

# Monta buffer da imagem completa
img_size = max(mo + sz for (fo, mo, sz, csz2, nm) in segs)
img      = bytearray(img_size)

# Bit 7 = UseZbicCompression (zstd), senão LZ4 block
use_zstd = bool(flags & (1 << 7))
print(f"=== Algoritmo: {'zstd' if use_zstd else 'lz4-block'} ===", flush=True)

for i, (file_off, mem_off, decomp_sz, comp_sz, seg_name) in enumerate(segs):
    is_compressed = bool((flags >> i) & 1)
    raw = main_bytes[file_off : file_off + comp_sz]

    print(f"  seg[{i}] .{seg_name}: lendo 0x{len(raw):x} bytes de file_off=0x{file_off:x} "
          f"compressed={is_compressed}", flush=True)

    if is_compressed:
        try:
            if use_zstd:
                import zstandard as zstd
                raw = zstd.ZstdDecompressor().decompress(raw, max_output_size=decomp_sz)
            else:
                raw = lz4.block.decompress(raw, uncompressed_size=decomp_sz)
        except Exception as e:
            print(f"[patch] FATAL: falha ao descomprimir seg[{i}] .{seg_name}: {e}")
            print(f"  primeiros 16 bytes: {main_bytes[file_off:file_off+16].hex()}")
            sys.exit(1)

    if len(raw) < decomp_sz:
        raw = raw + bytes(decomp_sz - len(raw))

    img[mem_off : mem_off + decomp_sz] = raw[:decomp_sz]
    print(f"  seg[{i}] .{seg_name} ok -> mem[0x{mem_off:x}..0x{mem_off+decomp_sz:x}]", flush=True)

print(f"=== Imagem descomprimida: 0x{img_size:x} bytes ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Disassembla APENAS o segmento .text
# ─────────────────────────────────────────────────────────────────────────────
text_mem_off  = segs[0][1]
text_decomp   = segs[0][2]
text_end      = text_mem_off + text_decomp

print(f"=== Disassemblando .text: mem[0x{text_mem_off:x}..0x{text_end:x}] ===", flush=True)

md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
md.detail = True

insns_all = list(md.disasm(bytes(img[text_mem_off:text_end]), text_mem_off))
print(f"=== Instruções disassembladas: {len(insns_all)} ===", flush=True)

if len(insns_all) < 1000:
    sample = img[text_mem_off:text_mem_off+32].hex()
    print(f"[patch] FATAL: apenas {len(insns_all)} instrucoes")
    print(f"  primeiros 32 bytes do .text (mem_off=0x{text_mem_off:x}): {sample}")
    sys.exit(1)

by_addr = {ins.address: ins for ins in insns_all}
print(f"=== by_addr: {len(by_addr)} entradas ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 6. Detector dinâmico pela vtable FMallocBinned3
# ─────────────────────────────────────────────────────────────────────────────
VTABLE_PAGE = 0x92fa000 & ~0xFFF

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
                        ops = [kk.reg_name(o.reg).lower()
                               if o.type == ARM64_OP_REG else ""
                               for o in kk.operands]
                        if "x29" in ops and "x30" in ops:
                            func_start = kk.address
                            break
                ctor_candidates.append({
                    "func":     func_start,
                    "this_reg": base,
                    "score":    100 - min(abs(ii.operands[1].mem.disp), 32)
                })
                break

if not ctor_candidates:
    print("[patch] FATAL: construtor nao encontrado pela vtable 0x92fa000")
    sys.exit(1)

ctor_candidates.sort(key=lambda x: (-x["score"], x["func"]))
ctor = ctor_candidates[0]
print(f"=== Construtor: func=0x{ctor['func']:x} this_reg=x{ctor['this_reg']} ===", flush=True)

# Acha BL que chama o construtor
bls = []
for off in range(text_mem_off, text_end - 4, 4):
    w = struct.unpack_from("<I", img, off)[0]
    t = decode_bl(w, off)
    if t is not None and ctor["func"] <= t <= ctor["func"] + 0x40:
        bls.append(off)

if not bls:
    print("[patch] FATAL: nenhum BL para o construtor")
    sys.exit(1)

best_cut   = None
best_score = -1
for bl in bls:
    obj_reg = ctor["this_reg"]
    score   = 0
    for a in range(max(text_mem_off, bl - 0x80), bl, 4):
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
        best_cut   = {"cut": bl, "obs": bl + 4,
                      "obj_reg": obj_reg, "ctor": ctor["func"]}

cut_addr      = best_cut["cut"]
obs_addr      = best_cut["obs"]
cut_orig_hex  = img[cut_addr:cut_addr+4].hex()
obs_orig_word = f"{struct.unpack_from('<I', img, obs_addr)[0]:08x}"
print(f"=== CUT=0x{cut_addr:x} ({cut_orig_hex}) "
      f"OBS=0x{obs_addr:x} ({obs_orig_word}) "
      f"OBJ_REG=x{best_cut['obj_reg']} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 7. Layout UE e flags extras
# ─────────────────────────────────────────────────────────────────────────────
vtable_addr = 0x92fa000
ue_layout   = "UE5"
if vtable_addr + 26 * 8 <= len(img):
    slot4_fn = struct.unpack_from("<Q", img, vtable_addr + 4 * 8)[0]
    if slot4_fn < len(img):
        s4_asm = " ; ".join(
            f"{i.mnemonic} {i.op_str}"
            for i in md.disasm(bytes(img[slot4_fn:slot4_fn+32]), slot4_fn)
        )
        if "#0x18" in s4_asm:
            ue_layout = "UE4_27"

ro_mem_off  = segs[1][1]
ro_decomp   = segs[1][2]
rodata      = bytes(img[ro_mem_off : ro_mem_off + ro_decomp])
has_ansimalloc = (b"ansimalloc" in rodata) or \
                 ("ansimalloc".encode("utf-16-le") in rodata)
print(f"=== Layout: {ue_layout} | ansimalloc={has_ansimalloc} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 8. patches.py e hle_uemalloc.c
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
    f"        (0x{obs_addr:x}, {best_cut['obj_reg']}, '{obs_orig_word}',\n"
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

# ─────────────────────────────────────────────────────────────────────────────
# 9. game.tsv
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

# Patch game.py para não lançar KeyError
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

# ─────────────────────────────────────────────────────────────────────────────
# 10. Dirs de trabalho
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
# 11. Cache com stamp (invalida se CUT mudou)
# ─────────────────────────────────────────────────────────────────────────────
cache_root = Path("/Users/runner/patched_cache")
cache_dir  = cache_root / tid_str
cache_dir.mkdir(parents=True, exist_ok=True)

stamp_file = cache_root / "uemalloc_cut_stamp.json"
stamp = {
    "sha256":  hashlib.sha256(main_bytes).hexdigest(),
    "cut":     cut_addr,
    "obs":     obs_addr,
    "obj_reg": best_cut["obj_reg"],
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
# 12. Build IPA
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
