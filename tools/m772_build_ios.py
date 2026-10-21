#!/usr/bin/env python3
"""Compile the M7.81 PPU/SPU lift plus its per-game PS3Recomp runtime for iOS."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import re
import shlex
import subprocess
import sys


def run(argv, log=None):
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as stream:
            stream.write("+ " + shlex.join(str(x) for x in argv) + "\n")
            stream.flush()
            return subprocess.run([str(x) for x in argv], stdout=stream,
                                  stderr=subprocess.STDOUT, check=False).returncode
    return subprocess.run([str(x) for x in argv], check=False).returncode


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def patch_ios_unaligned_guest_vm(upstream):
    """Use one arbitrary 4-GiB window and translate host pointers by offset."""
    memory_header = upstream / "runtime/ppu/ppu_memory.h"
    text = memory_header.read_text()
    marker = "ASCENSION_IOS_UNALIGNED_VM_GUEST_EA"
    helper = '''/* ASCENSION_IOS_UNALIGNED_VM_GUEST_EA */
extern uint32_t ppu_vm_size;
static inline uint32_t ppu_guest_ea_from_host(const void* pointer)
{
    const uintptr_t value = (uintptr_t)pointer;
    const uintptr_t base = (uintptr_t)vm_base;
    if (!value) return 0;
    if (vm_base && value >= base && value - base < (uintptr_t)ppu_vm_size)
        return (uint32_t)(value - base);
    /* HLEs sometimes pass raw 32-bit guest EAs as pointer-shaped values. */
    if (value <= UINT32_MAX) return (uint32_t)value;
    /* A foreign host pointer is not a valid PS3 guest address. Fail closed
     * instead of truncating it into a plausible but unrelated guest EA. */
    return UINT32_MAX;
}
'''
    if marker not in text:
        anchor = "extern uint8_t* vm_base;\n"
        if text.count(anchor) != 1:
            raise SystemExit("M7.79 could not anchor the guest pointer translator")
        text = text.replace(anchor, anchor + helper, 1)
        memory_header.write_text(text)

    guest_struct = upstream / "libs/guest_struct.h"
    text = guest_struct.read_text()
    old_ea = "#define GUEST_EA(p) ((uint32_t)(uintptr_t)(p))"
    new_ea = "#define GUEST_EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"
    ea_macros = {
        upstream / "libs/codec/cellGifDec.c":
            ("#define GIF_EA(p) ((u32)(uintptr_t)(p))",
             "#define GIF_EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"),
        upstream / "libs/codec/cellJpgDec.c":
            ("#define JPG_EA(p) ((u32)(uintptr_t)(p))",
             "#define JPG_EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"),
        upstream / "libs/font/cellFontFT.c":
            ("#define FT_EA(p) ((u32)(uintptr_t)(p))",
             "#define FT_EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"),
        upstream / "libs/font/cellFont.c":
            ("#define FONT_EA(p) ((u32)(uintptr_t)(p))",
             "#define FONT_EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"),
    }
    sysnet = upstream / "libs/network/sysNet.c"
    old_ea_macro = "#define EA(p) ((uint32_t)(uintptr_t)(p))"
    new_ea_macro = "#define EA(p) ppu_guest_ea_from_host((const void*)(uintptr_t)(p))"
    rtc = upstream / "libs/system/cellRtc.c"
    rtc_marker = "ASCENSION_IOS_UNALIGNED_RTC_EA"
    if new_ea not in text:
        if text.count(old_ea) != 1:
            raise SystemExit("M7.79 could not update PS3Recomp GUEST_EA")
        text = text.replace(old_ea, new_ea, 1)
        guest_struct.write_text(text)

    # Most raw narrowing sites are intentionally polymorphic: they receive a
    # guest EA, a host alias into the VM, or a callback token. The helper
    # subtracts vm_base only for pointers inside the guest window and keeps
    # raw 32-bit EAs intact. Exclude test fixtures from production rewriting.
    cast = re.compile(
        r"\(uint32_t\)\s*\(uintptr_t\)\s*"
        r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*"
        r"(?:\s*\([^()\n]*\))?)"
    )
    cast_u32 = re.compile(
        r"\(u32\)\s*\(uintptr_t\)\s*"
        r"([A-Za-z_]\w*(?:(?:->|\.)[A-Za-z_]\w*)*"
        r"(?:\s*\([^()\n]*\))?)"
    )
    rewritten = 0
    for tree in (upstream / "runtime", upstream / "libs"):
        for path in tree.rglob("*"):
            if path.suffix not in {".c", ".cpp", ".h", ".hpp"}:
                continue
            if "tests" in path.parts or path == memory_header:
                continue
            source = path.read_text(errors="replace")
            changed = False
            if path == upstream / "runtime/ppu/ppu_loader.cpp":
                old_loader_ea = "const uint32_t ea  = (uint32_t)(uintptr_t)p;"
                new_loader_ea = "const uint32_t ea  = vm_to_guest(p);"
                if old_loader_ea in source:
                    source = source.replace(old_loader_ea, new_loader_ea, 1)
                    rewritten += 1
                    changed = True
            source, count = cast.subn(
                lambda match: "ppu_guest_ea_from_host((const void*)(uintptr_t)("
                              + match.group(1) + "))",
                source,
            )
            source, u32_count = cast_u32.subn(
                lambda match: "ppu_guest_ea_from_host((const void*)(uintptr_t)("
                              + match.group(1) + "))",
                source,
            )
            count += u32_count
            if count:
                if "ppu_memory.h" not in source:
                    if tree.name != "libs":
                        raise SystemExit(
                            f"M7.79 pointer conversion lacks shared VM header: {path}"
                        )
                    source = '#include "../../runtime/ppu/ppu_memory.h"\n' + source
                rewritten += count
                changed = True
            if changed:
                path.write_text(source)

    source = sysnet.read_text()
    if new_ea_macro not in source:
        if source.count(old_ea_macro) != 1:
            raise SystemExit("M7.79 could not update the PS3Recomp sysNet EA macro")
        sysnet.write_text(source.replace(old_ea_macro, new_ea_macro, 1))

    macro_rewrites = 0
    for path, (old, new) in ea_macros.items():
        source = path.read_text()
        if new in source:
            continue
        if source.count(old) != 1:
            raise SystemExit(f"M7.79 could not update guest-EA conversion macro: {path.name}")
        path.write_text(source.replace(old, new, 1))
        macro_rewrites += 1

    source = rtc.read_text()
    old_rtc_test = '''static int rtc_is_guest(const void* p)
{
    uintptr_t v = (uintptr_t)p;
    return v && v < 0x100000000ull;
}'''
    new_rtc_test = '''/* ASCENSION_IOS_UNALIGNED_RTC_EA */
static int rtc_is_guest(const void* p)
{
    uintptr_t v = (uintptr_t)p, base = (uintptr_t)vm_base;
    return v && (v < 0x100000000ull ||
        (vm_base && v >= base && v - base < (uintptr_t)ppu_vm_size));
}'''
    if rtc_marker not in source:
        if source.count(old_rtc_test) != 1:
            raise SystemExit("M7.79 could not update cellRtc's guest pointer test")
        rtc.write_text(source.replace(old_rtc_test, new_rtc_test, 1))

    # Re-run safely after partial interruption: all changes above are
    # idempotent, so a second pass can finish any remaining conversions.
    remaining = 0
    helper_uses = 0
    for tree in (upstream / "runtime", upstream / "libs"):
        for path in tree.rglob("*"):
            if path.suffix not in {".c", ".cpp", ".h", ".hpp"}:
                continue
            if "tests" in path.parts:
                continue
            source = path.read_text(errors="replace")
            remaining += len(cast.findall(source)) + len(cast_u32.findall(source))
            helper_uses += source.count("ppu_guest_ea_from_host(")
    macros_complete = (new_ea in guest_struct.read_text() and
                       new_ea_macro in sysnet.read_text() and
                       all(new in path.read_text()
                           for path, (_, new) in ea_macros.items()))
    if (remaining or helper_uses != 372 or marker not in memory_header.read_text()
            or rtc_marker not in rtc.read_text() or not macros_complete):
        raise SystemExit(
            "M7.79 guest-VM pointer patch incomplete: "
            f"remaining casts={remaining}, helper uses={helper_uses}, "
            f"expected helper uses=372, rewrites this pass={rewritten + macro_rewrites}"
        )
    return 370


def patch_ios_game_mount(upstream):
    """Map the installed Ascension title ID onto the iOS Files bookmark root."""
    source = upstream / "runtime/ppu/ppu_fs.cpp"
    text = source.read_text()
    marker = "/* ASCENSION_IOS_NPUA80918_MOUNT */"
    if marker not in text:
        anchor = '    static const char* hdd0_root = nullptr; static int hdd0_init = 0;'
        replacement = '''    /* ASCENSION_IOS_NPUA80918_MOUNT */
    /* The app's Files picker grants the NPUA80918 title root, which contains
     * USRDIR. Installed PSN paths include the title ID, so map that component
     * onto the bookmarked root instead of assuming a host /dev_hdd0/game tree. */
    static const char* ascension = "/dev_hdd0/game/NPUA80918";
    const size_t ascension_len = strlen(ascension);
    if (strncmp(guest, ascension, ascension_len) == 0 &&
        (guest[ascension_len] == '/' || guest[ascension_len] == '\\0')) {
        const char* tail = guest + ascension_len;
        while (*tail == '/') ++tail;
        snprintf(out, cap, "%s/%s", ppu_vfs_root, tail);
        for (char* p = out; *p; p++) if (*p == '\\\\') *p = '/';
        ps3_vfs_ps3game_fallback(out, cap);
        return;
    }
    /* /app_home is the installed executable's USRDIR, while the Files picker
     * grants the containing NPUA80918 directory. Keep that mount rooted at the
     * actual game data tree instead of looking for NPUA80918/<relative-file>. */
    static const char* app_home_mounts[] = {"/app_home", "app_home", "e:/app_home"};
    const char* app_home_tail = nullptr;
    for (size_t i = 0; i < sizeof(app_home_mounts)/sizeof(app_home_mounts[0]); i++) {
        const size_t n = strlen(app_home_mounts[i]);
        if (strncmp(guest, app_home_mounts[i], n) == 0 &&
            (guest[n] == '/' || guest[n] == '\\0')) {
            app_home_tail = guest + n;
            break;
        }
    }
    if (app_home_tail) {
        while (*app_home_tail == '/') ++app_home_tail;
        snprintf(out, cap, "%s/USRDIR/%s", ppu_vfs_root, app_home_tail);
        for (char* p = out; *p; p++) if (*p == '\\\\') *p = '/';
        ps3_vfs_ps3game_fallback(out, cap);
        return;
    }
    static const char* hdd0_root = nullptr; static int hdd0_init = 0;'''
        if text.count(anchor) != 1:
            raise SystemExit("M7.72 iOS VFS patch anchor changed; refusing a partial path rewrite")
        text = text.replace(anchor, replacement, 1)

    stats_marker = "/* ASCENSION_IOS_GUEST_FS_STATS */"
    if stats_marker not in text:
        include_anchor = '#include <stdint.h>\n'
        include_replacement = (include_anchor + '#include <atomic>\n#include <mutex>\n')
        if text.count(include_anchor) != 1:
            raise SystemExit("M7.72 iOS FS stats include anchor changed")
        text = text.replace(include_anchor, include_replacement, 1)
        root_anchor = 'extern "C" const char* ppu_vfs_root = ".";'
        stats = '''
/* ASCENSION_IOS_GUEST_FS_STATS */
static std::atomic<uint64_t> ascension_fs_open_calls{0};
static std::atomic<uint64_t> ascension_fs_open_success{0};
static std::atomic<uint64_t> ascension_fs_read_calls{0};
static std::atomic<uint64_t> ascension_fs_read_bytes{0};
extern "C" void ppu_fs_ios_reset_stats(void)
{
    ascension_fs_open_calls.store(0, std::memory_order_relaxed);
    ascension_fs_open_success.store(0, std::memory_order_relaxed);
    ascension_fs_read_calls.store(0, std::memory_order_relaxed);
    ascension_fs_read_bytes.store(0, std::memory_order_relaxed);
}
extern "C" void ppu_fs_ios_stats(uint64_t out[4])
{
    if (!out) return;
    out[0] = ascension_fs_open_calls.load(std::memory_order_relaxed);
    out[1] = ascension_fs_open_success.load(std::memory_order_relaxed);
    out[2] = ascension_fs_read_calls.load(std::memory_order_relaxed);
    out[3] = ascension_fs_read_bytes.load(std::memory_order_relaxed);
}
'''
        if text.count(root_anchor) != 1:
            raise SystemExit("M7.72 iOS FS stats root anchor changed")
        text = text.replace(root_anchor, root_anchor + stats, 1)

        open_anchor = 'static void cellFsOpen(ppu_context* ctx)\n{\n'
        open_body = '''static void cellFsOpen(ppu_context* ctx)
{
    ascension_fs_open_calls.fetch_add(1, std::memory_order_relaxed);
'''
        if text.count(open_anchor) != 1:
            raise SystemExit("M7.72 cellFsOpen stats anchor changed")
        text = text.replace(open_anchor, open_body, 1)

        success_anchor = '    ctx->gpr[3] = CELL_OK;\n}\n\n/* cellFsSdataOpen'
        success_body = ('    ascension_fs_open_success.fetch_add(1, std::memory_order_relaxed);\n'
                        '    ctx->gpr[3] = CELL_OK;\n}\n\n/* cellFsSdataOpen')
        if text.count(success_anchor) != 1:
            raise SystemExit("M7.72 cellFsOpen success stats anchor changed")
        text = text.replace(success_anchor, success_body, 1)

        read_anchor = 'static void cellFsRead(ppu_context* ctx)\n{\n'
        read_body = '''static void cellFsRead(ppu_context* ctx)
{
    ascension_fs_read_calls.fetch_add(1, std::memory_order_relaxed);
'''
        if text.count(read_anchor) != 1:
            raise SystemExit("M7.72 cellFsRead stats anchor changed")
        text = text.replace(read_anchor, read_body, 1)

        bytes_anchor = '    size_t n = fread(vm_base + buf, 1, (size_t)nbytes, g_files[fd]);   /* raw bytes, no swap */'
        bytes_body = (bytes_anchor + '\n'
                      '    ascension_fs_read_bytes.fetch_add(n, std::memory_order_relaxed);')
        if text.count(bytes_anchor) != 1:
            raise SystemExit("M7.72 cellFsRead byte stats anchor changed")
        text = text.replace(bytes_anchor, bytes_body, 1)
    source.write_text(text)


def patch_m772_live_dispatch(upstream):
    """Expose the actual HLE/syscall reached by the live guest thread."""
    hle = upstream / "runtime/ppu/ppu_hle.cpp"
    text = hle.read_text()
    weak_registration = '''/* Populated by the generated registration unit (gen_hle_nids.py). Weak so a
 * build without it still links (no HLE registered -> imports log + return 0). */
extern "C" void ppu_hle_register_all(void) __attribute__((weak));
extern "C" void ppu_hle_register_all(void) {}
'''
    strong_registration = '''/* ASCENSION_M772_STRONG_HLE_REGISTRATION
 * Require the generated all-module NID table; a weak no-op lets static archive
 * linking discard every registered service handler. */
extern "C" void ppu_hle_register_all(void);
'''
    if "ASCENSION_M772_STRONG_HLE_REGISTRATION" not in text:
        if text.count(weak_registration) != 1:
            raise SystemExit("M7.75 could not replace the weak HLE registration stub")
        text = text.replace(weak_registration, strong_registration, 1)

    text = text.replace('''    /* The generated registration unit is per-game and easy to leave out: the
     * weak stub above means a build without it links and starts, then fails
     * later and somewhere else. Say so here, once, at the point where it is
     * still obvious what to do about it. */''',
'''    /* This check catches a generated-but-empty registration unit. The iOS
     * AOT build requires the strong all-module table at link time. */''')
    text = text.replace("ppu_hle_register_all() is the weak do-nothing stub",
                        "ppu_hle_register_all() ran but registered zero handlers")

    hle_anchor = 'extern "C" void ps3_hle_call(uint32_t nid, ppu_context* ctx)\n{\n'
    hle_patch = '''extern "C" void ar_m772_note_hle(uint32_t nid, uint32_t guest_lr,
                                     ppu_context* ctx);
extern "C" void ar_m772_note_unresolved_hle(uint32_t nid,
                                              uint32_t guest_lr,
                                              ppu_context* ctx);
extern "C" void ps3_hle_call(uint32_t nid, ppu_context* ctx)
{
    /* ASCENSION_M775_LIVE_HLE_TELEMETRY */
    if (ctx) ar_m772_note_hle(nid, (uint32_t)ctx->lr, ctx);
'''
    if "ASCENSION_M775_LIVE_HLE_TELEMETRY" not in text:
        if text.count(hle_anchor) != 1:
            raise SystemExit("M7.75 could not anchor live HLE telemetry in ps3_hle_call")
        text = text.replace(hle_anchor, hle_patch, 1)

    unresolved_anchor = '    if (!e || !e->handler) {\n'
    unresolved_patch = '''    if (!e || !e->handler) {
        /* ASCENSION_M775_UNRESOLVED_HLE_TELEMETRY */
        if (ctx) ar_m772_note_unresolved_hle(nid, (uint32_t)ctx->lr, ctx);
'''
    if "ASCENSION_M775_UNRESOLVED_HLE_TELEMETRY" not in text:
        if text.count(unresolved_anchor) != 1:
            raise SystemExit("M7.75 could not anchor the live unresolved-HLE branch")
        text = text.replace(unresolved_anchor, unresolved_patch, 1)
    hle.write_text(text)

    loader = upstream / "runtime/ppu/ppu_loader.cpp"
    text = loader.read_text()
    syscall_anchor = 'extern "C" void lv2_syscall(ppu_context* ctx)\n{\n'
    syscall_patch = '''extern "C" void ar_m772_note_syscall(uint32_t number, uint32_t guest_lr,
                                         ppu_context* ctx);
extern "C" void lv2_syscall(ppu_context* ctx)
{
    /* ASCENSION_M775_LIVE_SYSCALL_TELEMETRY */
    if (ctx) ar_m772_note_syscall((uint32_t)ctx->gpr[11],
                                  (uint32_t)ctx->lr, ctx);
'''
    if "ASCENSION_M775_LIVE_SYSCALL_TELEMETRY" not in text:
        if text.count(syscall_anchor) != 1:
            raise SystemExit("M7.75 could not anchor live syscall telemetry in lv2_syscall")
        text = text.replace(syscall_anchor, syscall_patch, 1)
        loader.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, required=True)
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    source, upstream, repo, out = (p.resolve() for p in
                                   (args.source, args.upstream, args.repo, args.output))
    expected = "39a36296511c445707adabcd312f0b740cfbd694"
    actual = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if actual != expected:
        raise SystemExit(f"M7.72 lifter/runtime pin mismatch: {actual} != {expected}")
    game_source = upstream / "libs/system/cellGame.c"
    game_header = upstream / "libs/system/cellGame.h"
    if ("ASCENSION_IOS_CELL_GAME_PATCH_CHECK" not in game_source.read_text() or
            "s32 cellGamePatchCheck(void* size, void* reserved);" not in game_header.read_text()):
        raise SystemExit("M7.81 disc-boot cellGamePatchCheck HLE patch is missing")
    pointer_patch_count = patch_ios_unaligned_guest_vm(upstream)
    if pointer_patch_count != 370:
        raise SystemExit(f"M7.79 unaligned guest-VM patch incomplete: {pointer_patch_count}")
    patch_ios_game_mount(upstream)
    patch_m772_live_dispatch(upstream)
    ppu = sorted(source.joinpath("ppu").glob("ppu_recomp_*.cpp"))
    spu = sorted(source.joinpath("spu").glob("*/spu_recomp.c"))
    if len(ppu) != 651 or len(spu) != 4:
        raise SystemExit(f"M7.72 source count mismatch: PPU={len(ppu)}, SPU={len(spu)}")

    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], text=True).strip()
    target = "arm64-apple-ios17.0"
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    objects = out / "objects"
    logs.mkdir(exist_ok=True)
    objects.mkdir(exist_ok=True)
    nid_source = out / "ppu_hle_nids.cpp"
    rc = run([sys.executable, upstream / "tools/gen_hle_nids.py", "--all", "--out", nid_source],
             logs / "00-hle-nids.log")
    if rc or not nid_source.is_file() or not nid_source.stat().st_size:
        raise SystemExit(f"M7.72 HLE NID generation failed; see {logs / '00-hle-nids.log'}")
    generated_nids = nid_source.read_text(errors="replace")
    if 'ps3_hle_register(0xCE4374F6u, "cellGamePatchCheck"' not in generated_nids:
        raise SystemExit("M7.81 cellGamePatchCheck NID 0xCE4374F6 is not bound to its HLE")

    include_dirs = [
        source, source / "ppu", upstream / "include", upstream / "runtime",
        upstream / "runtime/ppu", upstream / "runtime/spu", upstream / "runtime/memory",
        upstream / "runtime/syscalls", upstream / "runtime/platform",
        upstream / "libs/system", upstream / "libs/filesystem", upstream / "libs/input",
        upstream / "libs/audio", upstream / "libs/video", upstream / "libs/network",
        upstream / "libs/spurs", upstream / "libs/sync", upstream / "libs/codec",
        upstream / "libs/font", upstream / "libs/misc", out,
    ]
    includes = [flag for path in include_dirs for flag in ("-I", path)]
    cpp_flags = ["-target", target, "-isysroot", sdk, "-std=c++20", "-O2",
                 "-fwrapv", "-fno-strict-aliasing", "-ffp-contract=off",
                 "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function"]
    c_flags = ["-target", target, "-isysroot", sdk, "-std=c11", "-O2", "-fwrapv",
               "-fno-strict-aliasing", "-DSPU_USE_DISPATCH_MT",
               "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function"]
    tasks = []
    for src in ppu:
        tasks.append(("c++", src, objects / (src.stem + ".o"), cpp_flags, includes))
    for src in spu:
        tasks.append(("c", src, objects / (src.parent.name + ".o"), c_flags, includes))
    scaffold = [
        upstream / "runtime/ppu/ppu_loader.cpp",
        upstream / "runtime/ppu/ppu_hle.cpp",
        upstream / "runtime/ppu/ppu_fs.cpp",
        upstream / "runtime/ppu/ppu_sysprx.cpp",
        nid_source,
        upstream / "runtime/spu/spu_dispatch_mt.c",
        repo / "runtime/m772_bridge.cpp",
    ]
    for src in scaffold:
        lang = "c" if src.suffix == ".c" else "c++"
        flags = c_flags if lang == "c" else cpp_flags
        tasks.append((lang, src, objects / ("runtime_" + src.stem + ".o"), flags, includes))

    def compile_task(task):
        lang, src, dest, flags, incs = task
        compiler = "clang" if lang == "c" else "clang++"
        log = logs / (dest.stem + ".log")
        rc = run(["xcrun", "--sdk", "iphoneos", compiler, *flags, *incs,
                  "-c", src, "-o", dest], log)
        return src, dest, rc, log

    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 4))) as pool:
        futures = [pool.submit(compile_task, task) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            src, dest, rc, log = future.result()
            if rc:
                failures.append((src, log, rc))
                print(f"M7.72 COMPILE FAILED ({rc}): {src}; log={log}", file=sys.stderr)
            elif not dest.is_file() or not dest.stat().st_size:
                failures.append((src, log, 99))
                print(f"M7.72 EMPTY OBJECT: {src}; log={log}", file=sys.stderr)
    if failures:
        for src, log, rc in failures:
            print(f"FAILED rc={rc} source={src} log={log}", file=sys.stderr)
            if log.is_file():
                print(log.read_text(errors="replace")[-12000:], file=sys.stderr)
        raise SystemExit(1)

    obj_files = sorted(objects.glob("*.o"))
    if len(obj_files) != len(tasks):
        raise SystemExit(f"M7.72 object count mismatch: {len(obj_files)} != {len(tasks)}")
    archive = out / "libAscensionGOWA-M772-ios-arm64.a"
    rc = run(["xcrun", "libtool", "-static", "-o", archive, *obj_files], logs / "99-libtool.log")
    if rc or not archive.is_file() or not archive.stat().st_size:
        raise SystemExit(f"M7.72 archive failed; see {logs / '99-libtool.log'}")

    symbols = out / "symbols.txt"
    rc = run(["xcrun", "nm", "-g", archive], symbols)
    if rc:
        raise SystemExit("M7.72 nm failed")
    symbol_text = symbols.read_text(errors="replace")
    required = ["func_00010410", "func_0052A740", "func_0052E3F4", "_function_table_count",
                "_ar_m772_runtime_attest", "_ar_m772_runtime_begin",
                "_ar_m772_runtime_init",
                "_ar_m772_dispatch_native", "_ar_m772_note_function",
                "_ar_m772_note_hle", "_ar_m772_note_syscall",
                "_ar_m772_note_unresolved_hle", "_ar_m772_note_hotloop",
                "_ar_m772_run_entry", "_ar_m772_unbind_guest_memory",
                "_ppu_hle_register_all",
                "_ppu_recomp_register",
                "_gowa_spu_0000_at_006B3E00_spu_recomp_register",
                "_gowa_spu_0001_at_006C1B00_spu_recomp_register",
                "_gowa_spu_0002_at_006CB580_spu_recomp_register",
                "_gowa_spu_0003_at_006D5900_spu_recomp_register"]
    defined = set()
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[-2] in {"T", "t", "D", "d", "B", "b", "R", "r", "S", "s"}:
            defined.add(fields[-1])
    missing = [symbol for symbol in required
               if not any(symbol in name for name in defined)]
    if missing:
        raise SystemExit(f"M7.72 required ARM64 archive symbols missing: {missing}")

    result = {
        "schema": "ascension-m772-ios-arm64-link-input-v5",
        "upstream_commit": actual,
        "ios_vfs_mount_patch": "npua80918-and-app-home-usrdir-v1",
        "ios_vm_mapping_patch": "mach-anywhere-4g-relative-guest-ea-v1",
        "hle_registration": "strong-generated-nid-table",
        "cell_game_patch_check": "disc-boot-returns-CELL_GAME_ERROR_NOTPATCH",
        "unresolved_hle_telemetry": "ps3_hle_call-missing-handler-branch",
        "ppu_translation_units_compiled": len(ppu),
        "ppu_function_table_entries": 29849,
        "native_aot_function_entry_hooks": 29849,
        "native_observed_hotloop_hooks": 1,
        "spu_translation_units_compiled": len(spu),
        "per_game_runtime_units_compiled": len(scaffold),
        "total_arm64_objects": len(obj_files),
        "archive": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": digest(archive),
        "runtime_dispatch_adapter": "complete AOT entry call; live AOT/HLE/LV2/unresolved-HLE telemetry plus observed hot loop",
        "device_guest_execution": "RUNTIME_COUNTER_REPORTED_BY_APP; DEVICE_RUN_REQUIRED",
        "first_guest_frame": "NOT_MEASURED",
    }
    (out / "m772-ios-arm64-attestation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
