#!/usr/bin/env python3
"""Lower XEX-validated PPC local computed jumps to native C++ gotos.

No new AOT entry, interpreter, JIT, NOP or guessed PPC semantics is added.
The immutable archived AOT source and the original XEX rdata tables were
cross-checked at the exact guest virtual PCs. Fail closed on source changes.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import struct
import bisect
from pathlib import Path
import re

# Table values extracted in big-endian order from the user's XEX image.
# .rdata PointerToRawData equals RVA. .text's raw offset differs from its
# guest RVA by 0x9200; never use raw PE offsets as PPC virtual PCs.
# Verified original XEX .rdata at 0x820360C0 (426 big-endian uint16).
_COMPUTED_426_BE_B64 = (
    "AAAACAAUACAALAA0AEAATABYAGQAcAB8AIgAlACgAKwAuADEAMwA1ADgAOwA+AEEARABHAEkATABPAFIAVQB"
    "XAFkAXABfAGIAZABmAGgAagBsAG4AcAByAHQAdgB5AHwAfwCCAIQAhgCIAIsAjgCRAJQAlwCaAJ0AoACjAKY"
    "AqQCsAK8AsgC1ALgAuwC+AMEAxADGAMkAzADPANIA1ADWANgA2gDcAN4A4ADiAOQA5gDpAOsA7gDwAPIA9AD"
    "2APgA+gD8AP4BAQEEAQcBCgENARABEgEUARYBGAEaARwBHgEgASIBJAEmASgBKgEtAS8BMQEzATYBOQE8AT8"
    "BQgFEAUYBSQFMAU8BUgFVAVgBWgFdAWABYwFmAWgBawFuAXEBdAF3AXoBfAF/AYIBhQGIAYsBjgGRAZQBlwG"
    "aAZ0BnwGiAaQBpwGqAawBrwGyAbUBuAG7Ab4BwQHEAcYByQHMAc8B0gHVAdgB2wHeAeEB5AHnAekB7AHvAfI"
    "B9QH4AfsB/gIBAgQCBgIIAgsCDgIRAhQCFwIaAh0CIAIjAiUCJwIpAisCLQIvAjECMwI1AjcCOQI7Aj0CQAJ"
    "DAkYCSQJMAk4CUAJTAlYCWQJcAl8CYQJjAmYCaQJsAm8CcQJ0AnYCeAJ7An4CgQKEAocCigKNAo8CkQKTApU"
    "CmAKbAp4CoQKkAqcCqgKtArACsgK0ArcCugK8Ar8CwQLEAscCygLMAs8C0gLVAtcC2QLbAt4C4QLkAucC6gL"
    "tAvAC8wL2AvkC/AL/AwIDBQMIAwsDDgMRAxQDFgMZAxwDHwMiAyUDJwMpAywDLwMxAzQDNgM5AzsDPQNAA0M"
    "DRgNJA0sDTgNRA1QDVwNaA10DYANjA2YDaQNsA28DcgN1A3gDewN+A4EDhAOHA4oDjQOQA5MDlgOZA5wDnwO"
    "iA6UDqAOrA64DsQO0A7cDugO9A8ADwwPGA8kDzAPPA9ID1QPYA9sD3gPhA+QD5wPqA+0D8APzA/YD+QP8A/8"
    "EAgQFBAgECwQOBBEEFAQXBBoEHQQgBCMEJgQpBCwELwQyBDUEOAQ6BD0EQARDBEYESQRMBE8EUgRVBFgEWwR"
    "dBGAEYwRlBGcEaQRrBG0EbwRxBHQEdwR5BHsEfQR/BIE"
)
_COMPUTED_426_BE = base64.b64decode(_COMPUTED_426_BE_B64)
assert len(_COMPUTED_426_BE) == 852
assert hashlib.sha256(_COMPUTED_426_BE).hexdigest() == "383c790a80fffe10c8cf9feea05c2a35b487bccea125f006c6506d9b44cc0d90"
_COMPUTED_426 = struct.unpack(">426H", _COMPUTED_426_BE)
assert len({0x82D3440C + v for v in _COMPUTED_426}) == 426
assert 0x82D355F8 in {0x82D3440C + v for v in _COMPUTED_426}

TABLES = (
    # (guest owner, BCTR PC, table guest address, base guest PC, stride, values)
    (0x82B47360, 0x82B47450, 0x82086360, 0x82B47454, 4,
     (1, 0, 1, 100, 55, 55, 159, 168, 192, 192, 1, 192, 100, 192, 185, 188)),
    (0x82D2D0A8, 0x82D2D118, 0x82035D30, 0x82D2D0BC, 1,
     (96, 104, 536, 544, 552, 560, 568, 576, 584, 592, 9904, 0, 0, 32)),
    (0x82D2D0A8, 0x82D2D35C, 0x82035CC0, 0x82D2D360, 1,
     (272, 1136, 1660, 1568, 1568, 2388, 1568, 1568, 1568, 1568,
      3108, 1568, 3536, 1568, 4264, 1568, 4660, 5984, 7524, 1568,
      8856, 1568, 1568, 1568, 1568, 1568, 1568, 1568, 1568, 1568,
      1568, 0, 144, 400, 1200, 1788, 2028, 2336, 2464, 2528,
      1568, 1568, 2848, 3172, 3288, 3600, 3716, 1568, 4412, 4788,
      6160, 8080, 8444, 8940)),
    # XEX guest .rdata 0x820360C0; 426 targets in native sub_82D34268.
    (0x82D34268, 0x82D34408, 0x820360C0, 0x82D3440C, 1, _COMPUTED_426),
)
FUNC_RE = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\) \{\n')
INSN = re.compile(r'(?m)^\t// (.+?)\s*$')
LOC = re.compile(r'(?m)^loc_([0-9A-Fa-f]+):\s*$')
INDIRECT = '\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n\treturn;'


def patch_owner(source: str, owner: int, specs: list[tuple]) -> tuple[str,int]:
    label = f'sub_{owner:X}'
    entries = [m for m in FUNC_RE.finditer(source) if m[1].upper() == label.upper()]
    if len(entries) != 1:
        raise ValueError(f'{label}: expected exactly one native owner, found {len(entries)}')
    m = entries[0]
    end = source.find('\n}\n', m.end())
    if end < 0:
        raise ValueError(f'{label}: unterminated AOT function')
    body = source[m.start():end+3]
    asm = list(INSN.finditer(body))
    starts = [ins.start() for ins in asm]
    if len(asm) < 50:
        raise ValueError(f'{label}: unexpectedly short generated function')

    # Validate that source comment ordering exactly represents the guest PC.
    # This was checked against 18/398 existing branch labels in the owner's
    # original generated C++, not inferred from matching opcodes elsewhere.
    for loc in LOC.finditer(body):
        pc = int(loc[1], 16)
        idx = bisect.bisect_left(starts, loc.end())
        if pc < owner or (pc-owner)%4 or idx != (pc-owner)//4:
            raise ValueError(f'{label}: label 0x{pc:08X} does not match source PC index')

    replacements: list[tuple[int,int,str]] = []
    destinations: set[int] = set()
    existing = {int(loc[1],16) for loc in LOC.finditer(body)}
    for func, bctr, table, base, stride, offsets in specs:
        if func != owner or bctr < owner or (bctr-owner)%4:
            raise ValueError(f'{label}: invalid manifest function/PC')
        idx = (bctr-owner)//4
        if idx >= len(asm) or asm[idx][1].strip() != 'bctr':
            raise ValueError(f'{label}: expected real bctr at 0x{bctr:08X}')
        start = asm[idx].end()
        stop = asm[idx+1].start() if idx+1 < len(asm) else len(body)
        between = body[start:stop]
        if between.count(INDIRECT) != 1:
            raise ValueError(f'{label}: indirect dispatch body changed at 0x{bctr:08X}')
        targets = tuple(base + stride*item for item in offsets)
        if any(pc < owner or (pc-owner)%4 or (pc-owner)//4 >= len(asm) for pc in targets):
            raise ValueError(f'{label}: table 0x{table:08X} points outside native function')
        destinations.update(targets)
        lines = ['\tswitch (ctx.ctr.u32) {']
        for addr in sorted(set(targets)):
            lines.append(f'\tcase 0x{addr:08X}u: goto loc_{addr:08X};')
        lines += ['\tdefault: __builtin_trap();', '\t}']
        replacements.append((start,stop,between.replace(INDIRECT,'\n'.join(lines))))
        print(f'AOT_LOCAL_SWITCH owner={label} bctr=0x{bctr:08X} table=0x{table:08X} entries={len(targets)} unique={len(set(targets))}')

    for addr in destinations-existing:
        i=(addr-owner)//4
        replacements.append((asm[i].start(),asm[i].start(),f'loc_{addr:08X}:\n'))
    # All edits apply to the unmodified source offsets, from bottom to top.
    result=body
    for a,b,value in sorted(replacements,key=lambda v:(v[0],v[1]),reverse=True):
        result=result[:a]+value+result[b:]
    for bctr in [t[1] for t in specs]:
        if f'case 0x{bctr:08X}u:' in result:
            raise ValueError('computed branch dispatch unexpectedly branches to itself')
    for addr in destinations:
        if result.count(f'loc_{addr:08X}:') != 1:
            raise ValueError(f'{label}: missing or duplicated label 0x{addr:08X}')
    if INDIRECT in result:
        raise ValueError(f'{label}: unhandled indirect dispatch remains')
    return source[:m.start()]+result+source[end+3:],len(destinations)


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--ppc-dir',type=Path,required=True)
    args=ap.parse_args()
    sources=sorted(args.ppc_dir.glob('ppc_recomp.*.cpp'))
    if len(sources)!=344:
        raise SystemExit('Unexpected AOT unit count')
    by_owner:dict[int,Path]={}
    needed={t[0] for t in TABLES}
    for path in sources:
        src=path.read_text()
        for m in FUNC_RE.finditer(src):
            pc=int(m[1][4:],16)
            if pc in needed:
                if pc in by_owner:raise SystemExit('Duplicate AOT owner')
                by_owner[pc]=path
    if set(by_owner)!=needed:raise SystemExit(f'Missing native AOT owners: {needed-set(by_owner)}')
    for owner,path in by_owner.items():
        original=path.read_text()
        updated,unique=patch_owner(original,owner,[t for t in TABLES if t[0]==owner])
        path.write_text(updated)
        print(f'PASS native-switch owner=0x{owner:08X} labels={unique} source={path.name}')

if __name__=='__main__':
    main()
