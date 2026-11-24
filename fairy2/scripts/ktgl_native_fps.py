"""Fairy Tail 2 v1.4.1 engine limiter, adapted from the exact FPSLocker build.
Reference: masagrator/FPSLocker-Warehouse, v4,
SaltySD/plugins/FPSLocker/patches/0100B9801F872000/A588F7BB864AAD5F.yaml.
Only the FPS_LOCK_TARGET row; resolution thresholds and guest code unchanged.
"""
from pathlib import Path
import struct
BUILD="a588f7bb864aad5fb6a18236878d9216"
GLOBAL=0x2c0b558
SIG=bytes.fromhex("1f000071c8038052")
HEADER=Path(__file__).with_name("ktgl_fps_chain.h")
def require(ok,msg):
    if not ok:raise ValueError("Fairy2 FPS: "+msg)
def references(raw):
    """Verify the reference's nearby ADRP+ADD materializes the actual global."""
    matches=[]
    pos=raw.find(SIG)
    while pos!=-1:
        if pos%4==0:
            for a in range(max(0,pos-0x100),pos,4):
                w=struct.unpack_from("<I",raw,a)[0]
                if w&0x9f000000!=0x90000000:continue
                reg=w&31
                imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
                if imm&(1<<20):imm-=1<<21
                page=(a&~0xfff)+imm*4096
                for c in range(a+4,min(pos,a+36),4):
                    v=struct.unpack_from("<I",raw,c)[0]
                    if v&0xffc00000==0x91000000 and (v>>5)&31==reg and page+((v>>10)&0xfff)==GLOBAL:
                        matches.append({"signature":hex(pos),"adrp":hex(a),"add":hex(c),"global":hex(GLOBAL)})
        pos=raw.find(SIG,pos+1)
    require(matches,"published limiter signature/global not found in actual guest RX")
    return matches

def patch_host(repo):
    path=repo/"engine/dm/host/hle_fpslock.c"
    s=path.read_text()
    def one(a,b):
        nonlocal s
        require(s.count(a)==1,"pinned host anchor differs: "+a[:100])
        s=s.replace(a,b,1)
    one("uint32_t flag; } lock_t;", "uint32_t flag; uint32_t indirect; } lock_t;")
    one("static const lock_t k_locks[] = {", """static const lock_t k_locks[] = {
    // FAIRY2: exact v1.4.1 FPSLocker target; read both levels, not a
    // fabricated frame step. Keep the original KTGL simulation and DRS.
    { "a588f7bb864aad5fb6a18236878d9216", "Fairy Tail 2 KTGL native frame limit", 0x2c0b558, 0x18c, FPS_I32, 1, 0, 0, 0x170 },""")
    one("// NieR 1.0.3 exposes",HEADER.read_text()+"\n// NieR 1.0.3 exposes")
    one("        if (L->flag) { uint8_t b;", """        if (L->indirect) {
            // Root was read by the usual row logic. Resolve again before
            // writing, reject null, misaligned, unreadable or stale objects.
            uint64_t field = 0; uint32_t cur = 0;
            uint32_t want = (uint32_t)target;
            if (!f2_fps_resolve(rd, (uint64_t)(uintptr_t)(base + L->ptr_off),
                    L->indirect, L->field, &field, &cur)) continue;
            if (want != 30 && want != 60) continue;
            if (cur != want) {
                uint64_t check = 0; uint32_t now = 0;
                if (!f2_fps_resolve(rd,(uint64_t)(uintptr_t)(base + L->ptr_off),
                     L->indirect,L->field,&check,&now) || check != field || now != cur) continue;
                uint32_t *p = (uint32_t *)(uintptr_t)field;
                dm_guest_write_prepare(p, sizeof *p);
                __atomic_store_n(p, want, __ATOMIC_RELAXED);
            }
            if (nlog[r] < 1 || (cur != want && nlog[r] < 8)) {
                nlog[r]++;
                LOG("FAIRY2_KTGL_FPS_LOCK native field %#llx: %u -> %u fps (%s)", (unsigned long long)field, cur, want, src);
            }
            continue;
        }
        if (L->flag) { uint8_t b;""")
    path.write_text(s)
    return {"build":BUILD,"pointer_chain":[hex(GLOBAL),"0x170","0x18c"],
        "target_values":[30,60],"reference":"FPSLocker-Warehouse v4 exact BID",
        "host_sha256":__import__("hashlib").sha256(s.encode()).hexdigest(),
        "guest_code_modified":False,"dynamic_resolution_modified":False}
