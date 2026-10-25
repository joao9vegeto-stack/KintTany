# Build 39 — startup media EOF fallback

The Build 37 runtime trace showed the UE3 startup movie files `ravenlogo.xxx`,
`blank.bik`, `UE3_logo.xxx`, `FOX_LOGO.xxx` and `MARVEL_INTRO.xxx`
missing under `WGame/Movies`, followed by a long-running guest thread and no
fresh game frames.

This change adds a narrowly scoped compatibility fallback for only those six
known startup movie names (including `ATVI_logo.xxx`): if an open-existing
read request cannot find one, XOWUE creates/reuses a zero-byte placeholder under
`XOWUE-Saves/.XOWUEVirtualMedia`. The guest sees a successful file open and EOF
on read. The user's game directory and actual assets are not modified, and no
placeholder is created for arbitrary files.

This is a testable attempt to let UE3 treat a missing startup movie as finished;
it does **not** claim to fix the separate Xenos EDRAM/color-output blocker or
prove that Wolverine reaches the menu. The exit path and FPS HUD fixes are
included in the same consolidated commit.
