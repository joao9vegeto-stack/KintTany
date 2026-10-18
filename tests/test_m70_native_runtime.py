"""M7.0: signed iPhoneOS native PPU library is really linked into the app."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
BRIDGE=(R/"ios/ARLivePPUBridge.c").read_text()
APP=(R/"ios/ARProbeApp.m").read_text()
BUILD=(R/"tools/build_ios_probe_ipa.sh").read_text()
WF=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
HOST=(R/"tests/host_m70_native_runtime.c").read_text()
P=(R/"ios/Probe-Info.plist").read_text()
class NativePPU(unittest.TestCase):
 def test_real_runtime_in_app_binary(self):
  for x in ('ios/ARLivePPUBridge.c', 'libAscensionPPUCore-ios-arm64.a',
            'ios-probe/ARLivePPUBridge.o', '_ar_m70_native_runtime_probe'):
   self.assertIn(x,BUILD)
  for x in ("grep -q '_ar_run'", "grep -q '_ar_load_elf_image'",
            "grep -q '_ar_sys_initialize_tls'",
            'tests/host_m70_native_runtime.c', 'm70-native-host.log'):
   self.assertIn(x,WF)
 def test_signed_code_boundaries(self):
  for x in ('ar_bridge_init(cap)', 'ar_load_elf_image(d,len,cap,&ctx,&image)',
            'ar_private_import_match(d,len,guest_stub,match,module)',
            'ar_bind_import(guest_stub,match[0])',
            'ar_bind_hle(match[0],ar_sys_initialize_tls)',
            'ar_run(&ctx,image.entry_code,128u)',
            'ar_last_unresolved()', 'ar_bridge_shutdown()',
            'out[5]=(uint32_t)ar_registered_count()',
            'AR_UNRESOLVED', 'AR_NATIVE_LIMIT=128u*1024u*1024u'):
   self.assertIn(x,BRIDGE)
  self.assertNotIn('ar_register(image.entry_code',BRIDGE)
 def test_device_report_and_privacy(self):
  for x in ('ar_m70_native_runtime_probe(', 'M7.0 — RUNTIME PPU NATIVO',
            'Sem', 'Copiar diagnóstico PPU'):
   if x=='Sem':continue
   self.assertIn(x,APP)
  self.assertIn('<string>90</string>',P)
 def test_synthetic_negative_cases(self):
  for x in ('M7.0 signed native PPU staging, real NID/HLE, and honest AOT unresolved PASS',
            'out)!=-21','out)!=-23','out[7]!=0x10000u',
            'out[12]!=0x28000u', 'out[15]!=15u'):
   self.assertIn(x,HOST)
if __name__=="__main__":unittest.main()
