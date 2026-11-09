#!/usr/bin/env python3
"""Finish the Switch game framework and build the Route C Shared shell on macOS."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, zipfile
from pathlib import Path

def run(cmd, cwd=None, env=None):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nx2apple-root", type=Path, required=True)
    ap.add_argument("--engine-root", type=Path, required=True)
    ap.add_argument("--nup", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--game-data-folder-id", required=True,
                    help="Google Drive folder ID containing the already-extracted game data.")
    ap.add_argument("--game-data-size", type=int, required=True)
    ap.add_argument("--game-data-sha256", required=True)
    args = ap.parse_args()
    if sys.platform != "darwin":
        raise SystemExit("The Shared App finalizer must run on macOS.")
    nx, engine, nup, work, out = (args.nx2apple_root.resolve(), args.engine_root.resolve(),
                                  args.nup.resolve(), args.work_dir.resolve(), args.output.resolve())
    out.mkdir(parents=True, exist_ok=True)
    prep_path = work / "kleo-linux-prep.json"
    if not prep_path.is_file():
        raise SystemExit(f"Missing Colab preparation manifest: {prep_path}")
    prep = json.loads(prep_path.read_text())
    if prep.get("engine_pin") != (nx / ".upstream-ref").read_text().strip():
        raise SystemExit("Colab and Actions engine pins differ; refusing a mixed-engine build.")
    if prep.get("nx2apple_tag") != "v1.3.0-rc10":
        raise SystemExit("Unsupported NX2Apple builder version in the handoff.")
    title_id = str(prep.get("title_id", "")).upper()
    if len(title_id) != 16:
        raise SystemExit("Handoff manifest has no valid title ID.")

    framework_root = out / "frameworks"
    shutil.rmtree(framework_root, ignore_errors=True)
    framework_root.mkdir(parents=True)
    builder = engine / "scripts" / "build_ipa_from_nsp.py"
    # No offline Metal 4 archive: iOS 26 must build its pipeline bases on device.
    # Keep pulling shader libraries because the device may use them for Metal 4 prebuild/hybrid pipelines.
    builder_env = os.environ.copy()
    builder_env["IOS_PULL"] = "1"
    run([sys.executable, str(builder), str(nup), "--shell-framework", str(framework_root),
         "--work-dir", str(work), "--keep-extracted", "--progress", "lines",
         "--gpu", "none"], cwd=nx, env=builder_env)

    framework_name = f"DmGame{title_id}.framework"
    framework = framework_root / framework_name
    # iOS 26 cannot open the Metal 4 pipeline archive produced by the iOS 27 SDK.
    # Keep the regular Metal shader libraries, but require the offline PSO archive to be absent.
    pso_dir = framework / "pso"
    incompatible_pso = sorted(pso_dir.rglob("*.mtl4a")) if pso_dir.is_dir() else []
    if incompatible_pso:
        raise SystemExit("iOS 26-compatible build must not contain Metal 4 PSO archives: " +
                         ", ".join(str(p.relative_to(framework)) for p in incompatible_pso))
    manifest_path = framework / "game.manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"NXNative did not produce {framework_name}/game.manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("title_id", "").upper() != title_id or manifest.get("framework") != framework_name:
        raise SystemExit("Framework manifest title/name does not match the NUP handoff.")
    executable = framework / str(manifest.get("framework_executable", ""))
    if not executable.is_file():
        raise SystemExit(f"Framework executable is missing: {executable}")
    package_version = str(manifest.get("package_version", ""))
    romfs = work / "extract" / package_version / "RomFS.img"
    if not romfs.is_file():
        raise SystemExit(f"Separate RomFS image not found: {romfs}")

    # RomFS is already stored in the verified Google Drive work-only handoff archive.
    # Do not duplicate this multi-GB image on the runner or create a second ZIP copy.

    shell_dir = out / "shell-project"
    shutil.rmtree(shell_dir, ignore_errors=True)
    shell_dir.mkdir(parents=True)
    shell_script = engine / "dm" / "ios" / "tools" / "build_shell.sh"
    env = os.environ.copy()
    env.update({
        "SHELL_DIR": str(shell_dir),
        "DM_SHELL_FRAMEWORKS": str(framework),
        "DM_SHELL_PACKAGE": str(nx / "frontend-ios"),
        "DM_SHELL_NAME": "NX2Apple",
        "DM_BUNDLE_ID": "org.nxnative.shell",
        "DM_APP_VERSION": "1.0",
        "DM_TEAM_ID": "0000000000",
        "FONT_PY": sys.executable,
        "STD_FONT": "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    })
    run(["bash", str(shell_script), "--build"], cwd=engine, env=env)
    app = shell_dir / "dd" / "Build" / "Products" / "Release-iphoneos" / "DmShell.app"
    if not (app / "DmShell").is_file():
        raise SystemExit(f"Shared shell app was not built: {app}")
    entitlements = shell_dir / "Gen" / "DmShell.entitlements"
    if not entitlements.is_file():
        raise SystemExit("build_shell.sh did not generate DmShell.entitlements")

    for fw in sorted((app / "Frameworks").glob("*.framework")):
        run(["xattr", "-cr", str(fw)])
        run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(fw)])
        run(["codesign", "--verify", "--strict", str(fw)])
    run(["xattr", "-cr", str(app)])
    run(["codesign", "--force", "--sign", "-", "--entitlements", str(entitlements),
         "--timestamp=none", str(app)])
    run(["codesign", "--verify", "--deep", "--strict", str(app)])
    ent_dump = subprocess.run(["codesign", "-d", "--entitlements", ":-", str(app / "DmShell")],
                              capture_output=True, text=True, check=False)
    if "com.apple.developer.kernel.increased-memory-limit" not in (ent_dump.stdout + ent_dump.stderr):
        raise SystemExit("Ad-hoc shell signature is missing the Increased Memory Limit entitlement.")

    final_ipa = out / "NX2Apple.ipa"
    packer = engine / "dm" / "ios" / "tools" / "pack_ipa.py"
    run([sys.executable, str(packer), str(final_ipa), "--no-reuse", f"Payload/DmShell.app={app}"], cwd=engine)
    with zipfile.ZipFile(final_ipa) as zf:
        entries = set(zf.namelist())
        fw_exe = f"Payload/DmShell.app/Frameworks/{framework_name}/{manifest['framework_executable']}"
        required = ("Payload/DmShell.app/DmShell", fw_exe,
                    f"Payload/DmShell.app/Frameworks/{framework_name}/game.manifest.json")
        missing = [p for p in required if p not in entries]
        pso_entries = sorted(p for p in entries
                             if f"/{framework_name}/pso/" in p and p.endswith(".mtl4a"))
        if pso_entries:
            raise SystemExit("Final IPA contains unsupported Metal 4 PSO archives: " + ", ".join(pso_entries))
        if missing:
            raise SystemExit("Final Shared IPA failed structural validation: " + ", ".join(missing))

    report = {
        "title_id": title_id, "name": manifest.get("name"),
        "display_version": manifest.get("display_version"), "package_version": package_version,
        "engine_pin": prep["engine_pin"], "nx2apple_tag": prep["nx2apple_tag"],
        "ipa": str(final_ipa), "ipa_size": final_ipa.stat().st_size,
        "game_data": {
            "storage": "Google Drive",
            "folder_id": args.game_data_folder_id,
            "drive_url": f"https://drive.google.com/drive/folders/{args.game_data_folder_id}",
            "format": "extracted Drive folder",
            "size": args.game_data_size,
            "sha256": args.game_data_sha256,
            "romfs_size": romfs.stat().st_size,
            "contents": [f"games/{title_id}/romfs.img", f"games/{title_id}/aoc/"],
        },
        "framework": framework_name,
        "pipeline_archive": {
            "included": False,
            "gpu": "none",
            "reason": "Disabled for iOS 26; pipeline bases are prepared by the device at first use.",
        },
    }
    (out / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
