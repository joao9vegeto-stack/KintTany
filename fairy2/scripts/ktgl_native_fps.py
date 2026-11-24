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
    # Preserve real source instructions for follow-up rather than making
    # guesses about which reader consumes the pointer or fallback constant.
    from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
    dis=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    for hit in matches:
        start=int(hit["adrp"],16)
        end=min(len(raw),int(hit["signature"],16)+0x80)
        hit["disassembly"]=[f"{i.address:#x}: {i.mnemonic} {i.op_str}" for i in dis.disasm(raw[start:end],start)]
        print("FAIRY2_FPS_SOURCE",hit,flush=True)
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
    # Reuse NXNative's cheat subsystem memory boundary and kernel-copy
    # strategy for live game mappings. Never dereference or store through
    # an unvalidated native pointer in the host.
    one("// NieR 1.0.3 exposes",HEADER.read_text()+r"""
extern int dm_guest_as_contains(uintptr_t a);
static int f2_valid_span(uint64_t a,size_t n,int write) {
    if (!a || !n || a>UINT64_MAX-n) return 0;
    if (dm_guest_as_contains((uintptr_t)a) &&
        dm_guest_as_contains((uintptr_t)(a+n-1))) return 1;
    for (int i=0;i<g_nmod;i++) {
        const module_t *m=&g_mod[i];
        uint64_t b=(uint64_t)(uintptr_t)m->base;
        if (!b || a<b || a-b>=m->size || n>m->size-(a-b)) continue;
        if (!write) return 1;
        uint64_t o=a-b, end=o+n;
        uint64_t patch=m->patch_off>=0?(uint64_t)m->patch_off:(uint64_t)m->size;
        uint64_t k0=m->key_page_off,k1=k0+m->key_page_size;
        return o>=m->data_off && end<=patch &&
            !(m->key_page_size && o<k1 && end>k0);
    }
    return 0;
}
static int f2_write_kernel(uint64_t a,const void *p,size_t n) {
    if (!f2_valid_span(a,n,1)) return 0;
    dm_guest_write_prepare((void *)(uintptr_t)a,n);
    return vm_write(mach_task_self(),(vm_address_t)a,
                    (vm_offset_t)(uintptr_t)p,(mach_msg_type_number_t)n)==KERN_SUCCESS;
}
static void f2_drs_tick(uint8_t *base,uint32_t want) {
    static int last_budget,fail_logged;
    float budget[2]={want==60?1.0f/60.0f:1.0f/23.0f,
                     want==60?1.0f/65.0f:1.0f/27.0f};
    uint64_t bits=0,old=0,after=0,addr=(uint64_t)(uintptr_t)(base+0x2c53f00);
    memcpy(&bits,budget,sizeof bits);
    if (!rd(addr,&old,8) || (old!=bits && !f2_write_kernel(addr,&bits,8)) ||
        !rd(addr,&after,8) || after!=bits) {
        if (!fail_logged++) LOG("FAIRY2_KTGL_DRS_READBACK_FAILED addr=%#llx",(unsigned long long)addr);
        return;
    }
    if (last_budget!=(int)want) {
        last_budget=(int)want;
        LOG("FAIRY2_KTGL_DRS applied target=%u thresholds=%.6f,%.6f s",want,budget[0],budget[1]);
    }
}
"""+ "\n// NieR 1.0.3 exposes")
    one("        if (L->ptr_off && (!rd((uint64_t)(uintptr_t)(base + L->ptr_off), &obj, sizeof obj) || !obj)) continue;","""        if (L->indirect) {
            uint32_t want=(uint32_t)target, applied=0;
            if (want!=30 && want!=60) continue;
            // The reference has two independent writes. A delayed game
            // object must not prevent the static DRS target from applying.
            f2_drs_tick(base,want);
            f2_chain q;
            int status=f2_fps_apply(rd,f2_valid_span,f2_write_kernel,
                    (uint64_t)(uintptr_t)(base+L->ptr_off),L->indirect,
                    L->field,want,&q,&applied);
            static int last_status=-1;
            static unsigned ticks,good,changes;
            static const char *const reasons[]={"ok","root_read","root_range",
                "nested_read","nested_range","field_read","changed_chain",
                "kernel_write","readback"};
            ++ticks;
            if (status==F2_OK) {
                ++good; changes+=(q.value!=want);
                if (nlog[r]<1 || last_status!=F2_OK || (q.value!=want && nlog[r]<8)) {
                    nlog[r]++;
                    LOG("FAIRY2_KTGL_FPS_LOCK native field %#llx: %u -> %u fps (%s), root=%#llx nested=%#llx",
                        (unsigned long long)q.address,q.value,applied,src,
                        (unsigned long long)q.root,(unsigned long long)q.nested);
                }
            }
            if (status!=last_status || ticks%300==0) {
                LOG("FAIRY2_KTGL_FPS_STATE stage=%s tick=%u root=%#llx nested=%#llx field=%#llx old=%#x applied=%u target=%u good=%u changes=%u",
                    reasons[status],ticks,(unsigned long long)q.root,
                    (unsigned long long)q.nested,(unsigned long long)q.address,
                    q.value,applied,want,good,changes);
                last_status=status;
            }
            continue;
        }
        if (L->ptr_off && (!rd((uint64_t)(uintptr_t)(base + L->ptr_off), &obj, sizeof obj) || !obj)) continue;""")
    require("\n// NieR 1.0.3 exposes" in s and "\\n// NieR 1.0.3 exposes" not in s,
            "generated host has a literal escaped newline")
    path.write_text(s)
    return {"build":BUILD,"pointer_chain":[hex(GLOBAL),"0x170","0x18c"],
        "target_values":[30,60],"reference":"FPSLocker-Warehouse v4 exact BID",
        "host_sha256":__import__("hashlib").sha256(s.encode()).hexdigest(),
        "guest_code_modified":True,"dynamic_resolution_modified":True,"present_interval":"display","fps_readback":True,
        "prior_value_gate":False,"kernel_guest_write":True,"independent_drs":True,"stage_telemetry":True}
