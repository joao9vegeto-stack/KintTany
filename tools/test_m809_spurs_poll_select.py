#!/usr/bin/env python3
"""Compile/test the production SPURS selector, including ready workloads 16-31."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    source = (args.upstream / "libs/spurs/cellSpurs.c").read_text()
    match = re.search(r"\bu32 spurs_poll_select\(u32 ea, u32 current, u32 spu\)\n\{.*?\n\}", source, re.S)
    assert match, "patched runtime must include production SPURS selector"
    actual = match.group(0)
    assert "ready && ready >= si->active[wid]" in actual, "idle workload must not remain current"
    cc = shutil.which("clang") or shutil.which("cc")
    assert cc, "host compiler missing"
    fixture = r'''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
struct SpursInst { u32 active[32]; u32 nspus; };
static struct SpursInst instance;
static struct { int in_use; u32 spurs_ea; } s_workloads[32];
static uint8_t guest[8192];
static u32 enabled;
static int signals[32];
#define CELL_SPURS_MAX_SPU 6
#define SPURS_WKL_ENABLED 0x04u
static struct SpursInst* spurs_inst_find(u32 ea) { return ea == 0x100 ? &instance : 0; }
static u32 spurs_workload_limit(struct SpursInst* si) { (void)si; return 32; }
static u32 vm_read32(u32 ea) { assert(ea == 0x104); return enabled; }
static uint8_t vm_read8(u32 ea) { assert(ea < sizeof guest); return guest[ea]; }
static u32 wkl_state_off(u32 wid) { return 0x100u + wid; }
static u32 wkl_ready_off(u32 wid) { return 0x200u + wid; }
static u32 wkl_info_off(u32 wid) { return 0x400u + wid * 32u; }
static int wkl_signalled(u32 ea, u32 wid) { assert(ea == 0x100 && wid < 32); return signals[wid]; }
static void reset(void) {
    memset(&instance, 0, sizeof instance);
    memset(s_workloads, 0, sizeof s_workloads);
    memset(guest, 0, sizeof guest);
    memset(signals, 0, sizeof signals);
    enabled = 0;
    instance.nspus = 6;
}
static void workload(u32 id, u32 ready, u32 active) {
    enabled |= 0x80000000u >> id;
    s_workloads[id].in_use = 1;
    s_workloads[id].spurs_ea = 0x100;
    guest[0x100 + wkl_state_off(id)] = 2;
    guest[0x100 + wkl_ready_off(id)] = (uint8_t)ready;
    guest[0x100 + wkl_info_off(id) + 0x18] = 1;
    instance.active[id] = active;
}
/* PRODUCTION */
int main(void) {
    reset(); workload(0, 0, 0); workload(17, 1, 0);
    assert(spurs_poll_select(0x100, 0, 0) == 17);
    reset(); workload(0, 0, 0); workload(17, 0, 0);
    assert(spurs_poll_select(0x100, 0, 0) == 0x20u);
    reset(); workload(0, 1, 1); workload(17, 1, 0);
    assert(spurs_poll_select(0x100, 0, 0) == 0);
    reset(); workload(0, 0, 0); workload(17, 1, 0); signals[0] = 1;
    assert(spurs_poll_select(0x100, 0, 0) == 0);
    reset(); workload(0, 0, 0); workload(17, 1, 0);
    assert(spurs_poll_select(0x100, 0, CELL_SPURS_MAX_SPU) == 0x20u);
    puts("[PASS] M8.09 production SPURS selector retires idle current and admits ready WID 17");
    return 0;
}
'''
    fixture = fixture.replace("/* PRODUCTION */", actual)
    with tempfile.TemporaryDirectory(prefix="m809-spurs-select-") as temp:
        src = Path(temp) / "selector.c"
        exe = Path(temp) / "selector"
        src.write_text(fixture)
        subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)

if __name__ == "__main__":
    main()
