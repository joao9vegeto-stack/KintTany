/* M7.1 native-code interpreter fallback setup for user's private ELF.
 * Runs signed, generic PowerPC decode handlers: NO per-game ARM64 AOT.
 * This is a separate clean guest process, not the earlier M7.0 TLS smoke. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ppu_bridge.h"
#include "elf_image.h"
#include "../runtime/ppu_tls.h"

extern int ar_private_import_match(const uint8_t*,size_t,uint32_t,uint32_t[4],char[48]);
extern int ar_m71_signed_ppu_interpret(const uint8_t*,size_t,ppu_context*,
                            uint32_t,uint32_t,uint32_t,uint32_t[16]);

enum { AR71_LIMIT=256u*1024u*1024u, AR71_EXTRA=0x20000u };
static uint16_t r16(const uint8_t*p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint32_t r32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t r64(const uint8_t*p){return ((uint64_t)r32(p)<<32)|r32(p+4);}
/* out:
 0=bootstrap rc; 1=steps; 2=guest PC; 3=opcode; 4=stop reason;
 5=native HLE executions; 6=r13; 7=LR; 8=CTR; 9=fault EA;
 10=last completed PC; 11=AOT registered; 12=import NID;
 13=verified imported stub; 14=thread id; 15=memory capacity.
 */
/* Preserve M7.1/M7.2 entry-point ABI. M7.3 only observes the
 * actual failure state, without changing execution or faking HLE. */
