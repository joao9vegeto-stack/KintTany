import json
import tempfile
import unittest
from pathlib import Path
from audit_runtime_readiness import read_json


class ReadJsonTests(unittest.TestCase):
    def test_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                read_json(Path(d) / "missing.json", "fixture")

    def test_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text(json.dumps([]))
            with self.assertRaises(SystemExit):
                read_json(p, "fixture")


if __name__ == "__main__":
    unittest.main()
