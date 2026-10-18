"""M7.50 regression: real owner PPC path + verified current-run report."""
from pathlib import Path
import sys,unittest
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"tools"))
from ppu_cfg_lifter import lift,Unsupported
class TestM750(unittest.TestCase):
 def test_fsubs_native_generic_and_fallback(self):
  word=0xec21f828
  src,h=lift([word,0x4e800020],0x10000)
  self.assertEqual(h['fsubs'],1)
  self.assertIn('ar_fp_fsubs(c,1,1,31)',src)
  self.assertIn('ar_fp_fsubs', (R/'runtime/ppu_fp_scalar.h').read_text())
  self.assertIn('case 59', (R/'runtime/ppu_m720_fallback.c').read_text())
  with self.assertRaises(Unsupported):
   lift([word|1,0x4e800020],0x10000)
 def test_owner_signed_two_parts_guest_memory_and_ctr(self):
  n=(R/'runtime/ppu_m750_native_path.c').read_text()
  for x in ('ar_m750_native_003b1d78','ar_m750_native_003b1dc4',
            '19u,UINT64_C(0x52959d588494ed68)',
            '5u,UINT64_C(0x7f23904155db70b7)',
            'ar_vmx_guest_store','ar_fp_store','ar_fp_fsubs',
            'c->ctr--','ar_m712_exec_window','ar_read32',
            'ar_last_error','ar_register'):
   self.assertIn(x,n)
  bridge=(R/'ios/ARLivePPUBridge.c').read_text()
  self.assertLess(bridge.index('ar_gowa2_offline_aot_install_sha256(digest'),
                  bridge.index('ar_m750_register_owner(d,len)'))
  self.assertNotIn('ar_ppc_fallback_step(',n)
 def test_report_fresh_scoped_provenance_and_no_false_fs(self):
  ui=(R/'ios/ARProbeApp.m').read_text()
  for x in ('ARBuildProvenance.h','EXECUÇÃO ATUAL',
            'COMPARAÇÃO COM A BUILD ANTERIOR','HISTÓRICO',
            'AR_M750_BUILD_SHA','AR_M750_BUILD_RUN_ID',
            'NÃO MEDIDO','self.m750Run=nil','m750HostObservation',
            'cellFsRead com bytes positivos: %@',
            '0x003B064C','M7.53 (teste físico'):
   self.assertIn(x,ui)
  self.assertIn('AscensionRecomp-M7.54-NPUA80918',ui)
  sh=(R/'tools/build_ios_probe_ipa.sh').read_text()
  self.assertIn('GITHUB_SHA',sh)
  self.assertIn('GITHUB_RUN_ID',sh)
 def test_ios_build_host_ci_and_version(self):
  w=(R/'.github/workflows/ascension-recomp-m0.yml').read_text()
  for x in ('tests/host_m750_native_path.c','m750-native-host.log',
            'm750-native-arm64.o','_ar_m750_register_owner',
            'AscensionRecomp-M7.54-GOWA'):
   self.assertIn(x,w)
  self.assertIn('<string>90</string>',(R/'ios/Probe-Info.plist').read_text())
if __name__=='__main__':unittest.main()
