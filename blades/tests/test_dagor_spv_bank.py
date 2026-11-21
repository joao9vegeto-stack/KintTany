"""Real Dagor SMOL-V → SPIR-V regression, executable on Linux or macOS."""
import base64,hashlib,json,shutil,subprocess,struct,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SMOLV=base64.b64decode("TE9NUwAAAQAHAAgACgAAAAAAAADYAAAAkQIB0RACR0xTTC5zdGQuNDUwAAAAAKAEAAHPDgQC7cKl8wYAoAICB5MCBKEEAgO1AgIgALcCAgUEPgIGBjkHAgbGBgMLAAQYDo0eiAY=")

class DagorSPVBankTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "requires host-portable Node.js decoder")
    def test_extract_one_actual_smol_v_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp); payload=SMOLV+bytes(32)
            archive=t/"test.shdump.bin"
            archive.write_bytes(zlib.compress(bytes(112)+struct.pack("<I",len(payload))+payload,9))
            p=subprocess.run(["node",str(ROOT/"scripts/dagor_spv_bank.js"),
                 "--dump",str(archive),"--output",str(t/"out"),"--all",
                 "--report",str(t/"report.json"),"--min-matches","1"],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+"\n"+p.stderr)
            report=json.loads((t/"report.json").read_text())
            self.assertEqual(report["decoded"],1)
            self.assertEqual(report["matched"],1)
            paths=list((t/"out").glob("*.spv"));self.assertEqual(len(paths),1)
            spv=paths[0].read_bytes()
            self.assertEqual(spv[:4],b"\x03\x02\x23\x07")
            self.assertEqual(len(spv),216)
            self.assertEqual(hashlib.sha256(spv).hexdigest()[:16],paths[0].stem)
    def test_requested_shaders_match_actual_log(self):
        lines=(ROOT/"shaders/iphone_missing_shaders.txt").read_text().splitlines()
        keys=[line for line in lines if line and not line.startswith("#")]
        self.assertEqual(len(keys),110)
        self.assertEqual(len(set(keys)),110)
        self.assertTrue(all(len(x)==16 and int(x,16)>=0 for x in keys))

if __name__=="__main__":unittest.main()