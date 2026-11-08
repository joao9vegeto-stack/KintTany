#!/usr/bin/env python3
"""Finish a Colab-prepared NXNative build on macOS and export the Shared NX2Apple IPA."""
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

    stage_ipa = out / "framework-stage.ipa"
    builder = engine / "scripts" / "build_ipa_from_nsp.py"
    run([sys.executable, str(builder), str(nup), "--framework", "--romfs", "separate",
         "--work-dir", str(work), "--keep-extracted", "--progress", "lines",
         "--gpu", "g18p", "--out", str(stage_ipa)], cwd=nx, env=os.environ.copy())
    if not stage_ipa.is_file():
        raise SystemExit("NXNative completed without producing the framework-stage IPA.")

    framework_name = f"DmGame{title_id}.framework"
    extracted = out / "framework-extracted"
    shutil.rmtree(extracted, ignore_errors=True)
    extracted.mkdir(parents=True)
    prefix = f"Payload/DmIOS.app/Frameworks/{framework_name}/"
    with zipfile.ZipFile(stage_ipa) as zf:
        names = [n for n in zf.namelist() if n.startswith(prefix)]
        if not names:
            raise SystemExit(f"Framework {framework_name} is missing from the stage IPA.")
        for name in names:
            rel = name[len(prefix):]
            if rel:
                target = extracted / framework_name / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    framework = extracted / framework_name
    manifest_path = framework / "game.manifest.json"
    executable = framework / framework_name.removesuffix(".framework")
    if not manifest_path.is_file() or not executable.is_file():
        raise SystemExit("Extracted game framework is incomplete (manifest or executable missing).")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("title_id", "").upper() != title_id:
        raise SystemExit("Framework title ID does not match the Colab handoff.")
    package_version = manifest.get("package_version", "")
    romfs = work / "extract" / package_version / "RomFS.img"
    if not romfs.is_file():
        raise SystemExit(f"Separate RomFS image not found: {romfs}")

    # Shared-shell game data is deliberately outside the IPA.
    data_root = out / "game-data" / "games" / title_id
    shutil.rmtree(data_root, ignore_errors=True)
    data_root.mkdir(parents=True)
    shutil.copy2(romfs, data_root / "romfs.img")
    aoc_src = work / "data" / "aoc"
    if aoc_src.is_dir() and any(aoc_src.iterdir()):
        shutil.copytree(aoc_src, data_root / "aoc", dirs_exist_ok=True)
    data_archive = out / "game-data.tar.zst"
    run(["tar", "--zstd", "-1", "-cf", str(data_archive), "-C", str(out / "game-data"), "games"])

    shell_root = out / "shell-library"
    shutil.rmtree(shell_root, ignore_errors=True)
    template = shell_root / "template" / "DmShell.app"
    run([sys.executable, str(nx / "tools" / "build_shell_template.py"),
         "--engine", str(engine), "--out", str(template)], cwd=nx)
    sys.path.insert(0, str(nx / "frontend-qt"))
    from nspb_qt.win.shell_export import export_shell
    ok, ipa_path, message, notes = export_shell(
        root=shell_root, repo=engine, framework=framework, title_id=title_id,
        name=str(manifest.get("name") or title_id), python_exe=sys.executable,
        log=lambda line: print(line, end="" if line.endswith("\n") else "\n", flush=True))
    if not ok:
        raise SystemExit(f"Shared shell export failed: {message}")
    final_ipa = out / "NX2Apple.ipa"
    shutil.copy2(ipa_path, final_ipa)
    with zipfile.ZipFile(final_ipa) as zf:
        entries = set(zf.namelist())
        fw_exe = f"Payload/DmShell.app/Frameworks/{framework_name}/{framework_name.removesuffix('.framework')}"
        required = ("Payload/DmShell.app/DmShell", fw_exe,
                    f"Payload/DmShell.app/Frameworks/{framework_name}/game.manifest.json")
        missing = [p for p in required if p not in entries]
        if missing:
            raise SystemExit("Final Shared IPA failed structural validation: " + ", ".join(missing))
    report = {
        "title_id": title_id, "name": manifest.get("name"),
        "display_version": manifest.get("display_version"), "package_version": package_version,
        "engine_pin": prep["engine_pin"], "nx2apple_tag": prep["nx2apple_tag"],
        "ipa": str(final_ipa), "ipa_size": final_ipa.stat().st_size,
        "game_data": str(data_archive), "game_data_size": data_archive.stat().st_size,
        "notes": notes,
    }
    (out / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
