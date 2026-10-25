#!/usr/bin/env python3
"""Compile production taskset scheduler and atomic-line callback on the CI host."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
from m808_taskset_commit_kick import body_span

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--upstream", type=Path, required=True)
    upstream = p.parse_args().upstream
    work = (upstream / "runtime/spu/spu_workload.c").read_text()
    channels = (upstream / "runtime/spu/spu_channels.c").read_text()
    assert "ASCENSION_M808_TASKSET_COMMIT_KICK_V2" in work
    assert "spu_taskset_bits_committed(line);" in work
    assert channels.count("spu_taskset_line_committed(ea & ~127u);") >= 2
    assert "ts_start_ready(taskset_ea, done_task);" in work
    def extract(sig: str) -> str:
        a,b=body_span(work,sig)
        return work[a:b]
    ready=extract("static void ts_start_ready(uint32_t taskset_ea, uint32_t done_task)")
    callback=extract("void spu_taskset_bits_committed(uint32_t line)")
    for term in ("spu_workload_dispatch_async(vm_base + elf",
                 "ts_bits_clear(taskset_ea + 0x20 + t / 8, m)",
                 "asc_taskset_add(5, 1)"):
        assert term in ready, term
    fixture = r'''#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef struct { uint32_t ea; uint8_t running[16]; } slot;
#define TS_TRACK 8
static slot s_ts_run[TS_TRACK];
static uint64_t s_asc_taskset_commit_metrics[2];
static uint8_t guest[0x4000];
uint8_t* vm_base=guest;
uint32_t g_ydkj_real_taskset_ea, g_ydkj_real_taskid;
static unsigned locked, dispatches;
static uint64_t recorded[14];
static void ts_lock(void){assert(!locked);locked=1;}
static void ts_unlock(void){assert(locked);locked=0;}
static uint8_t* ts_running(uint32_t ea) {
    for(int i=0;i<TS_TRACK;i++)if(s_ts_run[i].ea==ea)return s_ts_run[i].running;
    return NULL;
}
static void ts_bits_clear(uint32_t ea,uint8_t mask){assert(locked);guest[ea]&=(uint8_t)~mask;}
static void asc_taskset_add(unsigned slot,uint64_t n){assert(slot<14);recorded[slot]+=n;}
static void asc_taskset_store(unsigned slot,uint64_t n){assert(slot<14);recorded[slot]=n;}
static size_t spu_elf_image_size(const uint8_t* image,size_t cap){
    (void)cap;return image==guest+0x1000 ? 128u : 0u;
}
static int spu_workload_dispatch_async(const uint8_t* image,uint32_t size,uint32_t ctx){
    assert(locked && image==guest+0x1000 && size==128 && ctx==0x2000);
    dispatches++;return 1;
}
/* PRODUCTION */
static void add_valid_task(void){
    const uint32_t base=0x100,ti=base+0x80;
    guest[base+0x10]=0x80;guest[base+0x20]=0x80;guest[base+0x30]=0x80;
    guest[ti+0x14]=0;guest[ti+0x15]=0;
    guest[ti+0x16]=0x10;guest[ti+0x17]=0;
    guest[ti+0x1c]=0;guest[ti+0x1d]=0;
    guest[ti+0x1e]=0x20;guest[ti+0x1f]=0;
}
int main(void){
    s_ts_run[0].ea=0x100;
    add_valid_task();
    spu_taskset_bits_committed(0x180);
    assert(!dispatches);
    /* Simulate guest-ready bits with callbacks delivered for other lines.
       The periodic sweep must discover the task on the 64th commit. */
    for(unsigned i=0;i<62;i++) spu_taskset_bits_committed(0x280);
    assert(!dispatches);
    spu_taskset_bits_committed(0x280);
    assert(dispatches==1 && recorded[5]==1);
    assert(s_ts_run[0].running[0]==0x80);
    spu_taskset_bits_committed(0x100);
    assert(dispatches==1 && !locked);
    assert(s_asc_taskset_commit_metrics[0]==65 && s_asc_taskset_commit_metrics[1]==1);
    assert(g_ydkj_real_taskset_ea==0x100 && g_ydkj_real_taskid==0);
    puts("[PASS] M8.15 periodic PUTLLC rescan discovers a ready task despite missed line match");
    return 0;
}
'''
    fixture=fixture.replace("/* PRODUCTION */",ready+"\n"+callback)
    cc=shutil.which("clang") or shutil.which("cc")
    assert cc, "missing host C compiler"
    with tempfile.TemporaryDirectory(prefix="m808-putllc-") as d:
        root=Path(d)
        (root/"test.c").write_text(fixture)
        subprocess.run([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",
                        str(root/"test.c"),"-o",str(root/"test")],check=True)
        subprocess.run([str(root/"test")],check=True)
    print("[PASS] M8.08 same production ready scan serves task exit and PUTLLC")

if __name__=="__main__":
    main()
