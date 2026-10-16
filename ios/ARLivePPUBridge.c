/* M7.0: actual iPhoneOS linkage to AscensionRecomp native PPU core.
 * Imports the user's own decrypted ELF into a private, temporary guest VM.
 * Never interprets a PS3 address as a native iOS pointer and never claims
 * missing AOT functions were successfully executed. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <CommonCrypto/CommonDigest.h>
/* A private, pre-signed AOT module is linked only in an explicit private
 * build. No weak unresolved externs are allowed by the macOS/iOS linker. */
#ifdef ASCENSION_PRIVATE_AOT_LINKED
extern int ar_private_aot_install_sha256(const unsigned char*,size_t);
#endif
#include "ppu_bridge.h"
#include "elf_image.h"
#include "../runtime/ppu_tls.h" /* explicit project header, not upstream ppu_tls.h */
#include "../runtime/ppu_lwmutex.h"
#include "../runtime/ppu_lv2_bootstrap.h"

extern int ar_private_import_match(const uint8_t*,size_t,uint32_t,uint32_t[4],char[48]);
extern int ar_private_import_find_nid(const uint8_t*,size_t,uint32_t,const char*,uint32_t[4],char[48]);

enum { AR_NATIVE_LIMIT=128u*1024u*1024u, AR_NATIVE_RESERVE=0x20000u };
static uint16_t g16(const uint8_t*p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint32_t g32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t g64(const uint8_t*p){return ((uint64_t)g32(p)<<32)|g32(p+4);}

/* out:
 0=loader RC, 1=entry PC, 2=TOC, 3=segments, 4=guest VM capacity,
 5=registered AOT functions, 6=entry dispatch RC, 7=unresolved entry PC,
 8=PRX match RC, 9=bind import RC, 10=bind HLE RC,
 11=registered TLS HLE dispatch RC, 12=r13 after HLE,
 13=loaded file bytes, 14=real guest first instruction word,
 15=state bitmask: 1=ELF staged, 2=import verified, 4=real HLE,
                   8=unknown AOT entry (expected until compiled). */
int ar_m70_native_runtime_probe(const uint8_t*d,size_t len,
                                 uint32_t guest_stub,uint32_t out[16]){
 if(!out)return -20;
 memset(out,0,16u*sizeof(*out));
 if(!d||len<64u)return -20;
 if(memcmp(d,"\177ELF",4)||d[4]!=2u||d[5]!=2u||d[6]!=1u||
    g16(d+16)!=2u||g16(d+18)!=21u||g32(d+20)!=1u)
   return -21;
 const uint64_t phoff=g64(d+32),stride=g16(d+54),count=g16(d+56);
 if(stride<56u||!count||count>64u||phoff>len||
    (uint64_t)stride*count>(uint64_t)len-phoff)return -22;
 uint64_t highest=0,tls_va=0,tls_file=0,tls_mem=0;
 unsigned have_tls=0,segments=0;
 for(unsigned i=0;i<count;i++){
    const uint8_t*p=d+phoff+(uint64_t)i*stride;
    const uint32_t type=g32(p),flags=g32(p+4);
    const uint64_t fileoff=g64(p+8),va=g64(p+16);
    const uint64_t fs=g64(p+32),ms=g64(p+40);
    if(type==1u){
       if(fs>ms||fileoff>len||fs>(uint64_t)len-fileoff||
          va>AR_NATIVE_LIMIT-AR_NATIVE_RESERVE||
          ms>(uint64_t)(AR_NATIVE_LIMIT-AR_NATIVE_RESERVE)-va)
          return -23;
       if(ms && va+ms>highest)highest=va+ms;
       if(ms)segments++;
       (void)flags;
    }else if(type==7u){
       if(have_tls++)return -24;
       if(fs>ms||ms>1024u*1024u||va>UINT32_MAX)return -25;
       tls_va=va;tls_file=fs;tls_mem=ms;
    }
 }
 if(!segments)return -26;
 const uint64_t aligned=(highest+0xfffu)&~UINT64_C(0xfff);
 if(aligned>AR_NATIVE_LIMIT-AR_NATIVE_RESERVE)return -27;
 const uint32_t tlsbase=(uint32_t)aligned;
 const size_t cap=(size_t)(aligned+AR_NATIVE_RESERVE);
 if(!tlsbase || tlsbase>=AR_NATIVE_LIMIT)return -27;
 const int rcinit=ar_bridge_init(cap);
 if(rcinit){out[0]=(uint32_t)rcinit;return rcinit;}
 ar_lwmutex_reset(); /* new guest process: no stale sync objects */
 ar_lv2_bootstrap_reset();
 ppu_context ctx;
 ppu_context_init(&ctx);
 ar_elf_image_result image={0};
 const int load=ar_load_elf_image(d,len,cap,&ctx,&image);
 out[0]=(uint32_t)load;
 if(load){ar_bridge_shutdown();return load;}
 out[15]|=1u;
 ctx.thread_id=1u; /* the current main guest thread; no fabricated game code */
 /* Use the same authentic PT_TLS process-entry ABI as M7.1 before
  * dispatching privately compiled guest CRT instructions. */
 ctx.gpr[7]=ctx.thread_id;
 ctx.gpr[8]=tls_va;
 ctx.gpr[9]=tls_file;
 ctx.gpr[10]=tls_mem;
 ctx.gpr[12]=0x100000u;
 ppu_set_stack(&ctx,(uint64_t)tlsbase+0x10000u,0x10000u);
 out[1]=image.entry_code;out[2]=image.toc;out[3]=image.segments;
 out[4]=(uint32_t)cap;out[13]=(uint32_t)image.loaded_bytes;
 out[14]=ar_read32(image.entry_code);
 if(ar_last_error()!=AR_OK){ar_bridge_shutdown();return -28;}
 /* M7.4: register ONLY offline-recompiled, pre-signed game code for
  * the exact SHA256 of the privately imported ELF. A public diagnostic
  * IPA has no such symbol; its real game AOT count stays zero. */
#ifdef ASCENSION_PRIVATE_AOT_LINKED
 if(len>UINT32_MAX){ar_bridge_shutdown();return -29;}
 unsigned char digest[CC_SHA256_DIGEST_LENGTH];
 if(!CC_SHA256(d,(CC_LONG)len,digest)){
   ar_bridge_shutdown();return -29;
 }
 const int aot_rc=ar_private_aot_install_sha256(digest,sizeof(digest));
 if(aot_rc!=AR_OK){ar_bridge_shutdown();return -29;}
#endif
 out[5]=(uint32_t)ar_registered_count(); /* genuine linked game AOT only */

 /* Bind only the exact verified ELF PRX import identified by the private
  * PPU trace, not hard-coded addresses or fake functions. */
 uint32_t match[4]={0};
 char module[48]={0};
 const int import_rc=guest_stub ?
    ar_private_import_match(d,len,guest_stub,match,module) : -1;
 out[8]=(uint32_t)import_rc;
 if(import_rc==0 && match[0]==0x744680a2u &&
    match[1]==guest_stub && strcmp(module,"sysPrxForUser")==0){
    out[15]|=2u;
    out[9]=(uint32_t)ar_bind_import(guest_stub,match[0]);
    if((int32_t)out[9]==AR_OK){
       out[10]=(uint32_t)ar_bind_hle(match[0],ar_sys_initialize_tls);
       if((int32_t)out[10]==AR_OK && have_tls && tls_file<=tls_mem &&
          tls_va<=UINT32_MAX &&
          ar_tls_configure(tlsbase,tlsbase+0x10000u)==AR_OK){
          /* M7.5: a legacy HLE smoke test must never mutate the real
           * native AOT entry context or consume its only TLS allocation.
           * When signed functions are present, let the ACTUAL compiled
           * process entry call its own verified HLE normally. */
          if(out[5]==0u){
             ppu_context smoke=ctx;
             smoke.gpr[3]=smoke.thread_id;
             smoke.gpr[4]=tls_va;
             smoke.gpr[5]=tls_file;
             smoke.gpr[6]=tls_mem;
             smoke.lr=image.entry_code;
             const int hlerr=ar_run(&smoke,guest_stub,32u);
             out[11]=(uint32_t)hlerr;
             out[12]=(uint32_t)smoke.gpr[13];
             if(hlerr==AR_OK && smoke.gpr[13])out[15]|=4u;
          }
       }
    }
 }

 /* M7.7: discover lwmutex's PRX stub from this ELF's import tables;
  * no game address is hardcoded. The NID is a verified system ABI.
  * Service remains functional only when guest AOT actually invokes it. */
 uint32_t lwimp[4]={0};char lwlib[48]={0};
 const int lwmatch=ar_private_import_find_nid(
    d,len,0x2f85c0efu,"sysPrxForUser",lwimp,lwlib);
 if(lwmatch==0 && lwimp[0]==0x2f85c0efu && lwimp[1] &&
    strcmp(lwlib,"sysPrxForUser")==0){
    out[15]|=16u; /* import table matched and stub executable */
    const int b=ar_bind_import(lwimp[1],lwimp[0]);
    if(b==AR_OK && ar_bind_hle(lwimp[0],ar_sys_lwmutex_create)==AR_OK)
       out[15]|=32u; /* genuine HLE implementation now available */
 }

 /* M7.8: OS ABI required by the authentic signed PPU startup path.
  * sys_time_get_system_time import must be authenticated by its PRX table,
  * never by blindly executing an address from guest registers.
  * 0x160 is a PS3 LV2 syscall number, not a function address. */
 if(ar_bind_syscall(0x160u,ar_lv2_user_memory_size)!=AR_OK){
   ar_bridge_shutdown();return -30;
 }
 uint32_t tmimp[4]={0}; char tmlib[48]={0};
 const int tmmatch=ar_private_import_find_nid(
    d,len,0x8461e528u,"sysPrxForUser",tmimp,tmlib);
 if(tmmatch==0 && tmimp[0]==0x8461e528u && tmimp[1] &&
    strcmp(tmlib,"sysPrxForUser")==0){
    out[15]|=64u; /* time import authenticated */
    if(ar_bind_import(tmimp[1],tmimp[0])==AR_OK &&
       ar_bind_hle(tmimp[0],ar_lv2_system_time)==AR_OK)
       out[15]|=128u; /* OS service bound */
 }

 /* M7.9: bind ONLY authenticated PRX entries from the imported ELF.
  * These are generic PS3 OS services, not interpreted game instructions. */
 struct {uint32_t nid;ar_hle_fn handler;uint32_t bit;} m79_services[] = {
    {0x350d454eu,ar_lv2_thread_get_id,0x100u},
    {0x1573dc3fu,ar_sys_lwmutex_lock,0x200u},
    {0x1bc200f4u,ar_sys_lwmutex_unlock,0x400u},
 };
 for(unsigned j=0;j<sizeof(m79_services)/sizeof(m79_services[0]);j++){
    uint32_t imp[4]={0};char lib[48]={0};
    const int found=ar_private_import_find_nid(
      d,len,m79_services[j].nid,"sysPrxForUser",imp,lib);
    if(found==0 && imp[0]==m79_services[j].nid && imp[1] &&
       strcmp(lib,"sysPrxForUser")==0 &&
       ar_bind_import(imp[1],imp[0])==AR_OK &&
       ar_bind_hle(imp[0],m79_services[j].handler)==AR_OK){
       out[15]|=m79_services[j].bit;
    }
 }

 /* This is the actual native AOT dispatcher, NOT the 48-step interpreter.
  * With no signed game AOT functions in the IPA it MUST return unresolved
  * rather than executing data as ARM64 or reporting boot success. */
 /* 128 ticks remains the legacy test's exact budget. 4096 AOT ticks
  * permit the verified multi-routine CRT prefix and fail bounded. */
 if(out[5])out[6]=(uint32_t)ar_run(&ctx,image.entry_code,4096u);
 else out[6]=(uint32_t)ar_run(&ctx,image.entry_code,128u);
 out[7]=ar_last_unresolved();
 /* In AOT mode this is the r13 reached by genuine recompiled guest
  * execution, not a separately invented HLE smoke result. The status
  * bit for the legacy smoke remains unset. */
 if(out[5])out[12]=(uint32_t)ctx.gpr[13];
 if((int32_t)out[6]==AR_UNRESOLVED && out[7]==image.entry_code)
    out[15]|=8u;
 ar_bridge_shutdown();
 return 0;
}
