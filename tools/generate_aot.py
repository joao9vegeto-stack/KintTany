#!/usr/bin/env python3
"""Apply only the XOWUE QPC replacement and targeted Build 65 guard."""
from __future__ import annotations
import argparse
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
AUDIT_SYMBOLS = ("sub_822000E0", "sub_82DC1FA0", "sub_82DC2390", "sub_82DC2A50", "sub_82DC2B74")
def function_span(source: str, symbol: str) -> tuple[int, int] | None:
    marker=f"PPC_FUNC_IMPL(__imp__{symbol}) {{"; start=source.find(marker)
    if start<0: return None
    brace=source.find("{",start); depth=0
    for i in range(brace,len(source)):
        if source[i]=="{": depth+=1
        elif source[i]=="}":
            depth-=1
            if depth==0: return start,i+1
    raise RuntimeError(f"unterminated generated function {symbol}")
def replace_qpc(source: str) -> tuple[str,int]:
    span=function_span(source,"sub_82C3C4D8")
    if span is None: return source,0
    start,end=span; old=source[start:end]; replacement=QPC_BODY
    if "xowue_thread_checkpoint();" in old and "xowue_thread_checkpoint(0x82C3C4D8u);" not in old:
        replacement=replacement.replace("xowue_thread_checkpoint(0x82C3C4D8u);","xowue_thread_checkpoint();")
    return (source,0) if old==replacement else (source[:start]+replacement+source[end:],1)
def add_null_callback_guard(source: str) -> tuple[str,int]:
    span=function_span(source,"sub_82DC2390")
    if span is None: return source,0
    start,end=span; body=source[start:end]; guard="    if (xowue_82dc2390_guard(ctx, base)) return;"
    if guard in body: return source,0
    brace=body.find("{"); body=body[:brace+1]+"\n"+guard+body[brace+1:]
    return source[:start]+body+source[end:],1
def self_test() -> None:
    fixture=("PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {\n    xowue_thread_checkpoint(0x82C3C4D8u);\n    return;\n}\n"+
      "".join(f"PPC_FUNC_IMPL(__imp__{s}) {{\n return;\n}}\n" for s in AUDIT_SYMBOLS)+
      "PPC_FUNC_IMPL(__imp__sub_82DC2390) {\n return;\n}\n")
    patched,n=replace_qpc(fixture); assert n==1 and "xowue_qpc_write(outPtr, xowue_guest_timebase()" in patched
    patched,n=add_null_callback_guard(patched); assert n==1 and "xowue_82dc2390_guard(ctx, base)" in patched
    again,n=add_null_callback_guard(patched); assert n==0 and again==patched
    for symbol in AUDIT_SYMBOLS: assert function_span(patched,symbol) is not None
    print("PASS: Build 65 QPC-only replacement, targeted null-callback guard, and five-function audit")
def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--ppc-dir",type=Path); parser.add_argument("--self-test",action="store_true"); args=parser.parse_args()
    if args.self_test: self_test(); return 0
    if not args.ppc_dir: parser.error("--ppc-dir is required unless --self-test is selected")
    sources=sorted(args.ppc_dir.glob("ppc_recomp.*.cpp"))
    if not sources: raise SystemExit(f"no generated AOT sources found in {args.ppc_dir}")
    qpc_count=guard_count=0; found={s:0 for s in AUDIT_SYMBOLS}; bodies={}
    for path in sources:
        source=path.read_text(encoding="utf-8"); source,qpc=replace_qpc(source); source,guard=add_null_callback_guard(source)
        qpc_count+=qpc; guard_count+=guard
        for symbol in AUDIT_SYMBOLS:
            span=function_span(source,symbol)
            if span is not None: found[symbol]+=1; bodies[symbol]=source[span[0]:span[1]]
        if qpc or guard: path.write_text(source,encoding="utf-8")
    if qpc_count!=1: raise SystemExit(f"expected exactly one QPC helper, found {qpc_count}")
    if guard_count!=1: raise SystemExit(f"expected exactly one 0x82DC2390 guard, found {guard_count}")
    missing=[s for s,n in found.items() if n!=1]
    if missing: raise SystemExit(f"expected one generated body for each Build 65 audit symbol: {missing}")
    print(f"XOWUE_B65_AOT_PATCH qpc={qpc_count} targeted_82DC2390_guard={guard_count} global_instruction_rewrites=0")
    for symbol in AUDIT_SYMBOLS: print(f"CODE_AUDIT_B65_CPP_BEGIN {symbol}\n{bodies[symbol]}\nCODE_AUDIT_B65_CPP_END {symbol}")
    return 0
if __name__=="__main__": raise SystemExit(main())
