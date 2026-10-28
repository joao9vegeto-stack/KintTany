import os, sys, re, struct, shutil, subprocess, json, hashlib
from pathlib import Path

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
# 4. Lê NSO e descomprime usando nso.py do repositório
#    (evita reimplementar a lógica — usa o loader oficial que já funciona)
# ─────────────────────────────────────────────────────────────────────────────
main_file  = exefs / "main"
main_bytes = main_file.read_bytes()

if main_bytes[:4] != b"NSO0":
    print(f"[patch] FATAL: magic invalido {main_bytes[:4]!r}")
    sys.exit(1)

flags    = struct.unpack_from("<I", main_bytes, 0x0C)[0]
main_bid = main_bytes[0x40:0x50].hex()
use_zstd = bool(flags & (1 << 7))
print(f"=== Build ID: {main_bid} ===", flush=True)
print(f"=== flags: 0x{flags:02x} | compressao: {'zstd' if use_zstd else 'lz4-block'} ===", flush=True)

# Usa nso.py do repositório para descomprimir — é o loader oficial e correto
try:
    sys.path.insert(0, str(Path("dm/tools").resolve()))
    import nso as _nso
    MOD     = _nso.cli_read(str(main_file))
    img     = MOD.image
    img_size = len(img)
    # Segmentos: ((mem_off, size), ...) para text, ro, data
    seg_text = MOD.segments[0]   # (mem_off, size)
    seg_ro   = MOD.segments[1]
    seg_data = MOD.segments[2]
    segs = [
        (None, seg_text[0], seg_text[1], None),
        (None, seg_ro[0],   seg_ro[1],   None),
        (None, seg_data[0], seg_data[1], None),
    ]
    print(f"=== nso.py: imagem 0x{img_size:x} bytes ===", flush=True)
    print(f"  .text:   mem=0x{seg_text[0]:x} size=0x{seg_text[1]:x}", flush=True)
    print(f"  .rodata: mem=0x{seg_ro[0]:x}   size=0x{seg_ro[1]:x}", flush=True)
    print(f"  .data:   mem=0x{seg_data[0]:x}  size=0x{seg_data[1]:x}", flush=True)
except Exception as e:
    print(f"  [warn] nso.py falhou ({e}), usando descompressão manual", flush=True)
    # Fallback manual — idêntico ao nso.py
    stored   = [struct.unpack_from("<III", main_bytes, 0x10 + i * 0x10) for i in range(3)]
    csz_hdr  = struct.unpack_from("<III", main_bytes, 0x60)
    csz      = [csz_hdr[i] if (flags >> i) & 1 else stored[i][2] for i in range(3)]
    seg_names_l = ["text","rodata","data"]
    for i, ((fo, mo, sz), c) in enumerate(zip(stored, csz)):
        print(f"  .{seg_names_l[i]}: file_off=0x{fo:x} mem_off=0x{mo:x} "
              f"decomp_sz=0x{sz:x} comp_sz=0x{c:x}", flush=True)
    end = stored[2][1] + stored[2][2]
    img = bytearray(end)
    for i, ((fo, mo, sz), c) in enumerate(zip(stored, csz)):
        raw = main_bytes[fo : fo + c]
        print(f"  seg[{i}]: lendo 0x{len(raw):x} bytes de 0x{fo:x}", flush=True)
        if (flags >> i) & 1:
            if use_zstd:
                import zstandard as zstd
                raw = zstd.ZstdDecompressor().decompress(raw, max_output_size=sz)
            else:
                raw = lz4.block.decompress(raw, uncompressed_size=sz)
        if len(raw) < sz:
            raw = raw + bytes(sz - len(raw))
        img[mo : mo + sz] = raw[:sz]
        print(f"  seg[{i}] ok -> mem[0x{mo:x}..0x{mo+sz:x}]", flush=True)
    img_size = end
    seg_text  = (stored[0][1], stored[0][2])
    seg_ro    = (stored[1][1], stored[1][2])
    seg_data  = (stored[2][1], stored[2][2])
    segs = [(stored[i][0], stored[i][1], stored[i][2], csz[i]) for i in range(3)]

