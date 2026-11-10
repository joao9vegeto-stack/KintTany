#!/usr/bin/env python3
"""Adjust the runtime memory profile in an existing IPA without rebuilding the host or game shaders."""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


MEMORY_ENTITLEMENT = "com.apple.developer.kernel.increased-memory-limit"


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    print("+", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True)


def read_entitlements(executable: Path, output: Path) -> None:
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(executable)],
        capture_output=True,
        text=True,
        check=False,
    )
    text = result.stdout + "\n" + result.stderr
    start = text.find("<?xml")
    end = text.find("</plist>", start)
    if result.returncode != 0 or start < 0 or end < 0:
        raise SystemExit("Could not read the existing app entitlements before re-signing.")
    xml = text[start:end + len("</plist>")] + "\n"
    entitlements = plistlib.loads(xml.encode("utf-8"))
    if entitlements.get(MEMORY_ENTITLEMENT) is not True:
        raise SystemExit("The original IPA does not carry the Increased Memory Limit entitlement.")
    output.write_text(xml, encoding="utf-8")


# Bananza iOS 26: keep the 5 GiB guest reservation, but rebalance 96 MiB
# from the 256 MiB stack + 64 MiB alias reservations into the app heap.
# The crash disassembly proves VoxelSceneHeap requests 0xb0e00000 (2,830 MiB)
# and the parent allocator returns NULL. Keep 192 MiB stack and 32 MiB alias;
# increase app_pool from 4,544 MiB to 4,640 MiB without changing mem_reserve.
MEMORY_PROFILE = {
    "mem_reserve": ("0x270000000", "0x140000000"),
    "mem_alias": ("0x10000000", "0x02000000"),
    "mem_stack": ("0x10000000", "0x0c000000"),
    "app_pool": ("0x240000000", "0x121000000"),
}


