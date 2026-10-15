#!/usr/bin/env python3
"""Compare PS3 firmware imports against upstream HLE registration inventory.

Registered DOES NOT mean semantically implemented. Fail closed on missing or
conflicting handler registries, instead of silently returning fake CELL_OK.
No commercial binaries or licenses are ever required for CI.
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter
from pathlib import Path
REGISTRATION=re.compile(r'ps3_hle_register\s*\(\s*0x([0-9a-fA-F]{1,8})u\s*,\s*"([^"]+)"')

def handlers_from_source(source: str) -> dict[int,str]:
    found={}
    for raw,name in REGISTRATION.findall(source):
        nid=int(raw,16)
        if nid in found and found[nid]!=name:
            raise ValueError(f'NID 0x{nid:08x} bound to both {found[nid]} and {name}')
        found[nid]=name
    if not found:raise ValueError('no handler registrations found; fail closed')
    return found

def audit(imports: list[dict],handlers: dict[int,str]) -> dict:
    seen=set();matched=[];missing=[];duplicates=[]
    for entry in imports:
        try:
            nid=int(str(entry['nid']),0)
            lib=str(entry['library'])
        except (KeyError,ValueError,TypeError) as exc:
            raise ValueError('malformed firmware import') from exc
        if nid<0 or nid>0xffffffff or not lib:raise ValueError('invalid NID or library')
        if nid in seen:
            duplicates.append({'nid':f'0x{nid:08x}','library':lib})
            continue
        seen.add(nid)
        row={'nid':f'0x{nid:08x}','library':lib}
        if nid in handlers:
            row['registered_handler']=handlers[nid]
            matched.append(row)
        else:missing.append(row)
    libs=Counter(e['library'] for e in imports)
    misses=Counter(e['library'] for e in missing)
    return {'schema':'ascension-recomp/hle-registration-audit-v1',
            'total_imports':len(imports),'unique_import_nids':len(seen),
            'registered_nids':len(matched),'not_registered_nids':len(missing),
            'libraries':dict(sorted(libs.items())),
            'missing_by_library':dict(sorted(misses.items())),
            'registered':matched,'unregistered':missing,
            'duplicate_imports':duplicates,
            'warning':'Registration is NOT proof a handler has correct semantics, SPURS behavior, or guest/host pointer translation.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registry-source',type=Path,required=True)
    ap.add_argument('--imports',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--dump-public-nids',action='store_true')
    args=ap.parse_args()
    handlers=handlers_from_source(args.registry_source.read_text())
    if args.imports:
        data=audit(json.loads(args.imports.read_text()),handlers)
    else:
        data={'schema':'ascension-recomp/public-upstream-hle-inventory-v1',
              'registered_count':len(handlers),
              'handlers':{f'0x{k:08x}':v for k,v in sorted(handlers.items())},
              'warning':'Registered only, NOT semantically verified'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print('Upstream HLE registrations:',len(handlers))
    if args.imports:
        print('Imports:',data['unique_import_nids'],'missing:',data['not_registered_nids'])
    if args.dump_public_nids:
        print('M24_REGISTERED_NIDS='+','.join(f'{n:08x}' for n in sorted(handlers)))
if __name__=='__main__':main()
