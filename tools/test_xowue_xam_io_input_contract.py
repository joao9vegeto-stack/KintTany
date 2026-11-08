#!/usr/bin/env python3
"""Guard XOWUE's XAM overlapped completion ABI and one-pad iOS input mapping."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = (ROOT / "Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


helper_start = ENGINE.index("static void xowueCompleteXamOverlappedImmediate(\n")
helper_end = ENGINE.index("\n}\n", helper_start) + 3
helper = ENGINE[helper_start:helper_end]

# XAM XOVERLAPPED/XOVERLAPPED is seven big-endian DWORDs (0x1C bytes).
require("validGuestRange(overlapped, 0x1Cu)" in helper,
        "completion must validate the complete 28-byte XOVERLAPPED")
for offset in ("0x00u", "0x04u", "0x08u", "0x18u"):
    require(f"PPC_STORE_U32(overlapped + {offset}," in helper,
            f"completion must write the XOVERLAPPED field at +{offset}")
require("PPC_LOAD_U32(overlapped + 0x0Cu)" in helper,
        "the event handle must be read from XOVERLAPPED +0x0C")
require("PPC_LOAD_U32(overlapped + 0x10u)" in helper,
        "the completion routine must be read from XOVERLAPPED +0x10")
require("queueGuestApc(completionThread, completionRoutine, status," in helper and
        "length, overlapped);" in helper,
        "completion APC arguments must be result, length and overlapped pointer")
require("PPC_STORE_U32(overlapped + 0x0Cu" not in helper,
        "completion must preserve the caller's event handle")
require("PPC_STORE_U32(overlapped + 0x14u" not in helper,
        "completion must preserve the caller's completion context")
require("status == kNtStatusSuccess ? 0u : 0xFFFFFFFFu" in helper,
        "immediate completion length must follow Xenia/ReXGlue semantics")

profile_start = ENGINE.index("static void xowueHandleXamUserReadProfileSettings(")
profile_end = ENGINE.index("static void xowueCompleteXamOverlappedImmediate(", profile_start)
profile = ENGINE[profile_start:profile_end]
require("validGuestRange(overlapped,0x1Cu)" in profile and
        "xowueCompleteXamOverlappedImmediate(base,overlapped,status)" in profile,
        "XAM profile reads must use the shared completion contract and full record size")

compat_start = ENGINE.index("void xowue_compat_import(")
compat = ENGINE[compat_start:]
device_start = compat.index('if (api == "XamContentGetDeviceState")')
device_end = compat.index('if (api == "XamContentGetDeviceData")', device_start)
device = compat[device_start:device_end]
require("validGuestRange(overlapped, 0x1Cu)" in device and
        "xowueCompleteXamOverlappedImmediate(base, overlapped, status)" in device,
        "XamContentGetDeviceState must complete through the same XOVERLAPPED helper")
msg_start = compat.index('if (api == "XMsgStartIORequest" || api == "XMsgStartIORequestEx" ||')
msg_end = compat.index('if (api == "XexGetModuleHandle")', msg_start)
messages = compat[msg_start:msg_end]
require("validGuestRange(overlapped, 0x1Cu)" in messages and
        "xowueCompleteXamOverlappedImmediate(base,overlapped,result)" in messages,
        "XMsgStartIORequest must complete through the same XOVERLAPPED helper")
write_start = compat.index('if (api == "XamUserWriteProfileSettings")')
write_end = compat.index('if (api == "XamContentGetLicenseMask")', write_start)
write_settings = compat[write_start:write_end]
require("validGuestRange(overlapped,0x1Cu)" in write_settings and
        "xowueCompleteXamOverlappedImmediate(base,overlapped,status)" in write_settings,
        "XamUserWriteProfileSettings must use the full shared completion contract")

# The UI exposes exactly one virtual/physical gamepad: Xbox user 0.
queue_start = ENGINE.index("static void queueTouchKeystrokeTransitions")
queue_end = ENGINE.index('extern "C" void xowue_set_touch_controller_state', queue_start)
queue = ENGINE[queue_start:queue_end]
require("g_guestInputKeystrokeQueues[0u]" in queue and
        "queue.push_back({virtualKey, 0u, flags, 0u, 0u})" in queue,
        "button edges must be assigned to the sole connected Xbox user 0")
require("for (uint8_t user = 0; user < 4u; ++user)" not in queue,
        "the same controller edge must not be broadcast to four user queues")

caps_start = ENGINE.index("static uint32_t writeTouchGamepadCapabilities")
caps_end = ENGINE.index("static void traceXowueInputImport", caps_start)
caps = ENGINE[caps_start:caps_end]
require("PPC_STORE_U16(address + 4u, 0xF3FFu)" in caps,
        "XInput capabilities must advertise documented buttons, not reserved bits")

state_start = ENGINE.index("static uint32_t writeTouchGamepadState")
state_end = ENGINE.index("static uint32_t writeTouchGamepadCapabilities", state_start)
state = ENGINE[state_start:state_end]
for field in ("PPC_STORE_U32(address, state.packetNumber)",
              "PPC_STORE_U16(address + 4u, static_cast<uint16_t>(state.buttons))",
              "base[address + 6u] = state.leftTrigger",
              "base[address + 7u] = state.rightTrigger",
              "PPC_STORE_U16(address + 8u, static_cast<uint16_t>(state.leftX))",
              "PPC_STORE_U16(address + 10u, static_cast<uint16_t>(state.leftY))",
              "PPC_STORE_U16(address + 12u, static_cast<uint16_t>(state.rightX))",
              "PPC_STORE_U16(address + 14u, static_cast<uint16_t>(state.rightY))"):
    require(field in state, "XINPUT_STATE must preserve its documented field layout: " + field)

print("XOWUE_XAM_OVERLAPPED_AND_INPUT_CONTRACT_OK")
