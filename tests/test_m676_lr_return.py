"""M6.7.6: PowerPC mtlr restores LR, blr verifies executable guest return."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
C=(R/"ios/ARPrivateELFProbe.c").read_text()
U=(R/"ios/ARProbeApp.m").read_text()
WF=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
HOST=(R/"tests/host_m676_lr_return.c").read_text()
PL=(R/"ios/Probe-Info.plist").read_text()
class GuestLR(unittest.TestCase):
 def test_exact_mt_spr(self):
  for token in ('((w>>1)&1023u)==467u',
                'spr!=8u && spr!=9u',
                'if(spr==8u)', 'lr=gpr[rt];',
                'detail[22]=pc;detail[23]=(uint32_t)lr;',
                'ctr=gpr[rt];', 'uint64_t lr=0;'):
   self.assertIn(token,C)
 def test_guarded_blr(self):
  for token in ('((w>>1)&1023u)==16u',
                'w!=0x4e800020u', 'lr&~UINT64_C(3)',
                'lookup(d,len,ss,used,target,4u,1u)',
                'return -1022;', 'return -1024;',
                'if(!tls_record)return -1006;'):
   self.assertIn(token,C)
  self.assertIn('return -1007; /* other invalid jumps remain forbidden */',C)
 def test_behavioral_cases(self):
  for token in ('0x7c0803a6u', '0x4e800020u',
                '0x4e000020u', '0x7c0803a7u',
                'out[0]!=16u', 'out[0]!=15u',
                'rc!=-1022','rc!=-1024','rc!=-1006',
                'M6.7.6 mtlr LR restore and guarded blr return PASS'):
   self.assertIn(token,HOST)
 def test_ui_and_ci(self):
  for token in ('ASCENSIONRECOMP   ·   M7.11',
                'Último mtlr: PC=',
                'detail48[22],detail48[23]',
                'Copiar diagnóstico PPU'):
   self.assertIn(token,U)
  for token in ('tests/host_m676_lr_return.c', 'm676-lr-host.log',
                'AscensionRecomp-M7.25-PPC-call-origin'):
   self.assertIn(token,WF)
  self.assertIn('<string>74</string>',PL)
if __name__=="__main__":unittest.main()
