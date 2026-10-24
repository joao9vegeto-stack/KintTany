#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "Runtime" / "generate_runtime_stubs.py"
spec = importlib.util.spec_from_file_location("xowue_generator", source)
if spec is None or spec.loader is None:
    raise SystemExit("could not load XOWUE source generator")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

fixture = (
    "PPC_FUNC_IMPL(__imp__sub_82345678) {\n    return;\n}\n"
    "PPC_FUNC_IMPL(__imp__sub_82ABCDEF) {\n    return;\n}\n"
)
expected = (
    "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint(0x82345678u);\n    return;\n}\n"
    "PPC_FUNC_IMPL(__imp__sub_82ABCDEF) {\n\txowue_thread_checkpoint(0x82ABCDEFu);\n    return;\n}\n"
)
actual, count = module.instrument_aot_entries(fixture)
if count != 2 or actual != expected:
    raise SystemExit("AOT entry instrumentation did not attach each guest address")

legacy = "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint();\n    return;\n}\n"
wanted = "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint(0x82345678u);\n    return;\n}\n"
upgraded, count = module.instrument_aot_entries(legacy)
if count != 1 or upgraded != wanted:
    raise SystemExit("legacy checkpoint was not upgraded to an address-bearing hook")

repeat, count = module.instrument_aot_entries(actual)
if count != 2 or repeat != actual:
    raise SystemExit("AOT entry instrumentation is not idempotent")
print("PASS: address-bearing AOT entry instrumentation (fresh, legacy, idempotent)")

recompiler_patch = (root / "patches" / "XenonRecomp-XOWUE.patch").read_text(encoding="utf-8")
required_switch_fallback = (
    r'-            println("\t\t__builtin_unreachable();");',
    r'+            println("\t\tPPC_CALL_INDIRECT_FUNC({}.u32);", ctr());',
    r'+            println("\t\treturn;");',
)
if any(line not in recompiler_patch for line in required_switch_fallback):
    raise SystemExit("BCTR switch-table default does not use the guarded guest CTR target")
print("PASS: BCTR switch-table fallback uses guarded guest CTR dispatch")

required_lookup_guard = (
    r'-#define PPC_LOOKUP_FUNC(x, y) *(PPCFunc**)(x + PPC_IMAGE_BASE + PPC_IMAGE_SIZE + (uint64_t(uint32_t(y) - PPC_CODE_BASE) * 2))',
    r'+#define PPC_LOOKUP_FUNC(x, y) xowue_lookup_indirect(ctx, x, uint32_t(y))',
    r'+PPCFunc* xowue_lookup_indirect(struct PPCContext& ctx, uint8_t* base, uint32_t target);',
)
if any(line not in recompiler_patch for line in required_lookup_guard):
    raise SystemExit("legacy PPC function-table lookup bypasses the guarded AOT resolver")
print("PASS: legacy PPC function-table lookup uses guarded AOT resolver")

# Build 31: evidence-first null AOT callsite, no interpreter or invented target.
assert "callsite_bytes=%s%02X%02X%02X%02X" in Path("Runtime/XOWUEEngine.cpp").read_text()
assert "NtCreateFile rejected invalid output/object attributes out=%08X" in Path("Runtime/XOWUEEngine.cpp").read_text()
assert "release must start at reservation base" in Path("Runtime/XOWUEEngine.cpp").read_text()
print("PASS: AOT invalid target records original bytes and arguments without fallback")
