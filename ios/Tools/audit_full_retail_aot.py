#!/usr/bin/env python3
"""Audit ALL generated PoP Xbox retail C, dispatch, entry repairs and explicit traps.
This is structural coverage, NOT proof of x86 semantic equivalence or full runtime.
Fail on missing/duplicated definitions or any silently returning unresolved stubs.
"""
import argparse
import collections
import json
import pathlib
import re
import sys

decl_re=re.compile(r"^void (sub_[0-9A-F]{8})\(void\);",re.M)
def_re=re.compile(r"^void (sub_[0-9A-F]{8})\(void\)",re.M)
disp_re=re.compile(r"\{\s*(0x[0-9A-Fa-f]+)u,\s*\(recomp_func_t\)(sub_[0-9A-F]{8})\s*\}")
fatal_re=re.compile(r"PoPTST FATAL: unimplemented guest target 0x[0-9A-F]{8}")
silent_re=re.compile(r"g_esp\s*\+=\s*\d+;\s*/\*\s*0x[0-9A-F]{8}:")

p=argparse.ArgumentParser()
p.add_argument("--repop",required=True,type=pathlib.Path)
p.add_argument("--report",required=True,type=pathlib.Path)
p.add_argument("--repair-json",type=pathlib.Path,default=pathlib.Path("reports/repair-mid.json"))
p.add_argument("--guard-json",type=pathlib.Path,default=pathlib.Path("reports/remaining-guards.json"))
a=p.parse_args()
gen=a.repop/"source/xbox-retail/gen"
files=sorted(gen.rglob("*.c"))
if len(files)<74:raise SystemExit("FAIL: retail C files missing")
decls=decl_re.findall((gen/"recomp_funcs.h").read_text())
dispatch=[(int(v,16),n) for v,n in disp_re.findall((gen/"recomp_dispatch.c").read_text())]
owners=collections.defaultdict(list)
category=collections.defaultdict(lambda:dict(files=0,bytes=0,definitions=0,unimplemented_opcodes=0,abi_call_sites=0,labels=0))
for f in files:
    rel=str(f.relative_to(gen))
    name=f.relative_to(gen).parts[0]
    stats=category[name]
    stats["files"]+=1
    stats["bytes"]+=f.stat().st_size
    with f.open(encoding="utf-8") as reader:
        for line in reader:
            m=def_re.match(line)
            if m:
                owners[m[1]].append(rel)
                stats["definitions"]+=1
            stats["unimplemented_opcodes"]+=line.count("RECOMP_UNIMPL(")
            stats["abi_call_sites"]+=line.count("RECOMP_ABI_CALL(")
            stats["labels"]+=bool(line.startswith("loc_"))
# The 15 hand-implemented retail entry hooks live OUTSIDE gen/.
# They are linked into libPoPTSTRetail.dylib by the CMake target, and the
# dispatcher legitimately names them. Excluding this file produces a false
# finding that 15 dispatch entries have missing definitions.
target_hooks=a.repop/"source/xbox-retail/target_hooks.c"
hooks=def_re.findall(target_hooks.read_text())
for fn in hooks: owners[fn].append(str(target_hooks.relative_to(a.repop)))
stub_text=(gen/"recomp_stubs_unresolved.c").read_text()
repair=json.loads(a.repair_json.read_text())
guards=json.loads(a.guard_json.read_text())
decl_set=set(decls);disp_set={name for _,name in dispatch}
defined_set=set(owners)
missing=sorted(decl_set-defined_set)
extra=sorted(defined_set-decl_set)
multiple={k:v for k,v in owners.items() if len(v)>1}
bad_dispatch=sorted(disp_set-defined_set)
bad_va=[f"{va:08X}:{name}" for va,name in dispatch if va != int(name[4:],16)]
fatal_count=len(fatal_re.findall(stub_text))
silent_count=len(silent_re.findall(stub_text))
repaired=repair["candidate_mid_entry_rewrites"]
unresolved=repair["unresolved_stubs"]
expected_total=repair["total_stubs"]
warnings=[]
if sum(st["unimplemented_opcodes"] for st in category.values()):
    warnings.append("Some x86 instructions are not implemented. Fail-closed guards are not semantic implementations.")
