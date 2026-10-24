#!/usr/bin/env python3
"""Structural native production regression for SPURS2 32-WID contexts."""
import argparse
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument("--upstream",type=Path,required=True)
r=a.parse_args().upstream
p=(r/"runtime/spu/spurs_policy.c").read_text()
c=(r/"runtime/spu/spu_channels.c").read_text()
for f in ("#define SPURS_PM_MAX_WKL 32","workload_users[SPURS_PM_MAX_WKL]","slots[SPURS_PM_MAX_WKL][6]",
          "spu_ascension_copy_upper_policy","for (unsigned w = 0; w < SPURS_PM_MAX_WKL; w++)"):
    assert f in p,f
for f in ("spu_ascension_copy_native_gap","ASCENSION_SPU_NATIVE_ONLY",
          "asc_native_gap_note(ctx);"):
    assert f in c,f
for f in ("SPURS_PM_MAX_WKL = 16","slots[16][6]","workload_users[16]"):
    assert f not in p,f
print("[PASS] policy high-WID native execution and AOT gap boundary")
