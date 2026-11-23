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
static uint64_t f2_skip(f2_reader_t *r,uint64_t n){
 if(!r||n>r->n||r->cur>r->n-n)return 0;
 r->cur+=n;return r->cur;
}
static uint64_t f2_read(f2_reader_t *r,void *dst,uint64_t unused,uint64_t n){
 (void)unused;
 if(!r||!dst||n>r->n||r->cur>r->n-n)return 0;
 memcpy(dst,r->p+r->cur,(size_t)n);r->cur+=n;return n;
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
"""

def patch_guest(exe,old):
    stamp=SOURCE_PATCH(exe,old)
    pieces,code=base.main_sections(exe)
    x0=pieces['x0']
    base.require(code[BNE_G1S:BNE_G1S+4]==BNE_OPCODE and
                 BNE_G1S+4<=x0['size'],'Original G1S B.NE opcode drift')
    with exe.open('r+b') as f:
        f.seek(x0['offset']+BNE_G1S)
        base.require(f.read(4)==BNE_OPCODE,'G1S original code modified')
        f.seek(x0['offset']+BNE_G1S);f.write(trace.BREAK)
    pieces_new,new=base.main_sections(exe)
    changed=bytearray(code);changed[BNE_G1S:BNE_G1S+4]=trace.BREAK
    base.require(new==bytes(changed) and
          pieces_new['w']['data']==pieces['w']['data'] and
          pieces_new['x1']['data']==pieces['x1']['data'],
          'Unexpected guest change')
    stamp['after_sha256']=hashlib.sha256(new).hexdigest()
    stamp['x0_after_sha256']=hashlib.sha256(pieces_new['x0']['data']).hexdigest()
    stamp['g1s_native_branch_original']='81780054'
    return stamp

def verify_guest(exe,stamp):
    SOURCE_VERIFY(exe,stamp)
    _,raw=base.main_sections(exe)
    base.require(raw[BNE_G1S:BNE_G1S+4]==trace.BREAK and
       stamp['g1s_native_branch_original']=='81780054','G1S B.NE source hook missing')

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
    (out/'ktgl-original-source-dual-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def selftest():
    assert RECORDS['g1t'][3:6]==(48,0xfb9ebd24,0xafbec60c)
    assert RECORDS['g1s'][3:6]==(18340,0xac9ed13e,0x7bcd279f)
    assert trace.BREAK.hex()=='40403ed4'
    assert BNE_OPCODE.hex()=='81780054'
    assert 'f2_auth_g1s,18340' in HOST_C and '0x6e7b94u' in HOST_C
    assert 'f2_auth_g1t,48' in HOST_C and '0x61210cu' in HOST_C
    assert '(z?0x6e7bb4u:0x6e8ac0u)' in HOST_C
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
