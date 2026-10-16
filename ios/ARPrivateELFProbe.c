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

/* M6.2: STRICT and isolated sixteen-step PowerPC entry path.
 * No guest bytes are distributed, and no HLE/OS/device calls happen.
 * Guest memory reads are only from PT_LOAD and writes are to a private
 * 4KiB virtual stack. Stops BEFORE invoking any imported function. */
int ar_ppu_bootstrap_sixteen(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[7]){
 if(!d||!info||!out)return -960;
 memset(out,0,7*sizeof(*out));
 uint32_t check[5]={0};
 if(ar_private_elf_inspect(d,len,check)||
    memcmp(info,check,sizeof(check)))return -961;
 segment ss[64]={0};unsigned used=0;
 const uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.mem&&s.size)ss[used++]=s;
 }
 uint64_t gpr[32]={0};
 uint8_t stack[4096]={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 if(pc>0xffffffbfu||(pc&3))return -962;
 for(unsigned step=0;step<16;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p)return -963;
  const uint32_t w=b32(p),op=w>>26;
  unsigned rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);
  uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   if(va>UINT32_MAX)return -964;
   const uint8_t*q=lookup(d,len,ss,used,(uint32_t)va,4,0);
   if(!q)return -965;
   gpr[rt]=b32(q);
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -966;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -967;
   for(unsigned j=0;j<8;j++)
      stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   stores++;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if((w&3u)!=1u)return -968;
   int64_t delta=(int64_t)(w&0x03fffffcu);
   if(delta&0x02000000)delta-=0x04000000;
   const int64_t dest=(int64_t)pc+delta;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,ss,used,(uint32_t)dest,4,1))return -969;
   lr=next;next=(uint32_t)dest;
  }else if(op==31 && ((w>>1)&1023u)==339u &&
            ((w>>11)&1023u)==256u && !(w&1u)){
   /* mflr rT, encoded SPR=8 => 0x100. No arbitrary SPR access. */
   gpr[rt]=lr;mflr++;
  }else{
   out[1]=w;return -970; /* unsupported opcode must fail */
  }
  pc=next;out[0]++;
 }
 if(gpr[2]!=info[2]||stores!=9u||mflr!=1u||gpr[0]!=lr)return -971;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;out[6]=(uint32_t)gpr[0];
 return 0;
}

/* Power ISA rldicl (MD form, XO=0, Rc=0). Bit index 0 is MSB.
 * Input and output remain uint64_t; shifts of 0 or 64 are guarded.
 * Unsupported MD forms / record-setting instructions FAIL CLOSED.
 * Reference: PowerPC rldicl RA,RS,SH,MB. */
int ar_ppu_rldicl(uint32_t w,uint64_t source,uint64_t *result) {
 if(!result || (w>>26)!=30u || ((w>>2)&7u)!=0u || (w&1u))return -1;
 const unsigned sh=((w>>11)&31u)|((w&2u)<<4);
 const unsigned mb=((w>>6)&31u)|(w&0x20u);
 const uint64_t rot=sh ? (source<<sh)|(source>>(64u-sh)) : source;
 const uint64_t mask=mb ? (UINT64_MAX>>(mb)) : UINT64_MAX;
 *result=rot&mask;
 return 0;
}

/* M6.3 private bounded PPU continuation, 24 instructions MAX.
 * No guest code bundled or uploaded. On error out[7]=raw opcode,
 * out[8]=PC; unsupported operations FAIL CLOSED. */
