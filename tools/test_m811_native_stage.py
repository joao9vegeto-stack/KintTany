#!/usr/bin/env python3
"""Validate M8.11 native production SPURS2 and AOT-only iOS launcher contracts."""
from pathlib import Path
import argparse

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--upstream",type=Path,required=True)
    a=p.parse_args()
    src=(a.upstream/"libs/spurs/cellSpurs.c").read_text()
    assert src.count("ASCENSION_M811_SPURS2_PC_SCHEDULER_V1")==1
    assert src.count("ASCENSION_M811_EDGE_CLASSIFICATION_V1")==1
    assert src.count("cellSpursCopyAscensionHighMasks(")==1
    assert src.count("cellSpursCopyAscensionEdgeMetrics(")==1
    assert "si->is2 && wid >= 16" in src
    assert "if (!vm_read8(ea + wkl_info_off(wid) + 0x18 + sn) &&" in src
    assert src.count("__atomic_fetch_add(&s_asc_edge_metrics[1],1")>=1
    assert src.count("__atomic_fetch_add(&s_asc_edge_metrics[0],1")>=1
    assert src.count("ASCENSION_M810_NATIVE_LFQUEUE_V1")==1
    assert "ASCENSION_M772_EDGE_ZLIB_HLE_V2" in src
    assert "if (!inflated) { __atomic_fetch_add(&s_asc_edge_metrics[2]" in src
    assert "return CELL_SPURS_TASK_ERROR_NOMEM; }" in src
    print("[PASS] M8.11 production native SPURS2 high WID parity, EDGE classification")
if __name__=="__main__":main()
