#!/usr/bin/env python3
"""Generate fail-closed adapters for imports and the undecoded .text tail."""
from __future__ import annotations
import argparse
import re
from pathlib import Path

IMPORT_RE = re.compile(r"PPC_EXTERN_FUNC\(__imp__([A-Za-z_][A-Za-z_0-9]*)\);")
DECODE_RE = re.compile(r"Unable to decode instruction [0-9A-Fa-f]+ at ([0-9A-Fa-f]+)")
PPC_FUNCTION_RE = re.compile(r"(PPC_FUNC_IMPL\(__imp__sub_([0-9A-Fa-f]{8})\)\s*\{)(?:\s*(xowue_thread_checkpoint\([^)]*\);))?")

COMPATIBILITY_IMPORTS = {
    "DbgBreakPoint",
    "DbgPrint",
    "InterlockedFlushSList",
    "InterlockedPopEntrySList",
    "IoCheckShareAccess",
    "IoCompleteRequest",
    "IoCreateDevice",
    "IoDeleteDevice",
    "IoDismountVolume",
    "IoDismountVolumeByFileHandle",
    "IoInvalidDeviceRequest",
    "IoRemoveShareAccess",
    "IoSetShareAccess",
    "KeBugCheck",
    "KeBugCheckEx",
    "KfAcquireSpinLock",
    "KfLowerIrql",
    "KfReleaseSpinLock",
    "NetDll_WSACleanup",
    "NetDll_WSACreateEvent",
    "NetDll_WSAGetLastError",
    "NetDll_WSASetLastError",
    "NetDll_WSAStartup",
    "NetDll_XNetCleanup",
    "NetDll_XNetDnsLookup",
    "NetDll_XNetDnsRelease",
    "NetDll_XNetGetEthernetLinkStatus",
    "NetDll_XNetGetTitleXnAddr",
    "NetDll_XNetQosListen",
    "NetDll_XNetQosLookup",
    "NetDll_XNetQosRelease",
    "NetDll_XNetRandom",
    "NetDll_XNetRegisterKey",
    "NetDll_XNetServerToInAddr",
    "NetDll_XNetStartup",
    "NetDll_XNetUnregisterKey",
    "NetDll_XNetXnAddrToInAddr",
    "NetDll_accept",
    "NetDll_bind",
    "NetDll_closesocket",
    "NetDll_connect",
    "NetDll_getsockname",
    "NetDll_getsockopt",
    "NetDll_inet_addr",
    "NetDll_ioctlsocket",
    "NetDll_listen",
    "NetDll_recv",
    "NetDll_recvfrom",
    "NetDll_select",
    "NetDll_send",
    "NetDll_sendto",
    "NetDll_setsockopt",
    "NetDll_socket",
    "ObIsTitleObject",
    "ObReferenceObject",
    "RtlRaiseException",
    "RtlUnwind",
    "StfsControlDevice",
    "StfsCreateDevice",
    "XAudioGetSpeakerConfig",
    "XAudioGetVoiceCategoryVolume",
    "XAudioGetVoiceCategoryVolumeChangeMask",
    "XAudioRegisterRenderDriverClient",
    "XAudioSubmitRenderDriverFrame",
    "XAudioUnregisterRenderDriverClient",
    "XMACreateContext",
    "XMAReleaseContext",
    "XMsgCancelIORequest",
    "XMsgInProcessCall",
    "XMsgStartIORequest",
    "XMsgStartIORequestEx",
    "XNetLogonGetTitleID",
    "XNotifyGetNext",
    "XNotifyPositionUI",
    "XamAlloc",
    "XamContentCreateEnumerator",
    "XamContentCreateEx",
    "XamContentGetDeviceData",
    "XamContentGetDeviceState",
    "XamContentGetLicenseMask",
    "XamCreateEnumeratorHandle",
    "XamEnumerate",
    "XamFree",
    "XamGetPrivateEnumStructureFromHandle",
    "XamLoaderGetLaunchData",
    "XamLoaderLaunchTitle",
    "XamNotifyCreateListener",
    "XamSessionCreateHandle",
    "XamSessionRefObjByHandle",
    "XamShowAchievementsUI",
    "XamShowCustomPlayerListUI",
    "XamShowDeviceSelectorUI",
    "XamShowDirtyDiscErrorUI",
    "XamShowFriendRequestUI",
    "XamShowFriendsUI",
    "XamShowGameInviteUI",
    "XamShowGamerCardUIForXUID",
    "XamShowKeyboardUI",
    "XamShowMarketplaceUI",
    "XamShowMessageBoxUIEx",
    "XamShowMessageComposeUI",
    "XamShowMessagesUI",
    "XamShowPlayerReviewUI",
    "XamShowPlayersUI",
    "XamShowSigninUI",
    "XamTaskCloseHandle",
    "XamTaskSchedule",
    "XamTaskShouldExit",
    "XamUserAreUsersFriends",
    "XamUserCheckPrivilege",
    "XamUserCreateAchievementEnumerator",
    "XamUserCreateStatsEnumerator",
    "XamUserGetName",
    "XamUserGetSigninInfo",
    "XamUserGetSigninState",
    "XamUserGetXUID",
    "XamUserReadProfileSettings",
    "XamUserWriteProfileSettings",
    "XamVoiceClose",
    "XamVoiceCreate",
    "XamVoiceHeadsetPresent",
    "XamVoiceSubmitPacket",
    "XamWriteGamerTile",
    "XeCryptSha",
    "XeKeysConsolePrivateKeySign",
    "XeKeysConsoleSignatureVerification",
    "XexGetModuleHandle",
    "XexGetModuleSection",
    "XexGetProcedureAddress",
    "__C_specific_handler",
    "_snprintf",
    "_vsnprintf",
    "sprintf",
}


