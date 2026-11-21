"""A shader dump is isolated by DMROMFS1 index, with no NSP extraction."""
import importlib.util
from pathlib import Path
import hashlib
import struct
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("extract_dagor_shdump",ROOT/"scripts/extract_dagor_shdump.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DagorDumpTests(unittest.TestCase):
    def test_indexed_file_only(self):
        data=b'VSPSdump' + b'\x00' * 112
        files=[b'',b'compiledShaders',b'gameSpirV.ps50.shdump.bin']
        pool=b''.join(files)
        body=module.HEAD.pack(b'DMROMFS1',module.HEAD.size+len(data),3*module.ENT.size+len(pool),3)+data
        index=b''.join([
            module.ENT.pack(1,1,0,0,0,0),
            module.ENT.pack(2,1,0,len(files[1]),0,0),
            module.ENT.pack(module.HEAD.size,len(data),len(files[1]),len(files[2]),1,0)
        ])+pool
        with tempfile.TemporaryDirectory() as t:
            image=Path(t)/"RomFS.img"; out=Path(t)/"shader.bin"
            image.write_bytes(body+index)
            report=module.extract(image,out)
            self.assertEqual(out.read_bytes(),data)
            self.assertEqual(report["sha256"],hashlib.sha256(data).hexdigest())
    def test_cannot_export_damage(self):
        with tempfile.TemporaryDirectory() as t:
            image=Path(t)/"RomFS.img"; image.write_bytes(b'WRONG')
            with self.assertRaises((ValueError,struct.error)): module.extract(image,Path(t)/"shader.bin")

if __name__=="__main__":unittest.main()
