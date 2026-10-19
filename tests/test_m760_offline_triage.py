"""M7.60 AOT triage tooling: never fabricate decoded code or device events."""
from pathlib import Path
import json,struct,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from triage_owner_aot_report import analyze

def make_elf():
 d=bytearray(512)
 d[:7]=b'\x7fELF\x02\x02\x01'
 struct.pack_into('>Q',d,32,64)
 struct.pack_into('>HH',d,54,56,1)
 struct.pack_into('>IIQQQQQQ',d,64,1,5,256,0x10000,0,64,64,0x10)
 struct.pack_into('>4I',d,256,0x60000000,0x48000008,0x60000000,0x4e800020)
 return bytes(d)

class Triage(unittest.TestCase):
 def test_old_report_without_json_truthfully_shows_unknown_path(self):
  txt='PC de parada=0x00010000 | opcode=0x60000000\nopcode ELF=0x60000000 | opcode RAM=0x60000000 | bytes=28'
  got=analyze(txt,make_elf(),16)
  self.assertFalse(got['source_device_triage'])
  self.assertIsNone(got['previous_aot'])
  self.assertEqual(got['candidate_word_count'],2)
  self.assertEqual(got['ppc_words'][1]['control_flow']['target'],'0x0001000C')
  self.assertFalse(got['candidate_is_function'])
 def test_structured_trace_preserves_aot_evidence(self):
  raw={'previous_aot':'0x00010410','first_aot':['0x00010410'],
       'first_truncated':False,'recent_runs':[{'pc':'0x00010410','hits':100}],
       'guest_fs_positive_bytes':0}
  txt=('PC de parada=0x00010000\n'
       'opcode ELF=0x60000000 | opcode RAM=0x60000000\n'
       'AOT_TRIAGE_JSON='+json.dumps(raw))
  got=analyze(txt,make_elf(),16)
  self.assertTrue(got['source_device_triage'])
  self.assertEqual(got['previous_aot'],'0x00010410')
  self.assertEqual(got['recent_compacted_runs'][0]['hits'],100)
  self.assertEqual(got['guest_fs_positive_bytes'],0)
 def test_refuses_mismatched_elf(self):
  with self.assertRaises(ValueError):
   analyze('PC de parada=0x00010000\nopcode ELF=0x12345678 | opcode RAM=0x12345678',make_elf(),16)
 def test_refuses_ram_different_from_owner(self):
  with self.assertRaises(ValueError):
   analyze('PC de parada=0x00010000\nopcode ELF=0x60000000 | opcode RAM=0x00000000',make_elf(),16)

if __name__=='__main__':unittest.main()
