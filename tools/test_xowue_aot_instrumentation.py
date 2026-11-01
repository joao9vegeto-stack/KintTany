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

# Build 94: a function-entry hook cannot interrupt a tight PPC backedge.
# Inject cooperative stop checks at every emitted branch label in the measured
# hot wait routines, while leaving unrelated AOT functions unchanged.
hot_fixture = (
    "PPC_FUNC_IMPL(__imp__sub_822A0278) {\n"
    "loc_822A0280:\n\tif (cr0.eq) goto loc_822A0280;\n"
    "loc_822A0290:\n\treturn;\n}\n"
    "PPC_FUNC_IMPL(__imp__sub_82345678) {\n"
    "loc_8234567C:\n\treturn;\n}\n"
)
hot_patched, hot_count = module.instrument_hot_loop_labels(hot_fixture)
assert hot_count == 2, f"expected 2 hot-loop label checkpoints, got {hot_count}"
assert "loc_822A0280:\n\txowue_thread_checkpoint(0x822A0280u, ctx);" in hot_patched
assert "loc_822A0290:\n\txowue_thread_checkpoint(0x822A0290u, ctx);" in hot_patched
assert "loc_8234567C:\n\treturn;" in hot_patched
print("PASS: cancellable checkpoints injected at measured hot PPC loop labels only")

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
assert "B85_MULTIWAIT_WATCHDOG_PUMP" in engine
assert "obj_creator_lr=0x%08X obj_signals=%u" in engine
assert 'CURRENT_PROJECT_VERSION: "90"' in (root / "iOS" / "project.yml").read_text(encoding="utf-8")
print("PASS: Build 66 allocator, PPC audit, synchronization telemetry and non-signaling wait pump")

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
assert "XOWUE_MEDIA_INVENTORY" in engine
assert "XOWUE_INPUT_POLLED" in engine
print("PASS: native guest cancellation, real guest-frame FPS, 16:9 viewport, touch diagnostics")


# Build 64: runtime diagnostics must expose the complete hot set and build-specific bounded summary.
runtime = (root / "Runtime" / "XOWUEEngine.cpp").read_text(encoding="utf-8")
diagnostics = (root / "iOS" / "App" / "XOWUEDiagnostics.swift").read_text(encoding="utf-8")
for token in ("hot0=", "hot1=", "hot2=", "hot3=", "hot4=", "hot5=", "hot6=", "hot7=",
              "HOT_FN_CODE", "THREAD_DUMP", "recentAotFns", "lastCallerFn", "CODE_AUDIT"):
    if token not in runtime:
        raise SystemExit(f"Build 62 runtime diagnostic missing {token}")
if 'resumo-b\\(buildNumber).txt' not in diagnostics or "utf8.count > 16384" not in diagnostics:
    raise SystemExit("Build 86 compact diagnostic is missing or exceeds 16 KB")
print("PASS: Build 86 hot-function/thread dumps and compact diagnostic are present")
# Preserve the verified native AOT/control-flow and scheduler diagnostics.
aot = (root / "tools" / "generate_aot.py").read_text(encoding="utf-8")
for forbidden in ("def normalize_32bit_writes","def normalize_rlw_instructions","def normalize_32bit_arithmetic"):
    assert forbidden not in aot, f"global PPC rewrite remains: {forbidden}"
assert "PPC_INST_MFTB" in workflow and "xowue_guest_timebase();" in workflow
assert "xowue_thread_checkpoint(0x82C3C4D8u, ctx);" in aot
assert "xowue_thread_checkpoint(uint32_t, PPCContext &);" in source.read_text(encoding="utf-8")
assert "const bool isMainThread = (g_currentGuestThread == nullptr);" in engine
assert "waitable->changed.wait_for(lock, std::chrono::milliseconds(16), ready)" in engine
assert "g_waitSetChanged.wait_until(waitLock, wakeDeadline" in engine
assert "B85_WAIT_WATCHDOG_PUMP" in engine and "B85_MULTIWAIT_WATCHDOG_PUMP" in engine
assert "snapshotAllGuestThreads()" in engine
assert "add(g_mainGuestThread);" in engine and "add(g_graphicsInterruptThread);" in engine
assert "static void logCodeAuditBuild69(uint8_t *base)" in engine
assert "CODE_AUDIT_B69_GUEST_WORD" in engine
assert "THREAD_DUMP id=%u entry=0x%08X exited=%u waiting=%u wait_target=0x%08X last_fn=0x%08X prev_fn=0x%08X lr=0x%08X" in engine

