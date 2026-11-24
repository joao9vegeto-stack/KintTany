"""Fairy Tail 2 v1.4.1 engine limiter, adapted from the exact FPSLocker build.
Reference: masagrator/FPSLocker-Warehouse, v4,
SaltySD/plugins/FPSLocker/patches/0100B9801F872000/A588F7BB864AAD5F.yaml.
FPS_LOCK_TARGET plus the two reviewed DRS readers and display-mode pacing.
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

# Exact FPSLocker v1.4.1 MASTER_WRITE; original immediates are 1/23 and 1/27.
DRS_SLOT=0x2c53f00
DRS_SITES=((0x138238c,0x5282c86a,0x72a7a64a,0xb94f014a),
           (0x13823a8,0x529684ca,0x72a7a2ea,0xb94f054a))
DRS_SEED=struct.pack("<ff",1/23,1/27)
def drs_patch(raw,x0_size,patch_off):
    require(max(s[0]+8 for s in DRS_SITES)<=x0_size<=DRS_SLOT and DRS_SLOT+8<=patch_off,
            "DRS code or slot is outside reviewed RX/W sections")
    require(raw[DRS_SLOT:DRS_SLOT+8]==bytes(8),"DRS slot occupied; refuse overwrite")
    out=bytearray(raw)
    sites=[]
    for at,a,b,ldr in DRS_SITES:
        require(struct.unpack_from("<II",raw,at)==(a,b),
                f"DRS source immediates differ at {at:#x}")
        struct.pack_into("<II",out,at,0xb000c68a,ldr)
        sites.append({"site":hex(at),"before":[hex(a),hex(b)],"after":["0xb000c68a",hex(ldr)]})
    out[DRS_SLOT:DRS_SLOT+8]=DRS_SEED
    verify_drs(out,x0_size,patch_off)
    return bytes(out),{"sites":sites,"slot":hex(DRS_SLOT),"initial_seconds":[1/23,1/27],
                       "30_mode":"original thresholds","60_mode":"1/60, 1/65",
                       "reference_exact_build":BUILD}
def verify_drs(raw,x0_size,patch_off):
    require(max(s[0]+8 for s in DRS_SITES)<=x0_size<=DRS_SLOT and DRS_SLOT+8<=patch_off,"DRS layout")
    for at,a,b,ldr in DRS_SITES:
        require(struct.unpack_from("<II",raw,at)==(0xb000c68a,ldr),"DRS readers lost")
        # Independently decode ADRP and LDR destination.
        w=0xb000c68a
        imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
        if imm&(1<<20):imm-=1<<21
        require((at&~0xfff)+imm*4096+((ldr>>10)&0xfff)*4==
                DRS_SLOT+(4 if at==DRS_SITES[1][0] else 0),"DRS reader destination")
    require(raw[DRS_SLOT:DRS_SLOT+8]==DRS_SEED,"DRS initial values lost")

def display_profile(path,canonical,previous):
    previous(path,canonical)
    rows=path.read_text().splitlines()
    rows=[r for r in rows if r.partition("\t")[0]!="present_interval"]
    rows.append("present_interval\tdisplay")
    path.write_text("\n".join(rows)+"\n")

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
                    L->indirect, L->field, &field, &cur)) {
                static int pending;
                if (!pending++) LOG("FAIRY2_KTGL_FPS_PENDING: native object not ready or unexpected value");
                continue;
            }
            if (want != 30 && want != 60) continue;
            if (cur != want) {
                uint64_t check = 0; uint32_t now = 0;
                if (!f2_fps_resolve(rd,(uint64_t)(uintptr_t)(base + L->ptr_off),
                     L->indirect,L->field,&check,&now) || check != field || now != cur) continue;
                uint32_t *p = (uint32_t *)(uintptr_t)field;
                dm_guest_write_prepare(p, sizeof *p);
                __atomic_store_n(p, want, __ATOMIC_RELAXED);
            }
            uint32_t applied = 0;
            if (!rd(field, &applied, sizeof applied) || applied != want) {
                static int failed;
                if (!failed++) LOG("FAIRY2_KTGL_FPS_READBACK_FAILED: expected %u, got %u", want, applied);
                continue;
            }
            // The exact game patch redirects both DRS readers to this aligned W slot.
            // Keep the original 30 FPS thresholds, use the reference 60 FPS budget.
            float budget[2] = {want == 60 ? 1.0f/60.0f : 1.0f/23.0f,
                               want == 60 ? 1.0f/65.0f : 1.0f/27.0f};
            uint64_t bits=0, oldbits=0, readback=0;
            memcpy(&bits,budget,sizeof bits);
            uint64_t address=(uint64_t)(uintptr_t)(base+0x2c53f00);
            if (rd(address,&oldbits,sizeof oldbits)) {
                if (oldbits != bits) {
                    uint64_t *d=(uint64_t *)(uintptr_t)address;
                    dm_guest_write_prepare(d,sizeof *d);
                    __atomic_store_n(d,bits,__ATOMIC_RELAXED);
                }
                if (rd(address,&readback,sizeof readback) && readback==bits) {
                    static int last_budget;
                    if (last_budget!=(int)want) {
                        last_budget=(int)want;
                        LOG("FAIRY2_KTGL_DRS applied target=%u thresholds=%.6f,%.6f s",want,budget[0],budget[1]);
                    }
                } else {
                    static int bad_drs;
                    if (!bad_drs++) LOG("FAIRY2_KTGL_DRS_READBACK_FAILED");
                }
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
        "guest_code_modified":True,"dynamic_resolution_modified":True,"present_interval":"display","fps_readback":True}