def instrument_aot_entries(contents: str) -> tuple[str, int]:
    instrumented = 0

    def add_checkpoint(match: re.Match[str]) -> str:
        nonlocal instrumented
        instrumented += 1
        guest_address = int(match.group(2), 16)
        checkpoint = f"xowue_thread_checkpoint(0x{guest_address:08X}u);"
        return match.group(1) + chr(10) + chr(9) + checkpoint

    return PPC_FUNCTION_RE.sub(add_checkpoint, contents), instrumented


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", required=True, type=Path)
    parser.add_argument("--recompile-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runtime-source", required=True, type=Path)
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
        contents, instrumented = instrument_aot_entries(contents)
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
            if instrumented and "extern void xowue_thread_checkpoint(uint32_t);" not in contents:
                declarations.append("extern void xowue_thread_checkpoint(uint32_t);")
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
            'void xowue_thread_checkpoint(uint32_t);',
            'void xowue_compat_import(const char *, PPCContext &, uint8_t *);',
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
            'void xowue_ObReferenceObjectByHandle(PPCContext &, uint8_t *);',
            'void xowue_ObDereferenceObject(PPCContext &);',
            'void xowue_ObOpenObjectByPointer(PPCContext &, uint8_t *);',
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
            'void xowue_XGetVideoMode(PPCContext &, uint8_t *);',
            'void xowue_ExGetXConfigSetting(PPCContext &, uint8_t *);',
            'void xowue_XInputGetState(PPCContext &, uint8_t *);',
            'void xowue_XamInputGetState(PPCContext &, uint8_t *);',
            'void xowue_XInputGetCapabilities(PPCContext &, uint8_t *);',
            'void xowue_XamInputGetCapabilities(PPCContext &, uint8_t *);',
            'void xowue_XamInputGetCapabilitiesEx(PPCContext &, uint8_t *);',
            'void xowue_XInputSetState(PPCContext &, uint8_t *);',
            'void xowue_XamInputSetState(PPCContext &, uint8_t *);',
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
            'void xowue_KiApcNormalRoutineNop(PPCContext &);',
            'void xowue_KeEnterCriticalRegion(PPCContext &, uint8_t *);',
            'void xowue_KeLeaveCriticalRegion(PPCContext &, uint8_t *);',
            'void xowue_KeRaiseIrqlToDpcLevel(PPCContext &);',
            'void xowue_KeAcquireSpinLockAtRaisedIrql(PPCContext &, uint8_t *);',
            'void xowue_KeReleaseSpinLockFromRaisedIrql(PPCContext &, uint8_t *);',
            'void xowue_KeLockL2(PPCContext &);',
            'void xowue_KeUnlockL2(PPCContext &);',
            'void xowue_KeEnableFpuExceptions(PPCContext &);',
            'void xowue_KeQuerySystemTime(PPCContext &, uint8_t *);',
            'void xowue_KeInitializeSemaphore(PPCContext &, uint8_t *);',
            'void xowue_KeReleaseSemaphore(PPCContext &, uint8_t *);',
            'void xowue_NtCreateSemaphore(PPCContext &, uint8_t *);',
            'void xowue_NtReleaseSemaphore(PPCContext &, uint8_t *);',
            'void xowue_NtCreateMutant(PPCContext &, uint8_t *);',
            'void xowue_NtReleaseMutant(PPCContext &);',
            'void xowue_NtCreateTimer(PPCContext &, uint8_t *);',
            'void xowue_NtSetTimerEx(PPCContext &, uint8_t *);',
            'void xowue_NtCancelTimer(PPCContext &, uint8_t *);',
            'void xowue_NtCreateFile(PPCContext &, uint8_t *);',
            'void xowue_NtOpenFile(PPCContext &, uint8_t *);',
            'void xowue_NtReadFile(PPCContext &, uint8_t *);',
            'void xowue_NtWriteFile(PPCContext &, uint8_t *);',
            'void xowue_NtReadFileScatter(PPCContext &, uint8_t *);',
            'void xowue_NtQueryInformationFile(PPCContext &, uint8_t *);',
            'void xowue_NtQueryFullAttributesFile(PPCContext &, uint8_t *);',
            'void xowue_NtQueryDirectoryFile(PPCContext &, uint8_t *);',
            'void xowue_NtQueryVolumeInformationFile(PPCContext &, uint8_t *);',
            'void xowue_NtSetInformationFile(PPCContext &, uint8_t *);',
            'void xowue_NtFlushBuffersFile(PPCContext &, uint8_t *);',
            'void xowue_NtDeviceIoControlFile(PPCContext &, uint8_t *);',
            'void xowue_NtDuplicateObject(PPCContext &, uint8_t *);',
            'void xowue_MmQueryAddressProtect(PPCContext &);',
            'void xowue_MmSetAddressProtect(PPCContext &);',
            'void xowue_MmQueryStatistics(PPCContext &, uint8_t *);',
            'void xowue_RtlCompareMemoryUlong(PPCContext &, uint8_t *);',
            'void xowue_RtlCompareStringN(PPCContext &, uint8_t *);',
            'void xowue_RtlFillMemoryUlong(PPCContext &, uint8_t *);',
            'void xowue_RtlFreeAnsiString(PPCContext &, uint8_t *);',
            'void xowue_RtlInitAnsiString(PPCContext &, uint8_t *);',
            'void xowue_RtlInitUnicodeString(PPCContext &, uint8_t *);',
            'void xowue_RtlUnicodeStringToAnsiString(PPCContext &, uint8_t *);',
            'void xowue_RtlUpcaseUnicodeChar(PPCContext &);',
            'void xowue_RtlTimeFieldsToTime(PPCContext &, uint8_t *);',
            'void xowue_RtlTimeToTimeFields(PPCContext &, uint8_t *);',
            'void xowue_ObCreateSymbolicLink(PPCContext &, uint8_t *);',
            'void xowue_ObDeleteSymbolicLink(PPCContext &, uint8_t *);',
            'void xowue_XamGetExecutionId(PPCContext &, uint8_t *);',
            'void xowue_XamGetSystemVersion(PPCContext &);',
            'void xowue_XGetLanguage(PPCContext &);',
            'void xowue_RtlImageXexHeaderField(PPCContext &);',
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
        elif name == "NtCreateFile":
            code.append("\txowue_NtCreateFile(ctx, base);")
        elif name == "NtOpenFile":
            code.append("\txowue_NtOpenFile(ctx, base);")
        elif name == "NtReadFile":
            code.append("\txowue_NtReadFile(ctx, base);")
        elif name == "NtWriteFile":
            code.append("\txowue_NtWriteFile(ctx, base);")
        elif name == "NtReadFileScatter":
            code.append("\txowue_NtReadFileScatter(ctx, base);")
        elif name == "NtQueryInformationFile":
            code.append("\txowue_NtQueryInformationFile(ctx, base);")
        elif name == "NtQueryFullAttributesFile":
            code.append("\txowue_NtQueryFullAttributesFile(ctx, base);")
        elif name == "NtQueryDirectoryFile":
            code.append("\txowue_NtQueryDirectoryFile(ctx, base);")
        elif name == "NtQueryVolumeInformationFile":
            code.append("\txowue_NtQueryVolumeInformationFile(ctx, base);")
        elif name == "NtSetInformationFile":
            code.append("\txowue_NtSetInformationFile(ctx, base);")
        elif name == "NtFlushBuffersFile":
            code.append("\txowue_NtFlushBuffersFile(ctx, base);")
        elif name == "NtDeviceIoControlFile":
            code.append("\txowue_NtDeviceIoControlFile(ctx, base);")
        elif name == "NtDuplicateObject":
            code.append("\txowue_NtDuplicateObject(ctx, base);")
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
        elif name == "KeEnterCriticalRegion":
            code.append("\txowue_KeEnterCriticalRegion(ctx, base);")
        elif name == "KeLeaveCriticalRegion":
            code.append("\txowue_KeLeaveCriticalRegion(ctx, base);")
        elif name == "KeRaiseIrqlToDpcLevel":
            code.append("\txowue_KeRaiseIrqlToDpcLevel(ctx);")
        elif name == "KeAcquireSpinLockAtRaisedIrql":
            code.append("\txowue_KeAcquireSpinLockAtRaisedIrql(ctx, base);")
        elif name == "KeReleaseSpinLockFromRaisedIrql":
            code.append("\txowue_KeReleaseSpinLockFromRaisedIrql(ctx, base);")
        elif name == "KeLockL2":
            code.append("\txowue_KeLockL2(ctx);")
        elif name == "KeUnlockL2":
            code.append("\txowue_KeUnlockL2(ctx);")
        elif name == "KeEnableFpuExceptions":
            code.append("\txowue_KeEnableFpuExceptions(ctx);")
        elif name == "KeQuerySystemTime":
            code.append("\txowue_KeQuerySystemTime(ctx, base);")
        elif name == "KeInitializeSemaphore":
            code.append("\txowue_KeInitializeSemaphore(ctx, base);")
        elif name == "KeReleaseSemaphore":
            code.append("\txowue_KeReleaseSemaphore(ctx, base);")
        elif name == "NtCreateSemaphore":
            code.append("\txowue_NtCreateSemaphore(ctx, base);")
        elif name == "NtReleaseSemaphore":
            code.append("\txowue_NtReleaseSemaphore(ctx, base);")
        elif name == "NtCreateMutant":
            code.append("\txowue_NtCreateMutant(ctx, base);")
        elif name == "NtReleaseMutant":
            code.append("\txowue_NtReleaseMutant(ctx);")
        elif name == "NtCreateTimer":
            code.append("\txowue_NtCreateTimer(ctx, base);")
        elif name == "NtSetTimerEx":
            code.append("\txowue_NtSetTimerEx(ctx, base);")
        elif name == "NtCancelTimer":
            code.append("\txowue_NtCancelTimer(ctx, base);")
        elif name == "MmQueryAddressProtect":
            code.append("\txowue_MmQueryAddressProtect(ctx);")
        elif name == "MmSetAddressProtect":
            code.append("\txowue_MmSetAddressProtect(ctx);")
        elif name == "MmQueryStatistics":
            code.append("\txowue_MmQueryStatistics(ctx, base);")
        elif name == "RtlCompareMemoryUlong":
            code.append("\txowue_RtlCompareMemoryUlong(ctx, base);")
        elif name == "RtlCompareStringN":
            code.append("\txowue_RtlCompareStringN(ctx, base);")
        elif name == "RtlFillMemoryUlong":
            code.append("\txowue_RtlFillMemoryUlong(ctx, base);")
        elif name == "RtlFreeAnsiString":
            code.append("\txowue_RtlFreeAnsiString(ctx, base);")
        elif name == "RtlInitAnsiString":
            code.append("\txowue_RtlInitAnsiString(ctx, base);")
        elif name == "RtlInitUnicodeString":
            code.append("\txowue_RtlInitUnicodeString(ctx, base);")
        elif name == "RtlUnicodeStringToAnsiString":
            code.append("\txowue_RtlUnicodeStringToAnsiString(ctx, base);")
        elif name == "RtlUpcaseUnicodeChar":
            code.append("\txowue_RtlUpcaseUnicodeChar(ctx);")
        elif name == "RtlTimeFieldsToTime":
            code.append("\txowue_RtlTimeFieldsToTime(ctx, base);")
        elif name == "RtlTimeToTimeFields":
            code.append("\txowue_RtlTimeToTimeFields(ctx, base);")
        elif name == "RtlImageXexHeaderField":
            code.append("\txowue_RtlImageXexHeaderField(ctx);")
        elif name == "ObCreateSymbolicLink":
            code.append("\txowue_ObCreateSymbolicLink(ctx, base);")
        elif name == "ObDeleteSymbolicLink":
            code.append("\txowue_ObDeleteSymbolicLink(ctx, base);")
        elif name == "XamGetExecutionId":
            code.append("\txowue_XamGetExecutionId(ctx, base);")
        elif name == "XamGetSystemVersion":
            code.append("\txowue_XamGetSystemVersion(ctx);")
        elif name == "XGetLanguage":
            code.append("\txowue_XGetLanguage(ctx);")
        elif name == "FscSetCacheElementCount":
            code.append("\txowue_FscSetCacheElementCount(ctx);")
        elif name == "NtCreateEvent":
            code.append("\txowue_NtCreateEvent(ctx, base);")
        elif name == "ObReferenceObjectByHandle":
            code.append("\txowue_ObReferenceObjectByHandle(ctx, base);")
        elif name == "ObDereferenceObject":
            code.append("\txowue_ObDereferenceObject(ctx);")
        elif name == "ObOpenObjectByPointer":
            code.append("\txowue_ObOpenObjectByPointer(ctx, base);")
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
        elif name == "XGetVideoMode":
            code.append("\txowue_XGetVideoMode(ctx, base);")
        elif name == "ExGetXConfigSetting":
            code.append("\txowue_ExGetXConfigSetting(ctx, base);")
        elif name == "XInputGetState":
            code.append("\txowue_XInputGetState(ctx, base);")
        elif name == "XamInputGetState":
            code.append("\txowue_XamInputGetState(ctx, base);")
        elif name == "XInputGetCapabilities":
            code.append("\txowue_XInputGetCapabilities(ctx, base);")
        elif name == "XamInputGetCapabilities":
            code.append("\txowue_XamInputGetCapabilities(ctx, base);")
        elif name == "XamInputGetCapabilitiesEx":
            code.append("\txowue_XamInputGetCapabilitiesEx(ctx, base);")
        elif name == "XInputSetState":
            code.append("\txowue_XInputSetState(ctx, base);")
        elif name == "XamInputSetState":
            code.append("\txowue_XamInputSetState(ctx, base);")
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
        elif name in ("KiApcNormalRoutineNop", "KiApcNormalRoutineNop_"):
            code.append("\txowue_KiApcNormalRoutineNop(ctx);")
        elif name == "HalReturnToFirmware":
            code.append("\txowue_HalReturnToFirmware(ctx, base);")
        else:
            if name not in COMPATIBILITY_IMPORTS:
                raise SystemExit(f"unclassified XEX import: {name}")
            code.append(f'\txowue_compat_import("{name}", ctx, base);')
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
        "KeEnterCriticalRegion", "KeLeaveCriticalRegion", "KeRaiseIrqlToDpcLevel",
        "KeAcquireSpinLockAtRaisedIrql", "KeReleaseSpinLockFromRaisedIrql",
        "KeLockL2", "KeUnlockL2", "KeEnableFpuExceptions", "KeQuerySystemTime",
        "KeInitializeSemaphore", "KeReleaseSemaphore", "NtCreateSemaphore", "NtReleaseSemaphore",
        "NtCreateMutant", "NtReleaseMutant", "NtCreateTimer", "NtSetTimerEx", "NtCancelTimer",
        "NtCreateFile", "NtOpenFile", "NtReadFile", "NtWriteFile", "NtReadFileScatter",
        "NtQueryInformationFile", "NtQueryFullAttributesFile", "NtQueryDirectoryFile",
        "NtQueryVolumeInformationFile", "NtSetInformationFile", "NtFlushBuffersFile",
        "NtDeviceIoControlFile", "NtDuplicateObject", "MmQueryAddressProtect",
        "MmSetAddressProtect", "MmQueryStatistics", "RtlCompareMemoryUlong",
        "RtlCompareStringN", "RtlFillMemoryUlong", "RtlFreeAnsiString", "RtlInitAnsiString",
        "RtlInitUnicodeString", "RtlUnicodeStringToAnsiString", "RtlUpcaseUnicodeChar",
        "RtlTimeFieldsToTime", "RtlTimeToTimeFields", "ObCreateSymbolicLink", "ObDeleteSymbolicLink",
        "RtlImageXexHeaderField", "XamGetExecutionId", "XamGetSystemVersion", "XGetLanguage",
        "FscSetCacheElementCount",
        "NtCreateEvent",
        "ObReferenceObjectByHandle", "ObDereferenceObject", "ObOpenObjectByPointer",
        "RtlInitializeCriticalSection", "RtlInitializeCriticalSectionAndSpinCount",
        "RtlEnterCriticalSection", "RtlTryEnterCriticalSection", "RtlLeaveCriticalSection",
        "XexCheckExecutablePrivilege",
        "XGetAVPack", "XGetGameRegion", "XGetVideoMode", "ExGetXConfigSetting",
        "XInputGetState", "XamInputGetState", "XInputGetCapabilities",
        "XamInputGetCapabilities", "XamInputGetCapabilitiesEx",
        "XInputSetState", "XamInputSetState",
        "KeTlsAlloc", "KeTlsFree", "KeTlsGetValue", "KeTlsSetValue",
        "RtlNtStatusToDosError",
        "NtQueryVirtualMemory",
        "RtlUnicodeToMultiByteN",
        "RtlMultiByteToUnicodeN",
        "XamLoaderGetLaunchDataSize",
        "KiApcNormalRoutineNop", "KiApcNormalRoutineNop_",
        "HalReturnToFirmware"
    }
    imported_set = set(imports)
    unclassified = imported_set - implemented - COMPATIBILITY_IMPORTS
    stale_compat = COMPATIBILITY_IMPORTS - imported_set
    if unclassified or stale_compat:
        raise SystemExit(
            f"import contract mismatch: unclassified={sorted(unclassified)}, "
            f"stale_compat={sorted(stale_compat)}"
        )
    runtime_source = args.runtime_source.read_text(encoding="utf-8")
    compat_start = runtime_source.find("void xowue_compat_import(")
    compat_end = runtime_source.find("\nvoid xowue_ExCreateThread", compat_start)
    socket_start = runtime_source.find("static bool handleNetDllSocketImport(")
    socket_end = runtime_source.find("\n}\n", socket_start)
    if min(compat_start, compat_end, socket_start, socket_end) < 0:
        raise SystemExit("runtime compatibility dispatch or socket router is missing")
    compat_dispatch = runtime_source[compat_start:compat_end]
    socket_dispatch = runtime_source[socket_start:socket_end + 3]
    missing_compat = set()
    for name in COMPATIBILITY_IMPORTS:
        if name.startswith("NetDll_") and not name.startswith("NetDll_XNet"):
            routed = (
                "handleNetDllSocketImport(api, context, base)" in compat_dispatch
                and re.search(rf'api\s*==\s*"{re.escape(name)}"', socket_dispatch)
            )
        elif name.startswith("XamShow"):
            routed = 'api.rfind("XamShow", 0u)' in compat_dispatch
        else:
            routed = re.search(rf'api\s*==\s*"{re.escape(name)}"', compat_dispatch)
        if not routed:
            missing_compat.add(name)
    if missing_compat:
        raise SystemExit(
            f"compatibility imports lack a dispatch route: {sorted(missing_compat)}"
        )
    implemented_imports = len(set(imports) & implemented)
    print(f"generated {len(imports)} import adapters ({implemented_imports} explicit handlers, {len(imports) - implemented_imports} classified runtime compatibility handlers); marked {len(to_mark)}/{len(addresses)} undecoded words with function entries")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

