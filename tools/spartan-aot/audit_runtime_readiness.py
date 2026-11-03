#!/usr/bin/env python3
"""Produce a fail-honest readiness audit for the complete PS4-to-iOS AOT port.

Static candidates and a compiled ARM64 archive are not a complete game port.
This report keeps translation gaps, module/import coverage and app-runtime
integration as separate, independently verifiable acceptance conditions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CPU_RUNTIME_MARKERS = (
    "bbcpu_run",
    "bbcpu_recomp_load",
    "bbcpu_call_on_stack",
    "SpartanIOSPS4CPU",
    "spartan_ps4_cpu_dispatch",
    "spartan_cpu_dispatch",
)
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".m", ".mm", ".S"}


def read_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid {label}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return value


def has_cpu_runtime(runtime_dir: Path) -> bool:
    """Require an actual CPU/dispatcher implementation, not any C source file."""
    if not runtime_dir.is_dir():
        return False
    for path in runtime_dir.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        if any(marker in source for marker in CPU_RUNTIME_MARKERS):
            return True
    return False


def has_app_aot_link(app_root: Path) -> bool:
    """Require target linkage plus a runtime load/call site inside the app."""
    if not app_root.is_dir():
        return False
    files = [
        p for p in app_root.rglob("*")
        if p.is_file() and p.suffix in {".yml", ".yaml", ".pbxproj", ".swift", ".m", ".mm", ".c"}
    ]
    contents = {p: p.read_text(errors="ignore") for p in files}
    configs = [p for p in files if p.name in {"project.yml", "project.yaml"} or p.suffix == ".pbxproj"]
    archive_declared = any(
        "libgow3-recompiled-ios" in contents[p] or "libgow3-aot-cpu-ios" in contents[p]
        for p in configs
    )
    runtime_load_present = any(
        any(token in source for token in ("dlopen(", "bbcpu_recomp_load(", "bbcpu_run("))
        for p, source in contents.items()
        if p.suffix in {".swift", ".m", ".mm", ".c"}
    )
    return archive_declared and runtime_load_present


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()

    aot = args.prepared / "aot"
    coverage = read_json(aot / "coverage-summary.json", "coverage summary")
    linked = read_json(args.prepared / "link.json", "module link report")
    build = read_json(args.compiled / "aot-build-manifest.json", "AOT build manifest")
    sites_path = aot / "coverage-sites.local.json"
    sites = read_json(sites_path, "local coverage-site inventory")
    unresolved = linked.get("unresolved_imports", [])
    modules = linked.get("modules", [])
    gap_count = coverage.get("distinct_gap_sites")
    if not isinstance(gap_count, int) or gap_count < 0:
        raise SystemExit("coverage summary has no valid distinct_gap_sites")
    if not isinstance(unresolved, list) or not isinstance(modules, list):
        raise SystemExit("link report has invalid module/import inventory")

    reported_gap_sites = sum(len(v) for v in sites.values() if isinstance(v, list))
    if reported_gap_sites != gap_count:
        raise SystemExit(
            f"coverage inventory mismatch: summary={gap_count}, local_sites={reported_gap_sites}"
        )

    runtime_dir = args.project / "SpartanPort-iOS/Sources/Runtime"
    app_has_cpu_runtime = has_cpu_runtime(runtime_dir)
    app_has_aot_link = has_app_aot_link(args.project / "SpartanPort-iOS")
    app_has_gpu_runtime = any(
        p.is_file() and p.suffix in {".swift", ".m", ".mm", ".metal", ".c", ".cpp"}
        and any(token in p.read_text(errors="ignore")
                for token in ("PS4 GNM", "shadPS4", "sceGnm", "GnmCommand"))
        for root in (args.project / "SpartanPort-iOS",)
        if root.exists() for p in root.rglob("*")
    )

    blockers = []
    if gap_count:
        blockers.append(f"{gap_count} static AOT gap sites remain; static scan does not prove reachability")
    if unresolved:
        blockers.append(f"{len(unresolved)} PS4 imports remain unresolved by the linked game modules")
    if len(modules) < 1:
        blockers.append("no bundled PS4 PRX modules were linked")
    if not app_has_cpu_runtime:
        blockers.append("PS4 CPU/dispatcher runtime is not integrated into the iOS app")
    if not app_has_aot_link:
        blockers.append("generated ARM64 archive is not linked into the iOS app target")
    if not app_has_gpu_runtime:
        blockers.append("PS4 GNM command processor/renderer is not integrated")
    if build.get("architecture") != "arm64":
        blockers.append("generated archive is not arm64")
    if build.get("compiled_jit") or build.get("compiled_interpreter") or build.get("compiled_fallback"):
        blockers.append("generated archive violates the no-JIT/no-interpreter/no-fallback policy")

    report = {
        "status": "INCOMPLETE" if blockers else "READY_FOR_DEVICE_VALIDATION",
        "complete_recompilation": not blockers,
        "game_start_ready": not blockers,
        "aot": {
            "architecture": build.get("architecture"),
            "generated_c_files": build.get("generated_c_files"),
            "function_candidates": coverage.get("function_candidates"),
            "decoded_instruction_instances": coverage.get("decoded_instruction_instances"),
            "static_gap_sites": gap_count,
            "gap_families": coverage.get("families", []),
            "local_gap_site_inventory": str(sites_path),
        },
        "ps4_modules": {
            "linked_count": len(modules),
            "names": [m.get("file") for m in modules],
            "unresolved_import_count": len(unresolved),
            "unresolved_imports": unresolved,
        },
        "ios_runtime": {
            "cpu_runtime_integrated": app_has_cpu_runtime,
            "aot_archive_linked": app_has_aot_link,
            "ps4_gpu_renderer_integrated": app_has_gpu_runtime,
        },
        "blockers": blockers,
        "policy": "Never infer game completion from generated C or archive compilation. No interpreter, JIT, emulation or fake launcher.",
    }
    out = args.compiled / "runtime-readiness.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
