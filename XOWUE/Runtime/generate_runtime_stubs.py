#!/usr/bin/env python3
"""Generate fail-closed adapters for imports and the undecoded .text tail."""
from __future__ import annotations
import argparse
import re
from pathlib import Path

IMPORT_RE = re.compile(r"PPC_EXTERN_FUNC\(__imp__([A-Za-z_][A-Za-z_0-9]*)\);")
DECODE_RE = re.compile(r"Unable to decode instruction [0-9A-Fa-f]+ at ([0-9A-Fa-f]+)")


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
            contents = contents.replace(
                '#include "ppc_recomp_shared.h"',
                '#include "ppc_recomp_shared.h"\nextern void xowue_untranslated_tail(uint32_t);',
                1,
            )
            source.write_text(contents, encoding="utf-8")
    if pending:
        missing = ", ".join(f"0x{address:08X}" for address in sorted(pending))
        raise SystemExit(f"no generated placeholder found for mapped undecoded words: {missing}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    code = ['#include "ppc_recomp_shared.h"',
            '[[noreturn]] void xowue_unsupported_import(const char *, const PPCContext &);',
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
            '[[noreturn]] void xowue_HalReturnToFirmware(PPCContext &, uint8_t *);', '']
    for name in imports:
        code.append(f"PPC_FUNC(__imp__{name}) {{")
        if name == "NtAllocateVirtualMemory":
            code.append("\txowue_NtAllocateVirtualMemory(ctx, base);")
        elif name == "NtFreeVirtualMemory":
            code.append("\txowue_NtFreeVirtualMemory(ctx, base);")
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
