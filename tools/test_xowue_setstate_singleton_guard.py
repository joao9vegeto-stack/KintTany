#!/usr/bin/env python3
"""Regression contract for the measured XOWUE singleton SetState self-link stall."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "Runtime/XOWUEEngine.cpp").read_text(
    encoding="utf-8"
)

signature = (
    "static void xowue_trace_hot_guest_entry(uint32_t guestAddress, PPCContext &ctx) {"
)
start = SOURCE.index(signature)
open_brace = SOURCE.index("{", start)
depth = 0
end = None
for position in range(open_brace, len(SOURCE)):
    if SOURCE[position] == "{":
        depth += 1
    elif SOURCE[position] == "}":
        depth -= 1
        if depth == 0:
            end = position + 1
            break
if end is None:
    raise SystemExit("FAIL: unterminated xowue_trace_hot_guest_entry")
BODY = SOURCE[start:end]

checks = {
    "repair is limited to a cycle with exactly one node":
        "cycle && count == 1u && cycleFrom == obj && cycleTo == obj",
    "repair runs only on an actual state transition":
        "oldState != requestedState",
    "repair terminates the PPC walk using its required NULL link":
        "storeGuestBe32(b80Base, obj + 0x28u, 0u);",
    "repair preserves the node's current state field":
        "const uint32_t oldState = loadGuestBe32(b80Base, obj + 0x24u);",
    "repair reports its exact before/after state":
        "XOWUE_B132_SETSTATE_SINGLETON_TERMINATED",
    "multi-node cycles retain the non-mutating diagnostic path":
        "XOWUE_B90_CIRCULAR_LIST_PRESERVED",
}
for label, token in checks.items():
    if token not in BODY:
        raise SystemExit(f"FAIL: {label}")

guard = (
    "cycle && count == 1u && cycleFrom == obj && cycleTo == obj &&\n"
    "                oldState != requestedState"
)
if guard not in BODY:
    raise SystemExit("FAIL: singleton repair guard changed or broadened")
if (
    "storeGuestBe32(b80Base, obj + 0x24u" in BODY
    or "storeGuestBe32(b80Base, obj + 0x98u" in BODY
):
    raise SystemExit("FAIL: repair must not forge state or node flags")
if (
    '"XOWUE_B132_SETSTATE_SINGLETON_TERMINATED"' not in SOURCE
    or '"XOWUE_B132_SETSTATE_SINGLETON_LINK_NORMALIZED"' not in SOURCE
):
    raise SystemExit("FAIL: repaired events must be retained by the runtime trace filter")

print("XOWUE_SETSTATE_SINGLETON_SELF_LINK_CONTRACT_OK")
