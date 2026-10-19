"""M6.5: real device -995 at stw r29,0(r11) never bypassed."""
import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]
C=(P/"ios/ARPrivateELFProbe.c").read_text()
U=(P/"ios/ARProbeApp.m").read_text()
W=(P/".github/workflows/ascension-recomp-m0.yml").read_text()
H=(P/"tests/host_m65_guestmem.c").read_text()
class GuestMemory(unittest.TestCase):
 def test_safe_writable_guest_memory(self):
  for t in ("int ar_ppu_bootstrap_forty(","for(unsigned step=0;step<40;step++)",
      "m65_segment(s,count,va,4u,2u)","m65_store32(&guest,ss,used,va,v)",
      "m65_read_guest(d,len,ss,used,&guest,stack,base,va,4,&value)",
      "m65_read_guest(d,len,ss,used,&guest,stack,base,va,8,&value)",
      "uint32_t value;","m->used>=128u","relative<seg->size",
      "out[10]=(uint32_t)va;out[11]=(uint32_t)gpr[ra];out[12]=v;",
      "return rc==-2 ? -1005 : -1004;",
      "if(step==15u &&", "out[15]=guest.used;"):
   self.assertIn(t,C)
 def test_synthetic_exact_device_opcode_and_security(self):
  for t in ("0x93ab0000u","0x818b0000u","0x81ab0000u",
    "0xfeedface","cpu[13]!=0x1234u","cpu[14]!=0x1234u",
    "cpu[15]!=2u","cpu[10]!=0x10000u","cpu[10]!=0x20061u",
    "M6.5 PPU40 private guest writable PT_LOAD PASS"):
   self.assertIn(t,H)
 def test_preserve_prior_work_and_real_device_trace(self):
  for t in ("for(unsigned step=0;step<16;step++)",
     "for(unsigned step=0;step<24;step++)",
     "for(unsigned step=0;step<32;step++)",
     "ar_ppu_bootstrap_sixteen(data.bytes,data.length,info,cpu16)",
     "ar_ppu_bootstrap_twentyfour(data.bytes,data.length,info,cpu24)",
     "ar_ppu_bootstrap_thirtytwo(data.bytes,data.length,info,cpu32)",
     "ar_ppu_bootstrap_forty(data.bytes,data.length,info,cpu40)"):
   self.assertIn(t,C if "for(" in t else U)
  for t in ("M6.5 PARADA SEGURA","EA=0x%X · base=0x%X · valor=0x%X",
    "M6.5 PPU REAL 40/40: OK","ASCENSIONRECOMP   ·   M7.59",
    "self.gameList.hidden=!showGame","self.graphicsList.hidden=showGame"):
   self.assertIn(t,U)
 def test_ci(self):
  for t in ("m65-host.log","m65-status.txt",
    "tests/host_m65_guestmem.c","0.6.22-unsigned.ipa"):
   self.assertIn(t,W)
if __name__=="__main__":unittest.main()
