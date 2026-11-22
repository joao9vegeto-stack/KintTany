"""Probe read-only RDB payload regression tests."""
import importlib.util,pathlib,struct,unittest,zlib
file=pathlib.Path(__file__).resolve().parents[1]/"scripts/probe_resource_origin.py"
spec=importlib.util.spec_from_file_location("origin",file)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class OriginTest(unittest.TestCase):
    def test_pointer(self):
        b=b"\x01\x04"+struct.pack("<IIHB",128,137,0,0)
        self.assertEqual(m.pointer(b),{"offset":128,"size":137,"marker":0})
    def test_rdb(self):
        b=b"_DRK0000"+bytes(24)+struct.pack("<8sQQQIIII",b"IDRK0000",61,13,48,8,0xac9ed331,0x7bcd279f,0x20000)+b"\x01\x04"+struct.pack("<IIHB",128,137,0,0)+bytes(3)
        self.assertEqual(next(m.records(b))["file"],0xac9ed331)
    def test_zlib_g1s(self):
        raw=b"_S2G3000"+bytes(22)
        payload=zlib.compress(raw)
        b=struct.pack("<HQ",len(payload),0)+payload
        class R:
            def at(self,p,off,n):return b[off:off+n]
        h={"data":0,"stored":len(b),"flags":0x400000,"plain":len(raw)}
        self.assertTrue(m.sample(R(),"file",h)["is_g1s"])
if __name__=="__main__":unittest.main()
