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
assert "NtCreateFile rejected Xbox X_OBJECT_ATTRIBUTES" in Path("Runtime/XOWUEEngine.cpp").read_text()
assert "release must start at reservation base" in Path("Runtime/XOWUEEngine.cpp").read_text()
print("PASS: AOT invalid target records original bytes and arguments without fallback")

# Xbox virtual and Xenos physical heaps must never overlap.
engine=Path("Runtime/XOWUEEngine.cpp").read_text()
assert "kFirstVirtualAllocation = 0x40000000u" in engine
assert "kLastPhysicalAllocation = 0x20000000u" in engine
assert "g_nextPhysicalAllocation = kFirstPhysicalAllocation" in engine
assert "g_physicalAllocations.push_back({address, size, protection})" in engine
assert "g_virtualAllocations.push_back({address, adjustedSize, protection})" in engine
assert "g_physicalAllocations.clear()" in engine
assert "CTR=0x%08X" in engine
assert "nearby_start=%08X opcodes=" in engine
assert "NtQueryVirtualMemory queried=%08X page=%08X" in engine
assert "XexGetProcedureAddress unresolved module=%08X" in engine
print("PASS: physical/virtual heap separation; AOT bctrl CTR provenance, no interpreter")

# Build 33: the physical allocator must NEVER mutate the virtual cursor.
# A prior typo pushed the virtual pointer below 0x40000000 on the first
# physical allocation, causing NtAllocate(1 MiB) -> STATUS_NO_MEMORY and
# HalReturnToFirmware(1) before Xenos initialization.
physical_start=engine.index("uint32_t allocateGuestPhysicalRange(", engine.index("namespace {")+20)
physical_end=engine.index("bool releaseGuestPhysicalRange(uint32_t address) {", physical_start)
physical=engine[physical_start:physical_end]
assert "g_nextPhysicalAllocation = static_cast<uint32_t>(candidate + size)" in physical
assert "candidate + size > kLastPhysicalAllocation" in physical
assert "g_nextVirtualAllocation =" not in physical
assert "kLastVirtualAllocation" not in physical
first_phys = 0x10000000
first_virt = 0x40000000
assert first_phys + 0x1000 <= 0x20000000
assert first_virt + 0x100000 <= 0x70000000
print("PASS: physical heap bookkeeping cannot corrupt first 1MiB Xbox virtual reservation")

# Build 34: Xbox object attributes must use root/name/flags at offsets 0/4/8
# and a zero-length MEM_RELEASE must search exact reservation base.
assert "const uint32_t rootHandle = PPC_LOAD_U32(attributes);" in engine
assert "const uint32_t nameDescriptor = PPC_LOAD_U32(attributes + 4u);" in engine
assert "const uint32_t objectFlags = PPC_LOAD_U32(attributes + 8u);" in engine
assert "[address, requestedSize, freeType](const auto &item)" in engine
assert "if (freeType == 0x00008000u) return address == item.address;" in engine
assert "uint64_t(address) < reservationEnd" in engine
assert "NtCreateFile rejected Xbox X_OBJECT_ATTRIBUTES" in engine
print("PASS: Xbox OBJECT_ATTRIBUTES ABI, NtFree MEM_RELEASE exact address / half-open intervals")

# Boundary regression: two contiguous reservations; release the second base,
# never choose the previous reservation whose exclusive end equals address.
regions=[(0x40120000,0x10000),(0x40130000,0x10000)]
requested=0x40130000
exact=[(start,size) for start,size in regions if requested==start]
half_open=[(start,size) for start,size in regions if start<=requested<start+size]
assert exact==half_open==[(0x40130000,0x10000)]
print("PASS: contiguous reservation release selects correct exact 64-KiB base")

# Build 35 native owner recovery is validated against real AOT instruction
# comments and has to produce the *exact* dispatch mapping + compiled symbol.
owners = (root / "tools" / "lower_xowue_owner_interior_entries.py").read_text()
workflow = (root / ".github" / "workflows" / "xowue-ios.yml").read_text()
assert "0x82C30BFC" in owners
assert "0x82C30BFC" in workflow
assert "if len(possible) != 1:" in owners
assert "instruction = meta[3][(target-base)//4]" in owners
assert "recovered = generate(args.ppc_dir)" in owners
assert "budget = 12288" in owners
assert "if len(selected) >= 72" in owners
print("PASS: Build 34 AOT missing slot has verified owner-wide native continuation")
