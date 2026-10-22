#!/usr/bin/env python3
"""Prepare rePOP reSOT 4ee3626 for the *existing* Metal-backed Vulkan ICD.

This is a narrowly scoped, fail-closed source adjustment, not a completed iOS
port. It enables the existing SDL GPU native renderer rather than pretending
that KosmicKrisp's Vulkan WSI is an SDL Metal shader compiler.
"""
from pathlib import Path
import argparse

def substitute(text, old, new, label):
    n=text.count(old)
    if n != 1:
        raise RuntimeError(f'{label}: expected one anchor, found {n}')
    return text.replace(old,new,1)

def apply(root:Path, check=False):
    edits={
       'port/third_party/xboxrecomp/src/kernel/nv2a_hw_d3d11.inc': [
          ('#if defined(_WIN32) || defined(__ANDROID__)',
           '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)')],
       'port/third_party/xboxrecomp/src/video/fb_present.c': [
          ('#if defined(_WIN32) || defined(__ANDROID__)',
           '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)')],
       'port/third_party/xboxrecomp/src/kernel/nv2a_hw_native.inc': [
          ('#if defined(__ANDROID__)\n/* RE-SoT: Android links the patched SDL directly;',
           '#if defined(__ANDROID__) || defined(__APPLE__)\n/* RE-SoT: mobile Apple/Android link the patched SDL directly;')],
       'port/third_party/xboxrecomp/src/kernel/guest_vmem.c': [
          ('#ifdef __ANDROID__\n    bytes = (GUEST_VMEM_TOP - s_lo)',
           '#if defined(__ANDROID__) || defined(__APPLE__)\n    bytes = (GUEST_VMEM_TOP - s_lo)')],
    }
    updates={}
    for relative,changes in edits.items():
        target=root/relative
        if not target.is_file(): raise RuntimeError('Missing upstream rePOP source: '+relative)
        text=target.read_text()
        for old,new in changes: text=substitute(text,old,new,relative)
        updates[target]=text
    # Preflight every file before modifying any file.
    if not check:
        for path,content in updates.items(): path.write_text(content)
    print(f'PASS: {len(updates)} rePOP iOS Vulkan driver anchors; edit={not check}')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('repop',type=Path)
    ap.add_argument('--check-only',action='store_true')
    args=ap.parse_args()
    apply(args.repop,args.check_only)
