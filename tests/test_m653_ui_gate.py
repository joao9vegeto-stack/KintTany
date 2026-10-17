"""iPhone M6.5.2 failed to reach PPU40: legacy PPU32 returned -995 at step 28."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
UI=(R/"ios/ARProbeApp.m").read_text()
HOST=(R/"tests/host_m65_guestmem.c").read_text()
C=(R/"ios/ARPrivateELFProbe.c").read_text()
class GuestStackGate(unittest.TestCase):
 def test_m65_starts_after_only_known_legacy_stack_limit(self):
  t=UI.index("const int rc32=ar_ppu_bootstrap_thirtytwo(")
  nextp=UI.index("const int rc40=ar_ppu_bootstrap_forty(",t)
  block=UI[t:nextp]
  self.assertIn("const BOOL legacyStackOnlyStop =",block)
  self.assertIn("rc32==-995 && cpu32[0]>=24u && (cpu32[7]>>26)==36u;",block)
  self.assertIn("if(rc32 && !legacyStackOnlyStop){",block)
  self.assertIn("M6.4 LEGADA: -995",block)
  self.assertNotIn("if(rc32){",block)
  self.assertIn("legacyState,rc40,cpu40[0],cpu40[8],cpu40[7]",UI)
  self.assertIn("M6.5 PARADA SEGURA",UI)
  self.assertIn("EA=0x%X · base=0x%X · valor=0x%X",UI)
  self.assertIn("ASCENSIONRECOMP   ·   M7.11",UI)
 def test_old_legacy_and_new_overlay_same_guest_fixture(self):
  for text in ("ar_ppu_bootstrap_thirtytwo(d,sizeof d,info,legacy)!=-995",
    "legacy[0]!=26u","legacy[7]!=0x93ab0000u",
    "legacy[8]!=0x10074u",
    "ar_ppu_bootstrap_forty(d,sizeof d,info,cpu)!=0",
    "cpu[0]!=40u","cpu[15]<1u"):
   self.assertIn(text,HOST)
  self.assertIn("m65_store32(&guest,ss,used,va,v)",C)
 def test_version(self):
  self.assertIn("<string>0.6.15</string>",(R/"ios/Probe-Info.plist").read_text())
  self.assertIn("0.6.15-unsigned.ipa",
     (R/".github/workflows/ascension-recomp-m0.yml").read_text())
if __name__=="__main__":unittest.main()
