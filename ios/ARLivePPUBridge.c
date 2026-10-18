
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <CommonCrypto/CommonDigest.h>
/* Owner game AOT services are linked for the iPhoneOS target.
 * Mac host tests keep their original isolated synthetic AOT ABI. */
#if defined(ASCENSION_PRIVATE_AOT_LINKED) && defined(__ENVIRONMENT_IPHONE_OS_VERSION_MIN_REQUIRED__)
#define ASCENSION_M711_OWNER_AOT 1
#endif

#ifdef ASCENSION_PRIVATE_AOT_LINKED
extern int ar_private_aot_install_sha256(const unsigned char*,size_t);
#endif
#ifdef ASCENSION_PRIVATE_BULK_AOT_LINKED
extern int ar_bulk_install_sha256(const unsigned char*,size_t);
#endif
#ifdef ASCENSION_PRIVATE_BULK2_AOT_LINKED
extern int ar_bulk2_install_sha256(const unsigned char*,size_t);
#endif
#ifdef ASCENSION_PRIVATE_FRONTIER_AOT_LINKED
extern int ar_m722_install_sha256(const unsigned char*,size_t);
#endif
#ifdef ASCENSION_GOWA2_OFFLINE_AOT_LINKED
extern int ar_gowa2_offline_aot_install_sha256(const uint8_t*,size_t);
#endif
#include "ppu_bridge.h"
#include "elf_image.h"
#include "../runtime/ppu_tls.h" /* explicit project header, not upstream ppu_tls.h */
#include "../runtime/ppu_lwmutex.h"
#include "../runtime/ppu_lv2_bootstrap.h"
#include "../runtime/ppu_mmapper.h"
#include "../runtime/ppu_native_sysutil.h"

extern int ar_m711_bind_memory(const uint8_t*,size_t,uint32_t*);
extern int ar_m711_bind_sysutil(const uint8_t*,size_t,uint32_t*);
extern int ar_m713_register_fragment(const uint8_t*,size_t);
extern int ar_m714_register_fragment(const uint8_t*,size_t);
extern int ar_m715_register_fragment(const uint8_t*,size_t);
extern int ar_m716_register_block(const uint8_t*,size_t);
extern int ar_m731_register_frontier(const uint8_t*,size_t);
extern int ar_m732_register_block(const uint8_t*,size_t);
extern int ar_m734_register_block(const uint8_t*,size_t);
extern int ar_m734_register_batch(const uint8_t*,size_t);
extern int ar_m735_register_owner(const uint8_t*,size_t);
extern int ar_m736_register_owner(const uint8_t*,size_t);
extern int ar_m744_register_owner(const uint8_t*,size_t);
extern int ar_m745_register_owner(const uint8_t*,size_t);
extern int ar_m746_register_hotloop(const uint8_t*,size_t);
extern int ar_m747_register_owner(const uint8_t*,size_t);
extern int ar_m748_register_owner(const uint8_t*,size_t);
extern int ar_m749_register_frsp(const uint8_t*,size_t);
extern int ar_private_import_match(const uint8_t*,size_t,uint32_t,uint32_t[4],char[48]);
extern int ar_private_import_find_nid(const uint8_t*,size_t,uint32_t,const char*,uint32_t[4],char[48]);

