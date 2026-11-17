#!/usr/bin/env python3
"""Repackage Kakarot's verified Metal image as the directory the iOS NVN host reads.

This is a resource-only repair of a previously built IPA. It never runs shader
translation, dmsh_build.py, Metal compilation, NSP extraction, or game rewriting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

TITLE_ID = "010051C0134F8000"
PROJECT = "KaKaRoTiOS"
BRANCH = "KaKaRoTiOS"
PACKAGE_VERSION = "v1048576"
ENGINE_PIN = "81906931262fb25d774cce8bca2db8926439e5a2"
CHAIN = "0c434f1b68df"
INPUTS = "c1afd2abe10a"
PACKAGE_KEY = "01a2622118c296274012da182f06801a66fed4f8aa1e8f1db3fe6ef60937ec0a"
SOURCE_RUN_ID = 43979353925
SOURCE_ARTIFACT_ID = 14283857940
METAL_SOURCE_RUN_ID = 43864761674
METAL_IMAGE_SHA256 = "29d30b869e7ccf15157e71b1b825698dd032ee27d005f8b15e10c935e33b1e24"
METAL_IMAGE_SIZE = 7289135427
FRAMEWORK_NAME = f"DmGame{TITLE_ID}.framework"
METALLIB_PROBE = "ab9a251449977e2b_b.metallib"
JSON_PROBE = "00011444f89c60a0_b.json"


def fail(message: str) -> None:
    raise SystemExit("[KaKaRoTiOS shader-folder repair] ERROR: " + message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def run(command, *, cwd: Path | None = None, capture: bool = False):
    command = [str(x) for x in command]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command, cwd=cwd, check=False, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        detail = ((result.stdout or "") + "\n" + (result.stderr or ""))[-12000:]
        fail(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_entitlements(executable: Path, destination: Path) -> dict:
    result = subprocess.run(
        ["/usr/bin/codesign", "-d", "--entitlements", ":-", str(executable)],
        capture_output=True, text=True, check=False,
    )
    raw = (result.stdout or "") + "\n" + (result.stderr or "")
    start, end = raw.find("<?xml"), raw.rfind("</plist>")
    if result.returncode != 0 or start < 0 or end < start:
        fail("could not read the existing DmShell entitlements; refusing to lose Increased Memory Limit")
    xml = raw[start:end + len("</plist>")]
    try:
        entitlements = plistlib.loads(xml.encode("utf-8"))
    except Exception as exc:
        fail(f"the source DmShell entitlements are not valid plist XML: {exc}")
    require(
        entitlements.get("com.apple.developer.kernel.increased-memory-limit") is True,
        "source app does not carry Increased Memory Limit",
    )
    destination.write_bytes(plistlib.dumps(entitlements, fmt=plistlib.FMT_XML, sort_keys=False))
    return entitlements


def validate_source_report(report: dict, ipa: Path) -> dict:
    expected = {
        "project": PROJECT,
        "branch": BRANCH,
        "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION,
        "engine_pin": ENGINE_PIN,
        "shader_chain": CHAIN,
        "shader_package_key": PACKAGE_KEY,
        "framework": FRAMEWORK_NAME,
    }
    for key, value in expected.items():
        require(report.get(key) == value,
                f"source build report mismatch for {key}: {report.get(key)!r} != {value!r}")
    require(report.get("ipa") == ipa.name, "source build report names another IPA")
    require(int(report.get("ipa_size_bytes", -1)) == ipa.stat().st_size,
            "source IPA size differs from its build report")
    reuse = report.get("shader_reuse") or {}
    require(reuse.get("source_run_id") == METAL_SOURCE_RUN_ID,
            "source IPA does not reuse the expected successful Build #6 Metal output")
    require(reuse.get("chain") == CHAIN and reuse.get("inputs") == INPUTS,
            "source IPA shader chain/input identity differs")
    image = reuse.get("metal_image") or {}
    require(image.get("sha256") == METAL_IMAGE_SHA256 and int(image.get("size", -1)) == METAL_IMAGE_SIZE,
            "source report does not identify the verified Build #6 Metal image")
    require(reuse.get("metal_compilation_executed") is False,
            "source build unexpectedly reports Metal compilation")
    require(reuse.get("shader_translation_executed") is False,
            "source build unexpectedly reports shader translation")
    return reuse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-run-id", type=int, required=True)
    parser.add_argument("--source-artifact-id", type=int, required=True)
    args = parser.parse_args()

    require(sys.platform == "darwin", "the signed IPA repack must run on macOS")
    require(args.source_run_id == SOURCE_RUN_ID, "unexpected source workflow run")
    require(args.source_artifact_id == SOURCE_ARTIFACT_ID, "unexpected source artifact ID")

    engine = args.engine_root.resolve()
    source_dir = args.source_dir.resolve()
    output = args.output.resolve()
    upstream_ref = engine.parent / ".upstream-ref"
    require(upstream_ref.is_file(), "pinned NX2Apple checkout is missing")
    require(upstream_ref.read_text(encoding="utf-8").strip() == ENGINE_PIN, "NXNative pin mismatch")
    packer = engine / "dm/ios/tools/pack_ipa.py"
    require(packer.is_file(), "pinned NXNative IPA packer is missing")

    ipas = sorted(source_dir.glob("*.ipa"))
    reports = sorted(source_dir.glob("build-report.json"))
    require(len(ipas) == 1 and len(reports) == 1,
            f"source artifact must contain exactly one IPA and one report; found {len(ipas)} and {len(reports)}")
    source_ipa = ipas[0]
    source_report = json.loads(reports[0].read_text(encoding="utf-8"))
    source_reuse = validate_source_report(source_report, source_ipa)
    print(f"Source IPA verified: {source_ipa.stat().st_size:,} bytes; no game or shader rebuild.", flush=True)

    output.mkdir(parents=True, exist_ok=True)
    work = output / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    unpacked = work / "unpacked"
    unpacked.mkdir()
    run(["/usr/bin/unzip", "-q", source_ipa, "-d", unpacked])

    apps = sorted((unpacked / "Payload").glob("*.app"))
    require(len(apps) == 1 and apps[0].name == "DmShell.app",
            "source IPA must contain exactly one Payload/DmShell.app")
    app = apps[0]
    framework = app / "Frameworks" / FRAMEWORK_NAME
    require(framework.is_dir(), f"source app is missing {FRAMEWORK_NAME}")
    manifest_path = framework / "game.manifest.json"
    require(manifest_path.is_file(), "source game framework manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(str(manifest.get("title_id", "")).upper() == TITLE_ID,
            "source framework manifest belongs to another game")
    require(manifest.get("framework") == FRAMEWORK_NAME,
            "source framework manifest names another framework")
    require(manifest.get("loader") == "FH", "source framework is not the Route C FH loader")

    msl_dir = framework / "msl"
    image = msl_dir / f"b-{CHAIN}.img"
    require(image.is_file(), f"the source framework is missing {image}")
    require(image.stat().st_size == METAL_IMAGE_SIZE, "embedded Metal image size changed")
    image_sha = sha256(image)
    require(image_sha == METAL_IMAGE_SHA256,
            f"embedded Metal image SHA-256 mismatch: {image_sha}")

    # Load the pinned format reader. This inspects the exact bytes that were
    # installed, not a separate workspace copy from the earlier build.
    sys.path.insert(0, str(engine / "dm/tools"))
    import shader_lib  # type: ignore

    library_view = shader_lib.view(str(image))
    image_names = {entry.name for entry in library_view.iterdir()}
    require("inputs.tsv" in image_names,
            "the cached image itself does not contain inputs.tsv")
    stamp = shader_lib.read_stamp(str(image))
    require(stamp.get("game") == TITLE_ID, f"Metal image game stamp mismatch: {stamp.get('game')!r}")
    require(stamp.get("inputs") == INPUTS,
            f"Metal image input stamp mismatch: {stamp.get('inputs')!r}")
    require(not shader_lib.left_out_pulling(str(image)),
            "the cached image has PULLING_LEFT_OUT; required pulling shader libraries are absent")
    require(METALLIB_PROBE in image_names,
            f"cached Metal image is missing the exact runtime-failed shader {METALLIB_PROBE}")
    require(JSON_PROBE in image_names,
            f"cached Metal image is missing the exact runtime-failed prebuild file {JSON_PROBE}")

    metallib_count = sum(name.endswith(".metallib") for name in image_names)
    json_count = sum(name.endswith(".json") for name in image_names)
    pulling_count = sum(name.endswith(shader_lib.PULLING) for name in image_names)
    require(metallib_count > 0 and json_count > 0 and pulling_count > 0,
            f"Metal image is incomplete: metallib={metallib_count}, json={json_count}, pulling={pulling_count}")
    print(
        f"Verified packed library: stamp {stamp['inputs']}, {len(image_names):,} files, "
        f"{metallib_count:,} metallib, {json_count:,} JSON, {pulling_count:,} pulling libraries.",
        flush=True,
    )

    # Route C's current iOS host reads the shader stamp and shader files by
    # directory path. Expand the already-compiled RomFS-style image verbatim;
    # no shader source is translated or compiled here.
    shader_lib.expand(str(image))
    library_dir = msl_dir / f"b-{CHAIN}"
    require(library_dir.is_dir() and not image.exists(),
            "shader image expansion did not produce the expected b-<chain> directory")
    folder_names = {path.name for path in library_dir.iterdir() if path.is_file()}
    require("inputs.tsv" in folder_names, "expanded library lost inputs.tsv")
    require(METALLIB_PROBE in folder_names, "expanded library lost the runtime-failed metallib")
    require(JSON_PROBE in folder_names, "expanded library lost the runtime-failed JSON file")
    require(not (library_dir / shader_lib.PULLING_LEFT_OUT).exists(),
            "expanded library unexpectedly contains PULLING_LEFT_OUT")

    dm_dir = framework / "dm"
    for name in ("shader_map.tsv", "c1_full.tsv", "cb_extent.tsv", "shader_pairs.tsv", "pso_pairs.tsv"):
        path = dm_dir / name
        require(path.is_file() and path.stat().st_size > 0,
                f"source framework is missing required NVN table {name}")
    for name in ("c1_full.tsv", "cb_extent.tsv"):
        first = (dm_dir / name).read_text(encoding="utf-8", errors="replace").splitlines()[0]
        expected = f"# chain b-{CHAIN} inputs {INPUTS} "
        require(first.startswith(expected), f"{name} does not match the expanded Metal image stamp")

    expanded_size = sum(path.stat().st_size for path in library_dir.iterdir() if path.is_file())
    print(
        f"Expanded {len(folder_names):,} files ({expanded_size:,} bytes) into "
        f"{library_dir}; the original .img was removed.",
        flush=True,
    )

    info_path = app / "Info.plist"
    require(info_path.is_file(), "DmShell Info.plist is missing")
    app_info = plistlib.loads(info_path.read_bytes())
    executable_name = str(app_info.get("CFBundleExecutable", "DmShell"))
    app_executable = app / executable_name
    require(app_executable.is_file(), "DmShell executable is missing")
    entitlements_path = work / "DmShell.entitlements"
    entitlements = extract_entitlements(app_executable, entitlements_path)

    embedded = sorted((app / "Frameworks").glob("*.framework"))
    require(any(item.name == FRAMEWORK_NAME for item in embedded),
            "the app's Frameworks folder lost DmGame")
    for item in embedded:
        run(["/usr/bin/xattr", "-cr", item])
        run(["/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", item])
        run(["/usr/bin/codesign", "--verify", "--strict", item])
    run(["/usr/bin/xattr", "-cr", app])
    run([
        "/usr/bin/codesign", "--force", "--sign", "-",
        "--entitlements", entitlements_path, "--timestamp=none", app,
    ])
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", app])
    require(entitlements.get("com.apple.developer.kernel.increased-memory-limit") is True,
            "Increased Memory Limit was not preserved")

    ipa = output / "KaKaRoTiOS.ipa"
    run([
        sys.executable, packer, ipa, "--no-reuse",
        f"Payload/DmShell.app={app}",
    ], cwd=engine)
    require(ipa.is_file() and ipa.stat().st_size > 0, "repacked IPA was not created")

    framework_prefix = f"Payload/DmShell.app/Frameworks/{FRAMEWORK_NAME}/"
    msl_prefix = framework_prefix + f"msl/b-{CHAIN}/"
    required_entries = [
        msl_prefix + "inputs.tsv",
        msl_prefix + METALLIB_PROBE,
        msl_prefix + JSON_PROBE,
        framework_prefix + "dm/shader_map.tsv",
        framework_prefix + "dm/c1_full.tsv",
        framework_prefix + "dm/cb_extent.tsv",
        framework_prefix + "dm/shader_pairs.tsv",
        framework_prefix + "dm/pso_pairs.tsv",
    ]
    with zipfile.ZipFile(ipa, "r") as archive:
        names = set(archive.namelist())
        missing = [name for name in required_entries if name not in names]
        require(not missing, "final IPA is missing shader runtime resources: " + ", ".join(missing))
        require(framework_prefix + f"msl/b-{CHAIN}.img" not in names,
                "final IPA still carries the single-file Metal image instead of the expanded directory")
        final_metallibs = sum(name.startswith(msl_prefix) and name.endswith(".metallib") for name in names)
        final_json = sum(name.startswith(msl_prefix) and name.endswith(".json") for name in names)
        final_pulling = sum(name.startswith(msl_prefix) and name.endswith(shader_lib.PULLING) for name in names)
        require(final_metallibs == metallib_count,
                f"final IPA metallib count changed: {final_metallibs} != {metallib_count}")
        require(final_json == json_count, f"final IPA JSON count changed: {final_json} != {json_count}")
        require(final_pulling == pulling_count,
                f"final IPA pulling library count changed: {final_pulling} != {pulling_count}")
        for name in required_entries[:3]:
            with archive.open(name) as stream:
                require(bool(stream.read(64)), f"final IPA shader entry is empty: {name}")

    framework_executable = manifest.get("framework_executable", "")
    framework_binary = framework / str(framework_executable)
    require(framework_binary.is_file(), "game framework executable is missing after repack")
    report = {
        "project": PROJECT,
        "branch": BRANCH,
        "game": source_report.get("game", "DRAGON BALL Z: KAKAROT + A NEW POWER AWAKENS SET"),
        "title_id": TITLE_ID,
        "package_version": PACKAGE_VERSION,
        "engine_pin": ENGINE_PIN,
        "framework": FRAMEWORK_NAME,
        "ipa": ipa.name,
        "ipa_size_bytes": ipa.stat().st_size,
        "source": {
            "run_id": SOURCE_RUN_ID,
            "artifact_id": SOURCE_ARTIFACT_ID,
            "ipa_sha256": sha256(source_ipa),
            "framework_executable_sha256_before_repack": source_report.get("framework_executable_sha256"),
        },
        "shader_reuse": {
            "compiled_shader_source_run_id": METAL_SOURCE_RUN_ID,
            "shader_package_key": PACKAGE_KEY,
            "chain": CHAIN,
            "inputs": INPUTS,
            "source_image_sha256": image_sha,
            "source_image_size": METAL_IMAGE_SIZE,
            "expanded_to_directory": True,
            "expanded_file_count": len(folder_names),
            "metallib_count": metallib_count,
            "json_count": json_count,
            "pulling_metallib_count": pulling_count,
            "sample_runtime_metallib_verified": METALLIB_PROBE,
            "sample_prebuild_json_verified": JSON_PROBE,
            "shader_split_executed": False,
            "shader_translation_executed": False,
            "metal_compilation_executed": False,
            "game_modules_recompiled": False,
            "romfs_rebuilt": False,
            "aoc_rebuilt": False,
        },
        "unreal_memory_fix": source_report.get("unreal_memory_fix"),
        "signature": "ad-hoc; Increased Memory Limit preserved",
        "runtime_layout": "msl/b-0c434f1b68df/ (expanded shader files; no b-0c434f1b68df.img)",
        "validation": {
            "source_image_sha256_verified": True,
            "image_stamp_verified": True,
            "runtime_failed_metallib_present": True,
            "runtime_failed_prebuild_json_present": True,
            "c1_full_and_cb_extent_stamps_match": True,
            "final_ipa_shader_entries_verified": True,
            "final_ipa_pulling_libraries_preserved": True,
        },
    }
    report_path = output / "build-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    print(f"REPAIRED_IPA_READY {ipa} ({ipa.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