int ar_ppu_bootstrap_twentyfour(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[9]){
 if(!d||!info||!out)return -980;
 memset(out,0,9*sizeof(*out));
 uint32_t check[5]={0};
 if(ar_private_elf_inspect(d,len,check)||
    memcmp(info,check,sizeof(check)))return -981;
 segment ss[64]={0};unsigned used=0;
 const uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.mem&&s.size)ss[used++]=s;
 }
 uint64_t gpr[32]={0};
 uint8_t stack[4096]={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 if(pc>0xffffffbfu||(pc&3))return -982;
 for(unsigned step=0;step<24;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p){out[8]=pc;return -983;}
  const uint32_t w=b32(p),op=w>>26;
  out[7]=w;out[8]=pc;
  unsigned rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);
  uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==15){
   gpr[rt]=(ra?gpr[ra]:0u)+(((uint64_t)(int64_t)imm)<<16);
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   if(va>UINT32_MAX)return -984;
   const uint8_t*q=lookup(d,len,ss,used,(uint32_t)va,4,0);
   if(!q)return -985;
   gpr[rt]=b32(q);
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -986;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -987;
   for(unsigned j=0;j<8;j++)
      stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   stores++;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if(w&2u)return -988; /* only relative branches */
   int64_t delta=(int64_t)(w&0x03fffffcu);
   if(delta&0x02000000)delta-=0x04000000;
   const int64_t dest=(int64_t)pc+delta;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,ss,used,(uint32_t)dest,4,1))return -989;
   if(w&1u)lr=next;
   next=(uint32_t)dest;
  }else if(op==58){
   if(!ra||(w&3u)!=0u)return -991;
   const int16_t ds=(int16_t)(w&0xfffcu);
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va>=base&&va<=base+sizeof(stack)-8)
      gpr[rt]=b64(stack+(size_t)(va-base));
   else {
      if(va>UINT32_MAX)return -992;
      const uint8_t*q=lookup(d,len,ss,used,(uint32_t)va,8,0);
      if(!q)return -993;
      gpr[rt]=b64(q);
   }
  }else if(op==36){
   if(!ra)return -994;
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)imm;
   if(va<base||va>base+sizeof(stack)-4)return -995;
   const uint32_t v=(uint32_t)gpr[rt];
   for(unsigned k=0;k<4;k++)stack[(size_t)(va-base)+k]=(uint8_t)(v>>(24-8*k));
   stores++;
  }else if(op==30){
   /* PowerPC MD-form rldicl, e.g. clrldi r4,r8,32 (0x79040020).
    * Preserve exact GPR 64-bit masking, refuse other XO/Rc forms. */
   uint64_t rotated=0;
   if(ar_ppu_rldicl(w,gpr[rt],&rotated))return -998;
   gpr[ra]=rotated;
  }else if(op==31 && ((w>>1)&1023u)==444u && !(w&1u)){
   const unsigned rb=(w>>11)&31u;
   gpr[ra]=gpr[rt]|gpr[rb];
  }else if(op==31 && ((w>>1)&1023u)==339u &&
            ((w>>11)&1023u)==256u && !(w&1u)){
   /* mflr rT, encoded SPR=8 => 0x100. No arbitrary SPR access. */
   gpr[rt]=lr;mflr++;
  }else{
   out[1]=w;return -990; /* unsupported opcode must fail */
  }
  pc=next;out[0]++;
  if(step==15u && (gpr[2]!=info[2]||stores!=9u||mflr!=1u||gpr[0]!=lr))return -996;
 }
 if(gpr[2]!=info[2])return -997;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;out[6]=(uint32_t)gpr[0];
 return 0;
}

/* M6.4: optional 32 guest-instruction continuation; checked 16-step
 * prefix, private sandbox and fail-closed PC/opcode preserved. */
