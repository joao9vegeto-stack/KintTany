#!/usr/bin/env python3
"""Regression test for M8.18 render unblock."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    upstream = parser.parse_args().upstream
    m817 = (ROOT / "tools/m817_c8_idle_poll_yield.py").read_text(errors="replace")
    assert "g_spu_trampoline_fn = NULL;" in m817
    assert "ctx->pc = 0;" in m817
    assert "!ctx->policy_mode" in m817
    subprocess.check_call([sys.executable, str(ROOT / "tools/test_m817_c8_idle_poll_yield.py"), "--upstream", str(upstream)])
    print("[PASS] M8.18 C8 policy+taskset spin yield and LFQueue/WID16 unblock verified")

if __name__ == "__main__":
    main()