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

/* M6.1: bounded 8-instruction guest PPU probe. Native stack isolated. */
int ar_ppu_bootstrap_eight(const uint8_t*d,size_t len,
                          const uint32_t info[5],uint32_t out[6]){
 if(!d||!info||!out)return -940;
 memset(out,0,6*sizeof(*out));
 uint32_t checked[5]={0};
 if(ar_private_elf_inspect(d,len,checked)||
    memcmp(checked,info,5*sizeof(*info)))return -941;
 segment segs[64]={0};unsigned used=0;
 uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.size&&s.mem)segs[used++]=s;
 }
 uint64_t gpr[32]={0};uint8_t stack[4096]={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0;
 if(pc>0xffffffe0u||(pc&3))return -942;
 for(unsigned step=0;step<8;step++){
  const uint8_t*p=lookup(d,len,segs,used,pc,4,1);
  if(!p)return -943;
  uint32_t w=b32(p);unsigned op=w>>26,rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   if(va>UINT32_MAX)return -944;
   const uint8_t*mem=lookup(d,len,segs,used,(uint32_t)va,4,0);
   if(!mem)return -945;
   gpr[rt]=b32(mem);
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -946;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -947;
   uint64_t value=gpr[rt];
   for(unsigned k=0;k<8;k++)
      stack[(size_t)(va-base)+k]=(uint8_t)(value>>(56-8*k));
   ++stores;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if((w&3u)!=1u)return -948;
   int64_t disp=(int64_t)(w&0x03fffffcu);
   if(disp&0x02000000)disp-=0x04000000;
   int64_t dest=(int64_t)pc+disp;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,segs,used,(uint32_t)dest,4,1))return -949;
   lr=next;next=(uint32_t)dest;
  }else{
   out[1]=w;return -950; /* never hide unknown guest opcode */
  }
  pc=next;out[0]++;
 }
 if(gpr[2]!=info[2]||stores!=2)return -951;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;
 return 0;
}
