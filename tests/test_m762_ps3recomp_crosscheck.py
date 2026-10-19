"""Cross-check upstream ps3recomp OPD/import data without exposing game bytes."""
import base64, gzip, hashlib, json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class M762CrossCheck(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads((ROOT/"runtime/m762-ps3recomp-crosscheck.json").read_text())
  raw=gzip.decompress(base64.b64decode((ROOT/"runtime/m762_semantic_snapshot.gz.b64").read_text().strip(),validate=True))
  cls.digest=hashlib.sha256(raw).hexdigest(); cls.ir=json.loads(raw)
 def test_authenticated_upstream_import_and_OPD_inventory(self):
  r=self.r
  self.assertEqual(r["schema"],"ascension-m762-ps3recomp-crosscheck-1")
  self.assertEqual(r["upstream_commit"],"39a36296511c445707adabcd312f0b740cfbd694")
  self.assertEqual(r["opd_descriptors"],7643)
  self.assertEqual(r["opd_unique_functions"],7643)
  self.assertEqual(len(r["files_verified_sha256"]),10)
  self.assertTrue(all(len(h)==64 for h in r["files_verified_sha256"].values()))
  self.assertFalse(r["source_ELF_in_package"])
  self.assertEqual(r["imports"],350)
  self.assertEqual(sum(r["import_libraries"].values()),350)
  self.assertEqual(len(r["import_libraries"]),25)
  self.assertEqual(r["import_libraries"]["sys_fs"],26)
  self.assertNotEqual(r["import_hle_execution"],"IMPLEMENTED")
 def test_upstream_opd_vs_cfg_provenance(self):
  r=self.r; entries=self.ir["accepted"]
  self.assertEqual(r["static_snapshot_sha256"],self.digest)
  self.assertEqual(len(entries),805)
  self.assertEqual(r["m762_accepted_from_upstream_opd"],sum(e["origin"]=="opd" for e in entries))
  self.assertEqual(r["m762_accepted_from_cfg_not_in_opd"],sum(e["origin"]=="direct_call_target" for e in entries))
  self.assertEqual((r["m762_accepted_from_upstream_opd"],r["m762_accepted_from_cfg_not_in_opd"]),(651,154))
  stop=next(e for e in entries if e["pc"]==0x002c53b0)
  self.assertEqual(stop["ir"],[["addis",3,0,1],["ori",3,3,32],["blr"]])
  self.assertTrue(r["same_guest_stop_in_ps3recomp_output"])
 def test_separate_lifter_output_from_iPhone_evidence(self):
  self.assertIn("NEVER",self.r["source_cpp_placeholders"])
  for key in ("compiled_apple_arm64","linked_macho","executed_on_iphone","guest_cellFsOpen_Read"):
   self.assertEqual(self.r[key],"NOT_MEASURED")
if __name__=="__main__": unittest.main()
