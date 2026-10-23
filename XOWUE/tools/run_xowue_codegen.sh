#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${XOWUE_XEX:?Set XOWUE_XEX to the local, authorized default.xex path}"
: "${XENONRECOMP_ROOT:?Set XENONRECOMP_ROOT to the XenonRecomp source checkout}"

build_dir="${XENONRECOMP_BUILD_DIR:-$XENONRECOMP_ROOT/build-clang}"
context_header="${PPC_CONTEXT_HEADER:-$XENONRECOMP_ROOT/XenonUtils/ppc_context.h}"
xenon_analyse="$build_dir/XenonAnalyse/XenonAnalyse"
xenon_recomp="$build_dir/XenonRecomp/XenonRecomp"

[[ -f "$XOWUE_XEX" ]] || { echo "XOWUE_XEX not found: $XOWUE_XEX" >&2; exit 2; }
[[ -x "$xenon_analyse" ]] || { echo "XenonAnalyse not found: $xenon_analyse" >&2; exit 2; }
[[ -x "$xenon_recomp" ]] || { echo "XenonRecomp not found: $xenon_recomp" >&2; exit 2; }
[[ -f "$context_header" ]] || { echo "PPC context header not found: $context_header" >&2; exit 2; }

work_dir="$(mktemp -d "$project_root/generated/.xowue-codegen.XXXXXX")"
backup_dir="$(mktemp -d "$project_root/generated/.xowue-backup.XXXXXX")"
cleanup() {
    rm -rf -- "$work_dir"
    if [[ -d "$backup_dir" ]]; then
        if [[ -d "$backup_dir/ppc" && ! -d "$project_root/generated/ppc" ]]; then
            mv -- "$backup_dir/ppc" "$project_root/generated/ppc"
        fi
        rm -rf -- "$backup_dir"
    fi
}
trap cleanup EXIT

mkdir -p "$work_dir/config" "$work_dir/ppc" "$project_root/generated/config"
"$xenon_analyse" "$XOWUE_XEX" "$work_dir/config/XOWUE_switch_tables.analyzed.toml"
python3 "$project_root/tools/prepare_switch_tables.py" \
    "$work_dir/config/XOWUE_switch_tables.analyzed.toml" \
    "$work_dir/config/XOWUE_switch_tables.toml"

python3 - "$XOWUE_XEX" "$work_dir/config/XOWUE.toml" <<'PY'
import json
import os
import sys
from pathlib import Path

xex = str(Path(sys.argv[1]).resolve())
config_path = Path(sys.argv[2])
xex_relative = os.path.relpath(xex, config_path.parent.resolve())
fixed = {
    "restgprlr_14_address": 0x82C29FE0,
    "savegprlr_14_address": 0x82C29F90,
    "restfpr_14_address": 0x82C2A80C,
    "savefpr_14_address": 0x82C2A7C0,
    "restvmx_14_address": 0x82E99088,
    "savevmx_14_address": 0x82E98DF0,
    "restvmx_64_address": 0x82E9911C,
    "savevmx_64_address": 0x82E98E84,
}
lines = ["[main]", f"file_path = {json.dumps(xex_relative)}", 'out_directory_path = "../ppc"',
         'switch_table_file_path = "XOWUE_switch_tables.toml"']
lines.extend(f"{key} = 0x{value:08X}" for key, value in fixed.items())
config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

"$xenon_recomp" "$work_dir/config/XOWUE.toml" "$context_header" \
    2>&1 | tee "$work_dir/config/XOWUE-recompile.log"

cp -- "$work_dir/config/XOWUE_switch_tables.analyzed.toml" \
    "$project_root/generated/config/XOWUE_switch_tables.analyzed.toml"
cp -- "$work_dir/config/XOWUE_switch_tables.toml" \
    "$project_root/generated/config/XOWUE_switch_tables.toml"
cp -- "$work_dir/config/XOWUE.toml" "$project_root/generated/config/XOWUE.toml"
python3 - "$project_root/generated/config/XOWUE.toml" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text, count = re.subn(r'(?m)^file_path\s*=\s*.+$', 'file_path = "../../upload/default.xex"', text)
if count != 1:
    raise SystemExit("Could not normalize the saved XOWUE.toml input path")
path.write_text(text, encoding="utf-8")
PY
cp -- "$work_dir/config/XOWUE-recompile.log" \
    "$project_root/generated/config/XOWUE-recompile.log"

if [[ -d "$project_root/generated/ppc" ]]; then
    mv -- "$project_root/generated/ppc" "$backup_dir/ppc"
fi
mv -- "$work_dir/ppc" "$project_root/generated/ppc"
rm -rf -- "$backup_dir/ppc"
python3 "$project_root/Runtime/generate_runtime_stubs.py" \
    --ppc-dir "$project_root/generated/ppc" \
    --recompile-log "$project_root/generated/config/XOWUE-recompile.log" \
    --output "$project_root/Runtime/generated/XOWUEImportStubs.cpp"

echo "Generated XOWUE C++ output at $project_root/generated/ppc"
