#!/usr/bin/env python3
"""Repair *structurally resolvable* mid-function stubs in a PRIVATE lifted-C tree.

This is a source-level entry trampoline: clone the ORIGINAL translated owner
with a jump to the exact decoded x86 label. It never generates fake x86
semantics, never touches original XBE, and never marks unimplemented opcodes
as fixed. A clone is a candidate, not proof of runtime correctness; local
flags/ebp and ABI state require targeted tests.

The tool fails closed if files/labels/owners differ from the input audit.
NEVER commit generated C to a public repo without resolving provenance.
"""
import argparse, csv, hashlib, json, re, pathlib, collections, sys

_FUNC = re.compile(r'(?m)^void sub_([0-9A-F]{8})\(void\)\n\{')
_STUB = re.compile(r'(?m)^void sub_([0-9A-F]{8})\(void\) \{ g_esp \+= (\d+); /\* 0x[0-9A-F]{8}: (?:not detected|ret \d+) \*/ \}\n')


def owners_from_csv(path):
    rows = list(csv.DictReader(open(path, newline='', encoding='utf-8')))
    assert len({r['va'] for r in rows}) == len(rows)
    return {r['va'][2:].upper():r for r in rows}


def extract_functions(root):
    """Returns owner name -> complete generated function body."""
    owners={}
    for p in sorted(root.rglob('*.c')):
        if p.name in ('recomp_stubs_unresolved.c', 'recomp_dispatch.c'):
            continue
        src=p.read_text('utf-8')
        matches=list(_FUNC.finditer(src))
        for m in matches:
            # The closing brace is column zero in this code-generator dialect.
            end=src.find('\n}\n',m.end())
            if end<0:
                raise ValueError(f'Missing closing brace {p} sub_{m[1]}')
            code=src[m.start():end+3]
            if m[1] in owners:
                raise ValueError(f'Duplicate function definition {m[1]}')
            owners[m[1]]=(code,p)
    return owners


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--gen',type=pathlib.Path,required=True)
    ap.add_argument('--stub-csv',type=pathlib.Path,required=True)
    ap.add_argument('--output-json',type=pathlib.Path,required=True)
    ap.add_argument('--apply-private',action='store_true')
    a=ap.parse_args()
    root=a.gen
    stubs_path=root/'recomp_stubs_unresolved.c'
    original=stubs_path.read_text('utf-8')
    stubs=owners_from_csv(a.stub_csv)
    original_names=[m[1] for m in _STUB.finditer(original)]
    if set(original_names)!=set(stubs) or len(original_names)!=len(stubs):
        raise SystemExit(f'FAIL CLOSED: stub list differs: source={len(original_names)}, audit={len(stubs)}')
    owners=extract_functions(root)
    repairs={}; unpatched={}
    for addr,row in sorted(stubs.items()):
        owner=row['owner_function_va'][2:].upper()
        if row['within_detected_function']!='True':
            unpatched[addr]='no owning function';continue
        if owner not in owners:
            unpatched[addr]='owning function missing in C';continue
        original_owner,filepath=owners[owner]
        label=f'loc_{addr}: ;'
        if original_owner.count(label)!=1 or not re.search(r'(?m)^'+re.escape(label)+r'\s*$',original_owner):
            unpatched[addr]='no unique exact label in original owner';continue
        first=re.search(r'(?m)^loc_[0-9A-F]{8}: ;\s*$',original_owner)
        if not first:
            unpatched[addr]='owner has no first label';continue
        # We can jump to a label within the function, preserving the owner's
        # decoded instruction bodies and owner locals/prologue setup. This is
        # a candidate only: the surrounding flags and register ABI may differ.
        clone=original_owner.replace(f'void sub_{owner}(void)',f'void sub_{addr}(void)',1)
        idx=re.search(r'(?m)^loc_[0-9A-F]{8}: ;\s*$',clone).start()
        clone=clone[:idx]+f'/* From {owner} at guest entry {addr}: verify flags/ABI at runtime. */\n    goto loc_{addr};\n\n'+clone[idx:]
        repairs[addr]=(clone,str(filepath.relative_to(root)),owner)
    if set(repairs)&set(unpatched):raise AssertionError('overlap')
    if len(repairs)+len(unpatched)!=len(stubs):raise AssertionError('missing')
    result={
        'total_stubs':len(stubs),'candidate_mid_entry_rewrites':len(repairs),
        'unresolved_stubs':len(unpatched),'candidate_bytes':sum(len(x[0]) for x in repairs.values()),
        'unresolved_by_reason':dict(collections.Counter(unpatched.values())),
        'candidate_addresses':sorted('0x'+x for x in repairs),
        'unresolved':{'0x'+x:r for x,r in unpatched.items()},
        'note':'Candidate patches preserve original decoded C; not verified semantics or boot. RECOMP_UNIMPL unchanged.'
    }
    if a.apply_private:
        # Keep the remaining stubs unchanged; the build cannot claim complete.
        new_stub=_STUB.sub(lambda m: '' if m[1] in repairs else m[0],original)
        if len(_STUB.findall(new_stub))!=len(unpatched):raise AssertionError('unexpected stub replacement count')
        preface=('/* GENERATED PRIVATE DERIVED SOURCE. DO NOT DISTRIBUTE UNTIL LICENSE RESOLVED. */\n'
                 '#define RECOMP_GENERATED_CODE\n#include "recomp_funcs.h"\n\n')
        out=root/'recomp_mid_entry_repaired.c'
        if out.exists():raise SystemExit('refuse overwrite: '+str(out))
        out.write_text(preface+'\n\n'.join(x[0] for x in repairs.values()),'utf-8')
        stubs_path.write_text(new_stub,'utf-8')
        result['applied_private']=True
        result['generated_c_sha256']=hashlib.sha256(out.read_bytes()).hexdigest()
        result['generated_c_path']=str(out)
    else:
        result['applied_private']=False
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(result,indent=2)+'\n','utf-8')
    print(f"mid-entry candidate rewrites: {len(repairs)}/{len(stubs)}; remaining {len(unpatched)}")
    print('reasons',result['unresolved_by_reason'])

if __name__=='__main__':
    main()
