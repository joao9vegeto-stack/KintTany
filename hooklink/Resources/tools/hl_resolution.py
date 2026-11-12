#!/usr/bin/env python3
# HookLink: writes the handheld resolution file for the iPhone from the player's own game files.
# Reads Pack/Bootup.Nin_Ounce_NVN2.pack.zs out of RomFS.img (nxnative's image), scales the handheld dynamic-resolution palette
# (#90e0a495) by FACTOR, sets its LoadThreshold, and writes the edited pack for Documents/res_overlay/Pack/ on the phone.
# Defaults are the tested iPhone 18 Pro Max values: top 1080x608 (0.5625), bottom 640x360 (0.3334), threshold 95.
# Usage: hl_resolution.py <nxnative dir> <RomFS.img> <out .pack.zs> [factor 0.75] [threshold 95]
import struct, sys
try:
    from compression import zstd as z          # Python 3.14+
except ImportError:
    import backports.zstd as z                 # older Pythons: pip install backports.zstd

def sarc(b):
    bo = '<' if b[6:8] == b'\xff\xfe' else '>'
    do = struct.unpack(bo + 'I', b[12:16])[0]; n = struct.unpack(bo + 'H', b[0x1a:0x1c])[0]
    nodes = 0x20; names = nodes + n * 16 + 8; out = {}
    for i in range(n):
        h, attr, s, e = struct.unpack(bo + 'IIII', b[nodes + i * 16:nodes + i * 16 + 16])
        nm = b[names + (attr & 0xffff) * 4:].split(b'\0', 1)[0].decode(); out[nm] = (do + s, do + e)
    return out

class Byml:
    def __init__(s, b):
        s.b = b; assert b[:2] == b'YB', 'not a BYML'
        s.keys = s.st(s.u(4)); s.strs = s.st(s.u(8)); s.root = s.u(12)
    def u(s, o, n=4): return int.from_bytes(s.b[o:o + n], 'little')
    def st(s, o):
        n = s.u(o + 1, 3); off = [s.u(o + 4 + 4 * i) for i in range(n)]
        return [s.b[o + x:].split(b'\0', 1)[0].decode('utf8', 'replace') for x in off]
    def node(s, t, v, o):
        if t == 0xa0: return s.strs[v]
        if t == 0xd0: return bool(v)
        if t == 0xd1: return struct.unpack('<i', struct.pack('<I', v))[0]
        if t == 0xd2: return ('f', struct.unpack('<f', struct.pack('<I', v))[0], o)
        if t == 0xd3: return v
        if t in (0xd4, 0xd5, 0xd6): return ('64', s.u(v, 8))
        if t == 0xff: return None
        if t in (0xc0, 0xc1, 0x20, 0x21): return s.cont(v)
        return ('t%x' % t, v)
    def cont(s, o):
        t = s.b[o]; n = s.u(o + 1, 3)
        if t == 0xc0:
            ty = s.b[o + 4:o + 4 + n]; p = o + 4 + ((n + 3) & ~3)
            return [s.node(ty[i], s.u(p + 4 * i), p + 4 * i) for i in range(n)]
        if t == 0xc1:
            out = {}
            for i in range(n):
                e = o + 4 + 8 * i; out[s.keys[s.u(e, 3)]] = s.node(s.b[e + 3], s.u(e + 4), e + 4)
            return out
        if t in (0x20, 0x21):
            esz = 8 if t == 0x20 else 12; base = o + 4; tyb = base + esz * n; out = {}
            for i in range(n):
                e = base + esz * i; out['#%08x' % s.u(e)] = s.node(s.b[tyb + i], s.u(e + 4), e + 4)
            return out
        raise ValueError(hex(t))

def main():
    if len(sys.argv) < 4: sys.exit(__doc__ or 'usage: hl_resolution.py <nxnative dir> <RomFS.img> <out> [factor] [threshold]')
    nx, img, out = sys.argv[1:4]
    factor = float(sys.argv[4]) if len(sys.argv) > 4 else 0.75
    thresh = float(sys.argv[5]) if len(sys.argv) > 5 else 95.0
    sys.path.insert(0, nx + '/dm/tools'); import romfs_image as r
    ix = r.read_index(img); f = open(img, 'rb')
    raw = lambda p: (f.seek(ix[p][1]), f.read(ix[p][2]))[1]
    zd = z.decompress(raw('Pack/ZsDic.pack.zs')); D = sarc(zd)
    pk = z.ZstdDict(zd[slice(*D['pack.zsdic'])])
    d = bytearray(z.decompress(raw('Pack/Bootup.Nin_Ounce_NVN2.pack.zs'), zstd_dict=pk))
    S = sarc(bytes(d)); k = [n for n in S if 'ModelSceneExtensionParam/Default' in n][0]; s0, e0 = S[k]
    # Every palette's levels (handheld #90e0a495 and docked #2ebeca77) are scaled, each stored value once: the BYML shares one stored value between equal entries
    B = Byml(bytes(d[s0:e0])); pals = B.cont(B.root)['DynamicResolutionParam']['LevelPaletteDict']; done = set()
    # The handheld palette first, its scales rounded to 4 places (as tested on the iPhone); the docked palette's own levels are scaled unrounded
    for key in sorted(pals, key=lambda k: k != '#90e0a495'):
        pal = pals[key]
        for lv in pal['DynamicResolutionLevelParamList']:
            _, v, off = lv['ResolutionReduceScale']
            if off in done: continue
            done.add(off); d[s0 + off:s0 + off + 4] = struct.pack('<f', round(v * factor, 4) if key == '#90e0a495' else v * factor)
        _, _, off = pal['LoadThreshold']
        if off not in done: done.add(off); d[s0 + off:s0 + off + 4] = struct.pack('<f', thresh)
    blob = z.compress(bytes(d), level=19, zstd_dict=pk)
    assert z.decompress(blob, zstd_dict=pk) == bytes(d)
    open(out, 'wb').write(blob)
    B2 = Byml(bytes(d[s0:e0])); p2 = B2.cont(B2.root)['DynamicResolutionParam']['LevelPaletteDict']['#90e0a495']
    sc = [round(l['ResolutionReduceScale'][1], 4) for l in p2['DynamicResolutionLevelParamList']]
    print(f'handheld resolution: {round(1920 * sc[0])}x{round(1080 * sc[0])} down to {round(1920 * sc[-1])}x{round(1080 * sc[-1])}, threshold {p2["LoadThreshold"][1]:g}')

if __name__ == '__main__': main()
