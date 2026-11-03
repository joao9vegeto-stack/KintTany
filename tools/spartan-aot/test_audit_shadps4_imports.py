import json
import subprocess
import tempfile
from pathlib import Path

script = Path(__file__).with_name("audit_shadps4_imports.py")
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / "src/core/libraries"
    source.mkdir(parents=True)
    (source / "kernel.cpp").write_text(
        'LIB_FUNCTION("abc123", "libkernel", 1, "libkernel", sceKernelExample);\n'
        'LIB_FUNCTION("def456", "libScePad", 1, "libScePad", scePadExample);\n'
    )
    linked = root / "link.json"
    linked.write_text(json.dumps({"unresolved_imports": [
        "abc123#libkernel", "missing#libkernel", "def456#libScePad"
    ]}))
    output = root / "report.json"
    subprocess.run([
        "python3", str(script), "--linked", str(linked), "--source", str(source),
        "--out", str(output), "--commit", "test-pin"
    ], check=True, capture_output=True, text=True)
    report = json.loads(output.read_text())
    assert report["unique_unresolved_imports"] == 3
    assert report["matched_imports"] == 2
    assert report["unmatched_imports"] == 1
    assert any(c["function"] == "sceKernelExample" for m in report["matches"] for c in m["candidates"])
print("PASS: PS4 import NID registry cross-reference")
