import json
import tempfile
import unittest
from pathlib import Path
from audit_runtime_readiness import has_cpu_runtime, read_json


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


class RuntimeDetectionTests(unittest.TestCase):
    def test_guest_memory_and_elf_loader_are_not_cpu_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "SpartanIOSGuestMemory.c").write_text("vm_allocate();")
            (root / "SpartanIOSGuestELFLoader.c").write_text("spartan_guest_elf_load();")
            self.assertFalse(has_cpu_runtime(root))

    def test_dispatcher_marker_counts_as_cpu_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "SpartanIOSPS4CPU.c").write_text("void spartan_ps4_cpu_dispatch(void) {}")
            self.assertTrue(has_cpu_runtime(root))


if __name__ == "__main__":
    unittest.main()
