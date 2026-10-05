# PsTJon

PsTJon is an isolated iOS RPCS3 research/build branch.

- Runtime shell: official RPCS3 iOS Preview 0.10.1
- Bundle identifier preserved: `com.xitrix.RPCS3`
- Core source: XITRIX/rpcs3 `ios-port`, pinned by the workflow
- The IPA is rebuilt by replacing only `Frameworks/libRPCS3Core.dylib`
- Existing RPCS3 Documents/settings/saves remain compatible when the sideload tool re-signs this IPA with the same bundle identifier.

This branch intentionally contains only the reproducible build overlay. The upstream RPCS3 source tree is checked out by CI so PsTJon stays isolated from every other KintTany branch.
