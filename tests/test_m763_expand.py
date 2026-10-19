"""M7.63 verified expansion of semantic opcode families over original OPD/CFG manifest."""
import base64,gzip,hashlib,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import m763_expand as m
SNAP_SHA='d7f7e024263d888c1b834a7ecddb1cafb862f64a0b066f6dbccb596026c854e7'
class Expansion(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  raw=gzip.decompress(base64.b64decode((ROOT/'runtime/m763_semantic_snapshot.gz.b64').read_text(),validate=True))
  assert hashlib.sha256(raw).hexdigest()==SNAP_SHA
  cls.snap=json.loads(raw)
 def test_whole_elf_new_no_manual_span_table(self):
  s=self.snap
  self.assertEqual(s['new_lifted'],1582)
  self.assertEqual(s['new_ppc_words'],8313)
  self.assertEqual(s['candidates'],19403)
  self.assertEqual(len(s['accepted']),1582)
  self.assertEqual(len({r['pc'] for r in s['accepted']}),1582)
  self.assertEqual(s['previous_entries'],805)
  self.assertEqual(s['source_sha256'],m.base.ELF_SHA)
 def test_real_iphone_frontier_14_guest_words(self):
  r={r['pc']:r for r in self.snap['accepted']}[0x002c53bc]
  self.assertEqual(r['count'],14)
  self.assertEqual(r['sha256'],'511fb65b662c91435c7e95c25b0baac075236829d1629d34ed158af466398541')
  self.assertEqual([x[0] for x in r['ir']],['addis','addis','addic','ori','addis','stw','xo','addic','ori','xo','stw','stw','stw','blr'])
  self.assertEqual([x[1] for x in r['ir'] if x[0]=='xo'],[10,10])
 def test_r0_addic_not_implicit_zero_and_unsupported_fails(self):
  self.assertEqual(m.decode(0x30000001),['addic',0,0,1])
  self.assertEqual(m.decode(0xf821ff91),['stdu',1,1,-112])
  for word in (0x4e800421,0x44000002,0x7c000000):
   with self.assertRaises(ValueError):m.decode(word)
  with tempfile.TemporaryDirectory() as d:
   code='\n'.join(x.read_text() for x in m.emit_sources([{'pc':0x00010000,'count':2,'ir':[['addic',3,0,1],['blr']]}],Path(d)))
   self.assertIn('c->gpr[0]',code)
 def test_emits_17_compile_units_with_full_elf_authentication(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);generated=m.emit_sources(self.snap['accepted'],p);ins=m.emit_installer(self.snap['accepted'],p)
   self.assertEqual(len(generated),17)
   self.assertIn('ar_m763_native_002c53bc', '\n'.join(f.read_text() for f in generated))
   source=ins.read_text()
   self.assertIn('CC_SHA256',source)
   self.assertIn('ar_m712_exec_window',source)
   self.assertIn('ar_read32',source)
   self.assertIn('ar_m763_register_discovered',source)
 def test_static_ios_compile_integration(self):
  build=(ROOT/'tools/build_ios_probe_ipa.sh').read_text()
  live=(ROOT/'ios/ARLivePPUBridge.c').read_text()
  self.assertIn('m763_semantic_snapshot.gz.b64',build)
  self.assertIn('m763-final-attestation.json',build)
  self.assertIn('ar_m763_register_discovered(d,len)',live)
if __name__=='__main__':unittest.main()