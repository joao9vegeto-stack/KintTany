# FAIRY2 — corrected two producers of the KTGL 2 GiB region

Device report, November 22 2026: bin47 allocator was valid until change 269 where an invalid pointer was written; this was a table-wide overwrite, not a memory-pressure fault.

Old sequential Mac allocator measurements (run 44986356916) show eight regions (MiB): 300, 200, 260, 192, 96, 1280, 304, 10.
First five sum to 1048 MiB. At iPhone guest root 0x32c000000, the old 1280MiB region begins 0x36d800000 and ENDS 0x3bd800000, exactly where the next 304MiB region stores its allocator bin table.
User log shows real NVN memory pool 0x3816ac000 + 0x50a00000 (1290 MiB), ending 0x3d20ac000, 0x148ac000 (328.671875 MiB) beyond previous allocation and into following region; this explains entire free-bin metadata overwrite.

Previous Fairy2iOS patch 1.25GiB at both guest site offsets main+0x21b6924 and main+0x21b6954 was erroneous. The internal child spans up to 2GiB and must reserve that full length.
Both sites use MOVZ #0x14000000 followed by shift left 2, yielding old 0x50000000; patched MOVZ #0x20000000 yields new 0x80000000.
New sixth region: 0x36d800000 .. 0x3ed800000; old NVN pool ends 0x3d20ac000, giving a 0x1b754000 buffer before next region.
304MiB seventh and 10MiB eighth remain contiguous and end at 0x401200000; full 4GiB root ends at 0x42c000000, leaving 0x2ae00000 spare (~682MiB).

This is an increase in reserved VIRTUAL bytes, not resident RAM, and does not require changing HLE SVC mapping or removing correct NVN device-shared guards.
New iPhone bin47 instrumentation watches alias+0xc5800178 corresponding to new metadata location; old +0x95800178 would watch the GPU pool and be misleading.
One host-only iOS repack modifies exactly two ARM64 instructions, keeps native code/shader hashes and externally mounted 14,770 RomFS entries and 16 DLC.
Pass criteria: correct exact guest SHA/opcodes, source IPA SHA, unique artifact SHA, ZIP CRC, Metal image SHA, settings for 30/60 and A/B; device test must pass previous frame 233 before proclaiming crash solved.
FPS selector packaging does not yet prove 60fps physics/game frame-step.
