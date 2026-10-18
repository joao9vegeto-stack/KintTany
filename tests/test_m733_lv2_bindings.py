"""M7.33 regression: LV2 144 must be wired into ACTUAL iPhone bootstrap.

M7.32 had a functional timezone handler and passing synthetic runtime
test, but ios/ARLivePPUBridge.c did not bind 144. The test itself had
registered 144 manually; this suite forbids that divergence.
"""
import unittest,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def source(path):return (ROOT/path).read_text(encoding="utf-8")
class TestM733IOSBindings(unittest.TestCase):
 def test_production_calls_exact_same_registrar_as_synthetic(self):
  prod=source("ios/ARLivePPUBridge.c")
  host=source("tests/host_m732_native_timezone.c")
  self.assertIn("if(ar_lv2_bind_bootstrap_syscalls()!=AR_OK)",prod)
  self.assertIn("if(ar_lv2_bind_bootstrap_syscalls()!=AR_OK)",host)
  self.assertEqual(prod.count("ar_lv2_bind_bootstrap_syscalls()"),1)
  self.assertEqual(host.count("ar_lv2_bind_bootstrap_syscalls()"),1)
  self.assertNotRegex(prod,r"ar_bind_syscall\s*\(\s*144")
  self.assertNotRegex(host,r"ar_bind_syscall\s*\(\s*144\s*u?\s*,\s*ar_lv2_timezone\s*\)\s*!=\s*AR_OK")
 def test_all_four_real_callbacks_come_from_one_c_table(self):
  header=source("runtime/ppu_lv2_bootstrap.h")
  impl=source("runtime/ppu_lv2_bootstrap.c")
  self.assertIn("int ar_lv2_bind_bootstrap_syscalls(void);",header)
  for number,name in [(352,"ar_lv2_user_memory_size"),
                      (147,"ar_lv2_timebase_frequency"),
                      (145,"ar_lv2_current_time"),
                      (144,"ar_lv2_timezone")]:
   txt="0x160" if number==352 else str(number)
   self.assertRegex(impl,r"\{\s*UINT32_C\("+txt+r"\)\s*,\s*"+name+r"\s*\}")
  self.assertIn("ar_bind_syscall(services[i].number,services[i].fn)",impl)
  self.assertIn("if(rc!=AR_OK)return rc;",impl)
 def test_guest_trace_shows_success_not_mere_call(self):
  runner=source("ios/ARLivePPUBridge.c")
  trace=source("runtime/ppu_bridge.h")
  ui=source("ios/ARProbeApp.m")
  self.assertIn("last_run_trace.lv2_timezone_completed=ar_lv2_timezone_queries()",runner)
  self.assertIn("uint32_t lv2_timezone_completed;",trace)
  self.assertIn("measured.lv2_timezone_completed",ui)
  self.assertIn("ASCENSIONRECOMP M7.38",ui)
  self.assertIn("AscensionRecomp-M7.38-NPUA80918",ui)
 def test_no_regression_of_verified_owner_aot(self):
  runner=source("ios/ARLivePPUBridge.c")
  for symbol in ("ar_m731_register_frontier(d,len)","ar_m732_register_block(d,len)"):
   self.assertIn(symbol,runner)
  self.assertLess(runner.index("ar_lv2_bind_bootstrap_syscalls()"),
                  runner.index("ar_run(&ctx,image.entry_code"))
if __name__=="__main__":unittest.main()
