#!/usr/bin/env python3
"""HookLink2iOS: genuine HookLink 4.0 / nxnative X3 rebuild from verified NUP.

The previous 1.8.5 IPA/shader image cannot be used: X3 changes its shader
translation ABI. Reuses ONLY the verified NUP / RomFS-input manifest from
the earlier handoff. New host, translated shaders, Metal libraries and app.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_PIN = "ee3ce6a02bc737d38795f0a96cce494cee7a799c"
ORIGINAL_PIN = "cf2a2fecc6ce3fb841131ffeffa90915cdadf109"
CHAIN = "b6112b954691"
TITLE = "0400486024DEC000"
VERSION = "v131072"
NEW_AOC_ANCHOR = (
    "    aoc = stage_external_dlc(work, aoc_dir) if aoc_dir is not None "
    "else extract_aoc(nx, keys, repo, work, app, fam, logs)\n"
)

def insist(ok, message):
    if not ok:
        raise RuntimeError("[HookLink2iOS v4] " + message)

def rows(path):
    fields = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "\t" in line:
            key, value = line.split("\t", 1)
            fields[key] = value
    return fields

def verify_v4_engine(engine):
    sha = subprocess.check_output(
        ["git", "-C", str(engine), "rev-parse", "HEAD"], text=True
    ).strip()
    insist(sha == UPSTREAM_PIN, "refusing unverified nxnative version " + sha)
    g = engine / "dm/games" / TITLE
    profile = rows(g / "game.tsv")
    insist(profile.get("title_id") == TITLE and profile.get("package") == VERSION, "Ocarina game profile/version mismatch")
    insist(profile.get("mem_alias") == "0x400000000" and profile.get("mem_reserve") == "0x620000000", "X3 16-GiB virtual alias space missing")
    insist(profile.get("pool_skip_retired") == "on", "X3 retired-texture protection missing")
    insist(profile.get("pso_mtl4") == "on", "Metal 4 pipeline profile missing")
    insist(profile.get("upscaler_chain", "").endswith("|d99fbeeb53d38847"), "X3 dynamic-resolution NDSR last-stage variant missing")
    assert (g / "shader_map.tsv").is_file() or (g / "shader_pairs.tsv").is_file()
    header = (engine / "dm/gfx/nvn/dmsh_chain.h").read_text(encoding="utf-8")
    insist(f'#define DMSH_CHAIN "{CHAIN}"' in header, "X3 new shader chain missing/changed; cannot use old cache")
    lock = rows(engine / "dm/gfx/tools/dmsh_chain.lock")
    insist(bool(lock.get("dmsh_xlate")) and bool(lock.get("metal_iphoneos")), "X3 compiler lock missing")
    settings = rows(engine / "dm/games/settings.tsv")
    insist("DM_NVN_TEX_MIP_SKIP" in settings and "DM_NVN_OCC_GPU" in settings, "X3 memory saver / GPU occlusion controls missing")
    project = (engine / "dm/ios/project.yml").read_text(encoding="utf-8")
    insist('iOS: "26.0"' in project, "X3 does not target iOS 26.0")
    builder = (engine / "scripts/build_ipa_from_nsp.py").read_text(encoding="utf-8")
    insist(builder.count(NEW_AOC_ANCHOR) == 1, "X3 NUP extract boundary changed; refusing destructive patch")
    insist("--allow-damaged" in builder and "--work-dir" in builder, "X3 builder argument contract changed")
    insist((engine / "dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate").is_file(), "missing X3 shader translator")
    insist((engine / "dm/gfx/tools/spirv_cross_bin/spirv-cross").is_file(), "missing pinned spirv-cross")
    print("HOOKLINK2IOS_V4_ENGINE_OK", sha, "chain", CHAIN, flush=True)

def release_verified_nup_after_extract(engine):
    """The X3-only hook, applied before the 25.6-GB download and fail-closed."""
    path = engine / "scripts/build_ipa_from_nsp.py"
    source = path.read_text(encoding="utf-8")
    marker = "    # HookLink2iOS v4: reclaim verified input NUP only after complete extraction.\n"
    if marker in source:
        return
    insist(source.count(NEW_AOC_ANCHOR) == 1, "missing unique X3 AOC/extraction boundary")
    extra = (
        marker
        + "    if fam.get('nup') is not None:\n"
        + "        _hl4_nup = fam['nup']\n"
        + "        _hl4_path = _hl4_nup.path\n"
        + "        _hl4_nup.close()\n"
        + "        fam['nup'] = None\n"
        + "        _hl4_path.unlink()\n"
        + "        say(f'HookLink2iOS 4.0: NUP extraído e liberado ({_hl4_path.name}); '
"
        + "            f'{shutil.disk_usage(work).free / 2**30:.1f} GiB livres para Metal')\n"
    )
    path.write_text(source.replace(NEW_AOC_ANCHOR, NEW_AOC_ANCHOR + extra), encoding="utf-8")
    insist(marker in path.read_text(encoding="utf-8"), "X3 NUP release hook not written")

def upgraded_manifest(original):
    """Original handoff is input provenance, never evidence of X3-prepared shaders."""
    insist(original.get("project") == "HookLink2iOS" and original.get("branch") == "HookLink2iOS", "wrong input handoff")
    insist(original.get("title_id") == TITLE and original.get("package_version") == VERSION, "wrong update/title")
    insist(original.get("engine", {}).get("commit") == ORIGINAL_PIN, "source must be the validated 1.8.5 NUP handoff")
    insist(original.get("gpu_arch") == "none", "offline PSO must remain disabled")
    for k in ("nup", "romfs", "resolution_overlay"):
        r = original.get(k, {})
        insist(r.get("id") and int(r.get("size", 0)) > 0 and re.fullmatch(r"[0-9a-f]{64}", r.get("sha256", "")), "invalid verified " + k + " record")
    identity = original["romfs"].get("identity", "")
    insist(re.search(r"^DMROMFSID1 title=" + TITLE + r" version=" + VERSION + r" build=" + ORIGINAL_PIN + r" size=\d+ index=[0-9a-f]+$", identity), "verified RomFS identity unexpectedly changed")
    target = copy.deepcopy(original)
    target["engine"]["commit"] = UPSTREAM_PIN
    target["engine"]["branch"] = "hooklink"
    target["romfs"]["identity"] = identity.replace("build=" + ORIGINAL_PIN, "build=" + UPSTREAM_PIN)
    target["v4_migration"] = {"from_engine": ORIGINAL_PIN, "target_engine": UPSTREAM_PIN, "shader_chain": CHAIN, "shader_rebuild_required": True, "source": "verified-original-NUP-not-original-IPA"}
    return target

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    insist(os.environ.get("GITHUB_REF") == "refs/heads/HookLink2iOS", "wrong git branch")
    verify_v4_engine(args.engine)
    raw = json.loads(args.handoff.read_text(encoding="utf-8"))
    upgraded = upgraded_manifest(raw)
    os.environ.pop("DMSH_CAS", None)  # X3 uses its own cas-<chain>.db generation.
    os.environ.update({
        "DM_QOS_MAP_DEFAULT": "1",
        "DM_DYNRES_DEFAULT": "1",
        "DM_THERMAL_CAP_DEFAULT": "0",
        "DM_FRAME_MODE_DEFAULT": "2",
        "DM_FRAMEGEN_SCALE_DEFAULT": "0.75",
        "DM_SHOW_FPS": "1",
        "DMSH_TARGETS": "mac,ios",
    })
    spec = importlib.util.spec_from_file_location(
        "hooklink2ios_legacy_builder", ROOT / "scripts/hooklink2ios_build.py"
    )
    insist(spec and spec.loader, "missing tested NUP / Drive transfer implementation")
    base = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = base
    spec.loader.exec_module(base)
    base.ENGINE_PIN = UPSTREAM_PIN
    base.preflight_hooklink_engine = verify_v4_engine
    base.patch_nxnative_release_nup_after_extract = release_verified_nup_after_extract
    old_class = base.ShaderCacheCheckpoint
    class X3Checkpoint(old_class):
        NAME = "hooklink2ios-x3-" + CHAIN + "-shader-cache.db"
        CACHE_TAG = "shader-cas-x3-" + CHAIN
        def __init__(self, drive, session, folder_id, cache_path, interval=900):
            p = Path(cache_path)
            insist(p.name == "cas.db", "old builder's shader-cache location changed")
            super().__init__(drive, session, folder_id, p.with_name(f"cas-{CHAIN}.db"), interval)
    base.ShaderCacheCheckpoint = X3Checkpoint
    with tempfile.TemporaryDirectory(prefix="hooklink2ios-v4-manifest-") as tmp:
        manifest = Path(tmp) / "handoff-v4-derived.json"
        manifest.write_text(json.dumps(upgraded, indent=2) + "\n", encoding="utf-8")
        old_argv = sys.argv
        try:
            sys.argv = [str(ROOT / "scripts/hooklink2ios_build.py"), "--handoff", str(manifest),
                        "--engine", str(args.engine), "--output", str(args.output)]
            base.main()
        finally:
            sys.argv = old_argv
    report_path = args.output / "build-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    insist(report.get("engine_commit") == UPSTREAM_PIN, "published IPA used wrong native engine")
    insist(report.get("ipa", {}).get("size", 0) < 4_000_000_000, "new IPA exceeds safe sideload size: investigate Metal-image compression")
    insist(report.get("ipa", {}).get("contents", {}).get("msl_files"), "missing freshly rebuilt iOS Metal shaders")
    report["hooklink_release"] = "4.0"
    report["shader_chain"] = CHAIN
    report["original_1_8_shader_image_reused"] = False
    report["new_4_0_shader_rebuild_required"] = True
    report["input_handoff_engine"] = ORIGINAL_PIN
    report["input_manifest_sha256"] = hashlib.sha256(args.handoff.read_bytes()).hexdigest()
    report["upstream_hooklink"] = "https://github.com/dsi-hub/HookLink/tree/b5c41acf469edb99abc5156f1f6f18397261f54a"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("HOOKLINK2IOS_V4_REAL_BUILD_OK", report["ipa"]["size"], report["ipa"]["sha256"], flush=True)

if __name__ == "__main__":
    main()
