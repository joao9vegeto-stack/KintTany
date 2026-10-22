# PoPTST B28: Native saves and purple flashes

## Baseline
B27 is approved on a physical iPhone for gameplay and controls. Two unresolved behaviors: flashes of purple during rendering and no slot in the Prince of Persia Load menu even after attempting an in-game Save.

## Verified source findings
- Pinned upstream rePOP POSIX kernel_file.c creates only the final save directory with mkdir(path, 0755); nested game profile folders UDATA/TDATA may fail when a parent does not exist. B26 logged ENOENT for t:\\$u\\contentmeta.xbx, but this is insufficient by itself to prove which write or enumeration failed.
- B27 HUD BACKUP incorrectly treats virtual .devices/Partition*.img as valid save content and backs up the entire Xbox save root. B27 Launcher restore replaced the entire save root including the synthetic partition backing. The game cannot load a synthetic Partition image as a title save.
- Upstream native Vulkan pipeline compilation defaults to async. When a PSO is pending, ng_pipeline returns NULL and ng_flush_draws SKIPS that guest draw. Transient missing geometry may be related to purple flashes, although the exact color source is not yet demonstrated.
- Native ng_compose can recreate an SDL GPU composed texture without clearing it when the front surface is non-null. The following blit uses LOAD on undefined new texture contents, risking an intermittent colored frame after render-target changes.

## B28 implementation
- iPhone only: create missing UDATA/TDATA parent directories for title CREATE requests, not for reads. Add bounded guest save OPEN success, WRITE byte count/errno, and LIST lookup logs to the exported native trace.
- HUD backs up only UDATA/TDATA and legacy UserData/TitleData, after confirming a nonempty regular file in those folders. Never copy Xbox .devices images, virtual partitions, or Cache.
- Launcher restores only native save folders, staging files and keeping prior save copies for rollback. Even old B27 backups containing .devices cannot overwrite synthetic Xbox disk images.
- iPhone only: RESOT_ASYNC_PIPELINES=0 to ensure no guest draw is skipped waiting for a cold PSO. May cause first-use shader compilation stalls instead of disappearing polygons.
- iPhone only: clear newly allocated composed texture before LOAD. Android and Windows source behavior unchanged.
- All modifications scoped to PoPTST branch, one root orphan commit / one workflow, no changes to main or other branches.

## User validation criteria
1. Make a legitimate in-game save at a recognized fountain/checkpoint. Exit fully and relaunch, then use in-game Load/Continue. The backend must persist files and enumerate the same directory.
2. After a confirmed game save, BACKUP in HUD and RESTORE in launcher must only affect title saves. An empty save tree must not be declared a successful backup.
3. Test purple flashes and compare FPS. First-time shader compilation may briefly stall. If flashes persist, capture a frame/video and exported native log.
4. Log B28 distinguishes successful save CREATE/WRITE from menu LIST; do not claim the original loading bug definitively fixed until device verification.
