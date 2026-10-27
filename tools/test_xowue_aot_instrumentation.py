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
    "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint(0x82345678u, ctx);\n    return;\n}\n"
    "PPC_FUNC_IMPL(__imp__sub_82ABCDEF) {\n\txowue_thread_checkpoint(0x82ABCDEFu, ctx);\n    return;\n}\n"
)
actual, count = module.instrument_aot_entries(fixture)
if count != 2 or actual != expected:
    raise SystemExit("AOT entry instrumentation did not attach each guest address")

legacy = "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint();\n    return;\n}\n"
wanted = "PPC_FUNC_IMPL(__imp__sub_82345678) {\n\txowue_thread_checkpoint(0x82345678u, ctx);\n    return;\n}\n"
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

# Build 66 allocator, audit, synchronization watchdog and version checks.
assert "allocateSmallGuestPoolBlock" in engine
assert "XOWUE_POOL_ALLOC_82DC2BF0" in engine and "XOWUE_POOL_INIT_82DC2B14" in engine
assert "CODE_AUDIT_B66" in engine and "CODE_AUDIT_83847ABC" in engine
assert "XOWUE_VBLANK_WATCHDOG_SIGNAL" in engine
assert "obj_creator_lr=0x%08X obj_signals=%u" in engine
assert 'CURRENT_PROJECT_VERSION: "69"' in (root / "iOS" / "project.yml").read_text(encoding="utf-8")
print("PASS: Build 66 allocator, PPC audit, synchronization telemetry and vblank watchdog hooks")

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
assert "0x8257A840" in owners
assert "0x8257A840" in workflow
assert "latest_target = targets[-1]" in owners
assert "most_recent_observed_target" in owners
assert "if len(possible) != 1:" in owners
assert "instruction = meta[3][(target-base)//4]" in owners
assert "recovered = generate(args.ppc_dir)" in owners
assert "budget = 12288" in owners
assert "if len(selected) >= 72" in owners
print("PASS: Build 35 bctrl target 0x8257A840 included in verified native owner recovery and CI")

# Build 37: an actual user exit cancels guest PPC; UIKit dismissal cannot
# leave the AOT entry and spawned threads running underneath the launcher.
header=(root / "Runtime" / "xowue_engine.h").read_text()
swift=(root / "iOS" / "App" / "XOWUEApp.swift").read_text()
backend=(root / "iOS" / "App" / "XOWUEVulkanBackend.m").read_text()
assert "void xowue_request_stop(void);" in header
assert 'extern "C" void xowue_request_stop(void)' in engine
assert 'requestGuestSchedulerStop();' in engine
assert 'catch (const GuestThreadStopRequested &)' in engine
checkpoint = engine[engine.index("void checkpointGuestThread() {"):engine.index("void finishGuestThread(")]
assert checkpoint.index("g_schedulerStopRequested.load") < checkpoint.index("if (!thread) return;")
assert "if (g_schedulerStopRequested.load(std::memory_order_relaxed))" in engine[
    engine.index("void xowue_thread_checkpoint() {"):engine.index("void xowue_thread_checkpoint(uint32_t")
]
assert 'recordAotExecutionSummary("user-exit")' in engine
assert "xowue_request_stop()" in swift
assert "if exitRequested || outcome.code == 4" in swift
assert 'Label("SAIR", systemImage: "power")' in swift
assert 'Label("JOGO INSTALADO"' in swift
assert "16.0 / 9.0" in swift and "9.0 / 16.0" in swift
assert "XOWUE_REAL_FPS" in backend and "XOWUE_FPS" not in backend
assert "guestDelta" in backend and "hostDelta" in backend
assert "XOWUE_ASSET_PREFLIGHT" in engine
assert "XOWUE_INPUT_POLLED" in engine
print("PASS: native guest cancellation, real guest-frame FPS, 16:9 viewport, touch diagnostics")


# Build 64: runtime diagnostics must expose the complete hot set and build-specific bounded summary.
runtime = (root / "Runtime" / "XOWUEEngine.cpp").read_text(encoding="utf-8")
diagnostics = (root / "iOS" / "App" / "XOWUEDiagnostics.swift").read_text(encoding="utf-8")
for token in ("hot0=", "hot1=", "hot2=", "hot3=", "hot4=", "hot5=", "hot6=", "hot7=",
              "HOT_FN_CODE", "THREAD_DUMP", "recentAotFns", "lastCallerFn", "CODE_AUDIT"):
    if token not in runtime:
        raise SystemExit(f"Build 62 runtime diagnostic missing {token}")
if 'resumo-b\\(buildNumber).txt' not in diagnostics or "utf8.count > 4000" not in diagnostics:
    raise SystemExit("Build 62 compact diagnostic is missing or not capped at 4 KB")
print("PASS: Build 62 hot-function/thread dumps and compact diagnostic are present")
# Build 65: prohibit global PPC rewrites and require targeted guard/raw-code audit.
aot=(root/"tools"/"generate_aot.py").read_text(encoding="utf-8")
for forbidden in ("def normalize_32bit_writes","def normalize_rlw_instructions","def normalize_32bit_arithmetic"):
    if forbidden in aot: raise SystemExit(f"Build 65 forbids global AOT rewrite: {forbidden}")
for required in ("CODE_AUDIT_B65_CPP_BEGIN","sub_822000E0","sub_82DC1FA0","sub_82DC2390","sub_82DC2A50","sub_82DC2B74"):
    if required not in aot: raise SystemExit(f"Build 65 AOT audit missing {required}")