# Build 90: restore native PPC semantics; diagnostics may observe, never repair guest state.
qpc_start = engine.index('extern "C" uint64_t xowue_qpc_write')
qpc_end = engine.index('extern "C" void xowue_log_stall_threads', qpc_start)
qpc_body = engine[qpc_start:qpc_end]
assert "signalGuestEventHandle" not in qpc_body
assert "pumpGuestXenosRingBuffer" not in qpc_body
assert "std::this_thread" not in qpc_body
assert "offset" not in qpc_body
assert "return tb64;" in qpc_body
assert "rate = 50000000ull" in engine

spin_start = engine.index("static void xowue_trace_hot_guest_entry(uint32_t guestAddress, PPCContext &ctx) {")
spin_brace = engine.index("{", spin_start)
spin_depth = 0
spin_end = None
for index in range(spin_brace, len(engine)):
    if engine[index] == "{":
        spin_depth += 1
    elif engine[index] == "}":
        spin_depth -= 1
        if spin_depth == 0:
            spin_end = index + 1
            break
assert spin_end is not None
spin_body = engine[spin_start:spin_end]
assert "signalGuestEventHandle" not in spin_body
assert "xowue_write_be32_raw" not in spin_body
assert "PPC_STORE_U32" not in spin_body
assert "ctx.r4.u32 =" not in spin_body
assert "ctx.r30.u32 =" not in spin_body
assert "XOWUE_B90_CIRCULAR_LIST_PRESERVED" in spin_body
assert "XOWUE_B90_BINK_STATE" in spin_body
assert "xowue_bink_wait_bypass_stub" not in engine
assert "XOWUE_B80_CYCLE_BROKEN" not in engine

guard_start = engine.index('extern "C" bool xowue_82dc2390_observe')
guard_end = engine.index("\n}", guard_start)
guard_body = engine[guard_start:guard_end]
assert "return false;" in guard_body
assert "context.r3.u64 =" not in guard_body
assert "context.cr0.compare" not in guard_body

assert "thread_local B90StreamWatchState g_b90StreamWatch" in engine
assert "g_b89WatchedStreamObject" not in engine
assert "B90_STREAM_WATCH_ARMED" in engine
assert "B90_STREAM_FIELD_TRANSITION" in engine
assert "B89_STREAM_FIELD_WRITE_CANDIDATE" not in engine
assert "g_b90LastAotEntry" in engine and "g_b90PreviousEntryLr" in engine
qpc_fastpaths = [line for line in engine.splitlines() if "const bool qpcFastPath =" in line]
assert len(qpc_fastpaths) == 2
assert all(line.strip().endswith("guestAddress == 0x82C3C4D8u;") for line in qpc_fastpaths)

# Event signals remain only in actual kernel/API completion paths.
assert "signalGuestEventHandle(event)" in engine
assert 'CURRENT_PROJECT_VERSION: "90"' in (root / "iOS" / "project.yml").read_text(encoding="utf-8")
print("PASS: Build 90 native PPC semantics, real 50 MHz timebase, no synthetic wakeups, thread-local stream tracing")

# Preserve the earlier bounded media/stream diagnostics and guest wait semantics.
assert "B86_STREAM_STATE" in engine and "B86_STREAM_ANOMALY" in engine
assert "B86_STREAM_CHUNK_TABLE" in engine and "B86_MEDIA_OPEN" in engine
assert "B87_STREAM_WAIT_STATE" in engine and "B87_STREAM_CACHE_ANOMALY" in engine
assert "B87_NTREADFILE" in engine

