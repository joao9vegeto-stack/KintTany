"""M7.48 VMX signed-word conversion, full 31-op native owner, local path."""
from pathlib import Path
import sys,unittest
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tools"))
from ppu_cfg_lifter import lift
class M748VCFSX(unittest.TestCase):
 def test_generically_lift_vcfsx_all_scale_bits(self):
  for scale in (0,1,13,31):
   word=(4<<26)|(2<<21)|(scale<<16)|(2<<11)|842
   src,h=lift([word,0x4e800020],0x10000)
   self.assertEqual(h["vcfsx"],1)
   self.assertIn(f'ar_vmx_vcfsx(c,2,2,{scale})',src)
   self.assertIn('ppu_vmx_cell.h',src)
 def test_owner_digest_and_native_arm64_gate(self):
  source=(R/"runtime/ppu_m748_native_vcfsx.c").read_text()
  for s in ("ar_m748_native_003ddf20","ar_m748_native_003ddf54",
            "31u,UINT64_C(0xfb0acf25e4d1ffbe)",
            "18u,UINT64_C(0x28089fab4a53d0b1)",
            "ar_m712_exec_window","ar_read32","ar_register"):
   self.assertIn(s,source)
  bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  self.assertLess(bridge.index("ar_gowa2_offline_aot_install_sha256(digest"),
                  bridge.index("ar_m748_register_owner(d,len)"))
  self.assertNotIn("ar_ppc_fallback_step",source)
 def test_fallback_and_carryover_directory_discovery(self):
  fallback=(R/"runtime/ppu_m720_fallback.c").read_text()
  self.assertIn("xo==842u",fallback)
  self.assertIn("ar_vmx_vcfsx(c,d,b,a)",fallback)
  store=(R/"ios/ARGameFolderStore.m").read_text()
  self.assertIn('@[@"AscensionRecomp",@"NPUA80918"]',store)
  self.assertIn("if(!files.count)",store)
  self.assertIn("indexError.code==35",store)
  self.assertIn("Não mova",store)
 def test_xcode_real_host_and_version(self):
  w=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  for t in ("m748-native-host.log","tests/host_m748_native_vcfsx.c",
            "m748-folder-host.log","tests/host_m748_local_home.m",
            "m748-native-arm64.o"):
   self.assertIn(t,w)
  plist=(R/"ios/Probe-Info.plist").read_text()
  self.assertIn("<string>7641</string>",plist)
if __name__=="__main__":unittest.main()
