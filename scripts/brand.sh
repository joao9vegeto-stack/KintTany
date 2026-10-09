#!/usr/bin/env bash
set -euo pipefail
root="${1:?Pass target Android source directory}"
gradle="$root/app/build.gradle.kts"
manifest="$root/app/src/main/AndroidManifest.xml"
names="$root/app/src/main/res/values/app_name.xml"
# Upstream v13.3 uses a literal application ID and .debug suffix.
grep -Fq 'applicationId = "com.metrolist.music"' "$gradle"
sed -i 's/applicationId = "com.metrolist.music"/applicationId = "com.spotijon.music"/;s/applicationIdSuffix = ".debug"/applicationIdSuffix = ""/' "$gradle"
grep -Fq '<string name="app_name">Metrolist</string>' "$names"
sed -i 's|<string name="app_name">Metrolist</string>|<string name="app_name">SpotiJon</string>|' "$names"
debug_names="$root/app/src/debug/res/values/app_name.xml"
if [ -f "$debug_names" ]; then
  sed -i 's|<string name="app_name">Metrolist Debug</string>|<string name="app_name">SpotiJon</string>|' "$debug_names"
fi
# The upstream filter contains LEANBACK_LAUNCHER but NO standalone LAUNCHER
# activity for a phone. Android/aapt reports it as leanback-only if LAUNCHER is
# added to the same filter. Insert a separate phone launcher intent-filter.
python3 - "$manifest" <<'PYCODE'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
marker = 'android:windowSoftInputMode="adjustResize">'
assert s.count(marker) == 1, "Upstream MainActivity launcher anchor changed"
# Original APK uses launcher aliases; aapt reports only the TV launcher.
# Keep those aliases, but add a direct independent phone launcher to MainActivity.
assert 'android:name=".MainActivityAlias"' in s, "Upstream launcher alias changed"
launcher = """
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
"""
s = s.replace(marker, marker + launcher, 1)
p.write_text(s)
PYCODE
sed -E -i 's|@mipmap/ic_launcher(_static)?(_round)?|@drawable/spotijon_foreground|g' "$manifest"
if grep -qE '@mipmap/ic_launcher|spotijon_foreground_(static|round)' "$manifest"; then
  echo 'Unmapped Sonora-style launcher icon reference' >&2
  exit 1
fi
res="$root/app/src/main/res"
mkdir -p "$res/drawable" "$res/values" "$res/mipmap-anydpi-v26"

# A fresh vector inspired by the inspected Sonora IPA's music-player role,
# not copied proprietary artwork or extracted iOS code.
cat > "$res/values/spotijon_colors.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="spotijon_icon_background">#14101F</color>
</resources>
XML

cat > "$res/drawable/spotijon_foreground.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#8A5CF6"
        android:pathData="M15,15h78v78h-78z" />
    <path
        android:fillColor="#14101F"
        android:pathData="M19,19h70v70h-70z" />
    <path
        android:fillColor="#DDB8FF"
        android:pathData="M62,29L81,25L81,34L62,38Z" />
    <path
        android:fillColor="#DDB8FF"
        android:pathData="M61,30L69,30L69,70L61,70Z" />
    <path
        android:fillColor="#DDB8FF"
        android:pathData="M51,66c7,-4 15,-2 17,3c2,5 -2,11 -9,14c-7,3 -15,1 -17,-4c-2,-5 2,-10 9,-13z" />
    <path
        android:fillColor="#B9A8F7"
        android:pathData="M27,42h26v3h-26zM27,49h23v3h-23zM27,56h19v3h-19z" />
</vector>
XML

for icon in ic_launcher ic_launcher_round ic_launcher_static ic_launcher_static_round; do
  cat > "$res/mipmap-anydpi-v26/${icon}.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/spotijon_icon_background"/>
    <foreground android:drawable="@drawable/spotijon_foreground"/>
</adaptive-icon>
XML
done

# These overrides are read by the existing Gradle build; original package
# namespace remains unchanged while applicationId is independent.
echo 'Brand applied: SpotiJon / com.spotijon.music'
