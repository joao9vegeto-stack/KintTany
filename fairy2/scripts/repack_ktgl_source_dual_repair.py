#!/usr/bin/env python3
"""Functional candidate: restore authentic FDATA G1T+G1S source to native parsers.

ONLY on verified first-read failure. FDATA compressed source is independently
checked by exact hash/type, SHA256, zlib Adler32, decoded size and 8-byte magic.
No generated textures, no abort suppression, no shader rebuild, no fallback on
other resource types. Device gameplay remains unverified.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,zlib
from pathlib import Path
import repack_ktgl_transaction_trace as trace

base=trace.base
RECORDS={
 'g1t':(3137776,137,49,48,0xfb9ebd24,0xafbec60c,'558ada8c563fe44fa18d894d01f39e8b1a230b26ad1bcd0782743797f815e494',b'GT1G0500',1),
 'g1s':(185248,4232,4176,18340,0xac9ed13e,0x7bcd279f,'edb3bceed3c426cfe5b851d78f2e7f56168abe8ac5d6aac3a6927bdaf6e3535a',b'_S2G5000',2),
}
FDATA='Motor/ReleasePackage/KIDS_PLATFORM_NX/release/0x38f972af.fdata'
BNE_G1S=0x6e7bb0
BNE_OPCODE=bytes.fromhex('81780054')
PRODUCER_SIGNED_OPCODES={
  0xc107d8:bytes.fromhex("f40319aa"), # mov x20,x25; mode4 context created
  0xc11f54:bytes.fromhex("880640f9"), # ldr x8,[x20,#8]; read failure clears source
}
SOURCE_PATCH=trace.patch_guest
SOURCE_VERIFY=trace.verify_guest
SOURCE_HOST=trace.patch_host
PAYLOADS={}

def read_original_packet(packet,kind):
    off,size,stored,plain,fileid,typeid,expected,magic,chunks=RECORDS[kind]
    def need(condition,label):
        if not condition:raise ValueError('Original FDATA '+kind+': '+label)
    need(len(packet)==size,'record length')
    m,es,cs,unc,parm,fid,tid,flags=struct.unpack_from('<8sQQQIIII',packet)
    need((m,es,cs,unc,fid,tid)==(b'IDRK0000',size,stored,plain,fileid,typeid),'IDRK identity')
    need(((flags>>20)&63)==4 and 0<stored<=size-48,'mode4 header')
    src=packet[-stored:];pos=0;data=bytearray();count=0
    while pos<len(src):
        if src[pos:]==b'\x00\x00':pos=len(src);break
        need(pos+10<=len(src),'truncated mode4 prefix')
        n=int.from_bytes(src[pos:pos+2],'little')
        need(0<n<=65536 and pos+10+n<=len(src),'invalid zlib chunk length')
        try:
            obj=zlib.decompressobj(15)
            out=obj.decompress(src[pos+10:pos+10+n])+obj.flush()
        except zlib.error as e:raise ValueError('Original mode4 zlib: invalid stream') from e
        need(obj.eof and not obj.unused_data and not obj.unconsumed_tail,'zlib integrity')
        data+=out;need(len(data)<=plain,'decoded size exceeded')
        pos+=10+n;count+=1
    need(pos==len(src) and count==chunks,'mode4 consumed wrong number of chunks')
    need(len(data)==plain and data[:8]==magic,'decoded native header')
    need(hashlib.sha256(data).hexdigest()==expected,'original SHA mismatch')
    return bytes(data)

def read_from_drive():
    from probe_resource_origin import Rom,Range
    rom=Rom(Range())
    if rom.info['size']!=7889449169 or rom.info['entries']!=14770:
        raise RuntimeError('Unexpected RomFS version: refuse asset substitution')
    return {name:read_original_packet(rom.at(FDATA,info[0],info[1]),name)
            for name,info in RECORDS.items()}

def payload_c(payloads):
    lines=['/* Original ROMFS IDRK+mode4+SHA source, generated in the Mac build. */']
    for name,raw in payloads.items():
        lines.append('static const unsigned char f2_auth_'+name+'['+str(len(raw))+']={')
        for off in range(0,len(raw),16):
            lines.append('  '+','.join('0x%02x'%b for b in raw[off:off+16])+',')
        lines.append('};')
    return '\n'.join(lines)+'\n'

HOST_C=r"""
/* FAIRY2_AUTHENTIC_DUAL_NATIVE_SOURCE: never bypass parser or abort. */
#include <mach/mach.h>
#include <stdint.h>
#include <unistd.h>
#include <string.h>
/* ORIGINAL_SOURCE_BYTES */
typedef struct {const void **vt;uint64_t cur;const unsigned char *p;uint64_t n;} f2_reader_t;
/* Pinned signed Fairy Tail 2 guest A64 main+c095c8/c09604:
 * vtable slot +0x18/+0x20 returns BYTES CONSUMED on this call, NOT
 * the absolute cursor, with the request clamped to remaining bytes. */
