/* M5.9: fail-closed, no guest code execution or game files embedded. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
static uint16_t b16(const uint8_t*p){return ((uint16_t)p[0]<<8)|p[1];}
static uint32_t b32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t b64(const uint8_t*p){return ((uint64_t)b32(p)<<32)|b32(p+4);}
static int within(uint64_t a,uint64_t n,uint64_t max){return a<=max&&n<=max-a;}
typedef struct{uint64_t offset,va,size,mem;uint32_t flags;} segment;
static const uint8_t *lookup(const uint8_t*d,size_t len,const segment*s,
 unsigned count,uint64_t va,unsigned n,unsigned perms){
 for(unsigned i=0;i<count;i++){
  const segment*x=s+i;
  if(perms && !(x->flags&perms))continue;
  if(va>=x->va&&within(va-x->va,n,x->size)&&
     within(x->offset+(va-x->va),n,len))return d+x->offset+(va-x->va);
 }
 return NULL;
}
/* Output: opd address, entry code, toc, first PPC instruction, segment count. */
int ar_private_elf_inspect(const uint8_t*d,size_t len,uint32_t info[5]){
 if(!info)return -901;
 memset(info,0,5*sizeof(*info));
 if(!d||len<64||len>32u*1024u*1024u)return -902;
 if(memcmp(d,"\177ELF",4)||d[4]!=2||d[5]!=2||d[6]!=1||d[7]!=0x66||
    b16(d+16)!=2||b16(d+18)!=21||b32(d+20)!=1)return -903;
 uint64_t entry=b64(d+24),offset=b64(d+32);
 uint16_t phsize=b16(d+54),n=b16(d+56);
 if(b16(d+52)<64||phsize<56||!n||n>64||
    !within(offset,(uint64_t)n*phsize,len))return -904;
 segment s[64]={0};unsigned used=0,executable=0;
 for(unsigned i=0;i<n;i++){
  const uint8_t*p=d+offset+(uint64_t)i*phsize;
  if(b32(p)!=1)continue;
  segment seg={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(!seg.mem&&!seg.size)continue;
  if(seg.size>seg.mem||!within(seg.offset,seg.size,len)||
     !within(seg.va,seg.mem,128u*1024u*1024u))return -905;
  for(unsigned j=0;j<used;j++)
   if(seg.va<s[j].va+s[j].mem&&s[j].va<seg.va+seg.mem)return -906;
  s[used++]=seg;if(seg.flags&1)executable++;
 }
 if(!used||!executable||entry>UINT32_MAX||(entry&3))return -907;
 const uint8_t*opd=lookup(d,len,s,used,entry,8,0);
 if(!opd)return -908;
 uint32_t code=b32(opd),toc=b32(opd+4);
 const uint8_t*word=lookup(d,len,s,used,code,4,1);
 if(!code||(code&3)||!word)return -909;
 int toc_ok=0;
 for(unsigned i=0;i<used;i++)
  if(toc>=s[i].va&&within(toc-s[i].va,4,s[i].mem))toc_ok=1;
 if(!toc_ok)return -910;
 info[0]=(uint32_t)entry;info[1]=code;info[2]=toc;info[3]=b32(word);info[4]=used;
 return 0;
}

/* M6.0: no HLE/syscalls/stack/guest writes. Precisely four PowerPC64
 * instructions from an on-device, user-selected decrypted ELF.
 * This strict CPU probe is NOT a game boot or a general PPU emulator. */
int ar_ppu_bootstrap_four(const uint8_t*d,size_t len,
                          const uint32_t info[5],uint32_t out[4]){
 if(!d||!info||!out)return -930;
 memset(out,0,4*sizeof(*out));
 uint32_t checked[5]={0};
 if(ar_private_elf_inspect(d,len,checked)||
    memcmp(checked,info,5*sizeof(*info)))return -931;
 uint64_t table=b64(d+32);
 unsigned phsize=b16(d+54),n=b16(d+56);
 segment segs[64]={0};unsigned used=0;
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.size&&s.mem)segs[used++]=s;
 }
 uint64_t gpr[32]={0};gpr[2]=info[2];
 uint32_t pc=info[1];
 if(pc>0xfffffff0u||(pc&3))return -932;
 for(unsigned step=0;step<4;step++){
  const uint8_t*p=lookup(d,len,segs,used,pc,4,1);
  if(!p)return -933;
  uint32_t word=b32(p),op=word>>26;
  unsigned rt=(word>>21)&31,ra=(word>>16)&31;
  int16_t imm=(int16_t)(word&0xffffu);
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(word&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(word&0xffffu);
  }else if(op==32){
   uint64_t addr=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   if(addr>UINT32_MAX)return -934;
   const uint8_t*mem=lookup(d,len,segs,used,(uint32_t)addr,4,0);
   if(!mem)return -935;
   gpr[rt]=b32(mem);
  }else{
   out[3]=word;
   return -936; /* unsupported guest instruction: NEVER emulate as NOP */
  }
  ++out[0];pc+=4;
 }
 if(gpr[2]!=info[2])return -937;
 out[1]=(uint32_t)gpr[2];out[2]=pc;
 return 0;
}