int ar_ppu_bootstrap_thirtytwo(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[10]){
 if(!d||!info||!out)return -980;
 memset(out,0,10*sizeof(*out));
 uint32_t check[5]={0};
 if(ar_private_elf_inspect(d,len,check)||
    memcmp(info,check,sizeof(check)))return -981;
 segment ss[64]={0};unsigned used=0;
 const uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.mem&&s.size)ss[used++]=s;
 }
 uint64_t gpr[32]={0};
 uint8_t stack[4096]={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 if(pc>0xffffff7fu||(pc&3))return -982;
 for(unsigned step=0;step<32;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p){out[8]=pc;return -983;}
  const uint32_t w=b32(p),op=w>>26;
  out[7]=w;out[8]=pc;
  unsigned rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);
  uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==15){
   gpr[rt]=(ra?gpr[ra]:0u)+(((uint64_t)(int64_t)imm)<<16);
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   if(va>UINT32_MAX)return -984;
   const uint8_t*q=lookup(d,len,ss,used,(uint32_t)va,4,0);
   if(!q)return -985;
   gpr[rt]=b32(q);
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -986;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -987;
   for(unsigned j=0;j<8;j++)
      stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   stores++;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if(w&2u)return -988; /* only relative branches */
   int64_t delta=(int64_t)(w&0x03fffffcu);
   if(delta&0x02000000)delta-=0x04000000;
   const int64_t dest=(int64_t)pc+delta;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,ss,used,(uint32_t)dest,4,1))return -989;
   if(w&1u)lr=next;
   next=(uint32_t)dest;
  }else if(op==58){
   if(!ra||(w&3u)!=0u)return -991;
   const int16_t ds=(int16_t)(w&0xfffcu);
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va>=base&&va<=base+sizeof(stack)-8)
      gpr[rt]=b64(stack+(size_t)(va-base));
   else {
      if(va>UINT32_MAX)return -992;
      const uint8_t*q=lookup(d,len,ss,used,(uint32_t)va,8,0);
      if(!q)return -993;
      gpr[rt]=b64(q);
   }
  }else if(op==36){
   if(!ra)return -994;
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)imm;
   if(va<base||va>base+sizeof(stack)-4)return -995;
   const uint32_t v=(uint32_t)gpr[rt];
   for(unsigned k=0;k<4;k++)stack[(size_t)(va-base)+k]=(uint8_t)(v>>(24-8*k));
   stores++;
  }else if(op==30){
   /* PowerPC MD-form rldicl, e.g. clrldi r4,r8,32 (0x79040020).
    * Preserve exact GPR 64-bit masking, refuse other XO/Rc forms. */
   uint64_t rotated=0;
   if(ar_ppu_rldicl(w,gpr[rt],&rotated))return -998;
   gpr[ra]=rotated;
  }else if(op==31 && ((w>>1)&1023u)==444u && !(w&1u)){
   const unsigned rb=(w>>11)&31u;
   gpr[ra]=gpr[rt]|gpr[rb];
  }else if(op==31 && ((w>>1)&1023u)==339u &&
            ((w>>11)&1023u)==256u && !(w&1u)){
   /* mflr rT, encoded SPR=8 => 0x100. No arbitrary SPR access. */
   gpr[rt]=lr;mflr++;
  }else{
   out[1]=w;return -990; /* unsupported opcode must fail */
  }
  pc=next;out[0]++;
  if(step==15u && (gpr[2]!=info[2]||stores!=9u||mflr!=1u||gpr[0]!=lr))return -996;
 }
 if(gpr[2]!=info[2])return -997;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;out[6]=(uint32_t)gpr[0];
 out[9]=(uint32_t)gpr[4]; /* visible proof of rldicl on synthetic 32-step fixture */
 return 0;
}

/* M6.5: bounded private guest-memory overlay, 128 aligned 32-bit writes.
 * These are GUEST addresses (not native pointers). PT_LOAD permissions
 * and p_memsz are checked before ANY write. Original GOWA.ELF bytes are
 * immutable and never uploaded. PT_LOAD BSS bytes start at zero.
 * Unknown pointers, misaligned accesses, exhausted overlay fail closed. */
