#!/usr/bin/env bash
# Build a genuine unsigned iPhone diagnostic IPA (no PS3 game or license).
set -euo pipefail
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
APP="ios-probe/Payload/AscensionRecompProbe.app"
mkdir -p "$APP"
cp ios/Probe-Info.plist "$APP/Info.plist"
xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.0 \
    -isysroot "$SDK" -fobjc-arc -fmodules -stdlib=libc++ \
    -O2 -Wl,-dead_strip -I ios \
    ios/ARMetalView.m ios/ARProbeApp.m ios/ARProbeGuestVM.c \
    build-ios-runtime/libps3recomp_runtime.a \
    -framework UIKit -framework Foundation -framework QuartzCore \
    -framework Metal -framework CoreGraphics -framework CoreFoundation \
    -framework Security -framework Accelerate \
    -lz -lc++ -o "$APP/AscensionRecompProbe"
test -s "$APP/AscensionRecompProbe"
file "$APP/AscensionRecompProbe" | tee m41-executable-file.txt
xcrun lipo -info "$APP/AscensionRecompProbe" | tee m41-executable-arch.txt
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist"
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.4.1-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.4.1-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.4.1-unsigned.ipa > m41-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
