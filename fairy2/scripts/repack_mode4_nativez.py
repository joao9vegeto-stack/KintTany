#!/usr/bin/env python3
"""Fairy2iOS v458752: reference-compatible libz fallback on original failure.

No G1T/G1S substitutions, no synthetic byte arrays, no 64x speculative
re-read loop, no parser bypass. The original Switch deflate path runs normally;
if and ONLY if it returns failure, the same stored chunk can be decoded via
native libz using a verified RFC1950 stream and Adler32. The guest parser and
resource factory then receive exactly their original source bytes.

Mac builds only the host and reuses the 19,210 already-compiled iOS shaders.
Game boot must still be verified on the actual iPhone.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import repack_resource_stages as stage

base = stage.base
BRK = (0xd43e4040).to_bytes(4, "little")
SITES = {
    0xc0ef8c: bytes.fromhex("e9e30191"),  # add x9,sp,#0x78
    0xc0f0d4: bytes.fromhex("e0031f2a"),  # mov w0,wzr
}

def patch_original_codec_guest(exe: Path, source_report: dict):
    stamp = stage.REAL_PATCH_MAIN(exe, source_report)
    parts, old = base.main_sections(exe)
    section = parts["x0"]
    for at, opcode in SITES.items():
        base.require(at + 4 <= section["size"], "codec hook outside guest executable RX")
        base.require(old[at:at+4] == opcode,
                     f"original v458752 codec instruction changed at main+0x{at:x}")
    updated = bytearray(old)
    with exe.open("r+b") as f:
        for at, opcode in SITES.items():
            f.seek(section["offset"] + at)
            base.require(f.read(4) == opcode, "source guest bytes changed during codec patch")
            f.seek(section["offset"] + at)
            f.write(BRK)
            updated[at:at+4] = BRK
    later, written = base.main_sections(exe)
    base.require(written == bytes(updated), "non-code guest section modified")
    base.require(later["w"]["data"] == parts["w"]["data"] and
                 later["x1"]["data"] == parts["x1"]["data"],
                 "guest data or original gate trampoline changed")
    stamp["after_sha256"] = hashlib.sha256(written).hexdigest()
    stamp["x0_after_sha256"] = hashlib.sha256(later["x0"]["data"]).hexdigest()
    stamp["mode4_original_source_only"] = True
    stamp["mode4_ktgl_codec_sites"] = {
        f"main+0x{site:x}": {"old": op.hex(), "new": BRK.hex()}
        for site, op in SITES.items()
    }
    stamp["mode4_original_failure_only"] = True
    return stamp

def verify_original_codec_guest(exe: Path, stamp: dict):
    stage.REAL_VERIFY_MAIN(exe, stamp)
    parts, raw = base.main_sections(exe)
    for at in SITES:
        base.require(raw[at:at+4] == BRK, f"native codec trap lost at main+0x{at:x}")
    base.require(len(stamp.get("mode4_ktgl_codec_sites") or {}) == 2,
                 "mode4 codec guest proof absent")
    base.require(stamp.get("mode4_original_failure_only") is True,
                 "guest codec may have suppressed native successful path")

def patch_host_crash(path: Path, root: Path):
    host = path.read_text()
    anchor = "static void on_crash(int sig, siginfo_t *si, void *uc_) {"
    delegate = "    if (sig == SIGTRAP && g_trap_hook && g_trap_hook(uc)) return;"
    base.require(host.count(anchor) == 1 and host.count(delegate) == 1,
                 "pinned NXNative crash callback contract changed")
    base.require("FAIRY2_KTGL_MODE4_NATIVE_FALLBACK" not in host,
                 "refuse to patch host twice")
    addon = (root / "fairy2/scripts/ktgl_zlib_fallback_host.h").read_text()
    for expected in ("f2_zlib_fail_path_trap(ucontext_t *uc)",
                     "f2_is_zlib_header(source + 8)",
                     "stream.avail_in == 0",
                     "f2_inflate_run(&stream, Z_FINISH)"):
        base.require(expected in addon, "missing original-source zlib fallback guard: "+expected)
    host = host.replace(anchor, addon + "\n" + anchor, 1)
    host = host.replace(delegate,
                        "    if (sig == SIGTRAP && f2_zlib_fail_path_trap(uc)) return;\n"
                        +delegate, 1)
    path.write_text(host)
    base.require(host.count("FAIRY2_KTGL_MODE4_NATIVE_FALLBACK") == 1,
                 "native codec was not included")

def make(source: Path, source_report: Path, repo: Path, output: Path):
    base.require((repo / ".upstream-ref").read_text().strip() ==
                 base.hook.ENGINE_PIN, "pinned engine changed")
    patch_host_crash(repo / "engine/dm/host/crash.c", repo)
    base.patch_main = patch_original_codec_guest
    base.verify_main = verify_original_codec_guest
    base.OUT_NAME = "Fairy2iOS-FairyTail2-OriginalMode4ZlibFallback.ipa"
    result = base.make(source, source_report, repo, output)
    result.update({
        "mode4_source": "original private external RDB/FDATA zlib stream",
        "mode4_fallback_only_if_guest_inflate_fails": True,
        "mode4_native_zlib_integrity_gate": "RFC1950 CMF/FLG + Adler32, full input consumption, max 16384 bytes",
        "mode4_fallback_codec_sites": ["main+0xc0ef8c", "main+0xc0f0d4"],
        "g1t_synthetic_stream": False,
        "g1s_synthetic_stream": False,
        "guest_parser_skipped": False,
        "native_resource_retry": False,
        "number_of_shaders_recompiled": 0,
        "external_romfs_unchanged": True,
        "device_boot_verified": False,
        "not_a_gameplay_fix": True,
        "experimental_crash_correction": True,
        "reference_ports": ["0100C2A01A730000", "01002B00111A2000"],
        "original_source_expected_and_guarded": True,
    })
    (output / "original-mode4-zlib-report.json").write_text(json.dumps(
        result, indent=2, ensure_ascii=False) + "\n")
    return result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source-ipa", required=True, type=Path)
    p.add_argument("--source-report", required=True, type=Path)
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    make(a.source_ipa, a.source_report, a.repo.resolve(), a.output)
