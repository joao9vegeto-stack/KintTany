#!/usr/bin/env python3
"""Checks integration wiring without claiming an Apple Xcode/device build."""
from pathlib import Path
import hashlib
import subprocess
try: import yaml
except ImportError: raise SystemExit('Missing pyyaml')
r=Path(__file__).resolve().parents[1]
w=yaml.safe_load((r/'.github/workflows/poptst-ios.yml').read_text())
assert set(w['jobs']) == {'shaders','ipa'}
assert w['jobs']['ipa']['needs']=='shaders'
yaml_src=(r/'.github/workflows/poptst-ios.yml').read_text()
assert 'macos-26' in yaml_src and 'iphoneos' in yaml_src
assert '4ee36260e71d39fd8b02028fd614b1907a0d451b' in yaml_src
assert 'gh run download 39067594955' in yaml_src
assert '753C58B191279BF4D1A8B28A936DF36AA222ED566487AB1FBDFCD090E91EE379' in (r/'ios/App/RetailFolderInstaller.swift').read_text()
for text in ['poptst_engine_start','SDL_CreateWindow','SDL_SetHint(SDL_HINT_VULKAN_LIBRARY','pthread_create']:
  assert text in (r/'ios/Native/poptst_engine.c').read_text(),text
for text in ['xbox_MemoryLayoutInit','xbox_kernel_init','xbox_path_init','xbox_OhciInit','xbe_entry_point()']:
  assert text in (r/'ios/Runtime/poptst_retail_boot.c').read_text(),text
assert 'repop/source/xbox-retail/gen/' in (r/'ios/CMakeLists.txt').read_text().replace('${RESOT_ROOT}/','repop/'), 'No real retail C in CMake'
assert 'xbox-demo/gen/' not in (r/'ios/CMakeLists.txt').read_text()
assert 'libPoPTSTRetail.dylib' in (r/'ios/Tools/validate_ipa.py').read_text()
for source in r.rglob('*'):
  if source.is_file() and source.suffix.lower() in ('.xbe','.bf','.psarc','.ipa'):
    raise AssertionError('Game/binary must not be packaged in git '+str(source))
print('PASS: 2-job single workflow, retail-only C sources, launch, Vulkan WSI, imports, packaging references')
print('Verified files:',len([x for x in r.rglob('*') if x.is_file()]))
