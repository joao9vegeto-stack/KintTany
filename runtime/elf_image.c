/* PS3 ELF64 MSB PowerPC64 ET_EXEC PT_LOAD/OPD staging. No code execution. */
#include "elf_image.h"
#include <string.h>
#define MAX_SEGS 64
static uint16_t b16(const uint8_t*p){return ((uint16_t)p[0]<<8)|p[1];}
static uint32_t b32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t b64(const uint8_t*p){return ((uint64_t)b32(p)<<32)|b32(p+4);}
struct seg{uint64_t off,va,fs,ms;uint32_t flags;};
static int in_file(uint64_t off,uint64_t n,size_t len){return off<=len&&n<=(uint64_t)len-off;}
static int in_guest(uint64_t va,uint64_t n,size_t len){return va<=UINT32_MAX&&n<=(uint64_t)len&&va<=(uint64_t)len-n;}
static int has(const struct seg*s,uint64_t addr,uint64_t n){
 return addr>=s->va&&n<=s->ms&&addr-s->va<=s->ms-n;
}
int ar_load_elf_image(const uint8_t*d,size_t size,size_t cap,
                      ppu_context*c,ar_elf_image_result*out){
 if(!d||!c||!out||size<64||!cap||cap>128u*1024u*1024u)return AR_BAD_ARGS;
 if(memcmp(d,"\177ELF",4)||d[4]!=2||d[5]!=2||d[6]!=1||
    b16(d+16)!=2||b16(d+18)!=21||b32(d+20)!=1)return AR_BAD_ARGS;
 uint64_t entry=b64(d+24),phoff=b64(d+32);
 uint16_t ehsz=b16(d+52),entsz=b16(d+54),count=b16(d+56);
 if(ehsz<64||entsz<56||!count||count>MAX_SEGS||
    !in_file(phoff,(uint64_t)entsz*count,size))return AR_BAD_ARGS;
 struct seg segs[MAX_SEGS];unsigned used=0;uint64_t bytes=0,bss=0;
 for(unsigned i=0;i<count;i++){
    const uint8_t*p=d+phoff+(uint64_t)i*entsz;
    if(b32(p)!=1)continue;
    struct seg s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
    if(s.fs>s.ms||!in_file(s.off,s.fs,size)||!in_guest(s.va,s.ms,cap))
        return AR_BAD_ARGS;
    if(!s.ms)continue;
    for(unsigned j=0;j<used;j++){
        const struct seg*t=&segs[j];
        if(s.va<t->va+t->ms&&t->va<s.va+s.ms)return AR_BAD_ARGS;
    }
    bytes+=s.fs;bss+=s.ms-s.fs;
    segs[used++]=s;
 }
 if(!used||entry>UINT32_MAX||(entry&3))return AR_BAD_ARGS;
 const struct seg*es=NULL;
 for(unsigned i=0;i<used;i++)
    if(segs[i].fs>=8&&has(&segs[i],entry,8)&&entry-segs[i].va<=segs[i].fs-8)
       es=&segs[i];
 if(!es)return AR_BAD_ARGS;
 const uint8_t*opd=d+es->off+(entry-es->va);
 uint32_t code=b32(opd),toc=b32(opd+4);
 int code_ok=0,toc_ok=0;
 for(unsigned i=0;i<used;i++){
    const struct seg*s=&segs[i];
    if((s->flags&1)&&s->fs>=4&&has(s,code,4)&&code-s->va<=s->fs-4)
        code_ok=1;
    if(has(s,toc,4))toc_ok=1;
 }
 if(!code_ok||!toc_ok||!code||(code&3))return AR_BAD_ARGS;
 /* Both regions and descriptor verified before guest memory is modified. */
 for(unsigned i=0;i<used;i++){
    const struct seg*s=&segs[i];
    if(ar_vm_load(s->va,d+s->off,(size_t)s->fs)!=AR_OK)return AR_MEM_FAULT;
    if(ar_vm_zero(s->va+s->fs,(size_t)(s->ms-s->fs))!=AR_OK)return AR_MEM_FAULT;
 }
 c->gpr[2]=toc;c->cia=code;
 *out=(ar_elf_image_result){code,(uint32_t)entry,toc,used,bytes,bss};
 return AR_OK;
}
