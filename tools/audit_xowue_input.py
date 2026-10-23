#!/usr/bin/env python3
"""Read-only XOWUE input inventory. Never copies game bytes."""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

EXECUTION_INFO = 0x00040006


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_xex(path):
    data = path.read_bytes()
    if len(data) < 24 or data[:4] != b"XEX2":
        raise ValueError("Expected a valid XEX2 header")
    module_flags, pe_offset, reserved, security_offset, header_count = struct.unpack_from(">IIIII", data, 4)
    table_end = 24 + header_count * 8
    if table_end > len(data):
        raise ValueError("Optional-header table exceeds file size")
    exec_offset = None
    entries = []
    for index in range(header_count):
        key, value = struct.unpack_from(">II", data, 24 + index * 8)
        entries.append({"key": f"0x{key:08X}", "value": f"0x{value:08X}"})
        if key == EXECUTION_INFO:
            exec_offset = value
    result = {
        "size_bytes": len(data),
        "sha256": sha256_file(path),
        "magic": "XEX2",
        "module_flags": f"0x{module_flags:08X}",
        "pe_offset": f"0x{pe_offset:08X}",
        "reserved": f"0x{reserved:08X}",
        "security_info_offset": f"0x{security_offset:08X}",
        "header_count": header_count,
        "optional_headers": entries,
    }
    if exec_offset is None:
        result["execution_info"] = None
        return result
    if exec_offset + 24 > len(data):
        raise ValueError("Execution Info points outside the file")
    media_id, version, base_version, title_id = struct.unpack_from(">IIII", data, exec_offset)
    platform, executable_table, disc_number, disc_count = struct.unpack_from(">4B", data, exec_offset + 16)
    savegame_id = struct.unpack_from(">I", data, exec_offset + 20)[0]
    result["execution_info"] = {
        "media_id": f"{media_id:08X}",
        "version_raw": f"0x{version:08X}",
        "base_version_raw": f"0x{base_version:08X}",
        "title_id": f"{title_id:08X}",
        "platform": platform,
        "executable_table": executable_table,
        "disc_number": disc_number,
        "disc_count": disc_count,
        "savegame_id": f"{savegame_id:08X}",
    }
    return result


def inventory_tree(root):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("--game-root must be a directory")
    files = []
    directories = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(d for d in dirnames if not (current_path / d).is_symlink())
        rel_dir = current_path.relative_to(root).as_posix()
        if rel_dir != ".":
            directories.append(rel_dir)
        for filename in sorted(filenames):
            path = current_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            files.append({
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
            })
    files.sort(key=lambda item: item["path"].casefold())
    return {
        "file_count": len(files),
        "directory_count": len(directories),
        "total_file_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "directories": sorted(directories, key=str.casefold),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xex", type=Path, help="Path to the user's default.xex")
    parser.add_argument("--game-root", type=Path, help="Optional root of the extracted game folder")
    parser.add_argument("--output", type=Path, help="Write JSON locally; defaults to stdout")
    args = parser.parse_args()
    report = {
        "project": "XOWUE",
        "xex_path_basename": args.xex.name,
        "xex": parse_xex(args.xex),
        "game_root_inventory": inventory_tree(args.game_root) if args.game_root else None,
        "policy": "Metadata only. This tool does not copy, upload, transform, or embed game files.",
    }
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"Wrote metadata report: {args.output}")
    else:
        sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
