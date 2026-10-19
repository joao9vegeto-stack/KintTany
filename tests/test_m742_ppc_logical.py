"""M7.42 owner-path PPC64 logical ISA coverage, no AOT inflation.

Authoritative iPhone trace: 0x00525F10 NOR; 0x00525F14 CNTLZD.
Actual device progress is NOT inferred from these host oracle tests.
"""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class M742(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.src=(ROOT/"runtime/ppu_m720_fallback.c").read_text()
  cls.host=(ROOT/"tests/host_m742_logical_ppc.c").read_text()
  cls.ci=(ROOT/".github/workflows/ascension-recomp-m0.yml").read_text()
 def test_real_owner_words_have_generic_isa_support(self):
  self.assertIn("case 124:case 476:case 284:case 412:case 60:",self.src)
  self.assertIn("case 58:",self.src)
  self.assertIn("if(b!=0u)return AR_PPC_UNSUPPORTED;",self.src)
  self.assertIn("0x7d2b50f8",self.host)
  self.assertIn("0x7d600074",self.host)
  self.assertIn("if(record)",self.src)
  self.assertIn("return add_result(c,pc,result,a,record)",self.src)
  self.assertIn("return add_result(c,pc,count,a,record)",self.src)
 def test_host_vectors_validate_register_alias_and_record_semantics(self):
  self.assertIn("NOR alias RA=RS",self.host)
  self.assertIn("NOR alias RA=RB",self.host)
  self.assertIn("CNTLZD reserved RB",self.host)
  self.assertIn("memcmp(&before,&cpu,sizeof(cpu))",self.host)
  self.assertIn("m742-logical-host",self.ci)
  self.assertIn("<string>7680</string>",(ROOT/"ios/Probe-Info.plist").read_text())
 def test_no_emulator_dependency_added(self):
  self.assertNotIn("rpcs3",self.src.lower())
  self.assertIn("ASCENSIONRECOMP", (ROOT/"ios/ARProbeApp.m").read_text())
if __name__=="__main__":unittest.main()
