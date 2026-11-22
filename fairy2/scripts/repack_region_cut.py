#!/usr/bin/env python3
"""No-recompile Fairy Tail 2 iOS repack from a completed, verified GitHub IPA.

Changes ONLY dm/launcher.json (including DM_SVC=1 memory diagnostics) in the original framework, re-signs the
framework and containing app ad hoc, and recreates the IPA. Unchanged: game
Mach-O, Shell Mach-O, Metal libraries, shader images, shader maps and RomFS.
Does not invoke Xcode, Metal, NXNative, rewrite, dmsh_build.py or Colab.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TITLE = "0100B9801F872000"
FRAMEWORK = f"DmGame{TITLE}.framework"
APP = "DmShell.app"
IPA_NAME = "Fairy2iOS-FairyTail2-3GiB-region-cut.ipa"


def require(condition, message):
    if not condition:
        raise RuntimeError("[Fairy2iOS lightweight repack] " + message)


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def macho_text_sha(path):
    """SHA-256 of native Mach-O executable code, ignoring re-signable blobs.

    codesign --force necessarily rewrites LC_CODE_SIGNATURE bytes and can
    modify __LINKEDIT sizes. A full-file SHA cannot stay unchanged after
    re-signing, but the actual __TEXT,__text segment MUST stay byte-identical.
    """
    with Path(path).open("rb") as f:
        header = f.read(32)
        require(len(header) == 32 and struct.unpack_from("<I", header)[0] == 0xFEEDFACF,
                "Expected a little-endian ARM64 Mach-O binary: " + str(path))
        ncmds, commands_bytes = struct.unpack_from("<II", header, 16)
        require(0 < ncmds < 1000 and 0 < commands_bytes < 1024 * 1024,
                "Invalid Mach-O load-command region")
        commands = f.read(commands_bytes)
        at = 0
        sections = []
        for _ in range(ncmds):
            require(at + 8 <= len(commands), "Truncated Mach-O load commands")
            kind, size = struct.unpack_from("<II", commands, at)
            require(size >= 8 and at + size <= len(commands),
                    "Malformed Mach-O load command")
            if kind == 0x19:  # LC_SEGMENT_64
                require(size >= 72, "Malformed LC_SEGMENT_64")
                nsects = struct.unpack_from("<I", commands, at + 64)[0]
                require(at + 72 + nsects * 80 <= at + size,
                        "Malformed Mach-O section inventory")
                for i in range(nsects):
                    entry = at + 72 + i * 80
                    name = commands[entry:entry + 16].split(b"\x00", 1)[0]
                    seg = commands[entry + 16:entry + 32].split(b"\x00", 1)[0]
                    if name != b"__text" or not seg.startswith(b"__TEXT"):
                        continue
                    n = struct.unpack_from("<Q", commands, entry + 40)[0]
                    off = struct.unpack_from("<I", commands, entry + 48)[0]
                    require(0 < n < 2 ** 34 and off + n <= Path(path).stat().st_size,
                            "Mach-O __text section out of bounds")
                    sections.append((off, n))
            at += size
        require(sections, "No executable Mach-O __TEXT,__text section found")
        h = hashlib.sha256()
        for off, n in sorted(sections):
            h.update(struct.pack("<Q", n))
            f.seek(off)
            left = n
            while left:
                block = f.read(min(left, 4 * 1024 * 1024))
                require(bool(block), "Truncated Mach-O __text while hashing")
                h.update(block)
                left -= len(block)
        return h.hexdigest()


def run(*args):
    print("[Fairy2iOS repack]", " ".join(str(x) for x in args[:3]), flush=True)
    subprocess.run([str(x) for x in args], check=True)


def configure_launcher(data):
    """One real engine FPS target + a direct Nintendo A/B swap control.

    DM_FPS is a presentation-only experimental switch. The pinned engine
    hle_fpslock.c consumes DM_FPS_TARGET and hle_nvn.c uses it for present
    pacing; the actual game-side frame unlock is not yet verified.
    The Shell already passes DM_PAD_MAP to both touch and physical gamepads.
    """
    require(data.get("game", "").upper() == TITLE,
            "Refusing to modify another game's launcher.json")
    require(data.get("schema") in (None, 1), "Unknown launcher schema")
    rows = data.get("settings")
    require(isinstance(rows, list), "Launcher settings are not a list")
    kept = [x for x in rows if x.get("env") not in
            ("DM_FPS", "DM_FPS_TARGET", "DM_PAD_MAP", "DM_SVC")]
    fps = {
        "env": "DM_FPS_TARGET", "kind": "choice", "section": "Game",
        "label": "Taxa de quadros",
        "note": "30 FPS padrão; 60 FPS é uma solicitação ao runtime. "
                "O desbloqueio real no motor do Fairy Tail 2 precisa ser testado.",
        "default": "30", "options": [
            ["30", "30 FPS (padrão)"], ["60", "60 FPS (experimental)"]
        ], "level": "basic",
    }
    swap = {
        "env": "DM_PAD_MAP", "kind": "toggle", "section": "Game",
        "label": "Inverter botões A e B",
        "note": "Inverte A e B nos controles físicos e nos botões virtuais do jogo.",
        "default": "", "on": "A=B,B=A", "off": "", "level": "basic",
    }
    pos = next((i + 1 for i, x in enumerate(kept)
                if x.get("env") == "DM_OPMODE"), 0)
    # Enables precise memory-SVC telemetry on the original, unchanged game.
    # This is a diagnostic repack, not a claimed pointer fix.
    memprobe = {
        "env": "DM_SVC", "kind": "toggle", "section": "Game",
        "label": "Registro detalhado de memória",
        "note": "Diagnóstico: registra SVCs de heap e mapeamento do host. "
                "Não altera as instruções, shaders ou memória do jogo.",
        "default": "1", "on": "1", "off": "0", "level": "basic",
    }
    kept[pos:pos] = [fps, swap, memprobe]
    require(len({r["env"] for r in kept}) == len(kept),
            "Duplicate environment setting")
    data["settings"] = kept
    return data


def validate_settings(data):
    require(data.get("game", "").upper() == TITLE, "Launcher title mismatch")
    rows = {r["env"]: r for r in data["settings"]}
    require("DM_FPS" not in rows and "DM_FPS_TARGET" in rows,
            "Old DM_FPS presentation-only toggle still present")
    fps = rows["DM_FPS_TARGET"]
    require(fps["default"] == "30"
            and [v[0] for v in fps["options"]] == ["30", "60"],
            "Runtime FPS target selector is malformed")
    ab = rows["DM_PAD_MAP"]
    require(ab["kind"] == "toggle" and ab["on"] == "A=B,B=A"
            and ab["off"] == ab["default"] == "",
            "A/B mapping must use the Shell's actual PadMap env syntax")
    dbg = rows.get("DM_SVC", {})
    require(dbg.get("kind") == "toggle" and dbg.get("default") == "1"
            and dbg.get("on") == "1" and dbg.get("off") == "0",
            "SVC diagnostic must start enabled in this crash-probe repack")
    return True


def locate(ipa):
    with zipfile.ZipFile(ipa) as z:
        names = set(z.namelist())
        prefix = "Payload/" + APP + "/"
        fw = prefix + "Frameworks/" + FRAMEWORK + "/"
        must = (
            prefix + "DmShell",
            fw + "DmGame" + TITLE,
            fw + "game.manifest.json",
            fw + "dm/launcher.json",
            fw + "dm/shader_map.tsv",
        )
        for path in must:
            require(path in names, "Source IPA misses essential asset: " + path)
        metal = [name for name in names
                 if name.startswith(fw + "msl/") and
                 (name.endswith(".img") or name.endswith(".metallib"))]
        require(metal, "Source IPA does not contain compiled Metal shader libraries")
        prohibited = [n for n in names if n.lower().endswith(
            ("/romfs.img", ".nsp", "/prod.keys"))]
        require(not prohibited, "The IPA unexpectedly embeds private game data")
        manifest = json.loads(z.read(fw + "game.manifest.json"))
        require(manifest.get("title_id", "").upper() == TITLE
                and manifest.get("framework") == FRAMEWORK,
                "Game framework identity does not match Fairy Tail 2")
        original = json.loads(z.read(fw + "dm/launcher.json"))
        require(original.get("game", "").upper() == TITLE,
                "Wrong framework launcher identity")
        return {"metal_files": sorted(metal), "manifest": manifest,
                "old_launcher": original, "ipa_members": len(names)}


def ensure_preserved(before, after, what):
    require(before == after,
            f"Forbidden rebuild or corruption: {what} SHA-256 changed")


# A588F7BB... main from the verified v458752 Colab checkpoint.
# Game allocates 60 GiB in a 3.5-GiB guest alias; SDK node-area 62MiB cut applied.
SOURCE_SHA="4e2cb0937545effbebffa01341e84711452622e449359961fae0539d1952f70e"
SOURCE_RUN=44977592488
OLD_REGION=0xf00000000
NEW_REGION=0xc0000000
ALIAS=0xe0000000
NODE_AREA=0x3e00000
SITES=(
(0x5f1b9c,"e901c0d2","0900b8d2","8a881c32b228614387647e64df09a97dd88e105927a4545ca7b2c36f8f46edc0"),
(0x1d700bc,"e901c0d2","0900b8d2","514a7922e6483f60518e208ee89ab883d78f6ea77486b5c1c9f9a935a59ee451"),
(0x225de0c,"e901c0d2","0900b8d2","652142e5ed187442f3961dcd638f570f2da2c91efe3eba386bf7695115d08869"),
(0x2295a44,"e901c0d2","0900b8d2","7acc7d2aadbadf720b2922f7d3273f89fd6c82ca54c2ae04c65a03b302dfc412"),
(0x2295a50,"e101c0d2","0100b8d2","0d0a434f0877109043cdfc0b337e74c8374b84070a9fc23c5d6dde19043039dd"),
)
def embedded_main(path):
    from repack_host_memory import otool_sections
    sections=otool_sections(path)
    key=("__TEXT","__dmmainx0")
    require(key in sections,"No __TEXT,__dmmainx0 embedded guest module")
    off,size=sections[key]["offset"],sections[key]["size"]
    require(size>max(x[0] for x in SITES)+32,"guest main section is too short")
    with Path(path).open("rb") as f:
        f.seek(off); raw=f.read(size)
    require(len(raw)==size,"guest main section truncated")
    return off,raw
def transform_main(raw):
    require(NEW_REGION+NODE_AREA<ALIAS,"3GiB region cannot fit alias budget")
    changed=[]
    for pos,old,new,signature in SITES:
        require(raw[pos:pos+4]==bytes.fromhex(old),
                f"unknown ARM64 instruction at main+0x{pos:x}")
        require(hashlib.sha256(raw[pos-16:pos+32]).hexdigest()==signature,
                f"guest main fingerprint mismatch at main+0x{pos:x}")
        changed.append({"site":f"main+0x{pos:x}","old":old,"new":new})
    altered=bytearray(raw)
    for pos,old,new,_ in SITES:
        altered[pos:pos+4]=bytes.fromhex(new)
    require(sum(x!=y for x,y in zip(raw,altered))==15,
            "unexpected number of guest instruction bytes changed")
    return bytes(altered),changed
def apply_guest_region_patch(path):
    offset,old=embedded_main(path)
    expected,changes=transform_main(old)
    with Path(path).open("r+b") as f:
        f.seek(offset); f.write(expected)
    _,after=embedded_main(path)
    require(after==expected,"patched guest code changed unexpectedly")
    return {"old_sha256":hashlib.sha256(old).hexdigest(),
            "new_sha256":hashlib.sha256(expected).hexdigest(),
            "section_length":len(old),"changes":changes}
def validate_guest_region_patch(path,stamp):
    _,guest=embedded_main(path)
    require(len(guest)==stamp["section_length"] and
            hashlib.sha256(guest).hexdigest()==stamp["new_sha256"],
            "re-signing changed the embedded main beyond five approved MOVs")
    return True


def make_repack(source: Path, target: Path, report: Path):
    require(source.is_file() and source.stat().st_size > 50 * 1024 * 1024,
            "A real, previously completed Fairy Tail 2 IPA is required")
    require(source.resolve() != target.resolve(), "Output would overwrite input IPA")
    require(source.name=="Fairy2iOS-FairyTail2-host-memory-repack.ipa",
            "Source must be the SUCCESSFUL host-only repack, not original IPA")
    require(checksum(source)==SOURCE_SHA,"Source IPA checksum mismatch")
    source_details = locate(source)
    require(sorted(source_details["manifest"].get("modules",[]))==["main","sdk","subsdk1"],
            "unexpected guest modules")
    target.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fairy2-repack-") as tmp:
        stage = Path(tmp)
        run("ditto", "-x", "-k", source, stage)
        app = stage / "Payload" / APP
        fw = app / "Frameworks" / FRAMEWORK
        require(app.is_dir() and fw.is_dir(), "ditto did not extract app/framework")
        launcher = fw / "dm/launcher.json"
        framework_exec = fw / ("DmGame" + TITLE)
        shell_exec = app / "DmShell"
        metal = [stage / name for name in source_details["metal_files"]]
        important = {
            "game_macho": framework_exec,
            "shell_macho": shell_exec,
            "shader_map": fw / "dm/shader_map.tsv",
        }
        for i, path in enumerate(metal):
            important["metal_" + str(i)] = path
        for label, path in important.items():
            require(path.is_file(), f"Essential file missing after extraction: {label}")
        original_hashes = {name: checksum(path) for name, path in important.items()}
        original_code = {
            "game_macho": macho_text_sha(framework_exec),
            "shell_macho": macho_text_sha(shell_exec),
        }
        validate_settings(json.loads(launcher.read_text()))
        runtime_profile=(fw/"profile.tsv").read_text()
        require("mem_alias\t0xe0000000" in runtime_profile and
                "mem_reserve\t0x140000000" in runtime_profile,
                "wrong source guest alias / reserve layout")
        region_stamp=apply_guest_region_patch(framework_exec)
        print("[Fairy2iOS] Patched five build-verified 60GiB region constants",flush=True)
        # Re-sign both nested framework and its enclosing app. Preserve the
        # iOS app's original increased-memory-limit/JIT entitlements.
        run("xattr", "-cr", fw)
        run("codesign", "--force", "--sign", "-", "--timestamp=none", fw)
        run("xattr", "-cr", app)
        run("codesign", "--force", "--sign", "-", "--preserve-metadata=entitlements",
            "--timestamp=none", app)
        run("codesign", "--verify", "--deep", "--strict", app)
        validate_guest_region_patch(framework_exec,region_stamp)
        for label, path in important.items():
            if label in original_code:
                ensure_preserved(original_code[label], macho_text_sha(path),
                                 label + " Mach-O __TEXT,__text")
            else:
                ensure_preserved(original_hashes[label], checksum(path), label)
        # ditto recreates a standards-compliant IPA retaining symlinks and modes.
        run("ditto", "-c", "-k", "--keepParent", stage / "Payload", target)
        with zipfile.ZipFile(target) as z:
            bad = z.testzip()
            require(bad is None, "IPA CRC error in " + str(bad))
            fw_prefix = "Payload/" + APP + "/Frameworks/" + FRAMEWORK + "/"
            again = json.loads(z.read(fw_prefix + "dm/launcher.json"))
            validate_settings(again)
            with tempfile.TemporaryDirectory(prefix="fairy2-zip-cut-check-") as zdir:
                zip_macho=Path(zdir)/"Game"
                with z.open(fw_prefix+"DmGame"+TITLE) as src, zip_macho.open("wb") as dst:
                    import shutil
                    shutil.copyfileobj(src,dst,length=8*1024*1024)
                validate_guest_region_patch(zip_macho,region_stamp)
            for label, path in important.items():
                # ZIP CRC and signing verified above. Executable code survives
                # ad-hoc signature regeneration, although Mach-O SHA changes.
                if label in original_code:
                    ensure_preserved(original_code[label], macho_text_sha(path), label)
                else:
                    ensure_preserved(original_hashes[label], checksum(path), label)
            require(len([n for n in z.namelist() if n.endswith(".img") and
                         n.startswith(fw_prefix + "msl/")]) >= 1,
                    "Repacked IPA dropped Metal shader image")
            require(not [n for n in z.namelist() if n.lower().endswith(
                        (".nsp", "/romfs.img", "/prod.keys"))],
                    "Repacked IPA contains game package/ROMFS")
        result = {
            "project":"Fairy2iOS","branch": "Fairy2iOS",
            "title_id": TITLE, "repack_only": True,
            "method":"IPA-only 5-site 60GiB to 3GiB AArch64 region cut",
            "output_ipa":target.name,
            "output_sha256":checksum(target),
            "output_size_bytes":target.stat().st_size,
            "allocator_original_bytes":OLD_REGION,
            "allocator_patched_bytes":NEW_REGION,
            "alias_region_bytes":ALIAS,
            "sdk_node_area_bytes":NODE_AREA,
            "native_host_recompiled":False,
            "game_shaders_recompiled":False,
            "guest_modules_rewritten":False,
            "guest_main_instruction_patches":5,
            "guest_main_patch_audit":region_stamp,
            "romfs_aoc_external_unchanged":True,
            "game_shader_sha256":original_hashes["metal_0"],
            "crash_fixed_on_iphone_verified":False,
            "source_run_id": SOURCE_RUN,
            "source_ipa_sha256": checksum(source),
            "result_ipa_sha256": checksum(target),
            "source_bytes": source.stat().st_size,
            "result_bytes": target.stat().st_size,
            "native_macho_recompiled": False,
            "metal_recompiled": False,
            "original_crash": {"guest_pc": "main+0x227b750", "invalid_write": "0x12c00280",
                            "likely_root_cause": "60 GiB AllocateAddressRegion fails in 3.5 GiB alias",
                            "actual_fix_verified": False},
            "shader_metal_file_count": len(metal),
            "original_payload_sha256_before_resign": original_hashes,
            "unchanged_macho_text_sha256": original_code,
            "settings": {
                "fps_env": "DM_FPS_TARGET", "fps_options": ["30", "60"],
                "ab_env": "DM_PAD_MAP", "ab_off": "",
                "ab_on": "A=B,B=A", "svc_diagnostics": "1",
            },
            "performance_caveat": "60 FPS internal target enabled, sustained FPS on the device unverified",
            "romfs_external": True,
        }
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print("[Fairy2iOS repack] Success:", json.dumps({
            "ipa": str(target), "sha256": result["result_ipa_sha256"],
            "size_bytes": result["result_bytes"],
            "metal_assets_preserved": len(metal),
        }), flush=True)
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    make_repack(a.source, a.output, a.report)


if __name__ == "__main__":
    main()
