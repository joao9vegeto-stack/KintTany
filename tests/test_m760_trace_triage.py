"""M7.60 report should retain first visit and compact hot loops."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class TestM760Trace(unittest.TestCase):
 def test_native_dispatcher_trace_no_interpreter(self):
  h=(R/'runtime/ppu_bridge.h').read_text()
  c=(R/'runtime/ppu_bridge.c').read_text()
  for needle in ('AR_AOT_TRIAGE_FIRST 256u','AR_AOT_TRIAGE_RUNS 128u',
                 'run_repetitions','stop_previous_aot','first_total'):
   self.assertIn(needle,h)
  for needle in ('triage_run_total','triage_first_count','triage_stop_prev',
                 'trace_ring[(trace_total-1u)&(AR_AOT_TRACE_PCS-1u)]',
                 'result=fault=AR_UNRESOLVED'):
   self.assertIn(needle,c)
 def test_report_machine_readable_and_honest_fs(self):
  s=(R/'ios/ARProbeApp.m').read_text()
  for needle in ('Chamadas de função AOT=%@','início(s) da entry=%@',
                 'cellFsOpen guest=%@ · opens OK=%@',
                 'cellFsRead guest=%@ · bytes lidos pelo guest=%@',
                 'Pasta reconhecida pelo HOST=%@',
                 'Leitura guest de arquivos do jogo= %@',
                 'PSARC específico= NÃO MEDIDO'):
   self.assertIn(needle,s)
  self.assertIn('Comandos RSX do jogo= %@',s)
 def test_ci_wires_synthetic_native_host(self):
  wf=(R/'.github/workflows/ascension-recomp-m0.yml').read_text()
  self.assertIn('host_m760_trace_triage.c',wf)
  self.assertIn('m760-triage-host.log',wf)
if __name__=='__main__':unittest.main()
