#!/usr/bin/env python3
"""Build 18: implement only proven Xbox video I/O instruction sites and WBINVD.
All remaining RECOMP_UNIMPL paths still trap; fail if pinned retail lift differs.
Run AFTER install_failclosed_guards.py on temporary Actions checkout.
"""
from pathlib import Path
import sys

SITES = {
    "out dx, al": ("00373580",),
    "in al, dx": ("0037246C","0037266D"),
    "wbinvd": ("00371224",),
}

def one(src, old, new, label):
    n=src.count(old)
    if n != 1: raise RuntimeError(f"{label}: expected one anchor, got {n}")
    return src.replace(old,new,1)

def main(root):
    gen=root/'source/xbox-retail/gen'
    d3d=gen/'xdk/d3d8/d3d8_0000.c'
    lifted=d3d.read_text()
    for opcode,vas in SITES.items():
        for va in vas:
            needle=f'RECOMP_UNIMPL("{opcode}", 0x{va}u)'
            if lifted.count(needle)!=1:
                raise RuntimeError(f'pinned retail opcode/VA mismatched: {needle}')
    header=gen/'recomp_types.h'
    h=header.read_text()
    old='#define RECOMP_UNIMPL(_text, _va) do { \\\n    recomp_unimpl((_text), (_va)); \\\n    __builtin_trap(); \\\n} while (0)'
    new='''/* B18 hardware-mapped x86 I/O, exact guest VAs from retail lift.
 * Unrelated/unknown opcodes continue to fail closed. */
void poptst_guest_out8(uint16_t port, uint8_t value, uint32_t va);
uint8_t poptst_guest_in8(uint16_t port, uint32_t va);
void poptst_guest_wbinvd(uint32_t va);
#define RECOMP_UNIMPL(_text, _va) do { \\
    switch ((uint32_t)(_va)) { \\
    case 0x00373580u: \\
        poptst_guest_out8((uint16_t)g_edx, (uint8_t)g_eax, (_va)); break; \\
    case 0x0037246Cu: case 0x0037266Du: \\
        g_eax = (g_eax & 0xFFFFFF00u) | (uint32_t)poptst_guest_in8((uint16_t)g_edx, (_va)); break; \\
    case 0x00371224u: \\
        poptst_guest_wbinvd((_va)); break; \\
    default: \\
        recomp_unimpl((_text), (_va)); \\
        __builtin_trap(); \\
    } \\
} while (0)'''
    h=one(h,old,new,'failclosed opcode dispatcher')
    header.write_text(h)
    # Unimplemented x86 operations must be visible in the app's persistent
    # trace rather than only stderr (LiveContainer often hides C stderr).
    f=root/'port/game/recomp_manual.c'
    s=f.read_text()
    old='    if (stop) abort();\n}\n'
    new='''    {
        extern void poptst_engine_trace(const char *);
        char msg[192];
        snprintf(msg,sizeof msg,"FATAL: unsupported Xbox x86 opcode VA=0x%08X text=%s",va,text);
        poptst_engine_trace(msg);
    }
    if (stop) abort();
}
'''
    s=one(s,old,new,'persistent unknown x86 opcode log')
    f.write_text(s)
    print('PASS B18: 4 verified D3D8 guest instruction addresses; all remaining sites trap')

if __name__ == '__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: patch_retail_io_ios.py <repop checkout>')
    main(Path(sys.argv[1]).resolve())
