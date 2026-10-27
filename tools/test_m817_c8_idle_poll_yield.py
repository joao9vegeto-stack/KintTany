#!/usr/bin/env python3
"""Verify M8.17 C8 0x00AD0 idle poll yield is installed in spu_channels.c and spurs_policy.c."""
from pathlib import Path
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--upstream", type=Path, required=True)
args = ap.parse_args()

chan = (args.upstream / "runtime/spu/spu_channels.c").read_text(errors="replace")
pol = (args.upstream / "runtime/spu/spurs_policy.c").read_text(errors="replace")

for token in (
    "ASCENSION_M817_C8_IDLE_POLL_YIELD_V1",
    "s_asc_c8_spin_restores >= 8u",
    "g_spurs_pm_exited = 1;",
    "g_spu_trampoline_fn = NULL;",
    "if (c8_rc == 2)",
):
    if token not in chan:
        raise SystemExit(f"missing {token} in {args.upstream}/runtime/spu/spu_channels.c")

if "ASCENSION_M817_C8_IDLE_POLL_YIELD_V1" not in pol:
    raise SystemExit(f"missing M8.17 marker in {args.upstream}/runtime/spu/spurs_policy.c")

print(f"M8.17 verification passed for {args.upstream}")
