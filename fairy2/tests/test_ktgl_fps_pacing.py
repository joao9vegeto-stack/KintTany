import sys,struct,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ktgl_native_fps import DRS_SITES,DRS_SLOT,DRS_SEED,drs_patch,verify_drs,display_profile

class Pacing(unittest.TestCase):
    def setUp(self):
        self.x0=0x2b00000
        self.end=0x2c60000
        self.raw=bytearray(self.end)
        for at,a,b,_ in DRS_SITES:
            struct.pack_into("<II",self.raw,at,a,b)
    def test_exact_readers_and_data(self):
        patched,p=drs_patch(self.raw,self.x0,self.end)
        verify_drs(patched,self.x0,self.end)
        self.assertEqual(patched[DRS_SLOT:DRS_SLOT+8],DRS_SEED)
        self.assertEqual(len(p["sites"]),2)
        self.assertEqual(patched[self.x0:DRS_SLOT],self.raw[self.x0:DRS_SLOT])
        self.assertEqual(patched[DRS_SLOT+8:],self.raw[DRS_SLOT+8:])
    def test_refuse_wrong_instructions(self):
        self.raw[DRS_SITES[0][0]]=0
        with self.assertRaises(ValueError):drs_patch(self.raw,self.x0,self.end)
    def test_refuse_occupied_slot(self):
        self.raw[DRS_SLOT]=1
        with self.assertRaises(ValueError):drs_patch(self.raw,self.x0,self.end)
    def test_profile_both_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"profile.tsv"
            for canonical in (True,False):
                p.write_text("mem_reserve\t0x180000000\npresent_interval\tgame\n")
                display_profile(p,canonical,lambda path,c:None)
                self.assertEqual(p.read_text().count("present_interval\t"),1)
                self.assertIn("present_interval\tdisplay",p.read_text())
if __name__=="__main__":unittest.main()
