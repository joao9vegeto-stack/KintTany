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

/* M6.7.3: identify the NID of a checked guest firmware import trampoline.
 * ET_EXEC proc_prx_param (PT 0x60000002) describes libstub tables.
 * This is read-only metadata; it DOES NOT bind, execute or fabricate HLE.
 * 0=matched, -1=no match, -2=invalid ELF/arguments,
 * -3=absent PRX params, -4=malformed import metadata. */
int ar_private_import_match(const uint8_t*d,size_t len,uint32_t code_va,
                            uint32_t result[4],char library[48]){
 if(!result||!library)return -2;
 memset(result,0,4u*sizeof(*result));memset(library,0,48u);
 uint32_t inspected[5]={0};
 if(!code_va||ar_private_elf_inspect(d,len,inspected))return -2;
 const uint64_t phoff=b64(d+32);
 const unsigned phentsize=b16(d+54),phcount=b16(d+56);
 segment ss[64]={0};unsigned used=0;
 uint64_t prx_va=0;
 for(unsigned i=0;i<phcount;i++){
   const uint8_t*p=d+phoff+(uint64_t)i*phentsize;
   const uint32_t type=b32(p);
   if(type==1u){
     const segment seg={b64(p+8),b64(p+16),b64(p+32),b64(p+40),b32(p+4)};
     if(seg.mem && seg.size)ss[used++]=seg;
   }else if(type==0x60000002u){
     if(prx_va)return -4; /* ambiguous PRX parameter segments */
     prx_va=b64(p+16);
   }
 }
 if(!prx_va)return -3;
 const uint8_t*hdr=lookup(d,len,ss,used,prx_va,32u,0);
 if(!hdr||b32(hdr+4)!=0x1b434cecu)return -3;
 const uint32_t first=b32(hdr+24),last=b32(hdr+28);
 if(!first||last<=first||last-first>32768u)return -4;
 typedef struct {
   uint32_t nfunc,nid_va,stub_va,name_va;
 } ar_libstub;
 ar_libstub list[128]={0};unsigned nlibs=0;
 uint32_t cursor=first;
 while(cursor<last){
   if(nlibs>=128u)return -4;
   const uint8_t*q=lookup(d,len,ss,used,cursor,28u,0);
   if(!q)return -4;
   const unsigned stride=q[0];
   if(stride<28u||stride>128u||stride>last-cursor)return -4;
   list[nlibs].nfunc=b16(q+6);
   list[nlibs].name_va=b32(q+16);
   list[nlibs].nid_va=b32(q+20);
   list[nlibs].stub_va=b32(q+24);
   if(list[nlibs].nfunc>4096u)return -4;
   nlibs++;
   cursor+=stride;
 }
 if(cursor!=last)return -4;
 result[3]=nlibs;
 for(unsigned j=0;j<nlibs;j++){
   const ar_libstub *entry=list+j;
   if(!entry->nid_va||!entry->stub_va)continue;
   unsigned count=entry->nfunc;
   /* PSL1GHT/PRX images can encode nfunc=0; bound inferred spans. */
   if(!count){
     uint32_t closest_nid=UINT32_MAX,closest_stub=UINT32_MAX;
     for(unsigned k=0;k<nlibs;k++){
       if(list[k].nid_va>entry->nid_va&&
          (!closest_nid||list[k].nid_va<closest_nid))
          closest_nid=list[k].nid_va;
       if(list[k].stub_va>entry->stub_va&&
          (!closest_stub||list[k].stub_va<closest_stub))
          closest_stub=list[k].stub_va;
     }
     if(closest_nid==UINT32_MAX)closest_nid=first;
     if(closest_stub==UINT32_MAX)closest_stub=0u;
     unsigned nid_count=(closest_nid>entry->nid_va &&
                      (closest_nid-entry->nid_va)%4u==0u)
                   ?(closest_nid-entry->nid_va)/4u:0u;
     unsigned stub_count=(closest_stub>entry->stub_va &&
                      (closest_stub-entry->stub_va)%4u==0u)
                   ?(closest_stub-entry->stub_va)/4u:0u;
     if(nid_count>4096u)nid_count=0u;
     if(stub_count>4096u)stub_count=0u;
     count=(nid_count&&stub_count)?(nid_count<stub_count?nid_count:stub_count):
           (nid_count?nid_count:stub_count);
   }
   if(count>4096u)return -4;
   for(unsigned i=0;i<count;i++){
     const uint64_t addr=(uint64_t)entry->stub_va+4u*i;
     const uint64_t nidaddr=(uint64_t)entry->nid_va+4u*i;
     const uint8_t*pt=lookup(d,len,ss,used,addr,4u,0);
     const uint8_t*pn=lookup(d,len,ss,used,nidaddr,4u,0);
     if(!pt||!pn)return -4;
     result[2]++;
     if(b32(pt)!=code_va)continue;
     result[0]=b32(pn);
     result[1]=code_va;
     /* A library name is optional, bounded and printable only. */
     if(entry->name_va){
       for(unsigned k=0;k<47u;k++){
         const uint8_t*ch=lookup(d,len,ss,used,
                                  (uint64_t)entry->name_va+k,1u,0);
         if(!ch||!*ch)break;
         if(*ch<0x20u||*ch>0x7eu)break;
         library[k]=(char)*ch;
       }
     }
     return 0;
   }
 }
 return -1;
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

/* M6.7.2: origin classification; guest addresses never become iOS pointers. */
static uint32_t m672_region(const segment*s,unsigned n,uint64_t va,
 unsigned bytes,uint64_t sb,uint32_t*flags){
 if(flags)*flags=0;
 if(va>=sb&&within(va-sb,bytes,4096u))return 1u;
 const int i=m65_segment(s,n,va,bytes,0u);
 if(i<0)return 0u;
 const segment*t=s+i;
 if(flags)*flags=t->flags;
 const int disk=within(va-t->va,bytes,t->size);
 return (t->flags&1u)?(disk?2u:5u):(disk?3u:4u);
}
/* Region tags 0=unmapped 1=stack 2=executable file 3=data file
 * 4=nonexecuted BSS 5=executable BSS. Original p_flags separate. */

/* M6.6 — strict CTR/mtspr and bounded PPU48 continuation.
 * 0x7C0903A6 = mtctr r0 observed on private NPUA80918 at PC=0x669C2C.
 * The next branch is validated against ELF executable segments, and no
 * guest address becomes a native host pointer. Zero per-step stale EA. */
/* M6.7: optional trace of bounded guest execution; no permission changes. */

/* M6.7.4: real bounded main-thread TLS storage. PS3 guest pointers are
 * only addressed through checked shadow mappings, never host pointers. */
#define AR_TLS_START UINT64_C(0x0e000000)
#define AR_TLS_SPACE 65536u
#define AR_TLS_MAX 16384u
static int ar_tls_read(const uint8_t*d,size_t len,const segment*s,unsigned n,
 const m65_memory*m,const uint8_t*stack,uint64_t sb,const uint8_t*tls,
 int ready,uint64_t va,unsigned width,uint64_t*out){
 if(ready&&va>=AR_TLS_START&&within(va-AR_TLS_START,width,AR_TLS_SPACE)){
   uint64_t v=0;
   for(unsigned i=0;i<width;i++)v=(v<<8)|tls[(size_t)(va-AR_TLS_START)+i];
   *out=v;return 0;
 }
 return m65_read_guest(d,len,s,n,m,stack,sb,va,width,out);
}
static int ar_tls_write(uint8_t*tls,int ready,uint64_t va,unsigned width,
 uint64_t val){
 if(!ready||va<AR_TLS_START||!within(va-AR_TLS_START,width,AR_TLS_SPACE))
   return -1;
 for(unsigned i=0;i<width;i++)
   tls[(size_t)(va-AR_TLS_START)+i]=(uint8_t)(val>>(8u*(width-i-1u)));
 return 0;
}
static int ar_tls_initialize(const uint8_t*d,size_t len,const segment*s,
 unsigned n,const m65_memory*m,const uint8_t*stack,uint64_t sb,
 uint8_t*tls,uint64_t gpr[32],uint32_t record[12]){
 const uint64_t id=gpr[3],src=gpr[4],size=gpr[5],mem=gpr[6];
 record[2]=(uint32_t)id;record[3]=(uint32_t)src;
 record[4]=(uint32_t)size;record[5]=(uint32_t)mem;
 if(gpr[13])return -1012;
 if(!id||id>UINT32_MAX||src>UINT32_MAX||size>mem||mem>AR_TLS_MAX||
    (size&&!src))return -1011;
 for(uint64_t i=0;i<size;i++){
   uint64_t value=0;
   if(m65_read_guest(d,len,s,n,m,stack,sb,src+i,1u,&value))return -1013;
   tls[i]=(uint8_t)value;
 }
 for(uint64_t i=size;i<mem;i++)tls[i]=0;
 gpr[13]=AR_TLS_START+0x7000u;
 gpr[3]=0; /* successful TLS image initialization (ABI CELL_OK) */
 record[0]=1u;record[1]++;
 record[6]=(uint32_t)gpr[13];record[7]=(uint32_t)size;
 return 0;
}

/* M6.7.5: genuine PS3 process-entry ABI. The LV2 launcher passes the
 * thread identity + PT_TLS descriptor in r7-r10 and page size in r12.
 * The guest CRT (not our HLE) transfers those into r3-r6 before calling
 * sys_initialize_tls. Never seed r3-r6 at the import call site. */
static int ar_m675_entry_tls(const uint8_t*d,size_t len,
                             const segment*s,unsigned n,
                             uint32_t params[4],uint32_t*found){
 params[0]=1u;params[1]=params[2]=params[3]=0u;
 *found=0u;
 const uint64_t offset=b64(d+32);
 const unsigned stride=b16(d+54),count=b16(d+56);
 for(unsigned i=0;i<count;i++){
   const uint8_t*p=d+offset+(uint64_t)i*stride;
   if(b32(p)!=7u)continue; /* PT_TLS */
   if(*found)return -1021; /* duplicate ELF TLS descriptors */
   *found=1u;
   const uint64_t va=b64(p+16),filesz=b64(p+32),memsz=b64(p+40);
   if(va>UINT32_MAX || filesz>memsz || memsz>AR_TLS_MAX ||
      (filesz && (va==0 || m65_segment(s,n,va,(unsigned)filesz,0u)<0)))
      return -1021;
   /* Required template bytes must be backed by the physical input ELF.
    * The subsequent HLE performs checked, bytewise guest reads. */
   if(filesz && !lookup(d,len,s,n,va,(unsigned)filesz,0u))
      return -1021;
   params[1]=(uint32_t)va;
   params[2]=(uint32_t)filesz;
   params[3]=(uint32_t)memsz;
 }
 return 0;
}

static int m672_core(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[20],
                             uint32_t trace[24],uint32_t detail[24],
                             uint32_t tls_record[12]){
 if(!d||!info||!out)return -980;
 memset(out,0,20*sizeof(*out));
 if(trace)memset(trace,0,24*sizeof(*trace));
 if(detail)memset(detail,0,24*sizeof(*detail));
 if(tls_record)memset(tls_record,0,12*sizeof(*tls_record));
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
 uint8_t tls_buffer[AR_TLS_SPACE]={0};
 int tls_ready=0;
 m65_memory guest={0};
 const uint64_t base=0x07000000u;
 gpr[1]=base+sizeof(stack);gpr[2]=info[2];
 if(tls_record){
    uint32_t entry[4]={0},has_tls=0;
    const int rc=ar_m675_entry_tls(d,len,ss,used,entry,&has_tls);
    if(rc){tls_record[8]=(uint32_t)(-rc);return rc;}
    gpr[7]=entry[0];gpr[8]=entry[1];
    gpr[9]=entry[2];gpr[10]=entry[3];
    gpr[12]=0x00100000u; /* genuine LV2 page size at _start */
    tls_record[9]=has_tls;
    tls_record[11]=(uint32_t)gpr[12];
 }
 uint32_t pc=info[1],lr=0,stores=0,mflr=0;
 uint64_t ctr=0;
 if(pc>0xffffff3fu||(pc&3))return -982;
 for(unsigned step=0;step<48;step++){
  const uint8_t*p=lookup(d,len,ss,used,pc,4,1);
  if(!p){out[8]=pc;return -983;}
  const uint32_t w=b32(p),op=w>>26;
  const uint64_t prior_r0=gpr[0];
  const uint64_t prior_r12=gpr[12];
  uint64_t load_va=0;
  if(detail){detail[18]=(uint32_t)gpr[12];detail[19]=(uint32_t)(gpr[12]>>32);}
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
   if(ar_tls_read(d,len,ss,used,&guest,stack,base,tls_buffer,tls_ready,va,4,&value)) {
      out[10]=(uint32_t)va;out[16]=1u;return -1001;
   }
   load_va=va;gpr[rt]=value;
   if(detail && ra==12u && (rt==0u || rt==2u)){
     const unsigned i=rt==0u?8u:12u;
     detail[i]=(uint32_t)va;detail[i+1u]=(uint32_t)value;
     detail[i+2u]=m672_region(ss,used,va,4u,base,&detail[i+3u]);
     if(rt==0u){detail[20]=(uint32_t)prior_r12;
                 detail[21]=(uint32_t)(prior_r12>>32);}
   }
  }else if(op==62){
   if(!ra||(w&3u)>1u)return -986;
   int16_t ds=(int16_t)(w&0xfffcu);
   uint64_t va=gpr[ra]+(uint64_t)(int64_t)ds;
   if(va>=base&&within(va-base,8u,sizeof(stack))){
     for(unsigned j=0;j<8;j++)
       stack[(size_t)(va-base)+j]=(uint8_t)(gpr[rt]>>(56-8*j));
   }else if(!tls_record||ar_tls_write(tls_buffer,tls_ready,va,8u,gpr[rt]))
     return -987;
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
   if(ar_tls_read(d,len,ss,used,&guest,stack,base,tls_buffer,tls_ready,va,8,&value)) {
       out[10]=(uint32_t)va;out[16]=1u;return -1002;
   }
   load_va=va;gpr[rt]=value;
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
   }else if(tls_record&&
             !ar_tls_write(tls_buffer,tls_ready,va,4u,v)){
     /* Authenticated guest TLS shadow, no host-pointer translation. */
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
   if(dest>UINT32_MAX || !lookup(d,len,ss,used,dest,4,1)){
      if(tls_record && w==0x4e800421u && gpr[12]<=UINT32_MAX &&
         !tls_ready && gpr[0]==ctr){
        uint32_t match[4]={0};char lib[48]={0};
        const int recognized=ar_private_import_match(
               d,len,(uint32_t)gpr[12],match,lib);
        const uint8_t*stub=lookup(d,len,ss,used,gpr[12],8u,1u);
        if(recognized==0 && match[0]==0x744680a2u &&
           strcmp(lib,"sysPrxForUser")==0 && stub &&
           b32(stub)==(uint32_t)ctr &&
           b32(stub+4)==(uint32_t)gpr[2]){
            const int rc=ar_tls_initialize(d,len,ss,used,&guest,stack,base,
                                        tls_buffer,gpr,tls_record);
            if(rc){tls_record[8]=(uint32_t)(-rc);return rc;}
            tls_ready=1;lr=next;gpr[2]=info[2];
            out[19]++;tls_record[10]=next;
            pc=next;out[0]++;
            continue; /* verified TLS initialized, return guest caller */
        }
      }
      return -1007; /* other invalid jumps remain forbidden */
   }
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
  if(detail && gpr[12]!=prior_r12){
    detail[0]=pc;detail[1]=w;detail[2]=(uint32_t)prior_r12;
    detail[3]=(uint32_t)gpr[12];detail[4]=(uint32_t)(gpr[12]>>32);
    detail[5]++;detail[6]=op;detail[7]=(uint32_t)load_va;
    detail[16]=detail[17]=0u;
    if((op==32u||op==58u)&&rt==12u)
      detail[16]=m672_region(ss,used,load_va,op==32u?4u:8u,base,&detail[17]);
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

/* Preserve both old exported APIs; extended diagnostics are opt-in. */
int ar_ppu_bootstrap_fortyeight_trace(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[20],
                             uint32_t trace[24]){
 return m672_core(d,len,info,out,trace,NULL,NULL);
}
int ar_ppu_bootstrap_fortyeight_trace_m672(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[20],
                             uint32_t trace[24],uint32_t detail[24]){
 return m672_core(d,len,info,out,trace,detail,NULL);
}
/* New opt-in bounded TLS/HLE probe. Earlier APIs are unchanged. */
int ar_ppu_bootstrap_fortyeight_trace_m674(const uint8_t*d,size_t len,
                             const uint32_t info[5],uint32_t out[20],
                             uint32_t trace[24],uint32_t detail[24],
                             uint32_t tls_record[12]){
 return m672_core(d,len,info,out,trace,detail,tls_record);
}
/* Preserve the M6.6 ABI and host regressions unchanged. */
int ar_ppu_bootstrap_fortyeight(const uint8_t*d,size_t len,
                          const uint32_t info[5],uint32_t out[20]){
 return ar_ppu_bootstrap_fortyeight_trace(d,len,info,out,NULL);
}
