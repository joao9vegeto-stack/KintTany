#!/usr/bin/env python3
"""M8.11: native SPURS2 schedule parity and honest LFQueue/EDGE evidence.

Applies to the PS3Recomp C runtime AFTER existing M8.10 patches.
No runtime guest instruction interpreter is enabled by this code.
"""
from pathlib import Path
import argparse
MARK = "ASCENSION_M811_SPURS2_PC_SCHEDULER_V1"
EDGE = "ASCENSION_M811_EDGE_CLASSIFICATION_V1"

def apply(upstream):
    p=Path(upstream)/"libs/spurs/cellSpurs.c"
    s=p.read_text()
    if MARK in s:
        for key in (EDGE,"cellSpursCopyAscensionHighMasks",
                    "cellSpursCopyAscensionEdgeMetrics"):
            assert key in s,(p,key)
        return
    assert "ASCENSION_M810_NATIVE_LFQUEUE_V1" in s
    assert "ASCENSION_M772_EDGE_ZLIB_HLE_V2" in s
    assert "ASCENSION_M772_SPURS2_WORKLOADS_32_V1" in s

    target="static DWORD WINAPI spurs_kernel_thread(LPVOID p)\n{"
    assert s.count(target)==1
    start=s.index(target)
    end=s.index("\nstatic s32 spurs_scheduler_start",start)
    scheduler=s[start:end]
    old="if (!vm_read8(ea + wkl_info_off(wid) + 0x18 + sn))"
    assert scheduler.count(old)==1
    scheduler=scheduler.replace(old,
      "if (!vm_read8(ea + wkl_info_off(wid) + 0x18 + sn) && "
      "!(spurs_ready_level() && si->is2 && wid >= 16))",1)
    # The PC gowa-fixes persistent policy scheduler dispatches enabled
    # registered policy modules without a readyCount/priority kick.
    # Restrict the parity behavior to CellSpurs2 upper WIDs; retain all
    # bounds/state/registered PM/maxContention checks from the native kernel.
    s=s[:start]+scheduler+s[end:]

    diag=r'''/* ASCENSION_M811_SPURS2_PC_SCHEDULER_V1
 * Snapshot physical SPURS2 upper workload state without altering guest RAM.
 * Each mask bit 0..15 corresponds to guest workload ID 16..31.
 * [0] registered [1] enabled [2] state==2 [3] any priority>0
 * [4] ready [5] signalled [6] active [7] dispatches upper workload.
 */
void cellSpursCopyAscensionHighMasks(u64 out[8])
{
    if(!out)return;
    for(unsigned k=0;k<8;k++)out[k]=0;
    for(unsigned inst=0; inst<MAX_SPURS_INST; ++inst) {
        struct SpursInst* si=&s_inst[inst];
        const u32 ea=__atomic_load_n(&si->ea,__ATOMIC_ACQUIRE);
        if(!ea || !si->is2 || !spurs_guest_range_valid(ea,0x2000u))
            continue;
        const u32 enabled=vm_read32(ea+SPURS_WKL_ENABLED);
        for(u32 wid=16;wid<SPURS_MAX_WID;wid++) {
            u64 bit=UINT64_C(1) << (wid-16);
            if(s_workloads[wid].in_use && s_workloads[wid].spurs_ea==ea)out[0]|=bit;
            if(enabled&(0x80000000u>>wid))out[1]|=bit;
            if(vm_read8(ea+wkl_state_off(wid))==2)out[2]|=bit;
            for(u32 sn=0;sn<si->nspus && sn<6;sn++)
                if(vm_read8(ea+wkl_info_off(wid)+0x18u+sn)){out[3]|=bit;break;}
            if(vm_read8(ea+wkl_ready_off(wid)))out[4]|=bit;
            if(wkl_signalled(ea,wid))out[5]|=bit;
            if(si->active[wid])out[6]|=bit;
        }
        break;
    }
    out[7]=__atomic_load_n(&s_asc_dispatches_hi,__ATOMIC_RELAXED);
}

/* ASCENSION_M811_EDGE_CLASSIFICATION_V1
 * Classifies the intentionally short-circuited EDGE host inflate path.
 * M8.10 counted it as a push but not a queue commit. This distinction is
 * essential: zero queue commits alone does NOT imply failed decompression.
 * [0] EDGE attempts [1] successes [2] rejects [3] uncompressed bytes
 * [4] completion event flags.
 */
static volatile u64 s_asc_edge_metrics[5];
void cellSpursResetAscensionEdgeMetrics(void)
{
    for(unsigned k=0;k<5;k++)__atomic_store_n(&s_asc_edge_metrics[k],0,__ATOMIC_RELAXED);
}
void cellSpursCopyAscensionEdgeMetrics(u64 out[5])
{
    if(!out)return;
    for(unsigned k=0;k<5;k++)out[k]=__atomic_load_n(&s_asc_edge_metrics[k],__ATOMIC_RELAXED);

}
'''
    s=s.replace(target,diag+"\n"+target,1)

    # Instrument actual EDGE fast-path, not the outer _LFQueue entry.
    edge_start=s.index("/* ASCENSION_M772_EDGE_ZLIB_HLE_V2")
    edge_end=s.index("/* ASCENSION_M810_RETAIN_EDGE_DEFLATE */",edge_start)
    edge=s[edge_start:edge_end]
    start_token="      if (s_edge) {"
    assert edge.count(start_token)==1
    edge=edge.replace(start_token,start_token+
        "\n          __atomic_fetch_add(&s_asc_edge_metrics[0],1,__ATOMIC_RELAXED);",1)
    # Failures must be counted separately from normal queue push rejections.
    check="              return CELL_SPURS_TASK_ERROR_FAULT;"
    assert edge.count(check)>=1
    edge=edge.replace(check,
         "              { __atomic_fetch_add(&s_asc_edge_metrics[2],1,__ATOMIC_RELAXED); return CELL_SPURS_TASK_ERROR_FAULT; }")
    malloc_check="if (!inflated) return CELL_SPURS_TASK_ERROR_NOMEM;"
    assert edge.count(malloc_check)==1
    edge=edge.replace(malloc_check,
        "if (!inflated) { __atomic_fetch_add(&s_asc_edge_metrics[2],1,__ATOMIC_RELAXED); "
        "return CELL_SPURS_TASK_ERROR_NOMEM; }",1)
    bad_result="              return CELL_SPURS_TASK_ERROR_INVAL;"
    assert edge.count(bad_result)==1
    edge=edge.replace(bad_result,
        "              __atomic_fetch_add(&s_asc_edge_metrics[2],1,__ATOMIC_RELAXED); "
        "return CELL_SPURS_TASK_ERROR_INVAL;",1)
    old_evt="          if (left == 1u && flag && bits)\n              cellSpursEventFlagSet((CellSpursEventFlag*)(uintptr_t)flag, bits);"
    assert edge.count(old_evt)==1
    edge=edge.replace(old_evt,
        "          if (left == 1u && flag && bits) {\n"
        "              cellSpursEventFlagSet((CellSpursEventFlag*)(uintptr_t)flag, bits);\n"
        "              __atomic_fetch_add(&s_asc_edge_metrics[4],1,__ATOMIC_RELAXED);\n"
        "          }",1)
    marker="          return CELL_OK;"
    assert edge.count(marker)==1
    edge=edge.replace(marker,
        "          __atomic_fetch_add(&s_asc_edge_metrics[1],1,__ATOMIC_RELAXED);\n"
        "          __atomic_fetch_add(&s_asc_edge_metrics[3],count,__ATOMIC_RELAXED);\n"+marker,1)
    s=s[:edge_start]+edge+s[edge_end:]
    assert s.count(MARK)==1 and s.count(EDGE)==1
    p.write_text(s)
    print("M8.11: native PC-compatible upper-WID scheduler and classified EDGE/queue metrics PASS")

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--upstream",required=True)
    apply(a.parse_args().upstream)
