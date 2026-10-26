#!/usr/bin/env python3
"""Patch only the QPC helper and print source-level Build 65 PPC audit bodies."""
from __future__ import annotations
import argparse
import re
from pathlib import Path
QPC_BODY = """PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {
    xowue_thread_checkpoint(0x82C3C4D8u);
    const uint32_t outPtr = ctx.r3.u32;
    const uint64_t tb64 = xowue_qpc_write(outPtr, xowue_guest_timebase(), static_cast<uint32_t>(ctx.lr));
    ctx.r11.u64 = tb64;
    ctx.r10.u64 = static_cast<uint32_t>(tb64);
    ctx.cr0.compare<int32_t>(ctx.r10.s32, 0, ctx.xer);
    ctx.r3.u64 = 1ull;
    return;
}"""
AUDIT_SYMBOLS=("sub_822000E0","sub_82DC1FA0","sub_82DC2390","sub_82DC2A50","sub_82DC2B74")
def function_spans(source: str):
    marker=re.compile(r"PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\)\s*\{")
    for m in marker.finditer(source):
        brace=source.find("{",m.start()); depth=0; end=None
        for i in range(brace,len(source)):
            if source[i]=="{": depth+=1
            elif source[i]=="}":
                depth-=1
                if depth==0: end=i+1; break
        if end is None: raise RuntimeError(f"unterminated generated function {m.group(1)}")
        yield m.group(1),m.start(),end
def replace_qpc(source: str) -> tuple[str,int]:
    matches=[(s,e) for name,s,e in function_spans(source) if name=="sub_82C3C4D8"]
    if not matches:return source,0
    if len(matches)!=1:raise RuntimeError(f"multiple QPC functions found: {len(matches)}")
    start,end=matches[0]; old=source[start:end]; replacement=QPC_BODY
    if "xowue_thread_checkpoint();" in old and "xowue_thread_checkpoint(0x82C3C4D8u);" not in old:
        replacement=replacement.replace("xowue_thread_checkpoint(0x82C3C4D8u);","xowue_thread_checkpoint();")
    return (source,0) if old==replacement else (source[:start]+replacement+source[end:],1)
def audit_bodies(source: str):
    spans=list(function_spans(source)); found={}
    for target in AUDIT_SYMBOLS:
        exact=[(name,s,e) for name,s,e in spans if name==target]
        if exact:
            found[target]=(exact[0][0],source[exact[0][1]:exact[0][2]])
            continue
        addr=target.removeprefix("sub_").upper()
        pat=re.compile(r"(?im)^\\s*//\\s*0x"+re.escape(addr)+r"(?:\\b|:)")
        owners=[(name,s,e) for name,s,e in spans if pat.search(source[s:e])]
        if owners: found[target]=(owners[0][0],source[owners[0][1]:owners[0][2]])
    return found
def self_test():
    fixture=("PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {\\n    xowue_thread_checkpoint(0x82C3C4D8u);\\n    return;\\n}\\n"+
      "".join(f"PPC_FUNC_IMPL(__imp__{s}) {{\\n return;\\n}}\\n" for s in AUDIT_SYMBOLS))
    patched,n=replace_qpc(fixture)
    assert n==1 and "xowue_qpc_write(outPtr, xowue_guest_timebase()" in patched
    assert len(audit_bodies(patched))==5
    print("PASS: Build 65 QPC-only replacement and five-function source audit")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--ppc-dir",type=Path);parser.add_argument("--self-test",action="store_true");args=parser.parse_args()
    if args.self_test:self_test();return 0
    if not args.ppc_dir:parser.error("--ppc-dir is required unless --self-test is selected")
    sources=sorted(args.ppc_dir.glob("ppc_recomp.*.cpp"))
    if not sources:raise SystemExit(f"no generated AOT sources found in {args.ppc_dir}")
    qpc_count=0; bodies={}
    for path in sources:
        source=path.read_text(encoding="utf-8"); source,n=replace_qpc(source);qpc_count+=n
        for target,(owner,body) in audit_bodies(source).items():bodies.setdefault(target,(owner,body,path.name))
        if n:path.write_text(source,encoding="utf-8")
    if qpc_count!=1:raise SystemExit(f"expected exactly one QPC helper, found {qpc_count}")
    print(f"XOWUE_B65_AOT_PATCH qpc={qpc_count} global_instruction_rewrites=0")
    for target in AUDIT_SYMBOLS:
        if target not in bodies:
            print(f"CODE_AUDIT_B65_CPP_MISSING target={target} standalone_or_owner_body_not_found")
        else:
            owner,body,path=bodies[target]
            print(f"CODE_AUDIT_B65_CPP_BEGIN target={target} owner={owner} file={path}\\n{body}\\nCODE_AUDIT_B65_CPP_END target={target}")
    return 0
if __name__=="__main__":raise SystemExit(main())
