"""Production no-interpreter source and Mach-O link regressions."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class TestM755(unittest.TestCase):
 def test_iOS_library_compiled_native_only(self):
  core=(R/'tools/build_ios_ppu_core.sh').read_text()
  app=(R/'tools/build_ios_probe_ipa.sh').read_text()
  bridge=(R/'ios/ARLivePPUBridge.c').read_text()
  dispatch=(R/'runtime/ppu_bridge.c').read_text()
  self.assertIn('-DASCENSION_NATIVE_ONLY=1',core)
  self.assertIn('-DASCENSION_NATIVE_ONLY=1',app)
  self.assertNotIn('    ios-probe/ppu_m720_fallback.o \\',app)
  self.assertIn("if grep -Eq ' [Tt] _ar_ppc_fallback_step$'",app)
  self.assertIn('&& !defined(ASCENSION_NATIVE_ONLY)',bridge)
  self.assertIn('#ifndef ASCENSION_NATIVE_ONLY',dispatch)
  self.assertIn('result=fault=AR_UNRESOLVED',dispatch)
 def test_history_not_falsely_promoted(self):
  app=(R/'ios/ARProbeApp.m').read_text()
  for needle in ('LAUNCHER / EXECUÇÃO NATIVA',
                 'PPC interpretado=0 · entradas HLE e LV2 contadas no runtime',
                 'Comandos RSX do jogo= %@',
                 'Primeiro flip guest apresentado= %@'):
   self.assertIn(needle,app)
  self.assertIn('cellFsRead guest=%@ · bytes lidos pelo guest=%@',app)
 def test_ci_native_only_host_gate(self):
  flow=(R/'.github/workflows/ascension-recomp-m0.yml').read_text()
  self.assertIn('host_m755_native_only.c',flow)
  self.assertIn('m755-native-only-host.log',flow)
if __name__=='__main__':unittest.main()