if repaired:
    warnings.append("Cloned mid-function entry candidates need independent flags/ABI/stack verification.")
if unresolved:
    warnings.append("Unresolved guest targets are fatal diagnostics, not translated functions.")
if len(decl_set)-len(disp_set)!=expected_total:
    warnings.append("Difference between declared and dispatched symbols requires further graph-level audit.")
errors=[]
if len(decls)!=len(decl_set):errors.append("duplicate declarations")
if len(dispatch)!=len({va for va,_ in dispatch}):errors.append("duplicate dispatch VAs")
if missing:errors.append("missing declared definitions")
if extra:errors.append("undeclared definitions")
if multiple:errors.append("duplicate definitions")
if bad_dispatch:errors.append("dispatch points to missing definition")
if bad_va:errors.append("dispatch VA differs from named x86 entry")
if silent_count:errors.append("silent unresolved stubs")
if repaired+unresolved!=expected_total:errors.append("candidate repair accounting inconsistent")
if fatal_count!=unresolved:errors.append("unresolved guard count differs from audit")
# Cloned mid-entry functions copy the original translated instruction body;
# count originals separately so 8 cloned RECOMP_UNIMPL calls are not mistaken
# for 8 NEW original Xbox opcode sites.
clone_opcodes=category.get("recomp_mid_entry_repaired.c",{}).get("unimplemented_opcodes",0)
unique_original_opcodes=sum(x["unimplemented_opcodes"] for x in category.values())-clone_opcodes
if guards.get("unimplemented_opcode_sites") != unique_original_opcodes:
    errors.append("original unimplemented x86 count differs from guard manifest")
if guards.get("silent_stubs_replaced_by_fatal_diagnostics")!=fatal_count:
    errors.append("guard manifest inconsistent")
result=dict(
    source_ref="FulGerNet/rePOP reSOT 4ee36260e71d39fd8b02028fd614b1907a0d451b",
    scope="static source inventory after all iOS build patches; no gameplay emulation or dynamic path execution",
    c_units=len(files),declarations=len(decls),unique_definitions=len(defined_set),
    linked_target_hook_definitions=len(hooks),
    dispatch_entries=len(dispatch),mid_entry_candidates=repaired,
    fatal_unresolved=fatal_count,unimplemented_opcode_sites=unique_original_opcodes,
    additional_cloned_mid_entry_opcode_sites=clone_opcodes,
    abi_call_sites=sum(x["abi_call_sites"] for x in category.values()),
    unique_x86_labels=sum(x["labels"] for x in category.values()),
    paths_with_duplicate_definitions=multiple,missing_definitions=missing,
    undeclared_definitions=extra,dispatch_missing_definitions=bad_dispatch,
    bad_dispatch_x86_va=bad_va[:30],silent_unresolved_stubs=silent_count,
    categories=dict(sorted(category.items())),structural_integrity_pass=not errors,
    translated_semantic_equivalence_proven=False,all_dynamic_execution_paths_verified=False,
    first_game_frame_confirmed=False,errors=errors,warnings=warnings
)
a.report.parent.mkdir(parents=True,exist_ok=True)
a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("AOT AUDIT: C units",len(files),"decl",len(decls),"defs",len(defined_set),"dispatch",len(dispatch))
print("AOT AUDIT: repaired",repaired,"guarded unresolved",fatal_count,
      "unimplemented x86 opcodes",result["unimplemented_opcode_sites"],
      "ABI calls",result["abi_call_sites"])
print("AOT AUDIT: STRUCTURE", "PASS" if not errors else "FAIL")
print("AOT AUDIT: SEMANTIC/DYNAMIC COVERAGE NOT PROVEN; first rendered frame NOT PROVEN")
for error in errors:print("AOT AUDIT ERROR:",error,file=sys.stderr)
if errors:sys.exit(2)
