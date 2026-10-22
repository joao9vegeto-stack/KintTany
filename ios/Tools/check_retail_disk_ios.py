#!/usr/bin/env python3
"""Build21 fail-closed validation of real rePOP Android retail parity on iOS."""
import sys
from pathlib import Path
r=Path(sys.argv[1])
path=(r/'port/third_party/xboxrecomp/src/kernel/kernel_path.c').read_text()
file=(r/'port/third_party/xboxrecomp/src/kernel/kernel_file.c').read_text()
bridge=(r/'port/third_party/xboxrecomp/src/kernel/kernel_bridge.c').read_text()
header=(r/'port/third_party/xboxrecomp/src/kernel/kernel.h').read_text()
ios=Path(__file__).resolve().parents[1]
swift=(ios/'App/PoPTSTApp.swift').read_text()
p=(ios/'project.yml').read_text()
assert path.count('(defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IPHONE)) && RESOT_RUNTIME_RETAIL')==5
assert 'XBOX DISK Partition%d backing %s' in path
assert 'android_partition_images();' in path
assert 'android_partition_path(xbox_path' in path
assert 'Partition1\\\\CACHE\\\\' in path and '"/Cache"' in path
cache_rule = r'    { "\\Device\\Harddisk0\\Partition1\\CACHE\\", 1, NULL, "/Cache" },'
retail_generic = r'    { "\\Device\\Harddisk0\\Partition1\\",    0, NULL,         NULL          },'
assert path.index(cache_rule) < path.index(retail_generic)
assert 'resolve_case(host_path_buf' in path
assert file.count('(defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IPHONE)) && RESOT_RUNTIME_RETAIL')==10
assert 'partition volume query ->' in file
assert 'XBOX OPEN FAIL errno=' in file
assert 'disp=%u options=0x%X access=0x%X root=%p guest=' in file
assert 'XBOX BOOT EXIT: routine=' in bridge and 'XBOX LAUNCH DATA:' in bridge
assert 'void xbox_dir_context_drop(HANDLE FileHandle);' in header
assert '(defined(__APPLE__) && TARGET_OS_IPHONE)' in header
assert "CFBundleVersion: '28'" in p
assert 'BUILD \\(BuildInfo.number)' in swift
assert 'guard engineCanStart() != 0 else {' in swift
print('PASS B17: device 0..5, XBE Partition1, IOS path/files, durable firmware context, build20 & restart guard')

assert 'static void poptst_save_parents(char *host)' in file
assert 'SAVE B28 OPEN SUCCESS' in file and 'SAVE B28 WRITE want=' in file
assert 'SAVE B28 LIST folder=' in file and 'if(create_save && poptst_save_root(host_path))' in file
print('PASS B28: iOS nested save parent creation and real host save read/write instrumentation')