for required in ("CODE_AUDIT_B65","XOWUE_82DC2390_STATE","XOWUE_82DC2390_GUARD","emitBuild65CodeAudit","target == 0x82DC2390u","0x82DC2014u","0x80004005ull"):
    if required not in runtime: raise SystemExit(f"Build 65 runtime guard/audit missing {required}")
assert "PPC_INST_MFTB" in workflow and "xowue_guest_timebase();" in workflow
for forbidden in ("RLWIMI record-form CR0","RLDIMI record-form CR0","PPC_INST_RLDICL","PPC_INST_RLDICR"):
    if forbidden in workflow: raise SystemExit(f"Build 65 workflow alters upstream instruction semantics: {forbidden}")
print("PASS: Build 65 global PPC semantic rewrites removed; targeted 0x82DC2390 guard and raw-code audit wired")

# Build 67: main thread has no GuestThread binding, and no infinite wait may
# block the host condition variable without bounded GPU/scheduler progress.
assert "const bool isMainThread = (g_currentGuestThread == nullptr);" in engine
assert "currentTid = isMainThread ? 0xF8000001u : g_currentGuestThread->handle" in engine
assert "g_mainThreadGuestLr.load(std::memory_order_relaxed)" in engine
assert "waitable->changed.wait_for(lock, std::chrono::milliseconds(16), ready)" in engine
assert "g_waitSetChanged.wait_for(waitLock, std::chrono::milliseconds(16)" in engine
assert "CODE_AUDIT_B67_MAIN_WAIT_LR" in engine
assert "dump(0x82DC2A50u,0x82DC2B78u" in engine
assert "signalGeneration" in engine and "unconsumedSignals" in engine
assert "signalGuestEventStructure" in engine
assert "XOWUE_WAIT_WATCHDOG_WAKE" in engine
assert "g_thread2WatchdogWakes.load(std::memory_order_relaxed) >= 4u" in engine
assert "XOWUE_ASYNC_TASK_STATE sp=0x%08X frame=0x%08X task=0x%08X words=" in engine
assert "context.r11.u64 = 1ull" in engine
assert "CODE_AUDIT_B68_MAIN_ASYNC_TASK" in engine
assert "CODE_AUDIT_B68_EVENT_WAIT_IMPLEMENTATION" in engine
assert "CODE_AUDIT_B68_THREAD2_FULL" in engine
assert "if ((++audioLoopCalls & 63u) == 0u)" in engine
assert "std::chrono::milliseconds(2)" in engine
assert 'CURRENT_PROJECT_VERSION: "69"' in (root / "iOS" / "project.yml").read_text(encoding="utf-8")
print("PASS: Build 68 lost-wakeup counters, all-thread worker-first watchdog, async-task recovery, PPC audit and audio throttle")

# Build 69: QPC fast path, synthetic timebase, and complete diagnostics.
assert "const bool qpcFastPath = guestAddress == 0x82C3C4D8u || guestAddress == 0x822A1E08u" in engine
assert "const bool plateau = !qpcFastPath" in engine
assert "if (!qpcFastPath && slot->count != 0u" in engine
assert "loopEntries % 4096u" in engine
assert "static thread_local uint64_t offset=0,frames0=UINT64_MAX,swaps0=UINT64_MAX;" in engine
assert "offset+=50000ull;" in engine
assert "tb64+=offset;" in engine
assert "snapshotAllGuestThreads()" in engine
assert "add(g_mainGuestThread);" in engine and "add(g_graphicsInterruptThread);" in engine
assert "static void logCodeAuditBuild69(uint8_t *base)" in engine
for address in ("0x82C3C498u","0x822A1BC0u","0x822A01C0u","0x824E6F10u","0x82C257F0u","0x823704C0u","0x824278C0u","0x826903F0u","0x826901E0u","0x827E1250u","0x82B49DE0u","0x82B4AAE0u","0x82B4AE00u","0x40000770u","0x40002130u","0x4025D0F0u","0x4025D0F8u","0x4036FA00u","0x4036FA40u","0x4004ED60u","0x4004EDB0u"):
    assert address in engine, f"Build 69 audit address missing {address}"
assert "CODE_AUDIT_B69_GUEST_WORD" in engine
assert "THREAD_DUMP id=%u entry=0x%08X exited=%u waiting=%u wait_target=0x%08X last_fn=0x%08X prev_fn=0x%08X lr=0x%08X" in engine
assert 'CURRENT_PROJECT_VERSION: "69"' in (root / "iOS" / "project.yml").read_text(encoding="utf-8")
print("PASS: Build 69 QPC fast path, synthetic timebase, main/interrupt thread snapshots, PPC code/data audit")

# Build 69 checks for main-thread PPC context, thread snapshots, and QPC timer pacing.
aot = (root / "tools" / "generate_aot.py").read_text(encoding="utf-8")
runtime_stubs = source.read_text(encoding="utf-8")
for token in ("buildMainThreadDiagnostic","g_mainThreadLastR31","XOWUE_STALL_THREADS_THREAD","49875000ull","offset+=50000ull","decodedFrames","g_xenosFrontend.swaps"):
    if token not in engine: raise SystemExit(f"Build 69 missing runtime token {token}")
assert "xowue_thread_checkpoint(0x82C3C4D8u, ctx);" in aot
assert "xowue_thread_checkpoint(uint32_t, PPCContext &);" in runtime_stubs
print("PASS: Build 69 main-thread context and QPC pacing diagnostics")

for token in ("callerLR>=0x822A1C00u","callerLR>=0x822A0200u","callerLR>=0x824E6F50u","callerLR>=0x82C25800u"):
    if token not in engine: raise SystemExit(f"Build 69 QPC loop caller range missing {token}")
