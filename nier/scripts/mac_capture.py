#!/usr/bin/env python3
"""Finish only those shader inputs that require a native Apple Silicon game host.

Never download NSPs, re-extract RomFS, redo the AArch64 rewrite or re-run
the Linux shader split when its package was already verified.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from port_stages import source_flags, deferred_mac_stages, require_valid_stage_list


def fail(reason: str):
    raise RuntimeError("[Nier2iOS Mac shader capture] " + reason)


def complete(builder, engine: Path, version: Path, patched: Path,
             work: Path, env: dict, logs: Path, profile, prep: dict, py: str,
             sources: dict) -> tuple[str | None, list[Path]]:
    """Return verified NVN split key and any GL/Vulkan run-time capture folder."""
    flags = source_flags(sources)
    if flags != prep.get("source_capture_flags"):
        fail(f"source capture facts changed since Colab: {flags} != {prep.get('source_capture_flags')}")
    jit = bool(builder.uses_jit(version / "ExeFS"))
    if jit != bool(prep.get("jit_required")):
        fail("JIT requirement differs from the original Linux survey")
    stages = require_valid_stage_list(prep.get("mac_host_stages"))
    expected = deferred_mac_stages(
        sources, jit=jit, linux_ue_complete=bool(prep.get("linux_ue_decode_complete")))
    if stages != expected:
        fail(f"macOS capture plan has drifted from real game inputs: {stages} != {expected}")
    if not isinstance(prep.get("shader_versions"), list) or not prep["shader_versions"]:
        fail("shader source versions missing from Colab manifest")
    dirs = {}
    for marker in prep["shader_versions"]:
        if not isinstance(marker, str) or not re.fullmatch(r"v[0-9]+", marker):
            fail(f"invalid shader version in Colab manifest: {marker!r}")
        candidate = work / "extract" / marker
        if not (candidate / "ExeFS/main").is_file() or not (candidate / "RomFS.img").is_file():
            fail(f"Colab/Drive did not provide complete shader input {marker} (ExeFS and RomFS)")
        dirs[marker] = candidate
    if prep.get("package_version") not in dirs:
        fail("packed update version is not among extracted shader inputs")
    if prep.get("linux_ue_decode_complete"):
        for marker, d in dirs.items():
            stamp = d / "ue_shaders/stamp"
            if not stamp.is_file() or stamp.read_text() != builder.ue_stamp(d):
                fail(f"Linux-decoded UE shader archive changed or vanished for {marker}")
        print("[Nier2iOS] UE shader decoding completed on Linux; no Mac decoder needed.", flush=True)

    observed_glslc = None
    capture_root = None
    if "glslc_capture" in stages:
        print("[Nier2iOS] Mac host: authentic game-generated GLSLC shader capture.", flush=True)
        observed_glslc = builder.capture_glslc(
            engine, dirs, prep["package_version"], patched, work, env, logs, profile)
    if "ue_decode" in stages:
        print("[Nier2iOS] Mac host: game Oodle/IoStore shader decoder.", flush=True)
        builder.decode_ue_shaders(
            engine, dirs, prep["package_version"], patched, work, env, logs, profile)
    if "vk_capture" in stages:
        print("[Nier2iOS] Mac host: Vulkan runtime capture with game-derived inputs.", flush=True)
        capture_root = builder.capture_shaders(
            engine, version, patched, work, env, logs, profile, "vk")
    if "gl_capture" in stages:
        print("[Nier2iOS] Mac host: OpenGL runtime shader capture.", flush=True)
        capture_root = builder.capture_shaders(
            engine, version, patched, work, env, logs, profile, "gl")

    key = prep.get("shader_package_key")
    if prep["graphics"] == "nvn":
        split_stage = prep.get("shader_split_stage")
        if split_stage == "linux_complete":
            print("[Nier2iOS] Reusing Linux shader split; no expensive Mac re-split.", flush=True)
        elif split_stage == "mac_pending":
            required_before_split = set(stages) - {"jit_capture"}
            if not required_before_split:
                fail("Mac shader split requested without a required native capture/decoder")
            decoder = None
            if any(x in stages for x in ("oodle_packs", "ue_legacy")):
                decoder = lambda: {
                    "DM_OODLE_HOST": str(builder.build_mac_host(
                        engine, work / "tools/dmhost", env, logs, profile)),
                    "DM_OODLE_MODULES": str(patched),
                }
            print("[Nier2iOS] Mac NVN split: required native shader inputs now exist; "
                  "the preceding Linux extraction and rewrite are reused.", flush=True)
            key = builder.split_shaders(
                py, engine,
                [builder.rfs.source(d) for d in dirs.values()],
                [d / "ExeFS/main" for d in dirs.values()],
                work / "shader" / "pkg", env, logs, profile,
                provisional=bool(prep["provisional"]), oodle=decoder)
        else:
            fail(f"unexpected Linux NVN split stage {split_stage!r}")
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
            fail("real NVN split did not return a valid SHA-256 key")
        if builder.package_key(work / "shader" / "pkg") != key:
            fail("finished NVN shader package failed checksum verification")
        if observed_glslc is not None:
            builder.check_glslc_coverage(observed_glslc, profile)
    elif prep.get("shader_split_stage") != "metal_deferred" or key is not None:
        fail("GL/Vulkan shader stage is not a valid Linux checkpoint")
    return key, ([capture_root] if capture_root is not None else [])


def finish_jit_if_needed(builder, engine, version, patched, work, env, logs,
                         profile, prep, py):
    if not prep.get("jit_required"):
        return
    if "jit_capture" not in require_valid_stage_list(prep.get("mac_host_stages")):
        fail("JIT capture flagged in Linux without a host operation in the manifest")
    print("[Nier2iOS] Mac host: capturing real nn::jit output, after shader preparation.", flush=True)
    result = builder.capture_jit(py, engine, version, patched, work, env, logs, profile)
    if not Path(result).is_dir() or not any(Path(result).rglob("*")):
        fail("game's JIT image was not produced")
