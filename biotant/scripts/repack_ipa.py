#!/usr/bin/env python3
"""No-recompile Biomutant iOS repack from a completed, verified GitHub IPA.

Changes ONLY dm/launcher.json in the existing game framework, re-signs the
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
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TITLE = "01004BA017CD6000"
FRAMEWORK = f"DmGame{TITLE}.framework"
APP = "DmShell.app"
IPA_NAME = "BioiOSMutant-Biomutant-60FPS-AB-repack.ipa"


def require(condition, message):
    if not condition:
        raise RuntimeError("[BioiOSMutant lightweight repack] " + message)


def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(*args):
    print("[BioiOSMutant repack]", " ".join(str(x) for x in args[:3]), flush=True)
    subprocess.run([str(x) for x in args], check=True)


def configure_launcher(data):
    """One real engine FPS target + a direct Nintendo A/B swap control.

    DM_FPS is a presentation-only experimental switch. The pinned engine
    hle_fpslock.c instead consumes DM_FPS_TARGET to write the game's Unreal
    t.MaxFPS and rhi.SyncInterval; hle_nvn.c uses it for present pacing too.
    The Shell already passes DM_PAD_MAP to both touch and physical gamepads.
    """
    require(data.get("game", "").upper() == TITLE,
            "Refusing to modify another game's launcher.json")
    require(data.get("schema") in (None, 1), "Unknown launcher schema")
    rows = data.get("settings")
    require(isinstance(rows, list), "Launcher settings are not a list")
    kept = [x for x in rows if x.get("env") not in
            ("DM_FPS", "DM_FPS_TARGET", "DM_PAD_MAP")]
    fps = {
        "env": "DM_FPS_TARGET", "kind": "choice", "section": "Game",
        "label": "Taxa de quadros",
        "note": "30 FPS padrão; 60 FPS desbloqueia t.MaxFPS e rhi.SyncInterval do Unreal. "
                "Cenas pesadas podem ficar abaixo de 60.",
        "default": "30", "options": [
            ["30", "30 FPS (padrão)"], ["60", "60 FPS (desbloqueado)"]
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
    kept[pos:pos] = [fps, swap]
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
            "Real UE target FPS selector is malformed")
    ab = rows["DM_PAD_MAP"]
    require(ab["kind"] == "toggle" and ab["on"] == "A=B,B=A"
            and ab["off"] == ab["default"] == "",
            "A/B mapping must use the Shell's actual PadMap env syntax")
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
                "Game framework identity does not match Biomutant")
        original = json.loads(z.read(fw + "dm/launcher.json"))
        require(original.get("game", "").upper() == TITLE,
                "Wrong framework launcher identity")
        return {"metal_files": sorted(metal), "manifest": manifest,
                "old_launcher": original, "ipa_members": len(names)}


def ensure_preserved(before, after, what):
    require(before == after,
            f"Forbidden rebuild or corruption: {what} SHA-256 changed")


def make_repack(source: Path, target: Path, report: Path):
    require(source.is_file() and source.stat().st_size > 50 * 1024 * 1024,
            "A real, previously completed Biomutant IPA is required")
    require(source.resolve() != target.resolve(), "Output would overwrite input IPA")
    source_details = locate(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="biomutant-repack-") as tmp:
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
        old_bytes = launcher.read_bytes()
        new_json = configure_launcher(json.loads(old_bytes.decode("utf-8")))
        validate_settings(new_json)
        launcher.write_text(json.dumps(new_json, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        require(launcher.read_bytes() != old_bytes,
                "Launcher was not changed: unexpectedly already repacked")
        # Re-sign both nested framework and its enclosing app. Preserve the
        # iOS app's original increased-memory-limit/JIT entitlements.
        run("xattr", "-cr", fw)
        run("codesign", "--force", "--sign", "-", "--timestamp=none", fw)
        run("xattr", "-cr", app)
        run("codesign", "--force", "--sign", "-", "--preserve-metadata=entitlements",
            "--timestamp=none", app)
        run("codesign", "--verify", "--deep", "--strict", app)
        for label, path in important.items():
            ensure_preserved(original_hashes[label], checksum(path), label)
        # ditto recreates a standards-compliant IPA retaining symlinks and modes.
        run("ditto", "-c", "-k", "--keepParent", stage / "Payload", target)
        with zipfile.ZipFile(target) as z:
            bad = z.testzip()
            require(bad is None, "IPA CRC error in " + str(bad))
            fw_prefix = "Payload/" + APP + "/Frameworks/" + FRAMEWORK + "/"
            again = json.loads(z.read(fw_prefix + "dm/launcher.json"))
            validate_settings(again)
            for label, path in important.items():
                # Re-signed file must stay identical, even after ZIP packaging.
                ensure_preserved(original_hashes[label], checksum(path), label)
            require(len([n for n in z.namelist() if n.endswith(".img") and
                         n.startswith(fw_prefix + "msl/")]) >= 1,
                    "Repacked IPA dropped Metal shader image")
            require(not [n for n in z.namelist() if n.lower().endswith(
                        (".nsp", "/romfs.img", "/prod.keys"))],
                    "Repacked IPA contains game package/ROMFS")
        result = {
            "branch": "BioiOSMutant", "title_id": TITLE, "repack_only": True,
            "source_run_id": 44880915730,
            "source_ipa_sha256": checksum(source),
            "result_ipa_sha256": checksum(target),
            "source_bytes": source.stat().st_size,
            "result_bytes": target.stat().st_size,
            "native_macho_recompiled": False,
            "metal_recompiled": False,
            "shader_metal_file_count": len(metal),
            "unchanged_payload_sha256": original_hashes,
            "settings": {
                "fps_env": "DM_FPS_TARGET", "fps_options": ["30", "60"],
                "ab_env": "DM_PAD_MAP", "ab_off": "",
                "ab_on": "A=B,B=A",
            },
            "performance_caveat": "60 FPS internal target enabled, sustained FPS on the device unverified",
            "romfs_external": True,
        }
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print("[BioiOSMutant repack] Success:", json.dumps({
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
