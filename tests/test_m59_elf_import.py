"""M5.9: app imports privately via Files, no user executable in CI."""
from pathlib import Path
import unittest
root=Path(__file__).resolve().parents[1]
app=(root/"ios/ARProbeApp.m").read_text()
build=(root/"tools/build_ios_probe_ipa.sh").read_text()
work=(root/".github/workflows/ascension-recomp-m0.yml").read_text()
code=(root/"ios/ARPrivateELFProbe.c").read_text()
class M59(unittest.TestCase):
 def test_guards(self):
  for x in ("UIDocumentPickerDelegate","didPickDocumentsAtURLs:",
            "CC_SHA256(","ar_private_elf_inspect(","testM58AlphaTest:"):
   self.assertIn(x,app)
  for x in ("ARPrivateELFProbe.o","0.6.7-unsigned.ipa"):
   self.assertIn(x,build)
  for x in ("host_m59_elf.c","m59-host.log"):
   self.assertIn(x,work)
  for x in ("within(offset,","within(seg.offset,seg.size,len)","lookup("):
   self.assertIn(x,code)
  self.assertNotIn("GOWA.SELF",build)
  self.assertNotIn(".rap",build)
if __name__=="__main__":unittest.main()
