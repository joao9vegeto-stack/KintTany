#!/usr/bin/env python3
"""Guard the Xbox 360 NtQueryDirectoryFile ABI and directory record layout."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


struct_start = ENGINE.index("struct GuestFile {")
struct_end = ENGINE.index("\n};", struct_start)
guest_file = ENGINE[struct_start:struct_end]
require('std::string directoryPattern = "*";' in guest_file,
        "directory handles must retain the active wildcard rule between calls")
require("bool directoryEnumerated = false;" in guest_file,
        "an empty directory must not be re-enumerated forever on continuation")

fn_start = ENGINE.index("void xowue_NtQueryDirectoryFile(PPCContext &context, uint8_t *base) {")
fn_end = ENGINE.index("\nvoid xowue_NtQueryVolumeInformationFile(", fn_start)
query = ENGINE[fn_start:fn_end]

require("const uint32_t namePointer = context.r10.u32;" in query,
        "Xbox 360 NtQueryDirectoryFile takes ANSI_STRING* FileName in r10")
require("const uint32_t restart = guestStackArgument(context, base, 9u);" in query,
        "RestartScan is the ninth argument and must be read from the PPC stack")
require("guestStackArgument(context, base, 10u)" not in query,
        "there is no tenth NtQueryDirectoryFile argument")
require("readGuestAnsiString(base, namePointer, pattern)" in query,
        "r10 must be parsed as an Xbox ANSI_STRING descriptor")
require("file->directoryPattern = pattern;" in query and
        "guestWildcardMatch(file->directoryPattern" in query,
        "a null FileName continuation must retain the previous wildcard rule")
require("if (!file->directoryEnumerated || restart != 0u)" in query,
        "the directory must be enumerated initially and restart must reset it")
require("? 0xC000000Fu" in query and ": 0x80000006u" in query,
        "a missing new pattern and an exhausted continuation have distinct NT statuses")
require("const uint32_t fileNameBytes = static_cast<uint32_t>(leaf.size());" in query,
        "Xbox directory entry filename length is a byte count")
require("PPC_STORE_U32(output + 60u, fileNameBytes);" in query and
        "std::memcpy(base + output + 64u, leaf.data(), fileNameBytes);" in query,
        "FILE_DIRECTORY_INFORMATION filename must be copied as ANSI bytes, not UTF-16")
require("storeGuestBe16(base, output + 64u" not in query and
        "utf16Bytes" not in query,
        "the runtime must not serialize the Xbox ANSI filename as UTF-16")
require("PPC_STORE_U32(output + 4u, static_cast<uint32_t>(file->directoryCursor));" in query,
        "FILE_DIRECTORY_INFORMATION must include the incremented file index")
require("isDirectory ? 0x10u : 0x80u" in query,
        "directory entries must use FILE_ATTRIBUTE_DIRECTORY/NORMAL")

print("XOWUE_NT_QUERY_DIRECTORY_ABI_OK")
