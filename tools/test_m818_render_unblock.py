#!/usr/bin/env python3
"""Verify M8.18 render unblock and crash logger are installed in upstream tree."""
from pathlib import Path
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--upstream", type=Path, required=True)
args = ap.parse_args()

chan = (args.upstream / "runtime/spu/spu_channels.c").read_text(errors="replace")
wkl = (args.upstream / "runtime/spu/spu_workload.c").read_text(errors="replace")
pol = (args.upstream / "runtime/spu/spurs_policy.c").read_text(errors="replace")
spurs = (args.upstream / "libs/spurs/cellSpurs.c").read_text(errors="replace")

for name, content in [("spu_channels.c", chan), ("spu_workload.c", wkl), ("spurs_policy.c", pol), ("cellSpurs.c", spurs)]:
    if "ASCENSION_M818_RENDER_UNBLOCK_V1" not in content:
        raise SystemExit(f"missing ASCENSION_M818_RENDER_UNBLOCK_V1 in {args.upstream}/{name}")

if "asc_signal_handler" not in chan:
    raise SystemExit(f"missing asc_signal_handler in {args.upstream}/runtime/spu/spu_channels.c")

if "g_spurs_pm_exited = 1;" not in chan:
    raise SystemExit(f"missing g_spurs_pm_exited = 1; in {args.upstream}/runtime/spu/spu_channels.c")

print(f"[PASS] M8.18 verification passed for {args.upstream}")