static uint64_t f2_skip(f2_reader_t *r,uint64_t n){
 if(!r||r->cur>r->n)return 0;
 uint64_t available=r->n-r->cur;
 uint64_t consumed=n<available?n:available;
 r->cur+=consumed;
 return consumed;
}
static uint64_t f2_read(f2_reader_t *r,void *dst,uint64_t unused,uint64_t n){
 (void)unused;
 if(!r||(!dst&&n)||r->cur>r->n)return 0;
 uint64_t available=r->n-r->cur;
 uint64_t consumed=n<available?n:available;
 if(consumed)memcpy(dst,r->p+r->cur,(size_t)consumed);
 r->cur+=consumed;
 return consumed;
}
static const void *f2_vt[5]={0,0,0,(const void *)f2_skip,(const void *)f2_read};
static __thread f2_reader_t f2_g1t_reader,f2_g1s_reader;
static unsigned f2_g1t_once,f2_g1s_once;
static int f2_auth_source_repair(ucontext_t *uc){
 uint64_t pc=uc->uc_mcontext->__ss.__pc;
 module_t *m=module_of((void *)(uintptr_t)pc);
 if(!m||strcmp(m->name,"main"))return 0;
 uint64_t at=pc-(uint64_t)(uintptr_t)m->base;
 if(at!=0x612120u&&at!=0x6e7bb0u)return 0;
 if(*(volatile uint32_t *)(uintptr_t)pc!=0xd43e4040u)return 0;
 unsigned z=(uc->uc_mcontext->__ss.__cpsr>>30)&1u;
 if(at==0x612120u){
   uint64_t reader=uc->uc_mcontext->__ss.__x[23],vt=0;
   vm_size_t n=0;
   kern_return_t rc=reader?vm_read_overwrite(mach_task_self(),
       (vm_address_t)reader,8,(vm_address_t)&vt,&n):KERN_INVALID_ADDRESS;
   if(z&&uc->uc_mcontext->__ss.__x[0]==0&&rc==KERN_SUCCESS&&n==8&&
      vt==(uint64_t)(uintptr_t)m->base+0x2a64540u&&
      __atomic_exchange_n(&f2_g1t_once,1,__ATOMIC_ACQ_REL)==0){
      f2_g1t_reader=(f2_reader_t){f2_vt,0,f2_auth_g1t,48};
      uc->uc_mcontext->__ss.__x[23]=(uint64_t)(uintptr_t)&f2_g1t_reader;
      uc->uc_mcontext->__ss.__x[2]=uc->uc_mcontext->__ss.__x[26];
      uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+0x61210cu;
      static const char msg[]="[dm] FAIRY2_SOURCE_REPAIR_G1T original 48 bytes, original parser retried\n";
      (void)write(2,msg,sizeof msg-1);
      return 1;
   }
   return 0; /* Original G1T NZCV hook retains the real B.EQ result. */
 }
 if(!z&&uc->uc_mcontext->__ss.__x[0]!=184&&
    __atomic_load_n(&f2_g1t_once,__ATOMIC_ACQUIRE)&&
    __atomic_exchange_n(&f2_g1s_once,1,__ATOMIC_ACQ_REL)==0){
    f2_g1s_reader=(f2_reader_t){f2_vt,0,f2_auth_g1s,18340};
    uc->uc_mcontext->__ss.__x[22]=(uint64_t)(uintptr_t)&f2_g1s_reader;
    uc->uc_mcontext->__ss.__x[8]=(uint64_t)(uintptr_t)f2_vt;
    uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+0x6e7b94u;
    static const char msg[]="[dm] FAIRY2_SOURCE_REPAIR_G1S original 18340 bytes, original parser retried\n";
    (void)write(2,msg,sizeof msg-1);
    return 1;
 }
 /* Original B.NE: PSTATE.Z=0 branches to failure. No forged result. */
 uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+
    (z?0x6e7bb4u:0x6e8ac0u);
 return 1;
}

