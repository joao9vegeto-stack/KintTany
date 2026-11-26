import importlib.util, pathlib, tempfile, unittest, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("translation",ROOT/"colab/translation.py")
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
class TranslationTests(unittest.TestCase):
    def test_asia_path_rebased(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"mod.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("atmosphere/contents/0100B8E016F76000/romfs/data014.cpk",b"translated")
            with zipfile.ZipFile(path) as z:
                files,title=mod.mod_files(z)
                self.assertEqual(title,mod.ASIA)
                self.assertEqual(list(files),["data014.cpk"])
    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"mod.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("0100B8E016F76000/romfs/../evil",b"x")
            with zipfile.ZipFile(path) as z:
                with self.assertRaises(ValueError): mod.mod_files(z)
