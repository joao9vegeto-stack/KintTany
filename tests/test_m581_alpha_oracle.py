"""M5.8.1 independent reference: accepted alpha=0 writes alpha ZERO.
Do not use a host rendering substitute; test only validates fixture oracle.
Actual GPU proof requires LINEAR and SWIZZLED physical-device readbacks.
"""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"ios/ARGuestDrawProbe.c").read_text()

class AlphaOracle(unittest.TestCase):
    @staticmethod
    def reference():
        colors=(0xffff0000,0xff00ff00,0xff0000ff,0xffffff00)
        palette=(0,1,2,3,3)
        state=list(colors)
        result=[list(state)]
        for phase in range(1,5):
            out=[]
            for quadrant in range(4):
                alpha=255 if quadrant&1 else 0
                threshold=(128,128,255,0)[phase-1]
                greater=(phase in (1,3,4))
                accept=(alpha>threshold) if greater else (alpha<threshold)
                incoming=(alpha<<24)|(colors[(quadrant+palette[phase])&3]&0xffffff)
                out.append(incoming if accept else state[quadrant])
            state=out
            result.append(list(state))
        return result

    def test_complete_five_phase_gpu_expected_values(self):
        m=re.search(r'static const uint32_t expected\[5\]\[4\]=\{(.*?)\};',
                    SOURCE,re.S)
        self.assertIsNotNone(m)
        rows=re.findall(r'\{([^{}]+)\}',m.group(1))
        self.assertEqual(len(rows),5)
        actual=[[int(x,16) for x in re.findall(r'0x([0-9a-fA-F]+)u',row)]
                for row in rows]
        self.assertTrue(all(len(row)==4 for row in actual))
        self.assertEqual(actual,self.reference())
        self.assertEqual(actual[2],[0x000000ff,0xff0000ff,0x00ff0000,0xffff0000])
        self.assertEqual(actual[3],actual[2])
        self.assertEqual(actual[4],[0x000000ff,0xffff0000,0x00ff0000,0xff0000ff])

    def test_guest_state_and_real_gpu_gate_remain_unchanged(self):
        for marker in (
            "d[0]=m58_alpha_phase>=2u ? (x>=4u ? 255u : 0u)",
            "rsx_draw_engine_method(NV4097_SET_ALPHA_FUNC,func[i])",
            "rsx_draw_engine_method(NV4097_SET_ALPHA_REF,ref[i])",
            "rsx_draw_engine_method(NV4097_SET_ALPHA_TEST_ENABLE,1u)",
            "ar_probe_m51_readback_quad(pixels)",
            "ar_probe_m58_alpha_draws()",
            "pixels[q]!=expected[i][q]",
            "m58_alpha_phase=0u",
            "ar_probe_m57_guest_blend_mask",
            "ar_probe_m56_guest_stencil_bitmasks"
        ):
            self.assertIn(marker,SOURCE)

if __name__=="__main__":
    unittest.main()
