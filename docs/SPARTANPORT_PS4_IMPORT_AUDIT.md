PS4 import audit
================

The AOT linker currently leaves some PS4 imports unresolved. CI cross-references their NID plus library identity against the pinned shadPS4 LIB_FUNCTION registry. It records names, source locations, and the pinned reference revision only; it does not compile or link shadPS4.

A registry match is not an implementation and is not permission to return a placeholder value. The native iOS runtime must provide a PS4-ABI-compatible service, with correct memory, threading, lifecycle, and error semantics, before the corresponding import can be marked resolved.
