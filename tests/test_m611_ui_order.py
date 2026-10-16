"""Guard: M6.1 can run only if M6.0 completed successfully."""
import unittest
from pathlib import Path
A=(Path(__file__).resolve().parents[1]/"ios/ARProbeApp.m").read_text()
class SafeSequence(unittest.TestCase):
 def test_cpu_error_path_is_closed(self):
  i=A.index("if(cpu_rc){")
  j=A.index("unsigned int eight[6]",i)
  block=A[i:j]
  self.assertIn("return;",block)
  self.assertIn("}",block)
  self.assertIn("M6.0 PPU FALHA",block)
 def test_m61_success_is_not_in_failure_branch(self):
  i=A.index("unsigned int eight[6]")
  j=A.index("} @finally {",i)
  block=A[i:j]
  self.assertIn("if(rc8)",block)
  self.assertIn("M6.1 PPU REAL 8/8: OK",block)
  self.assertIn("M5.9 NPUA80918: ELF REAL VALIDADO",block)
  self.assertIn("rc8,eight[0]",block)
if __name__=="__main__": unittest.main()