static int ar_continuous_core(const uint8_t*d,size_t len,
       uint32_t guest_stub,uint32_t budget,uint32_t out[16],
       uint32_t evidence[16],char library[48]){
 if(evidence)memset(evidence,0,16u*sizeof(*evidence));
 if(library)memset(library,0,48u);

 if(!out)return -1320;
 memset(out,0,sizeof(uint32_t)*16);
 if(!d||len<64u||memcmp(d,"\177ELF",4)||
    d[4]!=2||d[5]!=2||d[6]!=1||r16(d+18)!=21||
    budget==0||budget>8192)return -1320;
 const uint64_t off=r64(d+32);
 const unsigned size=r16(d+54),count=r16(d+56);
 if(size<56||!count||count>64||off>len||
    (uint64_t)size*count>len-off)return -1321;
 uint64_t end=0,tls_addr=0,tls_fs=0,tls_ms=0;
 unsigned loads=0,has_tls=0;
 for(unsigned i=0;i<count;i++){
   const uint8_t*p=d+off+(uint64_t)i*size;
   const uint32_t type=r32(p);
   const uint64_t fileoff=r64(p+8),va=r64(p+16);
   const uint64_t fs=r64(p+32),ms=r64(p+40);
   if(type==1u){
      if(fileoff>len||fs>len-fileoff||fs>ms||
         va>AR71_LIMIT-AR71_EXTRA ||
         ms>(uint64_t)(AR71_LIMIT-AR71_EXTRA)-va)return -1322;
      if(ms && va+ms>end)end=va+ms;
      if(ms)loads++;
   }else if(type==7u){
      if(has_tls++)return -1323;
      if(va>UINT32_MAX||fs>ms||ms>1024u*1024u)return -1323;
      tls_addr=va;tls_fs=fs;tls_ms=ms;
   }
 }
 if(!loads)return -1324;
 const uint64_t aligned=(end+0xfffu)&~UINT64_C(0xfff);
 if(!aligned||aligned>AR71_LIMIT-AR71_EXTRA)return -1324;
 const uint32_t tlsbase=(uint32_t)aligned;
 const size_t cap=(size_t)aligned+AR71_EXTRA;
 if(ar_bridge_init(cap)!=AR_OK)return -1325;
 ppu_context cpu;ppu_context_init(&cpu);
 ar_elf_image_result entry={0};
 const int loaded=ar_load_elf_image(d,len,cap,&cpu,&entry);
 if(loaded){ar_bridge_shutdown();out[0]=(uint32_t)loaded;return loaded;}
 cpu.thread_id=1u;cpu.gpr[7]=cpu.thread_id;
 cpu.gpr[8]=tls_addr;cpu.gpr[9]=tls_fs;cpu.gpr[10]=tls_ms;
 cpu.gpr[12]=0x100000u; /* LV2 process-entry page size */
 ppu_set_stack(&cpu,(uint64_t)tlsbase+0x10000u,0x10000u);
 out[11]=(uint32_t)ar_registered_count(); /* never count interpreted code as AOT */
 out[14]=(uint32_t)cpu.thread_id;out[15]=(uint32_t)cap;
 uint32_t im[4]={0};char lib[48]={0};
 if(guest_stub &&
    ar_private_import_match(d,len,guest_stub,im,lib)==0 &&
    im[0]==0x744680a2u && im[1]==guest_stub &&
    strcmp(lib,"sysPrxForUser")==0){
      out[12]=im[0];out[13]=guest_stub;
      if(ar_bind_import(guest_stub,im[0])!=AR_OK ||
         ar_bind_hle(im[0],ar_sys_initialize_tls)!=AR_OK ||
         ar_tls_configure(tlsbase,tlsbase+0x10000u)!=AR_OK){
        ar_bridge_shutdown();return -1326;
      }
 }
 uint32_t trace[16]={0};
 const int rc=ar_m71_signed_ppu_interpret(
        d,len,&cpu,guest_stub,entry.toc,budget,trace);
 out[0]=(uint32_t)rc;
 out[1]=trace[0];out[2]=trace[1];out[3]=trace[2];out[4]=trace[3];
 out[5]=trace[4];out[6]=trace[5];out[7]=trace[7];out[8]=trace[6];
 out[9]=trace[11];out[10]=trace[12];
 /* Only on a failed actual bctrl: examine the live r12 register.
  * This resolves PRX import metadata for ANY imported guest stub,
  * not just the one previously identified as sys_initialize_tls.
  * Identifying a NID NEVER binds or calls an unknown firmware HLE. */
 if(evidence && rc==-1314 && trace[2]==0x4e800421u){
   const uint64_t stub=cpu.gpr[12];
   evidence[0]=trace[1]; /* exact stopped guest PC */
   evidence[1]=(uint32_t)stub;
   evidence[2]=(uint32_t)cpu.ctr;
   evidence[3]=(uint32_t)cpu.gpr[2];
   evidence[11]=(uint32_t)cpu.gpr[3];
   evidence[12]=(uint32_t)cpu.gpr[4];
   evidence[13]=(uint32_t)cpu.gpr[5];
   evidence[14]=(uint32_t)cpu.gpr[6];
   evidence[15]=(uint32_t)cpu.gpr[0];
   uint32_t match[4]={0};
   char local_library[48]={0};
   int status=-2;
   if(stub!=0u && stub<=UINT32_MAX && (stub&3u)==0u)
      status=ar_private_import_match(d,len,(uint32_t)stub,match,local_library);
   evidence[6]=match[0];evidence[7]=(uint32_t)status;
   evidence[9]=match[2];evidence[10]=match[3];
   if(library && status==0)memcpy(library,local_library,48u);
   /* Check that both descriptor-looking words actually reside in the
    * file-backed executable guest ELF segment before reading them. */
   const uint64_t off=r64(d+32);
   const unsigned entrysize=r16(d+54),nentries=r16(d+56);
   int code_staged=0;
   if(stub<=UINT32_MAX && (uint64_t)entrysize*nentries<=len-off){
     for(unsigned k=0;k<nentries;k++){
       const uint8_t*ph=d+off+(uint64_t)k*entrysize;
       if(r32(ph)!=1u || !(r32(ph+4)&1u))continue;
       const uint64_t lo=r64(ph+16),sz=r64(ph+32);
       if(stub>=lo && stub-lo<=sz && sz-(stub-lo)>=8u){
          code_staged=1;break;
       }
     }
   }
   if(code_staged){
     evidence[8]|=1u;
     evidence[4]=ar_read32(stub);
     evidence[5]=ar_read32(stub+4u);
     if(ar_last_error()==AR_OK){
       if(evidence[4]==(uint32_t)cpu.ctr)evidence[8]|=2u;
       if(evidence[5]==(uint32_t)cpu.gpr[2])evidence[8]|=4u;
     }
   }
   if(status==0 && match[1]==stub)evidence[8]|=8u;
   if((evidence[8]&15u)==15u)evidence[8]|=16u;
 }
 ar_bridge_shutdown();
 return 0; /* probe executed: its guest stop code is in out[0] */
}
int ar_m71_private_continuous_probe(const uint8_t*d,size_t len,
                     uint32_t guest_stub,uint32_t budget,uint32_t out[16]){
 return ar_continuous_core(d,len,guest_stub,budget,out,NULL,NULL);
}
int ar_m73_private_import_probe(const uint8_t*d,size_t len,
                     uint32_t guest_stub,uint32_t budget,uint32_t out[16],
                     uint32_t evidence[16],char library[48]){
 if(!evidence||!library)return -1320;
 return ar_continuous_core(d,len,guest_stub,budget,out,evidence,library);
}
