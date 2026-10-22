#!/usr/bin/env python3
import sys,zipfile,plistlib,hashlib
from pathlib import Path
p=Path(sys.argv[1]); assert p.is_file() and p.stat().st_size > 2_000_000
with zipfile.ZipFile(p) as z:
    assert z.testzip() is None
    names=z.namelist()
    app='Payload/PoPTST.app/'
    assert app+'PoPTST' in names, 'missing app executable'
    assert app+'Frameworks/libPoPTSTRetail.dylib' in names, 'missing runtime library'
    assert app+'Frameworks/libKosmicKrisp.dylib' in names, 'missing Vulkan Metal backend'
    assert app+'Frameworks/libvulkan.dylib' in names, 'missing Vulkan loader bridge'
    info=plistlib.loads(z.read(app+'Info.plist'))
    assert info['CFBundleIdentifier']=='com.joaopedro.poptst'
    forbidden=('.xbe','.bf','.psarc','/sound/','/video/','/pop1/','/pop2/')
    assert not any(s in n.lower() for n in names for s in forbidden), 'game files leaked into IPA'
    runtime=z.read(app+'Frameworks/libPoPTSTRetail.dylib')
    assert len(runtime)>1_000_000, 'runtime suspiciously small'
    assert b'\xcf\xfa\xed\xfe' in runtime[:8], 'not a Mach-O 64-bit dylib'
print('PASS IPA structural, retail runtime, Metal backend, no game data',p.stat().st_size)
print('SHA256:',hashlib.sha256(p.read_bytes()).hexdigest())