print(f"=== Imagem descomprimida: 0x{img_size:x} bytes ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Base de dados de builds conhecidos (do hle_uemalloc.c do nxnative)
#    Para builds conhecidos: usa vtable/cut diretamente, sem disassembly
# ─────────────────────────────────────────────────────────────────────────────
# Formato: build_id -> (layout, obj, vtable, cut, obj_reg)
# obj=0 significa que o objeto é criado por GCreateMalloc (não é fixo)
# obj_reg=19 é o padrão para UE5 (x19 = this após o construtor)
KNOWN_BUILDS = {
    # Octopath Traveler 0 1.0.5
    "9fe60a212cff9b9a3656ab63d4f882e5": ("UE5",   0x68022c8, 0x5b06f38, 0x12e40,    19),
    # DRAGON QUEST VII Reimagined 1.2.0
    "f7ec03e4cb9de3bd8319d4e899d2e9cc": ("UE4_27",0,         0x5e4c0e8, 0x32758dc,  19),
    # Pikmin 4 1.1.1
    "060f827bd2b38703e9ea11e3210d89bc": ("UE4_27",0,         0x8da4758, 0x353f788,  19),
    # OCTOPATH TRAVELER II 1.1.1
    "0d9649011312f62e93f6a5673a09d7e9": ("UE4_27",0,         0x64710b0, 0xbecc08,   19),
}

cut_addr     = None
obs_addr     = None
vtable_addr  = None
ue_layout    = "UE5"
obj_reg_n    = 19

if main_bid in KNOWN_BUILDS:
    layout, obj, vtable, cut, oreg = KNOWN_BUILDS[main_bid]
    cut_addr    = cut
    obs_addr    = cut + 4
    vtable_addr = vtable
    ue_layout   = layout
    obj_reg_n   = oreg
    cut_orig_hex  = bytes(img[cut_addr:cut_addr+4]).hex()
    obs_orig_word = f"{struct.unpack_from('<I', img, obs_addr)[0]:08x}"
    print(f"=== Build conhecido: vtable=0x{vtable_addr:x} cut=0x{cut_addr:x} "
          f"layout={ue_layout} ===", flush=True)
    print(f"=== CUT=0x{cut_addr:x} ({cut_orig_hex}) OBS=0x{obs_addr:x} "
          f"({obs_orig_word}) OBJ_REG=x{obj_reg_n} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 6. Detector dinâmico — só roda se o build NÃO for conhecido
# ─────────────────────────────────────────────────────────────────────────────
if cut_addr is None:
    print(f"=== Build desconhecido — iniciando detector dinâmico ===", flush=True)

    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True

    text_start = seg_text[0]
    text_size  = seg_text[1]

    # Pula MOD0 — lê ponteiro em [0x04] do .text
    mod0_ptr   = struct.unpack_from("<I", img, text_start + 0x04)[0]
    mod0_magic = bytes(img[text_start + mod0_ptr : text_start + mod0_ptr + 4])
    if mod0_magic == b"MOD0":
        code_start = (text_start + mod0_ptr + 0x28 + 3) & ~3
        print(f"=== MOD0 em 0x{text_start+mod0_ptr:x}, código em 0x{code_start:x} ===", flush=True)
    else:
        code_start = text_start + 0x100
        print(f"=== MOD0 fallback 0x{code_start:x} ===", flush=True)
    code_end = text_start + text_size

    print(f"=== Disassemblando .text: [0x{code_start:x}..0x{code_end:x}] ===", flush=True)
    insns_all = list(md.disasm(bytes(img[code_start:code_end]), code_start))
    print(f"=== Instruções disassembladas: {len(insns_all)} ===", flush=True)

    if len(insns_all) < 100000:
        print(f"[patch] FATAL: apenas {len(insns_all)} instrucoes — imagem corrompida ou offset errado")
        print(f"  primeiros 32 bytes (0x{code_start:x}): {bytes(img[code_start:code_start+32]).hex()}")
        sys.exit(1)

    by_addr = {ins.address: ins for ins in insns_all}

    ro_start = seg_ro[0]
    ro_size  = seg_ro[1]
    ro_bytes = bytes(img[ro_start : ro_start + ro_size])

    def sign_extend(v, bits):
        s = 1 << (bits - 1)
        return (v & (s - 1)) - (v & s)

    def decode_bl(word, pc):
        if (word & 0xFC000000) != 0x94000000: return None
        return pc + sign_extend((word & 0x03FFFFFF) << 2, 28)

    def rnum(name):
        if not name: return None
        m2 = re.fullmatch(r"[xw](\d+)", name.lower())
        return int(m2.group(1)) if m2 and int(m2.group(1)) <= 30 else None

    # Busca vtable: sequência de ponteiros para .text no .rodata
    best_vtable = None
    best_count  = 0
    for off in range(ro_start, ro_start + ro_size - 64, 8):
        count = 0
        for slot in range(64):
            ptr_off = off + slot * 8
            if ptr_off + 8 > len(img): break
            ptr = struct.unpack_from("<Q", img, ptr_off)[0]
            if text_start <= ptr < text_start + text_size:
                count += 1
            else:
                break
        if count > best_count:
            best_count  = count
            best_vtable = off

    if not best_vtable or best_count < 20:
        print(f"[patch] FATAL: vtable nao encontrada (melhor={best_count} slots)")
        sys.exit(1)

    vtable_addr = best_vtable
    VTABLE_PAGE = vtable_addr & ~0xFFF
    print(f"=== vtable detectada: 0x{vtable_addr:x} ({best_count} slots) ===", flush=True)

    # Detecta layout UE pelo número de slots
    if best_count >= 30:
        ue_layout = "UE5_6"
    elif best_count >= 25:
        ue_layout = "UE5"
    else:
        ue_layout = "UE4_27"
    print(f"=== Layout detectado: {ue_layout} ({best_count} slots) ===", flush=True)

    # Busca ADRP para a página da vtable no .text
    ctor_candidates = []
    for idx, insn in enumerate(insns_all):
        if insn.mnemonic != "adrp" or len(insn.operands) < 2:
            continue
        if insn.operands[1].imm != VTABLE_PAGE:
            continue
        dst = rnum(insn.reg_name(insn.operands[0].reg))
        if dst is None: continue
        for j in range(idx+1, min(idx+16, len(insns_all))):
            jj = insns_all[j]
            if jj.mnemonic == "str" and len(jj.operands) >= 2:
                src_r  = rnum(jj.reg_name(jj.operands[0].reg))
                base_r = rnum(jj.reg_name(jj.operands[1].mem.base))
                if src_r == dst and base_r is not None:
                    func_start = insn.address
                    for k in range(idx, max(-1, idx-512), -1):
                        kk = insns_all[k]
                        if kk.mnemonic == "stp":
                            ops2 = [kk.reg_name(o.reg).lower() if o.type == ARM64_OP_REG else ""
                                    for o in kk.operands]
                            if "x29" in ops2 and "x30" in ops2:
                                func_start = kk.address
                                break
                    ctor_candidates.append({
                        "func": func_start, "this_reg": base_r,
                        "score": 100 - min(abs(jj.operands[1].mem.disp), 32)
                    })
                    break

    if not ctor_candidates:
        print(f"[patch] FATAL: construtor nao encontrado pela vtable 0x{vtable_addr:x}")
        sys.exit(1)

    ctor_candidates.sort(key=lambda x: (-x["score"], x["func"]))
    ctor = ctor_candidates[0]
    print(f"=== Construtor: func=0x{ctor['func']:x} this_reg=x{ctor['this_reg']} ===", flush=True)

    bls = []
    for off in range(code_start, code_end - 4, 4):
        w = struct.unpack_from("<I", img, off)[0]
        t = decode_bl(w, off)
        if t is not None and ctor["func"] <= t <= ctor["func"] + 0x40:
            bls.append(off)

    if not bls:
        print("[patch] FATAL: nenhum BL para o construtor")
        sys.exit(1)

    best_cut_d = None
    best_score = -1
    for bl in bls:
        obj_reg = ctor["this_reg"]
        score   = 0
        for a in range(max(code_start, bl - 0x80), bl, 4):
            ii = by_addr.get(a)
            if not ii: continue
            if ii.mnemonic == "mov" and len(ii.operands) >= 2:
                dr = rnum(ii.reg_name(ii.operands[0].reg))
                sr = rnum(ii.reg_name(ii.operands[1].reg))
                if dr == 0 and sr is not None:
                    obj_reg = sr
                    score  += 50 + (25 if sr in range(19, 29) else 0)
                    break
        score += 12 if obj_reg in (19, 28) else 0
        if score > best_score:
            best_score = score
            best_cut_d = {"cut": bl, "obs": bl+4, "obj_reg": obj_reg}

    cut_addr      = best_cut_d["cut"]
    obs_addr      = best_cut_d["obs"]
    obj_reg_n     = best_cut_d["obj_reg"]
    cut_orig_hex  = bytes(img[cut_addr:cut_addr+4]).hex()
    obs_orig_word = f"{struct.unpack_from('<I', img, obs_addr)[0]:08x}"
    print(f"=== CUT=0x{cut_addr:x} ({cut_orig_hex}) OBS=0x{obs_addr:x} "
          f"({obs_orig_word}) OBJ_REG=x{obj_reg_n} ===", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 7. ansimalloc
# ─────────────────────────────────────────────────────────────────────────────
ro_start   = seg_ro[0]
ro_size_v  = seg_ro[1]
ro_bytes_v = bytes(img[ro_start : ro_start + ro_size_v])
has_ansimalloc = (b"ansimalloc" in ro_bytes_v) or \
                 ("ansimalloc".encode("utf-16-le") in ro_bytes_v)
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
# 11. Cache com stamp
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
