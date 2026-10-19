"""M7.1 native precompiled PPC interpreter: no JIT/AOT misrepresentation."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
CPU=(ROOT/"ios/ARNativePPUContinuous.c").read_text()
SETUP=(ROOT/"ios/ARLivePPUContinuous.c").read_text()
UI=(ROOT/"ios/ARProbeApp.m").read_text()
BUILD=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
WORK=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
HOST=(ROOT/"tests/host_m71_continuous.c").read_text()
PL=(ROOT/"ios/Probe-Info.plist").read_text()
class M71(unittest.TestCase):
 def test_binary_contains_signed_fallback(self):
  for s in ("ARNativePPUContinuous.c","ARLivePPUContinuous.c",
            "ARNativePPUContinuous.o","ARLivePPUContinuous.o"):
   self.assertIn(s,BUILD)
  for s in ("_ar_m73_private_import_probe",
            "_ar_m71_signed_ppu_interpret","host_m71_continuous.c",
            "m71-continuous-host.log"):
   self.assertIn(s,WORK)
 def test_no_fake_aot_or_unsafe_isa(self):
  for s in ("ar_load_elf_image(d,len,cap,&cpu,&entry)",
            "ar_bridge_shutdown();", "out[11]=(uint32_t)ar_registered_count()",
            "cpu.gpr[7]=cpu.thread_id", "cpu.gpr[8]=tls_addr",
            "ar_bind_hle(im[0],ar_sys_initialize_tls)",
            "ar_m71_signed_ppu_interpret("):
   self.assertIn(s,SETUP)
  for s in ("const uint32_t word=ar_read32(pc)",
            "executable(seg,used,pc)", "ar_run(c,guest_stub,32u)",
            "guest_branch_test(c,bo,bi,1u,&taken)",
            "const uint64_t target=c->lr&~UINT64_C(3);",
            "rc=-1311;break;", "rc=-1312;break;",
            "rc=-1313;", "rc=-1314;", "budget>8192u",
            "uint32_t out[16]"):
   self.assertIn(s,CPU)
  self.assertNotIn("ar_register(",SETUP+CPU)
  self.assertNotIn("mmap(",CPU+SETUP)
 def test_long_host_test_is_real(self):
  for s in ("k<76u", "out[1]!=76u",
            "out[1]!=64u","(int32_t)out[0]!=-1314",
            "out[6]!=0x28000u",
            "M7.1 signed native PowerPC continuous 76-step, import TLS and fail-closed ISA PASS"):
   self.assertIn(s,HOST)
 def test_device_report(self):
  for s in ("M7.2 — EXECUÇÃO PPU CONTÍNUA + CR/BRANCH",
            "ar_m71_private_continuous_probe(",
            "INTERPRETAÇÃO NÃO É RECOMPILAÇÃO AOT",
            "Copiar diagnóstico PPU"):
   self.assertIn(s,UI)
  self.assertIn("<string>7641</string>",PL)
if __name__=="__main__": unittest.main()