/* FAIRY2_SIGNED_PRODUCER_PROVENANCE: original guest code values are checked
 * against read-only signed v458752 disassembly (45094304340). Both hooks
 * emulate the ORIGINAL AArch64 instructions. No rerouting of file reads,
 * no changes to PSTATE or allocator, no retries in the producer. */
static unsigned f2_mode4_return_count;
static unsigned f2_direct_reset_count;
static int f2_producer_branch_state(ucontext_t *uc){
 uint64_t pc=uc->uc_mcontext->__ss.__pc;
 module_t *m=module_of((void *)(uintptr_t)pc);
 if(!m||strcmp(m->name,"main"))return 0;
 uint64_t at=pc-(uint64_t)(uintptr_t)m->base;
 if(at!=0xc107d8u&&at!=0xc11f54u)return 0;
 if(*(volatile uint32_t *)(uintptr_t)pc!=0xd43e4040u)return 0;
 if(at==0xc107d8u){
   /* main+c107d8: MOV x20,x25; preceding c10d80 returned x0,
      the next c107dc tests bit 0 (success/failure) of that return. */
   unsigned n=__atomic_add_fetch(&f2_mode4_return_count,1,__ATOMIC_RELAXED);
   if(n<=64 || uc->uc_mcontext->__ss.__x[0]==0){
     char buf[300];
     int k=snprintf(buf,sizeof(buf),
       "[dm] FAIRY2_MODE4_PRODUCER_RETURN seq=%u result_x0=%#llx context_x25=%#llx reader_x22=%#llx fp=%#llx\n",
       n,(unsigned long long)uc->uc_mcontext->__ss.__x[0],
       (unsigned long long)uc->uc_mcontext->__ss.__x[25],
       (unsigned long long)uc->uc_mcontext->__ss.__x[22],
       (unsigned long long)uc->uc_mcontext->__ss.__fp);
     if(k>0&&(size_t)k<sizeof buf)(void)write(2,buf,(size_t)k);
   }
   uc->uc_mcontext->__ss.__x[20]=uc->uc_mcontext->__ss.__x[25];
   uc->uc_mcontext->__ss.__pc=pc+4;
   return 1;
 }
 /* main+c11f54: LDR x8,[x20,#8]; downstream C11F5C zeros [x20+8]
    on original direct stream failure. Probe the ACTUAL stream object
    at its original failure point before it is cleared. */
 uint64_t reader=uc->uc_mcontext->__ss.__x[20],source=0,raw[6]={0};
 vm_size_t nread=0;
 kern_return_t kr=reader?vm_read_overwrite(mach_task_self(),
    (vm_address_t)(reader+8),8,(vm_address_t)&source,&nread):
    KERN_INVALID_ADDRESS;
 if(kr!=KERN_SUCCESS||nread!=8)return 0; /* preserve fault semantics */
 nread=0;
 int snapshot_ok=(vm_read_overwrite(mach_task_self(),
    (vm_address_t)reader,sizeof raw,(vm_address_t)raw,&nread)==
    KERN_SUCCESS && nread==sizeof raw);
 unsigned seq=__atomic_add_fetch(&f2_direct_reset_count,1,__ATOMIC_RELAXED);
 if(seq<=128){
   char buf[550];
   int k=snprintf(buf,sizeof(buf),
    "[dm] FAIRY2_DIRECT_SOURCE_RESET seq=%u reader=%#llx input_source=%#llx snapshot_ok=%d vt=%#llx cursor0=%#llx cursor1=%#llx buffered_end=%#llx consumed_x19=%#llx requested_x21=%#llx remaining_x23=%#llx\n",
    seq,(unsigned long long)reader,(unsigned long long)source,
    snapshot_ok,(unsigned long long)raw[0],
    (unsigned long long)raw[4],(unsigned long long)raw[5],
    (unsigned long long)raw[3],
    (unsigned long long)uc->uc_mcontext->__ss.__x[19],
    (unsigned long long)uc->uc_mcontext->__ss.__x[21],
    (unsigned long long)uc->uc_mcontext->__ss.__x[23]);
   if(k>0&&(size_t)k<sizeof buf)(void)write(2,buf,(size_t)k);
 }
 uc->uc_mcontext->__ss.__x[8]=source;
 uc->uc_mcontext->__ss.__pc=pc+4;
 return 1;
}
"""

def patch_guest(exe,old):
    stamp=SOURCE_PATCH(exe,old)
    pieces,code=base.main_sections(exe)
    x0=pieces['x0']
    site_opcodes={BNE_G1S:BNE_OPCODE,**PRODUCER_SIGNED_OPCODES}
    for off,opcode in site_opcodes.items():
        base.require(off+4<=x0['size'] and code[off:off+4]==opcode,
            f"Signed guest production/read opcode drift main+0x{off:x}")
    with exe.open('r+b') as f:
        for off,opcode in site_opcodes.items():
            f.seek(x0['offset']+off)
            base.require(f.read(4)==opcode,
                f"Guest production site changed before write main+0x{off:x}")
            f.seek(x0['offset']+off)
            f.write(trace.BREAK)
    pieces_new,new=base.main_sections(exe)
    changed=bytearray(code)
    for off in site_opcodes:changed[off:off+4]=trace.BREAK
    base.require(new==bytes(changed) and
          pieces_new['w']['data']==pieces['w']['data'] and
          pieces_new['x1']['data']==pieces['x1']['data'],
          'Unexpected guest change')
    stamp['after_sha256']=hashlib.sha256(new).hexdigest()
    stamp['x0_after_sha256']=hashlib.sha256(pieces_new['x0']['data']).hexdigest()
    stamp['g1s_native_branch_original']='81780054'
    stamp['signed_producer_observation_hooks']={f"main+0x{at:x}":{
       "original":op.hex(),"emulated":True,"returns_unchanged":True}
       for at,op in PRODUCER_SIGNED_OPCODES.items()}
    return stamp

def verify_guest(exe,stamp):
    SOURCE_VERIFY(exe,stamp)
    _,raw=base.main_sections(exe)
    base.require(raw[BNE_G1S:BNE_G1S+4]==trace.BREAK and
       stamp['g1s_native_branch_original']=='81780054','G1S B.NE source hook missing')
    for at,op in PRODUCER_SIGNED_OPCODES.items():
        base.require(raw[at:at+4]==trace.BREAK and
          stamp['signed_producer_observation_hooks'][f"main+0x{at:x}"]["original"]==op.hex(),
          "Signed producer hook missing or original opcode not verified")

def patch_host(repo):
    SOURCE_HOST(repo)
    crash=repo/'engine/dm/host/crash.c'
    s=crash.read_text()
    extra=HOST_C.replace('/* ORIGINAL_SOURCE_BYTES */',payload_c(PAYLOADS))
    anchor='static void on_crash(int sig, siginfo_t *si, void *uc_) {'
    handler='    if (sig == SIGTRAP && f2_g1t_validator_branch(uc)) return;'
    base.require(s.count(anchor)==1 and s.count(handler)==1 and
                 'FAIRY2_AUTHENTIC_DUAL_NATIVE_SOURCE' not in s,
                 'Original host trap anchor differs')
    s=s.replace(anchor,extra+'\n'+anchor,1)
    s=s.replace(handler,
       '    if (sig == SIGTRAP && f2_producer_branch_state(uc)) return;\n'
       '    if (sig == SIGTRAP && f2_auth_source_repair(uc)) return;\n'+handler,1)
    crash.write_text(s)

def make(src,origin,repo,out):
    global PAYLOADS
    PAYLOADS=read_from_drive()
    trace.patch_guest=patch_guest
    trace.verify_guest=verify_guest
    trace.patch_host=patch_host
    try:report=trace.make(src,origin,repo,out)
    finally:
        trace.patch_guest=SOURCE_PATCH
        trace.verify_guest=SOURCE_VERIFY
        trace.patch_host=SOURCE_HOST
    report['authentic_source_g1t_sha256']=hashlib.sha256(PAYLOADS['g1t']).hexdigest()
    report['authentic_source_g1s_sha256']=hashlib.sha256(PAYLOADS['g1s']).hexdigest()
    report['original_parser_preserved']=True
    report['original_source_bytes_used_on_failure']=True
    report['no_shader_compile']=True
    report['gameplay_verified']=False
    report['source_dual_repair_candidate']=True
    report['signed_guest_producer_observed_without_changing_return']=True
    report['original_mode4_return_site']='main+0xc107d8'
    report['original_direct_reader_source_reset_site']='main+0xc11f54'
    report['original_guest_source_probes']={hex(k):v.hex() for k,v in PRODUCER_SIGNED_OPCODES.items()}
    (out/'ktgl-original-source-dual-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def selftest():
    assert RECORDS['g1t'][3:6]==(48,0xfb9ebd24,0xafbec60c)
    assert RECORDS['g1s'][3:6]==(18340,0xac9ed13e,0x7bcd279f)
    assert trace.BREAK.hex()=='40403ed4'
    assert BNE_OPCODE.hex()=='81780054'
    assert PRODUCER_SIGNED_OPCODES=={
        0xc107d8:bytes.fromhex('f40319aa'),
        0xc11f54:bytes.fromhex('880640f9')}
    assert 'FAIRY2_MODE4_PRODUCER_RETURN' in HOST_C
    assert 'FAIRY2_DIRECT_SOURCE_RESET' in HOST_C
    assert 'uc->uc_mcontext->__ss.__x[20]=uc->uc_mcontext->__ss.__x[25];' in HOST_C
    assert 'uc->uc_mcontext->__ss.__x[8]=source;' in HOST_C
    assert 'f2_auth_g1s,18340' in HOST_C and '0x6e7b94u' in HOST_C
    assert 'f2_auth_g1t,48' in HOST_C and '0x61210cu' in HOST_C
    assert '(z?0x6e7bb4u:0x6e8ac0u)' in HOST_C
    assert HOST_C.count('return consumed;')==2
    assert 'return r->cur;' not in HOST_C
    # Synthetic only for unit testing codec, never accepted as production SHA.
    data=b'GT1G0500'+bytes(40)
    comp=zlib.compress(data)
    blob=len(comp).to_bytes(2,'little')+bytes(8)+comp
    good=RECORDS['g1t']
    RECORDS['g1t']=(0,48+len(blob),len(blob),48,0xfb9ebd24,0xafbec60c,
                    hashlib.sha256(data).hexdigest(),b'GT1G0500',1)
    pkt=struct.pack('<8sQQQIIII',b'IDRK0000',48+len(blob),
                    len(blob),48,0,0xfb9ebd24,0xafbec60c,0x00400000)+blob
    try:
        assert read_original_packet(pkt,'g1t')==data
        try:read_original_packet(pkt[:-1]+b'\x00','g1t')
        except ValueError:pass
        else:raise AssertionError('truncated/tampered original was accepted')
    finally:RECORDS['g1t']=good
    print('Original FDATA G1T/G1S proof and native branch selftest: PASS')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--selftest',action='store_true')
    p.add_argument('--source-ipa',type=Path)
    p.add_argument('--source-report',type=Path)
    p.add_argument('--repo',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.selftest:selftest()
    else:
        if not all((a.source_ipa,a.source_report,a.repo,a.output)):
            p.error('source IPA/report/repo/output required')
        make(a.source_ipa,a.source_report,a.repo,a.output)