# Build 92.2: .xxx and .bik reads compare on-disk bytes with guest-buffer bytes
# before signaling the guest; persist those records and make MFTB cancellable.
read_start = engine.index("void xowue_NtReadFile(PPCContext &context, uint8_t *base) {")
read_end = engine.index("\n}\n\nvoid xowue_NtWriteFile", read_start)
read_body = engine[read_start:read_end]
for token in (
    'readExtension == ".xxx" || readExtension == ".bik"',
    "std::filesystem::file_size(file->path",
    "sourceFile.seekg(static_cast<std::streamoff>(offset)",
    "sourceHash",
    "guestHash",
    "sourceNonZero",
    "guestNonZero",
    "B92_XXX_INTEGRITY",
    "B92_BIK_INTEGRITY",
    "rangeWithinFile",
):
    assert token in read_body, f"Build 92 .xxx integrity check missing {token}"
assert read_body.index("B92_XXX_INTEGRITY") < read_body.index("signal.signalNow();")
assert read_body.index("B92_BIK_INTEGRITY") < read_body.index("signal.signalNow();")
assert "const uint8_t *guestBytes = base + buffer;" in read_body
assert "g_runtimeTracePersistB92.fetch_add" in engine
assert "XOWUE_B92_QPC_" in engine[engine.index("bool shouldPersistRuntimeTrace"):engine.index("void persistRuntimeTrace")]
timebase_start = engine.index('extern "C" uint64_t xowue_guest_timebase(void) {')
timebase_end = engine.index('extern "C" uint64_t xowue_qpc_write', timebase_start)
timebase_body = engine[timebase_start:timebase_end]
assert "g_schedulerStopRequested.load(std::memory_order_relaxed)" in timebase_body
assert "throw GuestThreadStopRequested{};" in timebase_body
assert "B92_XXX_INTEGRITY" in diagnostics and "B92_BIK_INTEGRITY" in diagnostics
assert 'lines.filter { $0.contains("XOWUE_B92_QPC_") }' in diagnostics
print("PASS: Build 92.2 .xxx/.bik source-vs-guest integrity, persisted evidence, and MFTB/AOT cooperative cancellation")
wait_start = engine.index("uint32_t waitGuestObject(")
wait_end = engine.index("uint32_t waitGuestObjects(", wait_start)
wait_body = engine[wait_start:wait_end]
assert "B85_WAIT_WATCHDOG_PUMP" in wait_body
assert "markGuestWaitableSignaledLocked(waitable);" not in wait_body
multi_end = engine.index("void signalGuestWaitable(", wait_end)
multi_body = engine[wait_end:multi_end]
assert "B85_MULTIWAIT_WATCHDOG_PUMP" in multi_body
assert "candidate->signaled = true" not in multi_body
assert "candidate.unconsumedSignals != 0u" in multi_body
assert "if (waitable->unconsumedSignals != 0u) --waitable->unconsumedSignals;" in multi_body

diag = (root / "iOS" / "App" / "XOWUEDiagnostics.swift").read_text(encoding="utf-8")
assert 'lines.filter { $0.contains("B86_STREAM_STATE") }' in diag
assert 'lines.filter { $0.contains("B85_WAIT_") || $0.contains("B85_MULTIWAIT_") }' in diag
assert '"XOWUE_BUILD_SUMMARY build=\\(buildNumber) source=' in diag
assert 'lines.filter { $0.contains("B84_CODE_AUDIT") }' in diag
assert 'lines.filter { $0.contains("B90_STREAM_") }' in diag
print("PASS: B86/B87 stream and file evidence, bounded wait diagnostics, compact app summary")

# Retry builds retain the successful base version and receive a dotted attempt suffix.
workflow_text = (root / ".github" / "workflows" / "xowue-ios.yml").read_text(encoding="utf-8")
assert 'const failedAttempts = priorRuns.filter(' in workflow_text
assert '`${baseBuildNumber}.${failedAttempts}`' in workflow_text
assert 'CURRENT_PROJECT_VERSION="$XOWUE_BUILD_NUMBER"' in workflow_text
assert 'IPA_NAME="XOWUE-Build-${XOWUE_BUILD_NUMBER}.ipa"' in workflow_text
print("PASS: failed/cancelled retries use dotted build identifiers (92.1, 92.2, ...) without consuming successful build numbers")
