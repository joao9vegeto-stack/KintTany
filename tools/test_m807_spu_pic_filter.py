#!/usr/bin/env python3
"""Host checks for M8.07's PIC capture filter and iOS report/present wiring."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    patcher = (ROOT / "tools/enable_ios_spu_pic_runtime.py").read_text()
    block_match = re.search(r"PIC_API\s*=\s*r'''(.*?)'''", patcher, re.S)
    assert block_match, "PIC_API raw C block not found"
    block = block_match.group(1)
    helper_match = re.search(
        r"static int spu_pic_generated_stack_bridge\(uint32_t pc, const uint8_t code\[64\]\)\s*\{.*?\n\}",
        block,
        re.S,
    )
    assert helper_match, "exact generated-stack-bridge predicate missing"
    assert "spu_pic_generated_stack_bridge(pc, code)" in block
    assert "s_pic_generated_stubs_filtered" in block
    assert "s_pic_capture_rows_written" in block

    c_source = r"""
#include <assert.h>
#include <stdint.h>
""" + helper_match.group(0) + r"""

static void make_bridge(uint8_t code[64], uint8_t form) {
    for (unsigned i = 0; i < 16; ++i) {
        code[i * 4] = form;
        code[i * 4 + 1] = 0xFF;
        code[i * 4 + 2] = (uint8_t)(0x38 + 2 * i);
        code[i * 4 + 3] = (uint8_t)i;
    }
}

int main(void) {
    uint8_t code[64];
    const uint8_t forms[] = {0x20, 0x30};
    for (unsigned f = 0; f < sizeof(forms); ++f) {
        make_bridge(code, forms[f]);
        assert(spu_pic_generated_stack_bridge(UINT32_C(0x3FEC0), code));
        assert(!spu_pic_generated_stack_bridge(UINT32_C(0x3FEC4), code));
        code[37] ^= 1;
        assert(!spu_pic_generated_stack_bridge(UINT32_C(0x3FEC0), code));
        code[37] ^= 1;
        code[0] = (uint8_t)(forms[f] == 0x20 ? 0x30 : 0x20);
        assert(!spu_pic_generated_stack_bridge(UINT32_C(0x3FEC0), code));
    }
    return 0;
}
"""
    compiler = shutil.which("clang") or shutil.which("cc")
    assert compiler, "clang or cc is required for this host test"
    with tempfile.TemporaryDirectory(prefix="m807-pic-test-") as temp:
        source = Path(temp) / "test.c"
        binary = Path(temp) / "test"
        source.write_text(c_source)
        subprocess.run(
            [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
            check=True,
        )
        subprocess.run([str(binary)], check=True)

    app = (ROOT / "ios/ARProbeApp.m").read_text()
    start = app.index("- (NSString *)arLivePpuReportText {")
    end = app.index("- (void)refreshAdvancedPpuReport:", start)
    report = app[start:end]
    assert "ASCENSIONRECOMP · RELATÓRIO AO VIVO" in report
    assert "Relatório vazio: nenhuma métrica foi retornada." not in report
    assert "draws guest=" in report and "flips guest apresentados=" in report
    assert "SPU PIC:" in report and "SPURS:" in report
    assert "Backedge amostrado" in report and "não é PC atual" in report
    assert "arUnifiedPpuText" not in report

    pump_start = app.index("- (void)runNativeRSXPump {")
    pump_end = app.index("- (void)showNativeGameFrame {", pump_start)
    pump = app[pump_start:pump_end]
    assert "cellGcm_rsx_process_fifo()" in pump
    assert "cellGcm_take_flip_pending_synced()" in pump
    assert "flipRequests!=lastFlipRequestCount" in pump
    assert "rsx_metal_backend_present()" in pump
    print("[PASS] M8.07 exact generated stack bridge filter")
    print("[PASS] M8.07 live report and guest flip presentation contracts")


if __name__ == "__main__":
    main()
