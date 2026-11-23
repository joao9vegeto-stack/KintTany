#!/usr/bin/env python3
"""No proprietary data: unit tests of exact unchanged ARM64 embedded-game sections."""
from __future__ import annotations
import importlib.util,struct,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("hooklink_relink", ROOT/"scripts/hooklink2ios_native_relink.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fake_macho(path,alter=None):
    names=[]
    for mod in ("main","subsdk0","sdk"):
        names.extend([("__TEXT",f"__dm{mod}x0"),(f"__DM{mod}W","__img"),("__TEXT",f"__dm{mod}x1")])
    n=len(names);size=72+80
    head=32+n*size
    out=bytearray(head+n*0x4000)
    struct.pack_into("<IiiIIIII",out,0,0xfeedfacf,0x0100000c,0,2,n,n*size,0,0)
    for i,(seg,name) in enumerate(names):
        p=32+i*size
        struct.pack_into("<II16sQQQQiiII",out,p,0x19,size,seg.encode(),0,0,0,0,7,3,1,0)
        off=head+i*0x4000
        struct.pack_into("<16s16sQQIIIIIIII",out,p+72,name.encode(),seg.encode(),
                         0,0x4000,off,14,0,0,0,0,0,0)
        out[off:off+0x4000]=bytes([65+i])*0x4000
    if alter is not None: out[head+alter*0x4000]=0
    path.write_bytes(out)

class NativeGuestSectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old=Path(self.temp.name)/"old"
        self.new=Path(self.temp.name)/"new"
        fake_macho(self.old)
        fake_macho(self.new)
    def test_identical_embedded_modules(self):
        result=m.assert_guest_pages_identical(self.old,self.new)
        self.assertEqual(len(result),9)
        self.assertTrue(all(row["bytes"]==0x4000 for row in result.values()))
    def test_changed_guest_code_halts_relink(self):
        fake_macho(self.new,alter=1)
        with self.assertRaisesRegex(RuntimeError,"original guest ARM64 code/data changed"):
            m.assert_guest_pages_identical(self.old,self.new)
    def test_thin_arm64_macho_required(self):
        data=bytearray(self.new.read_bytes())
        struct.pack_into("<I",data,0,0xcafebabe)
        self.new.write_bytes(data)
        with self.assertRaisesRegex(RuntimeError,"not thin arm64"):
            m.sections_macho(self.new)

if __name__=="__main__":unittest.main()
