"""M7.62 deterministic OPD + direct-call PPC static native batch gates.
Snapshot is generated OFFLINE from the canonical ELF; CI never has the ELF.
"""
import base64
import gzip
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import m762_pipeline as pipeline

SNAP_SHA="07b74c4557b4951c3c113c998dc5895932e28b33cf240fdc13f9315fe7d84eb3"

def snapshot():
    data=gzip.decompress(base64.b64decode(
        (ROOT/"runtime/m762_semantic_snapshot.gz.b64").read_text(),validate=True))
    if hashlib.sha256(data).hexdigest()!=SNAP_SHA:
        raise AssertionError("Untrusted offline semantic IR")
    return json.loads(data)

class M762Batch(unittest.TestCase):
    def test_snapshot_is_whole_elf_derived_not_manual_26_pcs(self):
        s=snapshot()
        self.assertEqual(s["source_sha256"],pipeline.ELF_SHA)
        self.assertEqual(s["schema"],"ascension-m762-aot-semantic-ir-1")
        self.assertEqual(len(s["accepted"]),805)
        self.assertEqual(sum(x["count"] for x in s["accepted"]),1171)
        self.assertEqual(len({x["pc"] for x in s["accepted"]}),805)
        self.assertTrue(any(x["origin"]=="direct_call_target" for x in s["accepted"]))
        self.assertTrue(any(x["origin"]=="opd" for x in s["accepted"]))
    def test_real_guest_stop_is_found_by_cfg_without_manual_override(self):
        found={x["pc"]:x for x in snapshot()["accepted"]}
        f=found[0x002c53b0]
        self.assertEqual(f["ir"],[["addis",3,0,1],["ori",3,3,0x20],["blr"]])
        self.assertEqual(f["origin"],"direct_call_target")
        self.assertEqual(f["sha256"],
           "8091ef1c555afb47e2b8f3acf183b659a1e65981893e4099db227df54bdf2475")
    def test_reject_unknown_semantics_and_indirect_dynamic(self):
        self.assertEqual(pipeline.decode(0x3c600001),["addis",3,0,1])
        self.assertEqual(pipeline.decode(0x60630020),["ori",3,3,0x20])
        self.assertEqual(pipeline.decode(0x4e800020),["blr"])
        for w in (0x7C000000,0x4E800421,0x44000002):
            with self.assertRaises(ValueError):pipeline.decode(w)
    def test_generated_c_is_linkable_native_not_embedded_guest_opcodes(self):
        s=snapshot()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            sources=pipeline.emit_sources(s["accepted"],p)
            pipeline.emit_installer(s["accepted"],p)
            self.assertEqual(len(sources),7)
            stop=(p/"ppu_m762_01.c").read_text()
            all_source="".join(x.read_text() for x in p.glob("*.c"))
            self.assertIn("int ar_m762_native_002c53b0",all_source)
            self.assertIn("c->gpr[3]",all_source)
            self.assertIn("ar_vm_read_bytes",all_source)
            self.assertIn("CC_SHA256",all_source)
            self.assertNotIn("0x3c600001",all_source.lower())
            self.assertNotIn("0x60630020",all_source.lower())
    def test_apple_build_and_runtime_use_exact_same_snapshot(self):
        build=(ROOT/"tools/build_ios_probe_ipa.sh").read_text()
        runtime=(ROOT/"ios/ARLivePPUBridge.c").read_text()
        bridge=(ROOT/"runtime/ppu_bridge.c").read_text()
        self.assertIn("m762_semantic_snapshot.gz.b64",build)
        self.assertIn("m762-final-attestation.json",build)
        self.assertIn("ar_m762_register_discovered(d,len)",runtime)
        self.assertIn("#define MAX_FUNCS 65535",bridge)
        self.assertNotIn("ar_ppc_fallback_step",pipeline.emit_sources.__code__.co_names)
if __name__=="__main__":
    unittest.main()
