"""M5.5 fail-closed source contracts: real RSX stencil on Metal."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=(ROOT/"ios/ARGuestDrawProbe.c").read_text()
OVER=(ROOT/"tools/enable_ios_guest_draw_probe.py").read_text()
APP=(ROOT/"ios/ARProbeApp.m").read_text()

class NativeRSXStencil(unittest.TestCase):
    def test_stencil_encoded_as_guest_registers(self):
        for needle in (
            "ar_probe_m55_guest_stencil_mask(",
            "NV4097_SET_STENCIL_TEST_ENABLE,1u",
            "NV4097_SET_STENCIL_FUNC,",
            "always ? 0x0207u : 0x0202u",
            "NV4097_SET_STENCIL_FUNC_REF,",
            "depth_mode==4u ? 2u : 1u",
            "NV4097_SET_STENCIL_FUNC_MASK,read_mask",
            "M55_NV4097_SET_STENCIL_MASK 0x0000032Cu",
            "rsx_draw_engine_method(M55_NV4097_SET_STENCIL_MASK,write_mask)",
            "*stencil_draws=ar_probe_m55_stencil_draws();",
            "NV4097_SET_STENCIL_OP_ZPASS,",
            "always ? 0x1e01u : 0x1e00u",
            "(depth_mode==3u || depth_mode==6u) ? 0xf2u",
            "depth_mode==3u || depth_mode==6u",
            "const unsigned expected[3]={0u,0u,2u}",
            "if(*stencil_draws!=3u) return -540",
            "pixels[q]!=m51_colors[(q+expected[i])&3u]"
        ): self.assertIn(needle,SRC)
    def test_genuine_guest_metal_draw_instrumented(self):
        for needle in (
           "u8 ar_m55_stencil",
           "ar_m55_stencil_draws_encoded",
           "rs->stencil_enable &&",
           "rs->s_write_mask == 0xffu",
           "r->depth && eng_obj(r->depth)",
           "p->ar_m51_tex0 && p->ar_m55_stencil",
        ): self.assertIn(needle,OVER)
        self.assertNotIn("computeCommandEncoder",OVER)
        self.assertNotIn("computeCommandEncoder",SRC)
    def test_old_paths_and_buttons_kept(self):
        for needle in ("ar_probe_m54_guest_depth_occlusion(",
          "ar_probe_m53_guest_multipass(","ar_probe_m52_guest_texture_mutation(",
          "ar_probe_m51_guest_textured_quad("):self.assertIn(needle,SRC)
        for needle in ("testM55StencilMask:","testM54DepthOcclusion:",
            "testM53Multipass:","testM52TextureMutation:","testM51GuestDraw:",
            "testRSXCache:"):self.assertIn(needle,APP)
        self.assertIn("0.6.20-unsigned.ipa",
            (ROOT/"tools/build_ios_probe_ipa.sh").read_text())
        wf=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
        self.assertIn("grep -q '_ar_probe_m55_guest_stencil_mask'",wf)
        self.assertIn("m55-status.txt",wf)

if __name__=="__main__":unittest.main()
