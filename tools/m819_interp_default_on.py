#!/usr/bin/env python3
"""M8.19: SPU interpreter fallback and PIC capture ON by default.

iOS apps never inherit shell environment variables, so the M7.95 fallback
guarded by getenv("SPU_INTERP_UNLIFTED") and getenv("SPU_PIC_CAPTURE")
never executed on the device. Every build since M7.95 ran with zero SPU
instructions executed (PIC hits=0, PM calls=0, draws=0).
Opt-out for diagnostics: ASCENSION_SPU_INTERP_OFF.
"""
from pathlib import Path
import argparse

MARK = "ASCENSION_M819_INTERP_DEFAULT_ON_V1"


def patch(root: Path) -> None:
    p = root / "runtime/spu/spu_channels.c"
    s = p.read_text()
    if MARK in s:
        print("[PASS] M8.19 already applied")
        return

    old_interp = 'const char* e = getenv("SPU_INTERP_UNLIFTED");'
    if s.count(old_interp) < 1:
        raise SystemExit("M8.19: SPU_INTERP_UNLIFTED getenv anchor missing (M7.95 not applied?)")
    s = s.replace(
        old_interp,
        old_interp + ' /* ' + MARK + ' */\n'
        '            if (!e && !getenv("ASCENSION_SPU_INTERP_OFF")) e = "1";')

    old_pic = 'const char* path = getenv("SPU_PIC_CAPTURE");'
    n = s.count(old_pic)
    if n != 1:
        raise SystemExit(f"M8.19: SPU_PIC_CAPTURE anchor count={n}")
    s = s.replace(
        old_pic,
        old_pic + ' /* ' + MARK + ' */\n'
        '    static char s_asc_pic_default[1024];\n'
        '    if (!path && !getenv("ASCENSION_SPU_INTERP_OFF")) {\n'
        '        const char* home = getenv("HOME");\n'
        '        if (home && !s_asc_pic_default[0])\n'
        '            snprintf(s_asc_pic_default, sizeof s_asc_pic_default,\n'
        '                     "%s/Documents/spu_pic_capture.txt", home);\n'
        '        if (s_asc_pic_default[0]) path = s_asc_pic_default;\n'
        '    }', 1)

    if "#include <stdio.h>" not in s:
        s = "#include <stdio.h>\n" + s
    p.write_text(s)
    print("[PASS] M8.19 SPU interpreter fallback and PIC capture default ON")


def verify(root: Path) -> None:
    s = (root / "runtime/spu/spu_channels.c").read_text()
    for req in (MARK, 'e = "1"', "spu_pic_capture.txt", "ASCENSION_SPU_INTERP_OFF"):
        if req not in s:
            raise SystemExit(f"M8.19 verify failed: {req}")
    print("[PASS] M8.19 verified")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--upstream", type=Path, required=True)
    a.add_argument("--verify", action="store_true")
    args = a.parse_args()
    (verify if args.verify else patch)(args.upstream)
