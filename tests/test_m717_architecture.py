"""M7.17 synthetic CFG, native trace contracts, and strict batch planner."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from m717_owner_reachability import discover, report_seeds
from ppu_cfg_lifter import Unsupported

class TinyImage:
    def __init__(self):
        self.w={
          0x1000:0x48000101, # bl 0x1100
          0x1004:0x4182000c, # conditional -> 0x1010
          0x1008:0x4e800020, # blr
          0x1010:0x48000020, # b 0x1030
          0x1030:0x4e800020,
          0x1100:0x4e800020,
        }
    def words(self,a,b):
        if b!=a+4 or a not in self.w:raise Unsupported("not executable")
        return (self.w[a],)
class M717Tests(unittest.TestCase):
    def test_bounded_control_flow(self):
        g=discover(TinyImage(),[0x1000],64)
        self.assertEqual(g["nodes_inspected"],6)
        self.assertEqual(g["possible_edges"]["direct_calls"],1)
        self.assertEqual(g["possible_edges"]["conditional"],1)
        self.assertEqual(g["possible_edges"]["indirect"],3)
        self.assertEqual(g["direct_call_candidates"],["0x00001100"])
        self.assertFalse(g["truncated"])
    def test_truncation_and_invalid_pc(self):
        g=discover(TinyImage(),[0x1000],2)
        self.assertTrue(g["truncated"])
        self.assertEqual(g["nodes_inspected"],2)
        with self.assertRaises(ValueError):
            discover(TinyImage(),[0x1001],3)
        with self.assertRaises(ValueError):
            discover(TinyImage(),[0x1000],100001)
    def test_iphone_report_seeds(self):
        r=("Próximo bloco sem ARM64: 0x003C4E14\n"
           "PC inicial=0x003C4E14\n"
           "CALL_CANDIDATE 0x0052E180\n"
           "AOT_EXEC 0x00010410\n")
        self.assertEqual(report_seeds(r),[0x003c4e14,0x0052e180])
    def test_new_ui_and_unchanged_secret_gate(self):
        ui=(ROOT/"ios/ARProbeApp.m").read_text()
        h=(ROOT/"runtime/ppu_bridge.h").read_text()
        c=(ROOT/"runtime/ppu_bridge.c").read_text()
        build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        self.assertIn("M7.17 — COBERTURA ARM64 REAL + GRAFO PPC ESTÁTICO",ui)
        self.assertIn("ar_m717_walk(data.bytes,data.length,roots,nr,2048u,&graph)",ui)
        self.assertIn("ar_m717_last_aot_trace(&measured)",ui)
        self.assertIn("AR_AOT_TRACE_PCS",h)
        self.assertIn("aot_slot[AR_AOT_INDEX_SIZE]",c)
        self.assertIn("ar_trace_snapshot",c)
        self.assertIn("ppu_m717_graph.o",build)
        self.assertIn("verify_m712_macho.py",build)
        self.assertIn("RSX do Ascension: não demonstrado",ui)

if __name__=="__main__":
    unittest.main()