typedef struct {uint64_t address;uint32_t value;} m65_written_word;
typedef struct {m65_written_word word[128];unsigned used;} m65_memory;
static int m65_segment(const segment*s,unsigned count,uint64_t va,
                       unsigned bytes,unsigned required) {
 for(unsigned i=0;i<count;i++)
  if((!required||(s[i].flags&required)==required)&&
     va>=s[i].va && within(va-s[i].va,bytes,s[i].mem))return (int)i;
 return -1;
}
static int m65_store32(m65_memory*m,const segment*s,unsigned count,
                       uint64_t va,uint32_t value) {
 if(!m||(va&3u)||m65_segment(s,count,va,4u,2u)<0)return -1;
 for(unsigned j=0;j<m->used;j++)
  if(m->word[j].address==va){m->word[j].value=value;return 0;}
 if(m->used>=128u)return -2;
 m->word[m->used].address=va;
 m->word[m->used].value=value;
 m->used++;
 return 0;
}
static int m65_read_guest(const uint8_t*d,size_t len,const segment*s,
                 unsigned count,const m65_memory*m,
                 const uint8_t*stack,uint64_t stackbase,
                 uint64_t va,unsigned bytes,uint64_t *result) {
 if(!result||!bytes||bytes>8u||va>UINT32_MAX)return -1;
 if(va>=stackbase&&within(va-stackbase,bytes,4096u)) {
   uint64_t v=0;
   for(unsigned i=0;i<bytes;i++)v=(v<<8)|stack[(size_t)(va-stackbase)+i];
   *result=v;return 0;
 }
 const int ix=m65_segment(s,count,va,bytes,0u);
 if(ix<0)return -2;
 const segment*seg=s+ix;
 uint64_t v=0;
 for(unsigned k=0;k<bytes;k++){
    const uint64_t a=va+k;
    unsigned char byte=0;
    const uint64_t relative=a-seg->va;
    if(relative<seg->size){
       const uint64_t off=seg->offset+relative;
       if(off>=len)return -3;
       byte=d[off];
    }
    for(unsigned j=0;j<m->used;j++)
      if(a>=m->word[j].address && a-m->word[j].address<4u){
        unsigned shift=(unsigned)(3u-(a-m->word[j].address))*8u;
        byte=(uint8_t)(m->word[j].value>>shift);
        break;
      }
    v=(v<<8)|byte;
 }
 *result=v;
 return 0;
}

/* M6.5: PPU40 with PRIVATE sparse writable PT_LOAD overlay and BSS.
 * Real device may stop before 40: failure reports PC/opcode/guest EA.
 * No guest address is ever dereferenced as a native pointer. */
