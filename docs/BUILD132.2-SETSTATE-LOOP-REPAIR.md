# XOWUE Build 132.2 — one-node SetState cycle recovery

## Device evidence from Build 132.1

The main PPC thread is captured at `0x824ACC1C`, inside the loop beginning at `0x824ACBF8`. The routine reads the node's `+0x28` next pointer and repeats until that pointer is zero.

The B80 diagnostics show the exact non-terminating shape:
- node: `0x40850618`
- next: `0x40850618` (self-reference)
- nodes visited: 1
- `+0x24` old state: `0xFFFFFFFF`
- requested state on the second call: `0x00000000`
- `+0x98` flags: `0x00000000`

The first call does not change state. The second requests a real state transition and never leaves the self-link loop. This is a guest-structure defect that a successful IPA build or a host video present cannot expose.

## Runtime correction

At the `0x824ACBF8` entry checkpoint, XOWUE now normalizes only the exact measured shape:
- the traversal has one node;
- that node points to itself;
- the node is the input object;
- the requested state differs from the stored state.

For this one case, `+0x28` is set to zero, so the original PPC routine processes that node once, evaluates its original `+0x98` flags, invokes its original callback path as written, and commits the requested state. The node contents and state are not fabricated. Multi-node cycles, unrelated circular lists, and no-op state requests are not rewritten.

The runtime persists the old link, old state, requested state, flags, node address, and guest thread in `XOWUE_B132_SETSTATE_SINGLETON_TERMINATED`. CI has a source-contract regression that rejects widening the repair or changing the node state/flags directly.

## Separate rendering and guest-memory writeback observations

The Build 132.1 capture does **not** establish that the entire renderer is black:
- the first sampled GPU readback is black (`sampled_nonblack=0`);
- subsequent readbacks contain about 8,160 non-black samples out of 8,209, consistent with the visible production-logo sequence in the recording;
- the EDRAM resolve path reports `copied_to_swapchain=1` repeatedly;
- however, the separate writeback into Xbox guest memory reports `XENOS_GUEST_RESOLVE_WRITEBACK ... status=0` on all 1,286 attempts in the captured log;
- the guest-content-update counter remains zero, so host presentation and non-black GPU samples are not proof that the game menu is being rendered.

The exact reason that guest-memory writeback returns false is not identified by this build: the function rejects several frontbuffer descriptor/address/size mismatches without a per-condition trace. It remains a separate item to diagnose after the main PPC state loop is released. It is not established as the cause of the SetState stall.

The actual menu acceptance test still requires the main PPC thread to leave `0x824ACC1C`, guest state to advance, the real Wolverine menu to appear, and the menu to respond to input on-device.
