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

## Separate blocker: guest rendering remains black

Build 132.1 also reports:
- 26 native draws submitted and a guest swap;
- Xenos EDRAM color/depth target state with missing/zero target fields in the initial draw sequence;
- GPU readback `sampled_nonblack=0` with a stable black checksum;
- repeated host presents are not new guest content frames.

This commit does not pretend that the SetState repair solves the Xenos renderer. The actual menu acceptance test still requires changing non-black guest pixels, continued VdSwap progression after the transition, and the real Wolverine menu on-device.
