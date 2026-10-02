#!/usr/bin/env python3
from pathlib import Path
import hashlib
import struct
import sys

if len(sys.argv) != 4:
    raise SystemExit("usage: patch-d3d9-msl32.py <d3d9-emulated.dll> <new.metallib> <report>")

target = Path(sys.argv[1])
new_path = Path(sys.argv[2])
report = Path(sys.argv[3])

new = new_path.read_bytes()
if new[:4] != b"MTLB" or len(new) < 32:
    raise SystemExit("replacement metallib invalid")
if struct.unpack_from("<Q", new, 16)[0] != len(new):
    raise SystemExit("replacement metallib header length mismatch")

data = bytearray(target.read_bytes())
markers = (
    b"clear_texture_1d_uint",
    b"fs_blit_quad",
    b"vs_present_quad",
    b"cs_clear_buffer_uint",
)
candidates = []
pos = 0
while True:
    p = data.find(b"MTLB", pos)
    if p < 0:
        break
    if p + 24 <= len(data):
        size = struct.unpack_from("<Q", data, p + 16)[0]
        if 128 <= size <= 16 * 1024 * 1024 and p + size <= len(data):
            blob = data[p:p + size]
            score = sum(m in blob for m in markers)
            if score:
                candidates.append((score, p, size))
    pos = p + 4

exact = [x for x in candidates if x[0] == 4]
if len(exact) != 1:
    raise SystemExit(f"expected exactly one DXMT command metallib, got {exact}")

_, blob_off, old_len = exact[0]
if len(new) > old_len:
    raise SystemExit(f"replacement {len(new)} > embedded {old_len}")

needle = struct.pack("<I", old_len)
hits = []
pos = 0
while True:
    p = data.find(needle, pos)
    if p < 0:
        break
    if not (blob_off <= p < blob_off + old_len):
        hits.append(p)
    pos = p + 1
if not hits:
    raise SystemExit("dxmt_command_len not found")
hits.sort(key=lambda p: abs(p - (blob_off + old_len)))
len_off = hits[0]

before = hashlib.sha256(data).hexdigest()
old_blob = hashlib.sha256(data[blob_off:blob_off + old_len]).hexdigest()
new_sha = hashlib.sha256(new).hexdigest()

data[blob_off:blob_off + len(new)] = new
if len(new) < old_len:
    data[blob_off + len(new):blob_off + old_len] = b"\0" * (old_len - len(new))
struct.pack_into("<I", data, len_off, len(new))
target.write_bytes(data)

check = target.read_bytes()
if check[blob_off:blob_off + 4] != b"MTLB":
    raise SystemExit("MTLB magic mismatch after patch")
if struct.unpack_from("<Q", check, blob_off + 16)[0] != len(new):
    raise SystemExit("embedded MTLB length mismatch")
if struct.unpack_from("<I", check, len_off)[0] != len(new):
    raise SystemExit("dxmt_command_len mismatch")
if hashlib.sha256(check[blob_off:blob_off + len(new)]).hexdigest() != new_sha:
    raise SystemExit("replacement metallib hash mismatch")

after = hashlib.sha256(check).hexdigest()
report.write_text(
    "D3D9 MSL32 preservation patch\n"
    f"target={target}\n"
    f"blob_offset=0x{blob_off:x}\n"
    f"old_len={old_len}\n"
    f"new_len={len(new)}\n"
    f"old_metallib_sha256={old_blob}\n"
    f"new_metallib_sha256={new_sha}\n"
    f"d3d9_before_sha256={before}\n"
    f"d3d9_after_sha256={after}\n"
    "compiler=iphoneos Metal 3.2 iOS 18.0\n"
)
print(report.read_text(), end="")
