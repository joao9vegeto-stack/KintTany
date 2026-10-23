#!/usr/bin/env python3
"""Generate fail-closed adapters for imports and the undecoded .text tail."""
from __future__ import annotations
import argparse
import re
from pathlib import Path

IMPORT_RE = re.compile(r"PPC_EXTERN_FUNC\(__imp__([A-Za-z_][A-Za-z_0-9]*)\);")
DECODE_RE = re.compile(r"Unable to decode instruction [0-9A-Fa-f]+ at ([0-9A-Fa-f]+)")
PPC_FUNCTION_RE = re.compile(r"(PPC_FUNC_IMPL\(__imp__sub_[0-9A-Fa-f]+\)\s*\{)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", required=True, type=Path)
    parser.add_argument("--recompile-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    shared = (args.ppc_dir / "ppc_recomp_shared.h").read_text(encoding="utf-8")
    imports = sorted(set(IMPORT_RE.findall(shared)))
    if len(imports) != 261:
        raise SystemExit(f"expected 261 XEX imports, found {len(imports)}")

    log = args.recompile_log.read_text(encoding="utf-8")
    addresses = sorted({int(value, 16) for value in DECODE_RE.findall(log)})
    if len(addresses) != 161:
        raise SystemExit(f"expected 161 undecoded PPC words, found {len(addresses)}")

    # Make mapped calls into the unresolved final .text words fail visibly.
    # Some decoded words have no function-map entry and therefore cannot be
    # reached through the AOT dispatch table. Scan each large source once.
    mapped = set(int(value, 16) for value in re.findall(
        r"\{\s*0x([0-9A-Fa-f]+),\s*sub_", (args.ppc_dir / "ppc_func_mapping.cpp").read_text(encoding="utf-8")
    ))
    to_mark = set(addresses) & mapped
    pending = set(to_mark)
    for source in sorted(args.ppc_dir.glob("ppc_recomp.*.cpp")):
        contents = source.read_text(encoding="utf-8")
        original = contents
        instrumented = 0

        def add_checkpoint(match: re.Match[str]) -> str:
            nonlocal instrumented
            instrumented += 1
            following = contents[match.end():match.end() + 100]
            if re.match(r"\s*xowue_thread_checkpoint\(\);", following):
                return match.group(1)
            return match.group(1) + "\n\txowue_thread_checkpoint();"

        contents = PPC_FUNCTION_RE.sub(add_checkpoint, contents)
        for address in sorted(tuple(pending)):
            symbol = f"sub_{address:08X}"
            marker = f"PPC_FUNC_IMPL(__imp__{symbol}) {{"
            if marker not in contents:
                continue
            start = contents.index(marker) + len(marker)
            end = contents.find("\n}", start)
            if end < 0:
                raise SystemExit(f"unterminated generated body for {symbol}")
            body = contents[start:end]
            if f"xowue_untranslated_tail(0x{address:08X})" not in body:
                contents = contents[:start] + f"\n\txowue_untranslated_tail(0x{address:08X});\n" + contents[end:]
            pending.remove(address)
        if contents != original:
            declarations = []
            if instrumented and "extern void xowue_thread_checkpoint();" not in contents:
                declarations.append("extern void xowue_thread_checkpoint();")
            if "xowue_untranslated_tail(" in contents and "extern void xowue_untranslated_tail(uint32_t);" not in contents:
                declarations.append("extern void xowue_untranslated_tail(uint32_t);")
            if declarations:
                include = '#include "ppc_recomp_shared.h"'
                contents = contents.replace(include, include + "\n" + "\n".join(declarations), 1)
            source.write_text(contents, encoding="utf-8")
    if pending:
        missing = ", ".join(f"0x{address:08X}" for address in sorted(pending))
        raise SystemExit(f"no generated placeholder found for mapped undecoded words: {missing}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    code = ['#include "ppc_recomp_shared.h"',
            'void xowue_thread_checkpoint();',
            '[[noreturn]] void xowue_unsupported_import(const char *, const PPCContext &);',
            'void xowue_ExCreateThread(PPCContext &, uint8_t *);',
            'void xowue_ExTerminateThread(PPCContext &);',
            'void xowue_ExRegisterTitleTerminateNotification(PPCContext &);',
            'void xowue_NtClose(PPCContext &);',
            'void xowue_NtSetEvent(PPCContext &, uint8_t *);',
            'void xowue_NtClearEvent(PPCContext &);',
            'void xowue_NtPulseEvent(PPCContext &, uint8_t *);',
            'void xowue_NtWaitForSingleObjectEx(PPCContext &, uint8_t *);',
            'void xowue_NtWaitForMultipleObjectsEx(PPCContext &, uint8_t *);',
            'void xowue_NtResumeThread(PPCContext &, uint8_t *);',
            'void xowue_NtSuspendThread(PPCContext &, uint8_t *);',
            'void xowue_KeSetEvent(PPCContext &, uint8_t *);',
            'void xowue_KeResetEvent(PPCContext &, uint8_t *);',
            'void xowue_KeWaitForSingleObject(PPCContext &, uint8_t *);',
            'void xowue_KeWaitForMultipleObjects(PPCContext &, uint8_t *);',
            'void xowue_KeResumeThread(PPCContext &);',
            'void xowue_KeSetAffinityThread(PPCContext &, uint8_t *);',
            'void xowue_KeSetBasePriorityThread(PPCContext &);',
            'void xowue_KeDelayExecutionThread(PPCContext &, uint8_t *);',
            'void xowue_XamLoaderTerminateTitle(PPCContext &);',
            'void xowue_KeGetCurrentProcessType(PPCContext &);',
            'void xowue_KeQueryPerformanceFrequency(PPCContext &);',
            'void xowue_FscSetCacheElementCount(PPCContext &);',
            'void xowue_NtCreateEvent(PPCContext &, uint8_t *);',
            'void xowue_RtlInitializeCriticalSection(PPCContext &, uint8_t *);',
            'void xowue_RtlInitializeCriticalSectionAndSpinCount(PPCContext &, uint8_t *);',
            'void xowue_RtlEnterCriticalSection(PPCContext &, uint8_t *);',
            'void xowue_RtlTryEnterCriticalSection(PPCContext &, uint8_t *);',
            'void xowue_RtlLeaveCriticalSection(PPCContext &, uint8_t *);',
            'void xowue_XexCheckExecutablePrivilege(PPCContext &);',
            'void xowue_XGetAVPack(PPCContext &);',
            'void xowue_XGetGameRegion(PPCContext &);',
            'void xowue_KeTlsAlloc(PPCContext &);',
            'void xowue_KeTlsFree(PPCContext &);',
            'void xowue_KeTlsGetValue(PPCContext &);',
            'void xowue_KeTlsSetValue(PPCContext &);',
            'void xowue_RtlNtStatusToDosError(PPCContext &);',
            'void xowue_NtQueryVirtualMemory(PPCContext &, uint8_t *);',
            'void xowue_RtlUnicodeToMultiByteN(PPCContext &, uint8_t *);',
            'void xowue_RtlMultiByteToUnicodeN(PPCContext &, uint8_t *);',
            'void xowue_XamLoaderGetLaunchDataSize(PPCContext &, uint8_t *);',
            'void xowue_NtAllocateVirtualMemory(PPCContext &, uint8_t *);',
            'void xowue_NtFreeVirtualMemory(PPCContext &, uint8_t *);',
            'uint32_t xowue_MmAllocatePhysicalMemoryEx(PPCContext &, uint8_t *);',
            'void xowue_MmFreePhysicalMemory(PPCContext &);',
            'void xowue_MmGetPhysicalAddress(PPCContext &);',
            'void xowue_MmMapIoSpace(PPCContext &);',
            'void xowue_ExAllocatePool(PPCContext &, uint8_t *);',
            'void xowue_ExFreePool(PPCContext &);',
            'void xowue_VdInitializeEngines(PPCContext &);',
            'void xowue_VdShutdownEngines();',
            'void xowue_VdInitializeRingBuffer(PPCContext &, uint8_t *);',
            'void xowue_VdEnableRingBufferRPtrWriteBack(PPCContext &);',
            'void xowue_VdGetSystemCommandBuffer(PPCContext &, uint8_t *);',
            'void xowue_VdSetSystemCommandBufferGpuIdentifierAddress(PPCContext &);',
            'void xowue_VdSetGraphicsInterruptCallback(PPCContext &);',
            'void xowue_VdSwap(PPCContext &, uint8_t *);',
            'void xowue_VdInitializeScalerCommandBuffer(PPCContext &, uint8_t *);',
            'void xowue_VdQueryVideoMode(PPCContext &, uint8_t *);',
            'void xowue_VdQueryVideoFlags(PPCContext &);',
            'void xowue_VdGetCurrentDisplayGamma(PPCContext &, uint8_t *);',
            'void xowue_VdGetCurrentDisplayInformation(PPCContext &, uint8_t *);',
            'void xowue_VdSetDisplayMode(PPCContext &);',
            'void xowue_VdEnableDisableClockGating(PPCContext &);',
            'void xowue_VdIsHSIOTrainingSucceeded(PPCContext &);',
            'void xowue_VdPersistDisplay(PPCContext &);',
            'void xowue_VdRetrainEDRAM(PPCContext &);',
            'void xowue_VdRetrainEDRAMWorker(PPCContext &);',
            'void xowue_VdCallGraphicsNotificationRoutines(PPCContext &);',
            '[[noreturn]] void xowue_HalReturnToFirmware(PPCContext &, uint8_t *);', '']
    for name in imports:
        code.append(f"PPC_FUNC(__imp__{name}) {{")
        code.append("\txowue_thread_checkpoint();")
        if name == "ExCreateThread":
            code.append("\txowue_ExCreateThread(ctx, base);")
        elif name == "ExTerminateThread":
            code.append("\txowue_ExTerminateThread(ctx);")
        elif name == "ExRegisterTitleTerminateNotification":
            code.append("\txowue_ExRegisterTitleTerminateNotification(ctx);")
        elif name == "NtClose":
            code.append("\txowue_NtClose(ctx);")
        elif name == "NtSetEvent":
            code.append("\txowue_NtSetEvent(ctx, base);")
        elif name == "NtClearEvent":
            code.append("\txowue_NtClearEvent(ctx);")
        elif name == "NtPulseEvent":
            code.append("\txowue_NtPulseEvent(ctx, base);")
        elif name == "NtWaitForSingleObjectEx":
            code.append("\txowue_NtWaitForSingleObjectEx(ctx, base);")
        elif name == "NtWaitForMultipleObjectsEx":
            code.append("\txowue_NtWaitForMultipleObjectsEx(ctx, base);")
        elif name == "NtResumeThread":
            code.append("\txowue_NtResumeThread(ctx, base);")
        elif name == "NtSuspendThread":
            code.append("\txowue_NtSuspendThread(ctx, base);")
        elif name == "KeSetEvent":
            code.append("\txowue_KeSetEvent(ctx, base);")
        elif name == "KeResetEvent":
            code.append("\txowue_KeResetEvent(ctx, base);")
        elif name == "KeWaitForSingleObject":
            code.append("\txowue_KeWaitForSingleObject(ctx, base);")
        elif name == "KeWaitForMultipleObjects":
            code.append("\txowue_KeWaitForMultipleObjects(ctx, base);")
        elif name == "KeResumeThread":
            code.append("\txowue_KeResumeThread(ctx);")
        elif name == "KeSetAffinityThread":
            code.append("\txowue_KeSetAffinityThread(ctx, base);")
        elif name == "KeSetBasePriorityThread":
            code.append("\txowue_KeSetBasePriorityThread(ctx);")
        elif name == "KeDelayExecutionThread":
            code.append("\txowue_KeDelayExecutionThread(ctx, base);")
        elif name == "XamLoaderTerminateTitle":
            code.append("\txowue_XamLoaderTerminateTitle(ctx);")
        elif name == "NtAllocateVirtualMemory":
            code.append("\txowue_NtAllocateVirtualMemory(ctx, base);")
        elif name == "NtFreeVirtualMemory":
            code.append("\txowue_NtFreeVirtualMemory(ctx, base);")
        elif name == "MmAllocatePhysicalMemoryEx":
            code.append("\txowue_MmAllocatePhysicalMemoryEx(ctx, base);")
        elif name == "MmFreePhysicalMemory":
            code.append("\txowue_MmFreePhysicalMemory(ctx);")
        elif name == "MmGetPhysicalAddress":
            code.append("\txowue_MmGetPhysicalAddress(ctx);")
        elif name == "MmMapIoSpace":
            code.append("\txowue_MmMapIoSpace(ctx);")
        elif name == "ExAllocatePool" or name == "ExAllocatePoolTypeWithTag":
            code.append("\txowue_ExAllocatePool(ctx, base);")
        elif name == "ExFreePool":
            code.append("\txowue_ExFreePool(ctx);")
        elif name == "VdInitializeEngines":
            code.append("\txowue_VdInitializeEngines(ctx);")
        elif name == "VdShutdownEngines":
            code.append("\txowue_VdShutdownEngines();")
        elif name == "VdInitializeRingBuffer":
            code.append("\txowue_VdInitializeRingBuffer(ctx, base);")
        elif name == "VdEnableRingBufferRPtrWriteBack":
            code.append("\txowue_VdEnableRingBufferRPtrWriteBack(ctx);")
        elif name == "VdGetSystemCommandBuffer":
            code.append("\txowue_VdGetSystemCommandBuffer(ctx, base);")
        elif name == "VdSetSystemCommandBufferGpuIdentifierAddress":
            code.append("\txowue_VdSetSystemCommandBufferGpuIdentifierAddress(ctx);")
        elif name == "VdSetGraphicsInterruptCallback":
            code.append("\txowue_VdSetGraphicsInterruptCallback(ctx);")
        elif name == "VdSwap":
            code.append("\txowue_VdSwap(ctx, base);")
        elif name == "VdInitializeScalerCommandBuffer":
            code.append("\txowue_VdInitializeScalerCommandBuffer(ctx, base);")
        elif name == "VdQueryVideoMode":
            code.append("\txowue_VdQueryVideoMode(ctx, base);")
        elif name == "VdQueryVideoFlags":
            code.append("\txowue_VdQueryVideoFlags(ctx);")
        elif name == "VdGetCurrentDisplayGamma":
            code.append("\txowue_VdGetCurrentDisplayGamma(ctx, base);")
        elif name == "VdGetCurrentDisplayInformation":
            code.append("\txowue_VdGetCurrentDisplayInformation(ctx, base);")
        elif name == "VdSetDisplayMode":
            code.append("\txowue_VdSetDisplayMode(ctx);")
        elif name == "VdEnableDisableClockGating":
            code.append("\txowue_VdEnableDisableClockGating(ctx);")
        elif name == "VdIsHSIOTrainingSucceeded":
            code.append("\txowue_VdIsHSIOTrainingSucceeded(ctx);")
        elif name == "VdPersistDisplay":
            code.append("\txowue_VdPersistDisplay(ctx);")
        elif name == "VdRetrainEDRAM":
            code.append("\txowue_VdRetrainEDRAM(ctx);")
        elif name == "VdRetrainEDRAMWorker":
            code.append("\txowue_VdRetrainEDRAMWorker(ctx);")
        elif name == "VdCallGraphicsNotificationRoutines":
            code.append("\txowue_VdCallGraphicsNotificationRoutines(ctx);")
        elif name == "KeGetCurrentProcessType":
            code.append("\txowue_KeGetCurrentProcessType(ctx);")
        elif name == "KeQueryPerformanceFrequency":
            code.append("\txowue_KeQueryPerformanceFrequency(ctx);")
        elif name == "FscSetCacheElementCount":
            code.append("\txowue_FscSetCacheElementCount(ctx);")
        elif name == "NtCreateEvent":
            code.append("\txowue_NtCreateEvent(ctx, base);")
        elif name == "RtlInitializeCriticalSection":
            code.append("\txowue_RtlInitializeCriticalSection(ctx, base);")
        elif name == "RtlInitializeCriticalSectionAndSpinCount":
            code.append("\txowue_RtlInitializeCriticalSectionAndSpinCount(ctx, base);")
        elif name == "RtlEnterCriticalSection":
            code.append("\txowue_RtlEnterCriticalSection(ctx, base);")
        elif name == "RtlTryEnterCriticalSection":
            code.append("\txowue_RtlTryEnterCriticalSection(ctx, base);")
        elif name == "RtlLeaveCriticalSection":
            code.append("\txowue_RtlLeaveCriticalSection(ctx, base);")
        elif name == "XexCheckExecutablePrivilege":
            code.append("\txowue_XexCheckExecutablePrivilege(ctx);")
        elif name == "XGetAVPack":
            code.append("\txowue_XGetAVPack(ctx);")
        elif name == "XGetGameRegion":
            code.append("\txowue_XGetGameRegion(ctx);")
        elif name == "KeTlsAlloc":
            code.append("\txowue_KeTlsAlloc(ctx);")
        elif name == "KeTlsFree":
            code.append("\txowue_KeTlsFree(ctx);")
        elif name == "KeTlsGetValue":
            code.append("\txowue_KeTlsGetValue(ctx);")
        elif name == "KeTlsSetValue":
            code.append("\txowue_KeTlsSetValue(ctx);")
        elif name == "RtlNtStatusToDosError":
            code.append("\txowue_RtlNtStatusToDosError(ctx);")
        elif name == "NtQueryVirtualMemory":
            code.append("\txowue_NtQueryVirtualMemory(ctx, base);")
        elif name == "RtlUnicodeToMultiByteN":
            code.append("\txowue_RtlUnicodeToMultiByteN(ctx, base);")
        elif name == "RtlMultiByteToUnicodeN":
            code.append("\txowue_RtlMultiByteToUnicodeN(ctx, base);")
        elif name == "XamLoaderGetLaunchDataSize":
            code.append("\txowue_XamLoaderGetLaunchDataSize(ctx, base);")
        elif name == "HalReturnToFirmware":
            code.append("\txowue_HalReturnToFirmware(ctx, base);")
        else:
            code.append(f'\txowue_unsupported_import("{name}", ctx);')
        code.extend(["}", ""])
    args.output.write_text("\n".join(code), encoding="utf-8")
    implemented = {
        "NtAllocateVirtualMemory", "NtFreeVirtualMemory", "KeGetCurrentProcessType",
        "MmAllocatePhysicalMemoryEx", "MmFreePhysicalMemory", "MmGetPhysicalAddress", "MmMapIoSpace",
        "ExAllocatePool", "ExAllocatePoolTypeWithTag", "ExFreePool",
        "VdInitializeEngines", "VdShutdownEngines", "VdInitializeRingBuffer",
        "VdEnableRingBufferRPtrWriteBack", "VdGetSystemCommandBuffer",
        "VdSetSystemCommandBufferGpuIdentifierAddress", "VdSetGraphicsInterruptCallback",
        "VdSwap", "VdInitializeScalerCommandBuffer", "VdQueryVideoMode",
        "VdQueryVideoFlags", "VdGetCurrentDisplayGamma", "VdGetCurrentDisplayInformation",
        "VdSetDisplayMode", "VdEnableDisableClockGating", "VdIsHSIOTrainingSucceeded",
        "VdPersistDisplay", "VdRetrainEDRAM", "VdRetrainEDRAMWorker",
        "VdCallGraphicsNotificationRoutines",
        "ExCreateThread", "ExTerminateThread", "ExRegisterTitleTerminateNotification",
        "NtClose", "NtSetEvent", "NtClearEvent", "NtPulseEvent",
        "NtWaitForSingleObjectEx", "NtWaitForMultipleObjectsEx", "NtResumeThread", "NtSuspendThread",
        "KeSetEvent", "KeResetEvent", "KeWaitForSingleObject", "KeWaitForMultipleObjects",
        "KeResumeThread", "KeSetAffinityThread", "KeSetBasePriorityThread", "KeDelayExecutionThread",
        "XamLoaderTerminateTitle",
        "KeQueryPerformanceFrequency",
        "FscSetCacheElementCount",
        "NtCreateEvent",
        "RtlInitializeCriticalSection", "RtlInitializeCriticalSectionAndSpinCount",
        "RtlEnterCriticalSection", "RtlTryEnterCriticalSection", "RtlLeaveCriticalSection",
        "XexCheckExecutablePrivilege",
        "XGetAVPack", "XGetGameRegion",
        "KeTlsAlloc", "KeTlsFree", "KeTlsGetValue", "KeTlsSetValue",
        "RtlNtStatusToDosError",
        "NtQueryVirtualMemory",
        "RtlUnicodeToMultiByteN",
        "RtlMultiByteToUnicodeN",
        "XamLoaderGetLaunchDataSize",
        "HalReturnToFirmware"
    }
    print(f"generated {len(imports)} import adapters ({len(implemented)} implemented, {len(imports) - len(implemented)} fail-closed); marked {len(to_mark)}/{len(addresses)} undecoded words with function entries")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

