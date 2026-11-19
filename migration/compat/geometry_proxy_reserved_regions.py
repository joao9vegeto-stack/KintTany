#!/usr/bin/env python3
"""Apply narrow SwiftUI SDK compatibility changes to the verbatim NX2Apple snapshot.

The current Xcode 27.1 SDK lacks GeometryProxy.reservedRegions(kind:).
The UIKit UIView/UIWindow reservedRegions calls are deliberately left untouched.
Do not change layout calculations, views, or the pinned nxnative patch queue.
"""
from pathlib import Path
import argparse
import shutil

MAP = {
    "CoverFlowView.swift": "proxy.reservedRegions(kind: .division)",
    "GameLaunchActions.swift": "geometry.reservedRegions(kind: .division)",
    "LibraryView.swift": "geometry.reservedRegions(kind: .division)",
    "PortraitLibrary.swift": "geometry.reservedRegions(kind: .division)",
    "TouchLayoutEditorView.swift": "proxy.reservedRegions(kind: .division)",
}

def apply(root: Path, shim: Path) -> None:
    shell = root / "frontend-ios" / "Sources" / "ShellUI"
    if not (shell / "CoverFlowView.swift").is_file():
        raise RuntimeError("NX2Apple SwiftUI sources missing: refusing a partial migration")
    if not shim.is_file():
        raise RuntimeError("Missing authored GeometryProxy shim")
    changes = 0
    for filename, old in MAP.items():
        source = shell / filename
        if not source.is_file():
            raise RuntimeError(f"Missing upstream SwiftUI source: {source}")
        before = source.read_text(encoding="utf-8")
        new = old.replace(".reservedRegions(", ".danteReservedRegions(")
        if before.count(old) == 1 and new not in before:
            after = before.replace(old, new, 1)
            if after.replace(new, old, 1) != before:
                raise RuntimeError(f"Unintended edits in {source}")
            source.write_text(after, encoding="utf-8")
            changes += 1
        elif new in before and old not in before:
            # Already applied, e.g. during a deterministic local rerun.
            pass
        elif old not in before and "reservedRegions(kind: .division)" not in before:
            # Future upstream may have already replaced the missing API.
            pass
        else:
            raise RuntimeError(f"Upstream {filename} changed its division API usage; review it")
    # The same SDK also lacks ArrangementView, used only for a divided
    # tabletop layout. With the reserved-region adapter returning an empty
    # list, tabletop stays false. Remove only this unreachable SDK-only
    # branch and retain the normal expanded/portrait layout verbatim.
    portrait_path = shell / "PortraitLibrary.swift"
    portrait = portrait_path.read_text(encoding="utf-8")
    arrangement = """                    if #available(iOS 27.1, macOS 27.1, *), tabletop {
                        ArrangementView {
                            VStack(spacing: 0) {
                                tabletopHero
                                gridHeading
                            }
                        } secondary: {
                            gameScroll(includesHero: false)
                                .safeAreaBar(edge: .bottom, spacing: 0) { bottomBar }
                        }
                        .arrangementViewStyle(.split.axes(.vertical))
                        .background(Color.black)
                    } else if expanded {"""
    if portrait.count(arrangement) == 1:
        updated = portrait.replace(arrangement, "                    if expanded {", 1)
        if updated.count("                    if expanded {") != 1 or "ArrangementView {" in updated:
            raise RuntimeError("Portrait fallback did not isolate ArrangementView correctly")
        portrait_path.write_text(updated, encoding="utf-8")
        print("Replaced unsupported ArrangementView branch with the existing expanded/portrait layouts.")
    elif "ArrangementView {" not in portrait:
        print("Upstream PortraitLibrary already avoids ArrangementView; no change needed.")
    else:
        raise RuntimeError("Upstream ArrangementView call changed; refusing a broad rewrite")

    destination = shell / "DanteReservedRegionsCompat.swift"
    if destination.is_file() and destination.read_bytes() != shim.read_bytes():
        raise RuntimeError("Unexpected upstream collision with our named shim")
    shutil.copyfile(shim, destination)
    print(f"Applied GeometryProxy SDK compatibility in {changes} upstream source files; UIKit calls unchanged.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--shim", type=Path, required=True)
    args = parser.parse_args()
    apply(args.repo.resolve(), args.shim.resolve())

if __name__ == "__main__":
    main()