int ar_ppu_bootstrap_forty(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[16]){
 if(!d||!info||!out)return -980;
 memset(out,0,16*sizeof(*out));
 uint32_t check[5]={0};
 if(ar_private_elf_inspect(d,len,check)||
    memcmp(info,check,sizeof(check)))return -981;
 segment ss[64]={0};unsigned used=0;
 const uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.mem&&s.size)ss[used++]=s;
 }
 uint64_t gpr[32]={0};
 uint8_t stack[4096]={0};
 m65_memory guest={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 if(pc>0xffffff5fu||(pc&3))return -982;
 for(unsigned step=0;step<40;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p){out[8]=pc;return -983;}
  const uint32_t w=b32(p),op=w>>26;
  out[7]=w;out[8]=pc;
  unsigned rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);
  uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==15){
   gpr[rt]=(ra?gpr[ra]:0u)+(((uint64_t)(int64_t)imm)<<16);
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   const uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   uint64_t value=0;
   if(m65_read_guest(d,len,ss,used,&guest,stack,base,va,4,&value)) {
      out[10]=(uint32_t)va;return -1001;
   }
   gpr[rt]=value;
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -986;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -987;
   for(unsigned j=0;j<8;j++)
      stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   stores++;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if(w&2u)return -988; /* only relative branches */
   int64_t delta=(int64_t)(w&0x03fffffcu);
   if(delta&0x02000000)delta-=0x04000000;
   const int64_t dest=(int64_t)pc+delta;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,ss,used,(uint32_t)dest,4,1))return -989;
   if(w&1u)lr=next;
   next=(uint32_t)dest;
  }else if(op==58){
   if(!ra||(w&3u)!=0u)return -991;
   const int16_t ds=(int16_t)(w&0xfffcu);
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   uint64_t value=0;
   if(m65_read_guest(d,len,ss,used,&guest,stack,base,va,8,&value)) {
       out[10]=(uint32_t)va;return -1002;
   }
   gpr[rt]=value;
  }else if(op==36){
   /* Exact device opcode 0x93AB0000: stw r29,0(r11).
    * Permit stack OR writable guest PT_LOAD (including BSS), nothing else.
    * Save the effective address for an accurate physical-device diagnosis. */
   const uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   const uint32_t v=(uint32_t)gpr[rt];
   out[10]=(uint32_t)va;out[11]=(uint32_t)gpr[ra];out[12]=v;
   if(!ra||va>UINT32_MAX||(va&3u))return -1003;
   if(va>=base&&within(va-base,4u,sizeof(stack))) {
       for(unsigned k=0;k<4u;k++)
          stack[(size_t)(va-base)+k]=(uint8_t)(v>>(24u-8u*k));
   }else{
       const int rc=m65_store32(&guest,ss,used,va,v);
       if(rc)return rc==-2 ? -1005 : -1004;
   }
   stores++;
  }else if(op==30){
   /* PowerPC MD-form rldicl, e.g. clrldi r4,r8,32 (0x79040020).
    * Preserve exact GPR 64-bit masking, refuse other XO/Rc forms. */
   uint64_t rotated=0;
   if(ar_ppu_rldicl(w,gpr[rt],&rotated))return -998;
   gpr[ra]=rotated;
  }else if(op==31 && ((w>>1)&1023u)==444u && !(w&1u)){
   const unsigned rb=(w>>11)&31u;
   gpr[ra]=gpr[rt]|gpr[rb];
  }else if(op==31 && ((w>>1)&1023u)==339u &&
            ((w>>11)&1023u)==256u && !(w&1u)){
   /* mflr rT, encoded SPR=8 => 0x100. No arbitrary SPR access. */
   gpr[rt]=lr;mflr++;
  }else{
   out[1]=w;return -990; /* unsupported opcode must fail */
  }
  pc=next;out[0]++;
  if(step==15u && (gpr[2]!=info[2]||stores!=9u||mflr!=1u||gpr[0]!=lr))return -996;
 }
 if(gpr[2]!=info[2])return -997;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;out[6]=(uint32_t)gpr[0];
 out[9]=(uint32_t)gpr[4];
 out[13]=(uint32_t)gpr[12];out[14]=(uint32_t)gpr[13];
 out[15]=guest.used; /* distinct guest PT_LOAD shadow words */
 return 0;
}

/* M6.6 — strict CTR/mtspr and bounded PPU48 continuation.
 * 0x7C0903A6 = mtctr r0 observed on private NPUA80918 at PC=0x669C2C.
 * The next branch is validated against ELF executable segments, and no
 * guest address becomes a native host pointer. Zero per-step stale EA. */