enum { AR_NATIVE_LIMIT=128u*1024u*1024u, AR_NATIVE_RESERVE=0x20000u };
/* Native AOT trace copied before ar_bridge_shutdown; no game code stored. */
static ar_aot_trace last_run_trace;
void ar_m717_last_aot_trace(ar_aot_trace *out){if(out)*out=last_run_trace;}
static uint16_t g16(const uint8_t*p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint32_t g32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t g64(const uint8_t*p){return ((uint64_t)g32(p)<<32)|g32(p+4);}


int ar_m70_native_runtime_probe(const uint8_t*d,size_t len,
                                 uint32_t guest_stub,uint32_t out[16]){
 if(!out)return -20;
 memset(out,0,16u*sizeof(*out));
 memset(&last_run_trace,0,sizeof(last_run_trace));
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
 ar_lwmutex_reset();
#ifdef ASCENSION_M711_OWNER_AOT
 ar_mmapper_reset();ar_sysutil_reset();
#endif /* new guest process: no stale sync objects */
 ar_lv2_bootstrap_reset();
 ppu_context ctx;
 ppu_context_init(&ctx);
 ar_elf_image_result image={0};
 const int load=ar_load_elf_image(d,len,cap,&ctx,&image);
 out[0]=(uint32_t)load;
 if(load){ar_bridge_shutdown();return load;}
 out[15]|=1u;
 ctx.thread_id=1u; /* the current main guest thread; no fabricated game code */
 
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
 
#ifdef ASCENSION_PRIVATE_AOT_LINKED
 if(len>UINT32_MAX){ar_bridge_shutdown();return -29;}
 unsigned char digest[CC_SHA256_DIGEST_LENGTH];
 if(!CC_SHA256(d,(CC_LONG)len,digest)){
   ar_bridge_shutdown();return -29;
 }
 const int aot_rc=ar_private_aot_install_sha256(digest,sizeof(digest));
 if(aot_rc!=AR_OK){ar_bridge_shutdown();return -29;}
#ifdef ASCENSION_M711_OWNER_AOT
 /* The 64 owner entries are authenticated first. Accept the native four-opcode
  * continuation only if imported executable ELF bytes exactly match. */
 if(ar_m713_register_fragment(d,len)!=AR_OK){
   ar_bridge_shutdown();return -32;
 }
 /* The second owner-observed fragment modifies guest memory. Validate
  * exact executable PPC words before native registration (fail closed). */
 if(ar_m714_register_fragment(d,len)!=AR_OK){
   ar_bridge_shutdown();return -33;
 }
 /* Authenticate the four new instructions before any guest PPU dispatch.
  * The 64-entry owner source and M7.13/14 registrations stay intact. */
 if(ar_m715_register_fragment(d,len)!=AR_OK){
   ar_bridge_shutdown();return -34;
 }
 /* The 15-word owner-observed branch is linked native ARM64 and may only
  * enter guest dispatch after the real ELF's exact instructions validate. */
 if(ar_m716_register_block(d,len)!=AR_OK){
   ar_bridge_shutdown();return -35;
 }
#ifdef ASCENSION_PRIVATE_BULK_AOT_LINKED
 /* All 500 distinct C-AOT entrypoints were verified against the original
  * owner ELF digest in the staging step. The signed native binary installs
  * them only AFTER the original 68 AOT entries are present. */
 if(ar_bulk_install_sha256(digest,sizeof(digest))!=AR_OK){
   ar_bridge_shutdown();return -36;
 }
#endif
#ifdef ASCENSION_PRIVATE_BULK2_AOT_LINKED
 /* M7.19: validate and register the second 850-block owner-only AOT
  * module ONLY after all 568 legacy entries are present. */
 if(ar_bulk2_install_sha256(digest,sizeof(digest))!=AR_OK){
   ar_bridge_shutdown();return -37;
 }
#endif
#ifdef ASCENSION_PRIVATE_FRONTIER_AOT_LINKED
 if(ar_m722_install_sha256(digest,sizeof(digest))!=AR_OK){
   ar_bridge_shutdown();return -39;
 }
#endif
 /* M7.31: the original 1,419 private blocks are now authenticated.
  * Verify guest executable bytes and register ONE genuinely native ARM64
  * two-instruction continuation. Never falls back to silent success. */
 if(ar_m731_register_frontier(d,len)!=AR_OK){
    ar_bridge_shutdown();return -40;
 }
 /* M7.32 native stack/timezone call setup; verified on owner ELF only. */
 if(ar_m732_register_block(d,len)!=AR_OK){
    ar_bridge_shutdown();return -41;
 }
 /* M7.34: after private SHA-256 validation of the original ELF, verify
  * exact PPU executable bytes of a 29-word block before native install. */
 if(ar_m734_register_block(d,len)!=AR_OK){
    ar_bridge_shutdown();return -42;
 }
 /* M7.34 native batch: 10 additional traced guest basic blocks;
  * ALL X segments verified and memory bytes matched before registration. */
 if(ar_m734_register_batch(d,len)!=AR_OK){
    ar_bridge_shutdown();return -43;
 }
 /* Owner ELF SHA is authenticated, seven additional AOT blocks verified. */
 if(ar_m735_register_owner(d,len)!=AR_OK){
    ar_bridge_shutdown();return -44;
 }
 /* M7.36: fully verified owner-ELF nine-op native time continuation. */
 if(ar_m736_register_owner(d,len)!=AR_OK){
    ar_bridge_shutdown();return -45;
 }
 /* M7.43: only after the ORIGINAL game ELF has passed the existing
  * CC_SHA256 + private AOT authentication, and after old entries have
  * been registered, install the 6251 offline-translated guest functions.
  * ar_register preserves the first (older validated) AOT on duplicate PC.
  * This is static ARM64 machine code after AppleClang compilation, no JIT.
  * Neither registration nor linking constitutes proof of guest execution. */
#ifdef ASCENSION_GOWA2_OFFLINE_AOT_LINKED
 const size_t before_gowa2=ar_registered_count();
 if(before_gowa2>8192u||6251u>8192u-before_gowa2){
    ar_bridge_shutdown();return -46;
 }
 const int gowa2_rc=ar_gowa2_offline_aot_install_sha256(digest,sizeof(digest));
 if(gowa2_rc!=AR_OK){
    ar_bridge_shutdown();return -47;
 }
 const size_t after_gowa2=ar_registered_count();
 if(after_gowa2<=before_gowa2||after_gowa2>before_gowa2+6251u||
    after_gowa2>8192u){
    ar_bridge_shutdown();return -48;
 }
#endif
  /* M7.44: native CROR+BC at the actual device blockade.
   * Install only after SHA-256 and offline AOT registration; require
   * matching executable words and loaded guest memory, else fail closed. */
  if(ar_m744_register_owner(d,len)!=AR_OK){
     ar_bridge_shutdown();return -49;
  }
  /* M7.45: signed owner-ELF PPC 0x0052BA70 native block */
  if(ar_m745_register_owner(d,len)!=AR_OK){
    ar_bridge_shutdown();return -50;
  }
  /* M7.46: 69 owner PPC instructions with two CTR loops native ARM64;
   * authenticated all 4 entry points against executable ELF and guest VM. */
  if(ar_m746_register_hotloop(d,len)!=AR_OK){
    ar_bridge_shutdown();return -51;
  }
  /* M7.47: signed original executable FMR guest entries, no emulation. */
  if(ar_m747_register_owner(d,len)!=AR_OK){
    ar_bridge_shutdown();return -52;
  }
  /* M7.48 two SHA/PT_LOAD-X authenticated native VMX entries. */
  if(ar_m748_register_owner(d,len)!=AR_OK){
    ar_bridge_shutdown();return -53;
  }
  /* M7.49 first owner-authenticated PPC frsp -> Apple ARM64. */
  if(ar_m749_register_frsp(d,len)!=AR_OK){
    ar_bridge_shutdown();return -54;
  }
#endif
#endif
 out[5]=(uint32_t)ar_registered_count(); /* genuine linked game AOT only */

 
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

 
 /* M7.33: production's single source of truth, also tested on host. */
 if(ar_lv2_bind_bootstrap_syscalls()!=AR_OK){
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

 
 
#ifdef ASCENSION_M711_OWNER_AOT
 if(ar_m711_bind_sysutil(d,len,out)!=AR_OK ||
    ar_m711_bind_memory(d,len,out)!=AR_OK){
   ar_mmapper_reset();ar_bridge_shutdown();return -31;
 }
#endif
 /* M7.20 EXPERIMENTAL: after the exact owner SHA-256 AOT guard has
  * succeeded, permit a finite signed PPC interpreter for AOT gaps.
  * Native ARM64 entries take precedence, no JIT or new secret required.
  * Previous HLE/VM mappings and 1418 AOT definitions are unchanged. */
#ifdef ASCENSION_M711_OWNER_AOT
 if(ar_ppc_fallback_attach(d,len,AR_PPC_FALLBACK_MAX_STEPS,ar_ppc_fallback_step)!=AR_OK){
    ar_mmapper_reset();ar_bridge_shutdown();return -38;
 }
#endif
 if(out[5])out[6]=(uint32_t)ar_run(&ctx,image.entry_code,32768u);
 else out[6]=(uint32_t)ar_run(&ctx,image.entry_code,128u);
 out[7]=ar_last_unresolved();
 ar_trace_snapshot(&last_run_trace);
 last_run_trace.lv2_timezone_completed=ar_lv2_timezone_queries();
 
 if(out[5])out[12]=(uint32_t)ctx.gpr[13];
 if((int32_t)out[6]==AR_UNRESOLVED && out[7]==image.entry_code)
    out[15]|=8u;
#ifdef ASCENSION_M711_OWNER_AOT
 if(ar_mmapper_mapped_count())out[15]|=0x1000u;
 ar_mmapper_reset();ar_sysutil_reset();
#endif
 ar_bridge_shutdown();
 return 0;
}
