#!/usr/bin/env python3
"""Patch the pinned PS3Recomp runtime for Ascension's disc boot path."""
import argparse
import pathlib
import subprocess


PIN = "39a36296511c445707adabcd312f0b740cfbd694"
MARKER = "ASCENSION_IOS_CELL_GAME_PATCH_CHECK"
DECL = "s32 cellGamePatchCheck(void* size, void* reserved);"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    upstream = parser.parse_args().upstream.resolve()
    head = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != PIN:
        raise SystemExit(f"PS3Recomp pin mismatch: {head} != {PIN}")

    source_path = upstream / "libs/system/cellGame.c"
    header_path = upstream / "libs/system/cellGame.h"
    source = source_path.read_text()
    header = header_path.read_text()
    impl_anchor = "s32 cellGameGetLocalWebContentPath(char* path)\n{"
    header_anchor = "s32 cellGameGetSizeKB(s32* sizeKB);\n"

    if MARKER not in source:
        if source.count(impl_anchor) != 1:
            raise SystemExit("could not anchor the pinned cellGamePatchCheck implementation")
        implementation = (
            f"/* {MARKER}: a disc boot has no installed game patch. */\n"
            "s32 cellGamePatchCheck(void* size, void* reserved)\n"
            "{\n"
            "    (void)size;\n"
            "    (void)reserved;\n"
            "    return CELL_GAME_ERROR_NOTPATCH;\n"
            "}\n\n"
        )
        source = source.replace(impl_anchor, implementation + impl_anchor, 1)

    if DECL not in header:
        if header.count(header_anchor) != 1:
            raise SystemExit("could not anchor the pinned cellGamePatchCheck declaration")
        header = header.replace(header_anchor, header_anchor + DECL + "\n", 1)

    if MARKER not in source or DECL not in header:
        raise SystemExit("cellGamePatchCheck HLE patch did not apply completely")
    source_path.write_text(source)
    header_path.write_text(header)
    print("PS3Recomp cellGamePatchCheck: disc boot returns CELL_GAME_ERROR_NOTPATCH")


if __name__ == "__main__":
    main()