def patch_runtime_profile(framework: Path, manifest: dict) -> tuple[str, dict]:
    """Patch the external runtime profile read by the shell through DM_PROFILE."""
    rel = str(manifest.get("profile") or "profile.tsv")
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise SystemExit(f"Unsafe runtime profile path in manifest: {rel}")
    profile = framework / rel_path
    if not profile.is_file():
        raise SystemExit(f"Framework runtime profile is missing: {profile}")
    content = profile.read_text(encoding="utf-8")
    changes = {}
    for key, (before, after) in MEMORY_PROFILE.items():
        pattern = re.compile(rf"(?m)^{re.escape(key)}([\t ]+){re.escape(before)}([\t ]*)$")
        updated, count = pattern.subn(lambda m: f"{key}{m.group(1)}{after}{m.group(2)}", content)
        if count != 1:
            raise SystemExit(
                f"Expected exactly one {key}={before} in {profile}; found {count}. "
                "Refusing an ambiguous memory-profile patch."
            )
        content = updated
        changes[key] = {"before": before, "after": after}
    profile.write_text(content, encoding="utf-8")
    saved = profile.read_text(encoding="utf-8")
    for key, (_, after) in MEMORY_PROFILE.items():
        if len(re.findall(rf"(?m)^{re.escape(key)}[\t ]+{re.escape(after)}[\t ]*$", saved)) != 1:
            raise SystemExit(f"Runtime profile verification failed for {key}={after}.")
    return rel, changes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--engine-root", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--source-run-id", type=int, required=True)
    args = ap.parse_args()

    ipa = args.ipa.resolve()
    report_path = args.report.resolve()
    engine = args.engine_root.resolve()
    out = args.output_dir.resolve()
    if sys.platform != "darwin":
        raise SystemExit("IPA re-signing must run on macOS.")
    if not ipa.is_file() or not report_path.is_file():
        raise SystemExit("The original IPA or build report is missing.")
    packer = engine / "dm" / "ios" / "tools" / "pack_ipa.py"
    if not packer.is_file():
        raise SystemExit(f"NXNative IPA packer is missing: {packer}")

    with zipfile.ZipFile(ipa) as zf:
        names = set(zf.namelist())
        pso_entries = sorted(
            n for n in names
            if "/Frameworks/" in n and "/pso/" in n and n.lower().endswith(".mtl4a")
        )
        if not pso_entries:
            raise SystemExit("The source IPA contains no Metal 4 PSO archive to remove.")
        framework_roots = sorted({
            n.split("/pso/", 1)[0]
            for n in pso_entries
        })
        if len(framework_roots) != 1:
            raise SystemExit(f"Expected one game framework, found: {framework_roots}")
        framework_root = framework_roots[0]
        app_root = "Payload/DmShell.app"
        if not framework_root.startswith(app_root + "/Frameworks/"):
            raise SystemExit(f"Unexpected framework location: {framework_root}")
        manifest_name = framework_root + "/game.manifest.json"
        if manifest_name not in names:
            raise SystemExit("The original IPA is missing the game framework manifest.")
        manifest = json.loads(zf.read(manifest_name))
        executable_name = str(manifest.get("framework_executable", ""))
        required = [
            app_root + "/DmShell",
            manifest_name,
            framework_root + "/" + executable_name,
        ]
        missing = [n for n in required if n not in names]
        if missing:
            raise SystemExit("The original IPA is structurally incomplete: " + ", ".join(missing))
        shader_prefix = framework_root + "/msl/"
        shader_entries_before = {
            n: (zf.getinfo(n).file_size, zf.getinfo(n).CRC)
            for n in names if n.startswith(shader_prefix) and not n.endswith("/")
        }
        if not shader_entries_before:
            raise SystemExit("The original IPA has no bundled Metal shader libraries to preserve.")

    out.mkdir(parents=True, exist_ok=True)
    work = out / "repack-work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    run(["ditto", "-x", "-k", str(ipa), str(work)])
    app = work / "Payload" / "DmShell.app"
    framework = app / "Frameworks" / framework_root.split("/Frameworks/", 1)[1]
    if not app.is_dir() or not framework.is_dir():
        raise SystemExit("Could not locate DmShell.app or the Bananza framework after extraction.")

    executable = app / "DmShell"
    entitlements_file = work / "DmShell.entitlements"
    read_entitlements(executable, entitlements_file)

    profile_rel, memory_changes = patch_runtime_profile(framework, manifest)

    pso_dir = framework / "pso"
    if not pso_dir.is_dir():
        raise SystemExit("The expected PSO folder disappeared during IPA extraction.")
    removed = sorted(str(p.relative_to(app)) for p in pso_dir.rglob("*") if p.is_file())
    if not removed:
        raise SystemExit("The PSO folder is empty; refusing an unverified repack.")
    shutil.rmtree(pso_dir)

    # Re-seal the modified nested framework, then the app, preserving its memory entitlement.
    run(["xattr", "-cr", str(framework)])
    run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(framework)])
    run(["codesign", "--verify", "--strict", str(framework)])
    run(["xattr", "-cr", str(app)])
    run([
        "codesign", "--force", "--sign", "-", "--entitlements", str(entitlements_file),
        "--timestamp=none", str(app),
    ])
    run(["codesign", "--verify", "--deep", "--strict", str(app)])
    signed = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(executable)],
        capture_output=True, text=True, check=False,
    )
    if MEMORY_ENTITLEMENT not in (signed.stdout + signed.stderr):
        raise SystemExit("Re-signed app lost the Increased Memory Limit entitlement.")

    output_ipa = out / "NX2Apple-iOS26.ipa"
    run([
        sys.executable, str(packer), str(output_ipa), "--no-reuse",
        f"Payload/DmShell.app={app}",
    ], cwd=engine)

    with zipfile.ZipFile(output_ipa) as zf:
        final_names = set(zf.namelist())
        remaining = sorted(
            n for n in final_names
            if "/Frameworks/" in n and "/pso/" in n and n.lower().endswith(".mtl4a")
        )
        if remaining:
            raise SystemExit("The repacked IPA still contains Metal 4 archives: " + ", ".join(remaining))
        final_shader_entries = {
            n: (zf.getinfo(n).file_size, zf.getinfo(n).CRC)
            for n in final_names if n.startswith(shader_prefix) and not n.endswith("/")
        }
        if final_shader_entries != shader_entries_before:
            raise SystemExit("Metal shader library entries changed during repack; refusing to publish.")
        profile_entry = framework_root + "/" + profile_rel.replace("\\", "/")
        if profile_entry not in final_names:
            raise SystemExit("Repacked IPA is missing the runtime memory profile.")
        with zf.open(profile_entry) as f:
            final_profile = f.read().decode("utf-8")
        for key, (_, after) in MEMORY_PROFILE.items():
            if len(re.findall(rf"(?m)^{re.escape(key)}[\t ]+{re.escape(after)}[\t ]*$", final_profile)) != 1:
                raise SystemExit(f"Final IPA runtime profile has the wrong {key} value.")
        final_missing = [n for n in required if n not in final_names]
        if final_missing:
            raise SystemExit("Repacked IPA is missing required files: " + ", ".join(final_missing))

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["ipa"] = str(output_ipa)
    report["ipa_size"] = output_ipa.stat().st_size
    report["pipeline_archive"] = {
        "included": False,
        "gpu": "none",
        "reason": "Removed because the iOS 27 Metal 4 archive is not loadable on iOS 26; the device builds its pipeline bases at first use.",
        "removed_files": removed,
    }
    report["shader_libraries"] = {
        "recompiled": False,
        "retained_from_original_ipa": True,
        "verified_entries_unchanged": len(shader_entries_before),
    }
    report["memory_profile"] = {
        "source": profile_rel,
        "loaded_by": "DM_PROFILE (NX2Apple Route C EngineLaunchPlan)",
        "mode": "ios26_5gb_rebalanced_4437m_heap_64m_alias_256m_stack_test",
        "changes": memory_changes,
        "shader_rebuild": False,
        "framework_rebuild": False,
    }
    report["repackaged_from_run_id"] = args.source_run_id
    report["repackaged_at_utc"] = datetime.now(timezone.utc).isoformat()
    (out / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
