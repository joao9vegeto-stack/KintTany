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
        result=m.sample(R(),"file",h)
        self.assertTrue(result["is_g1s"])
        self.assertEqual(result["status"],"zlib_ok")
        self.assertEqual(result["decoded_length"],len(raw))
        self.assertEqual(result["chunks"],1)
    def test_zlib_terminal_zero_detects_short_resource(self):
        first=b"_S2G5000"+bytes(16376)
        a=zlib.compress(first)
        packed=struct.pack("<HQ",len(a),0)+a+bytes(2)
        class R:
            def at(self,p,off,n):return packed[off:off+n]
        row={"data":0,"stored":len(packed),"flags":0x400000,"plain":18340}
        got=m.sample(R(),"file",row)
        self.assertEqual(got["status"],"plain_size_mismatch")
        self.assertEqual(got["decoded_length"],16384)
        self.assertEqual(got["complete_input_bytes"],len(packed))

    def test_zlib_two_chunks_complete(self):
        first=b"_S2G5000"+bytes(16376)
        second=b"tail"+bytes(1952)
        a=zlib.compress(first);b=zlib.compress(second)
        packed=struct.pack("<HQ",len(a),0)+a+struct.pack("<HQ",len(b),0)+b
        class R:
            def at(self,p,off,n):return packed[off:off+n]
        row={"data":0,"stored":len(packed),"flags":0x400000,"plain":len(first)+len(second)}
        result=m.sample(R(),"file",row)
        self.assertEqual(result["status"],"zlib_ok")
        self.assertEqual(result["chunks"],2)
        self.assertEqual(result["decoded_length"],18340)
if __name__=="__main__":unittest.main()