/* M6.7: optional trace of bounded guest execution; no permission changes. */
int ar_ppu_bootstrap_fortyeight_trace(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[20],
                             uint32_t trace[24]){
 if(!d||!info||!out)return -980;
 memset(out,0,20*sizeof(*out));
 if(trace)memset(trace,0,24*sizeof(*trace));
 uint32_t check[5]={0};
 if(ar_private_elf_inspect(d,len,check)||
    memcmp(info,check,sizeof(check)))return -981;
 segment ss[64]={0};unsigned used=0;
 const uint64_t table=b64(d+32);unsigned phsize=b16(d+54),n=b16(d+56);
 for(unsigned j=0;j<n;j++){
  const uint8_t*p=d+table+(uint64_t)j*phsize;
  if(b32(p)!=1)continue;
  segment s={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
  if(s.mem&&s.size)ss[used++]=s;
 }
 uint64_t gpr[32]={0};
 uint8_t stack[4096]={0};
 m65_memory guest={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 uint64_t ctr=0;
 if(pc>0xffffff3fu||(pc&3))return -982;
 for(unsigned step=0;step<48;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p){out[8]=pc;return -983;}
  const uint32_t w=b32(p),op=w>>26;
  const uint64_t prior_r0=gpr[0];
  out[7]=w;out[8]=pc;
  if(trace){
   unsigned ix=(trace[15]&3u);
   trace[16u+2u*ix]=pc;
   trace[17u+2u*ix]=w;
   trace[15]++;
   trace[5]=(uint32_t)gpr[0];trace[6]=(uint32_t)(gpr[0]>>32);
  }
  /* Per-step diagnostics: never leak a previous memory EA when the
   * CURRENT failing opcode is e.g. mtctr, bctr, or unknown. */
  out[10]=out[11]=out[12]=0u;
  out[16]=0u;out[17]=(uint32_t)ctr;out[18]=(uint32_t)(ctr>>32);
  unsigned rt=(w>>21)&31,ra=(w>>16)&31;
  int16_t imm=(int16_t)(w&0xffffu);
  uint32_t next=pc+4;
  if(op==14){
   gpr[rt]=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
  }else if(op==15){
   gpr[rt]=(ra?gpr[ra]:0u)+(((uint64_t)(int64_t)imm)<<16);
  }else if(op==25){
   gpr[ra]=gpr[rt]|((uint64_t)(w&0xffffu)<<16);
  }else if(op==24){
   gpr[ra]=gpr[rt]|(uint64_t)(w&0xffffu);
  }else if(op==32){
   const uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   uint64_t value=0;
   if(m65_read_guest(d,len,ss,used,&guest,stack,base,va,4,&value)) {
      out[10]=(uint32_t)va;out[16]=1u;return -1001;
   }
   gpr[rt]=value;
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -986;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va<base||va>base+sizeof(stack)-8)return -987;
   for(unsigned j=0;j<8;j++)
      stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   stores++;
   if((w&3u)==1u)gpr[ra]=va;
  }else if(op==18){
   if(w&2u)return -988; /* only relative branches */
   int64_t delta=(int64_t)(w&0x03fffffcu);
   if(delta&0x02000000)delta-=0x04000000;
   const int64_t dest=(int64_t)pc+delta;
   if(dest<0||dest>UINT32_MAX||
      !lookup(d,len,ss,used,(uint32_t)dest,4,1))return -989;
   if(w&1u)lr=next;
   next=(uint32_t)dest;
  }else if(op==58){
   if(!ra||(w&3u)!=0u)return -991;
   const int16_t ds=(int16_t)(w&0xfffcu);
   const uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   uint64_t value=0;
   if(m65_read_guest(d,len,ss,used,&guest,stack,base,va,8,&value)) {
       out[10]=(uint32_t)va;out[16]=1u;return -1002;
   }
   gpr[rt]=value;
  }else if(op==36){
   /* Exact device opcode 0x93AB0000: stw r29,0(r11).
    * Permit stack OR writable guest PT_LOAD (including BSS), nothing else.
    * Save the effective address for an accurate physical-device diagnosis. */
   const uint64_t va=(ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm;
   const uint32_t v=(uint32_t)gpr[rt];
   if(!ra||va>UINT32_MAX||(va&3u)){
      out[10]=(uint32_t)va;out[11]=(uint32_t)gpr[ra];out[12]=v;
      out[16]=1u;return -1003;
   }
   if(va>=base&&within(va-base,4u,sizeof(stack))) {
       for(unsigned k=0;k<4u;k++)
          stack[(size_t)(va-base)+k]=(uint8_t)(v>>(24u-8u*k));
   }else{
       const int rc=m65_store32(&guest,ss,used,va,v);
       if(rc) {
          out[10]=(uint32_t)va;out[11]=(uint32_t)gpr[ra];out[12]=v;
          out[16]=1u;
          return rc==-2 ? -1005 : -1004;
       }
   }
   stores++;
  }else if(op==30){
   /* PowerPC MD-form rldicl, e.g. clrldi r4,r8,32 (0x79040020).
    * Preserve exact GPR 64-bit masking, refuse other XO/Rc forms. */
   uint64_t rotated=0;
   if(ar_ppu_rldicl(w,gpr[rt],&rotated))return -998;
   gpr[ra]=rotated;
  }else if(op==31 && ((w>>1)&1023u)==444u && !(w&1u)){
   const unsigned rb=(w>>11)&31u;
   gpr[ra]=gpr[rt]|gpr[rb];
  }else if(op==31 && ((w>>1)&1023u)==467u){
   /* mtspr SPR,RS — Power ISA encoded SPR swaps two 5-bit fields.
    * This bounded probe supports only mtctr (SPR=9).
    * Do not silently treat mtlr / mtspr XER as mtctr. */
   const unsigned spr_field=(w>>11)&1023u;
   const unsigned spr=((spr_field&31u)<<5)|(spr_field>>5);
   if((w&1u) || spr!=9u)return -1006;
   ctr=gpr[rt];out[17]=(uint32_t)ctr;out[18]=(uint32_t)(ctr>>32);
   if(trace){trace[10]=pc;trace[11]=rt;trace[12]=(uint32_t)ctr;
              trace[13]=(uint32_t)(ctr>>32);}
  }else if(op==19 && ((w>>1)&1023u)==528u){
   /* bctr and bctrl only (unconditional BO=20, BI=0, BH=0).
    * Conditional CTR branches need CR modeling and remain unsupported. */
   if(w!=0x4e800420u && w!=0x4e800421u)return -1008;
   const uint64_t dest=ctr&~UINT64_C(3);
   if(trace){trace[14]=pc;trace[5]=(uint32_t)gpr[0];
              trace[6]=(uint32_t)(gpr[0]>>32);}
   if(dest>UINT32_MAX || !lookup(d,len,ss,used,dest,4,1))
      return -1007; /* guest executable map validated */
   if(w&1u)lr=next;
   next=(uint32_t)dest;
   out[19]++; /* indirect branches executed in this sandbox */
  }else if(op==31 && ((w>>1)&1023u)==339u){
   const unsigned spr_field=(w>>11)&1023u;
   const unsigned spr=((spr_field&31u)<<5)|(spr_field>>5);
   if((w&1u)|| (spr!=8u && spr!=9u))return -1009;
   if(spr==8u){gpr[rt]=lr;mflr++;}
   else gpr[rt]=ctr;
  }else{
   out[1]=w;return -990; /* unsupported opcode must fail */
  }
  if(trace && gpr[0]!=prior_r0){
    trace[0]=pc;trace[1]=w;trace[2]=(uint32_t)prior_r0;
    trace[3]=(uint32_t)gpr[0];trace[4]=(uint32_t)(gpr[0]>>32);
    trace[5]=(uint32_t)gpr[0];trace[6]=(uint32_t)(gpr[0]>>32);
    trace[7]++;
    if((op==32u || op==58u) && rt==0u){
       trace[8]=(uint32_t)((ra?gpr[ra]:0u)+(uint64_t)(int64_t)imm);
       trace[9]=op;
    }else{trace[8]=0;trace[9]=op;}
  }
  pc=next;out[0]++;
  if(step==15u && (gpr[2]!=info[2]||stores!=9u||mflr!=1u||gpr[0]!=lr))return -996;
 }
 if(gpr[2]!=info[2])return -997;
 out[1]=(uint32_t)gpr[2];out[2]=pc;out[3]=lr;
 out[4]=(uint32_t)gpr[1];out[5]=stores;out[6]=(uint32_t)gpr[0];
 out[9]=(uint32_t)gpr[4];
 out[13]=(uint32_t)gpr[12];out[14]=(uint32_t)gpr[13];
 out[15]=guest.used; /* distinct guest PT_LOAD shadow words */
 out[17]=(uint32_t)ctr;out[18]=(uint32_t)(ctr>>32);
 return 0;
}

/* Preserve the M6.6 ABI and host regressions unchanged. */
int ar_ppu_bootstrap_fortyeight(const uint8_t*d,size_t len,
                          const uint32_t info[5],uint32_t out[20]){
 return ar_ppu_bootstrap_fortyeight_trace(d,len,info,out,NULL);
}
