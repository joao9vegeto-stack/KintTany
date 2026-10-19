/* Isolated PPU dispatcher for smoke tests, not full PS3Recomp runtime. */
#include "ppu_bridge.h"
#include <stdlib.h>
#include <string.h>
#define MAX_FUNCS 16384
#define MAX_MEM (128u*1024u*1024u)
#define MAX_DEPTH 64
#define MAX_IMPORTS 2048
#define MAX_HANDLERS 2048
#define MAX_LV2_SYSCALLS 512
static struct {uint32_t pc;ar_ppu_fn fn;} funcs[MAX_FUNCS];
static size_t nfunc,mem_size;
/* Open-addressed 32k index: bounded lookup, no allocations during dispatch.
 * Slot stores registered-index+1; zero is empty. */
#define AR_AOT_INDEX_SIZE 32768u
static uint16_t aot_slot[AR_AOT_INDEX_SIZE];
static uint8_t trace_seen[MAX_FUNCS];
static uint32_t trace_ring[AR_AOT_TRACE_PCS],trace_total,trace_unique;
static uint32_t trace_hle,trace_pending,trace_budget;
/* Runtime-only bounded triage: no allocations or PPC decoder in dispatch. */
static uint32_t triage_first[AR_AOT_TRIAGE_FIRST],triage_first_count;
static uint32_t triage_run_pcs[AR_AOT_TRIAGE_RUNS];
static uint32_t triage_run_hits[AR_AOT_TRIAGE_RUNS],triage_run_total;
static uint32_t triage_stop_prev,triage_stop_cr,triage_stop_xer;
static uint64_t triage_stop_lr,triage_stop_ctr,triage_stop_r1,triage_stop_r2,triage_stop_r3;
/* Experimental signed PPC fallback. No JIT, never register as native AOT. */
static const uint8_t *fb_elf;
static ar_ppc_fallback_fn fb_eval;
static size_t fb_elf_size;
static uint32_t fb_cap,fb_steps,fb_pc,fb_op,fb_bad_pc,fb_bad_op;
static uint32_t fb_history_pc[AR_FALLBACK_TRACE_PCS],fb_history_op[AR_FALLBACK_TRACE_PCS];
static uint32_t fb_callsite_pc,fb_call_target;
static uint32_t lv2_pc_pending,lv2_calls,lv2_last_number,lv2_last_pc;
static uint32_t lv2_missing_number,lv2_missing_pc;
static uint32_t barrier_eieio,barrier_sync,barrier_lwsync,barrier_isync;
static uint32_t barrier_last_pc;
static uint32_t fp_loads,fp_stores,fp_converts,fp_divides,fp_last_pc;

static uint32_t aot_hash(uint32_t pc){
  return (((pc>>2)*UINT32_C(2654435761)) & (AR_AOT_INDEX_SIZE-1u));
}
void ar_trace_snapshot(ar_aot_trace *out) {
 if(!out)return;
 memset(out,0,sizeof(*out));
 out->aot_dispatches=trace_total;
 out->unique_aot=trace_unique;
 out->unresolved_pc=trace_pending;
 out->hle_dispatches=trace_hle;
 out->max_budget=trace_budget;
 out->trace_count=trace_total<AR_AOT_TRACE_PCS?trace_total:AR_AOT_TRACE_PCS;
 out->fallback_steps=fb_steps;out->fallback_last_pc=fb_pc;
 out->fallback_last_opcode=fb_op;
 out->fallback_unsupported_pc=fb_bad_pc;
 out->fallback_unsupported_word=fb_bad_op;
 out->fallback_callsite_pc=fb_callsite_pc;
 out->fallback_call_target=fb_call_target;
 out->lv2_calls=lv2_calls;
 out->lv2_last_number=lv2_last_number;
 out->lv2_last_pc=lv2_last_pc;
 out->lv2_missing_number=lv2_missing_number;
 out->lv2_missing_pc=lv2_missing_pc;
 out->eieio_steps=barrier_eieio;
 out->sync_steps=barrier_sync;
 out->lwsync_steps=barrier_lwsync;
 out->isync_steps=barrier_isync;
 out->last_barrier_pc=barrier_last_pc;
 out->fp_loads=fp_loads;out->fp_stores=fp_stores;
 out->fp_converts=fp_converts;out->fp_divides=fp_divides;
 out->fp_last_pc=fp_last_pc;
 out->fallback_step_limit=fb_cap;
 out->fallback_trace_count=fb_steps<AR_FALLBACK_TRACE_PCS?fb_steps:AR_FALLBACK_TRACE_PCS;
 const uint32_t fb_start=fb_steps-out->fallback_trace_count;
 for(uint32_t i=0;i<out->fallback_trace_count;i++){
    const uint32_t at=(fb_start+i)&(AR_FALLBACK_TRACE_PCS-1u);
    out->fallback_trace_pcs[i]=fb_history_pc[at];
    out->fallback_trace_words[i]=fb_history_op[at];
 }
 const uint32_t start=trace_total-out->trace_count;
 for(uint32_t i=0;i<out->trace_count;i++)
   out->trace_pcs[i]=trace_ring[(start+i)&(AR_AOT_TRACE_PCS-1u)];
 out->first_total=trace_unique;
 out->first_count=triage_first_count;
 for(uint32_t i=0;i<triage_first_count;i++)
   out->first_pcs[i]=triage_first[i];
 out->run_total=triage_run_total;
 out->run_count=triage_run_total<AR_AOT_TRIAGE_RUNS?
                triage_run_total:AR_AOT_TRIAGE_RUNS;
 const uint32_t rstart=triage_run_total-out->run_count;
 for(uint32_t i=0;i<out->run_count;i++){
   const uint32_t at=(rstart+i)&(AR_AOT_TRIAGE_RUNS-1u);
   out->run_pcs[i]=triage_run_pcs[at];
   out->run_repetitions[i]=triage_run_hits[at];
 }
 out->stop_previous_aot=triage_stop_prev;
 out->stop_cr=triage_stop_cr;out->stop_xer=triage_stop_xer;
 out->stop_lr=triage_stop_lr;out->stop_ctr=triage_stop_ctr;
 out->stop_r1=triage_stop_r1;out->stop_r2=triage_stop_r2;
 out->stop_r3=triage_stop_r3;
}
static struct {uint32_t stub,nid;} imports[MAX_IMPORTS];
static size_t nimports;
static struct {uint32_t nid;ar_hle_fn fn;} handlers[MAX_HANDLERS];
static size_t nhandlers;
static uint32_t missing_nid,missing_syscall;
static struct {uint32_t number;ar_hle_fn fn;} syscalls[MAX_LV2_SYSCALLS];
static size_t nsyscalls;
static uint8_t *mem;
#define AR_EXTERNAL_MAX 512u
static struct {uint32_t start;size_t size;uint8_t *bytes;} extra[AR_EXTERNAL_MAX];
static size_t nextra;
static int fault;
static uint32_t missing,budget,depth;
int ar_ppc_fallback_attach(const uint8_t*elf,size_t len,uint32_t limit,
                            ar_ppc_fallback_fn evaluate){
#ifdef ASCENSION_NATIVE_ONLY
 /* Production iOS: PPC interpretation prohibited, including accidental
  * attachment by legacy app code. No JIT or dynamic translation. */
 (void)elf;(void)len;(void)limit;(void)evaluate;
 return AR_BAD_ARGS;
#else
 if(!mem||!elf||!evaluate||len<64u||!limit||
    limit>AR_PPC_FALLBACK_MAX_STEPS||depth)
    return AR_BAD_ARGS;
 fb_elf=elf;fb_elf_size=len;fb_cap=limit;fb_eval=evaluate;return AR_OK;
#endif
}
int ar_bridge_init(size_t n) {
  if(!n||n>MAX_MEM)return AR_BAD_ARGS;
  ar_bridge_shutdown();
  mem=(uint8_t*)calloc(n,1);
  if(!mem)return AR_NO_MEMORY;
  mem_size=n;return AR_OK;
}
void ar_bridge_shutdown(void){
  free(mem);mem=0;mem_size=0;memset(extra,0,sizeof(extra));nextra=0;nfunc=0;memset(aot_slot,0,sizeof(aot_slot));
 memset(trace_seen,0,sizeof(trace_seen));memset(trace_ring,0,sizeof(trace_ring));
 trace_total=0;trace_unique=0;trace_hle=0;trace_pending=0;trace_budget=0;
 triage_first_count=triage_run_total=0;
 memset(triage_first,0,sizeof(triage_first));
 memset(triage_run_pcs,0,sizeof(triage_run_pcs));
 memset(triage_run_hits,0,sizeof(triage_run_hits));
 triage_stop_prev=triage_stop_cr=triage_stop_xer=0;
 triage_stop_lr=triage_stop_ctr=triage_stop_r1=triage_stop_r2=triage_stop_r3=0;
 nimports=0;nhandlers=0;nsyscalls=0;missing_nid=0;missing_syscall=0;fault=0;missing=0;budget=0;depth=0;
 fb_elf=0;fb_eval=0;fb_elf_size=0;fb_cap=0;fb_steps=0;fb_pc=0;fb_op=0;fb_bad_pc=0;fb_bad_op=0;
 fb_callsite_pc=0;fb_call_target=0;
 lv2_pc_pending=0;lv2_calls=0;lv2_last_number=0;lv2_last_pc=0;
 lv2_missing_number=0;lv2_missing_pc=0;
 barrier_eieio=0;barrier_sync=0;barrier_lwsync=0;barrier_isync=0;
 barrier_last_pc=0;
 fp_loads=fp_stores=fp_converts=fp_divides=fp_last_pc=0;
}
int ar_last_error(void){return fault;}
uint32_t ar_last_missing_nid(void){return missing_nid;}
uint32_t ar_last_missing_syscall(void){return missing_syscall;}
int ar_bind_syscall(uint32_t n,ar_hle_fn fn){
 if(n>=1024||!fn||nsyscalls>=MAX_LV2_SYSCALLS)return AR_BAD_ARGS;
 for(size_t i=0;i<nsyscalls;i++)if(syscalls[i].number==n)return AR_DUPLICATE;
 syscalls[nsyscalls].number=n;syscalls[nsyscalls++].fn=fn;return AR_OK;
}
void ar_ppc_note_fp(uint32_t pc,uint32_t insn){
  const unsigned op=insn>>26;
  if(op==48u||op==50u)fp_loads++;
  else if(op==52u||op==54u)fp_stores++;
  else if(op==63u){
    const unsigned xo=(insn>>1)&1023u;
    if(xo==846u)fp_converts++;
    else if(xo==18u)fp_divides++;
    else return;
  }else return;
  fp_last_pc=pc;
}
void ar_ppc_note_barrier(uint32_t pc,uint32_t insn){
  /* Count only authenticated PPC fallback barriers actually executed. */
  switch(insn){
  case UINT32_C(0x7c0006ac):barrier_eieio++;break;
  case UINT32_C(0x7c0004ac):barrier_sync++;break;
  case UINT32_C(0x7c2004ac):barrier_lwsync++;break;
  case UINT32_C(0x4c00012c):barrier_isync++;break;
  default:return;
  }
  barrier_last_pc=pc;
}
void ar_ppc_note_syscall_pc(uint32_t pc){
 lv2_pc_pending=pc;
}
int ar_guest_syscall(ppu_context*c){
 if(!c||!depth)return AR_BAD_ARGS;
 const uint32_t source_pc=lv2_pc_pending;
 lv2_pc_pending=0;
 uint64_t n=c->gpr[11];
 ++lv2_calls;
 lv2_last_number=(uint32_t)n;lv2_last_pc=source_pc;
 if(n>=1024){
  missing_syscall=(uint32_t)n;
  lv2_missing_number=(uint32_t)n;lv2_missing_pc=source_pc;
  fault=AR_MISSING_LV2;return AR_MISSING_LV2;
 }
 for(size_t i=0;i<nsyscalls;i++)if(syscalls[i].number==n){
  int rc=syscalls[i].fn(c);
  if(fault)return fault;
  if(rc){fault=AR_LV2_FAILURE;return AR_LV2_FAILURE;}
  return AR_OK;
 }
 missing_syscall=(uint32_t)n;
 lv2_missing_number=(uint32_t)n;lv2_missing_pc=source_pc;
 fault=AR_MISSING_LV2;return AR_MISSING_LV2;
}
int ar_bind_import(uint32_t stub,uint32_t nid){
 if(!stub||(stub&3)||!nid||nimports>=MAX_IMPORTS)return AR_BAD_ARGS;
 for(size_t i=0;i<nimports;i++)if(imports[i].stub==stub)return AR_DUPLICATE;
 imports[nimports].stub=stub;imports[nimports++].nid=nid;return AR_OK;
}
int ar_bind_hle(uint32_t nid,ar_hle_fn fn){
 if(!nid||!fn||nhandlers>=MAX_HANDLERS)return AR_BAD_ARGS;
 for(size_t i=0;i<nhandlers;i++)if(handlers[i].nid==nid)return AR_DUPLICATE;
 handlers[nhandlers].nid=nid;handlers[nhandlers++].fn=fn;return AR_OK;
}
uint32_t ar_last_unresolved(void){return missing;}
size_t ar_registered_count(void){return nfunc;}

/* Guest low ELF plus sparse high mappings; no PPC interpreter.
 * External map OWNS NO bytes: the mapper manages their lifetime.
 * An address reservation alone cannot create valid memory. */
static int overlap(uint64_t a,size_t n,uint64_t b,size_t m){
 return a<(b+(uint64_t)m) && b<(a+(uint64_t)n);
}
int ar_vm_external_map(uint32_t addr,uint8_t *bytes,size_t count){
 if(!mem||!bytes||!addr||!count||nextra>=AR_EXTERNAL_MAX ||
    (uint64_t)addr+count>(uint64_t)UINT32_MAX+1u ||
    overlap(addr,count,0,mem_size))return AR_BAD_ARGS;
 for(size_t i=0;i<nextra;i++)
  if(overlap(addr,count,extra[i].start,extra[i].size))return AR_DUPLICATE;
 extra[nextra].start=addr;extra[nextra].size=count;
 extra[nextra++].bytes=bytes;return AR_OK;
}
int ar_vm_external_unmap(uint32_t addr){
 for(size_t i=0;i<nextra;i++)if(extra[i].start==addr){
   extra[i]=extra[--nextra];memset(&extra[nextra],0,sizeof(extra[0]));
   return AR_OK;
 }
 return AR_BAD_ARGS;
}
static uint8_t* guest_ptr(uint64_t addr,size_t n){
 if(!mem||!n||addr>UINT32_MAX||
    n>(uint64_t)UINT32_MAX+1u-addr){fault=AR_MEM_FAULT;return NULL;}
 if(addr<mem_size && n<=mem_size-(size_t)addr)
   return mem+(size_t)addr;
 for(size_t i=0;i<nextra;i++){
   if(addr>=extra[i].start &&
      addr-(uint64_t)extra[i].start<extra[i].size &&
      n<=extra[i].size-(size_t)(addr-extra[i].start))
      return extra[i].bytes+(size_t)(addr-extra[i].start);
 }
 fault=AR_MEM_FAULT;return NULL;
}
int ar_vm_read_bytes(uint64_t a,void *dest,size_t n){
 if(!n)return AR_OK;
 if(!dest)return AR_BAD_ARGS;
 uint8_t *src=guest_ptr(a,n);
 if(!src)return AR_MEM_FAULT;
 memcpy(dest,src,n);return AR_OK;
}
int ar_vm_load(uint64_t a,const void *b,size_t n){
 if(!n)return AR_OK;
 if(!b)return AR_BAD_ARGS;
 uint8_t *dest=guest_ptr(a,n);if(!dest)return AR_MEM_FAULT;
 memcpy(dest,b,n);return AR_OK;
}
int ar_vm_zero(uint64_t a,size_t n){
 if(!n)return AR_OK;
 uint8_t *dest=guest_ptr(a,n);if(!dest)return AR_MEM_FAULT;
 memset(dest,0,n);return AR_OK;
}
static uint64_t read_be(uint64_t a,size_t n){
 uint8_t *p=guest_ptr(a,n);if(!p)return 0;
 uint64_t v=0;for(size_t i=0;i<n;i++)v=(v<<8)|p[i];return v;
}
static void write_be(uint64_t a,uint64_t v,size_t n){
 uint8_t *p=guest_ptr(a,n);if(!p)return;
 for(size_t i=0;i<n;i++){p[n-1-i]=(uint8_t)v;v>>=8;}
}
uint8_t ar_read8(uint64_t a){return (uint8_t)read_be(a,1);}
uint16_t ar_read16(uint64_t a){return (uint16_t)read_be(a,2);}
uint32_t ar_read32(uint64_t a){return (uint32_t)read_be(a,4);}
uint64_t ar_read64(uint64_t a){return read_be(a,8);}
void ar_write8(uint64_t a,uint8_t v){write_be(a,v,1);}
void ar_write16(uint64_t a,uint16_t v){write_be(a,v,2);}
void ar_write32(uint64_t a,uint32_t v){write_be(a,v,4);}
void ar_write64(uint64_t a,uint64_t v){write_be(a,v,8);}
int ar_register(uint32_t pc,ar_ppu_fn fn){
  if(!pc||(pc&3)||!fn||nfunc>=MAX_FUNCS)return AR_BAD_ARGS;
  uint32_t slot=aot_hash(pc);
  for(unsigned probes=0;probes<AR_AOT_INDEX_SIZE;probes++){
    if(!aot_slot[slot]){
      funcs[nfunc].pc=pc;funcs[nfunc].fn=fn;
      aot_slot[slot]=(uint16_t)(nfunc+1u);nfunc++;
      return AR_OK;
    }
    if(funcs[aot_slot[slot]-1u].pc==pc)return AR_DUPLICATE;
    slot=(slot+1u)&(AR_AOT_INDEX_SIZE-1u);
  }
  return AR_BAD_ARGS;
}
static ar_ppu_fn lookup(uint64_t addr,size_t *index){
  if(addr>UINT32_MAX||(addr&3u))return 0;
  uint32_t slot=aot_hash((uint32_t)addr);
  for(unsigned probes=0;probes<AR_AOT_INDEX_SIZE;probes++){
    if(!aot_slot[slot])return 0;
    const size_t idx=(size_t)aot_slot[slot]-1u;
    if(funcs[idx].pc==addr){
      if(index)*index=idx;
      return funcs[idx].fn;
    }
    slot=(slot+1u)&(AR_AOT_INDEX_SIZE-1u);
  }
  return 0;
}
void ar_ppc_note_failed_call(uint32_t site,uint32_t target){
 if(site && target && !fb_callsite_pc){fb_callsite_pc=site;fb_call_target=target;}
}
static uint32_t import_nid(uint64_t stub){
 for(size_t i=0;i<nimports;i++)if(imports[i].stub==stub)return imports[i].nid;
 return 0;
}
static ar_hle_fn hle_handler(uint32_t nid){
 for(size_t i=0;i<nhandlers;i++)if(handlers[i].nid==nid)return handlers[i].fn;
 return 0;
}
static int dispatch(ppu_context *c,uint64_t pc){
  if(depth>=MAX_DEPTH){fault=AR_DEPTH;return AR_DEPTH;}
  depth++;int result=AR_OK;
  for(;;){
    if(!budget){result=fault=AR_BUDGET;break;}
    budget--;
    size_t found_index=0u;
    ar_ppu_fn fn=lookup(pc,&found_index);
    if(!fn){
      uint32_t nid=import_nid(pc);
      if(nid){
        ar_hle_fn hle=hle_handler(nid);
        if(!hle){missing_nid=nid;result=fault=AR_MISSING_HLE;break;}
        trace_hle++;
        uint64_t saved_toc=c->gpr[2];
        int rc=hle(c);
        c->gpr[2]=saved_toc;
        if(fault){result=fault;break;}
        if(rc){result=fault=AR_HLE_FAILURE;break;}
        c->cia=c->lr;result=AR_OK;break;
      }
      /* M7.20: only if the user-imported ELF was authenticated and the
       * bridge explicitly attached it. Native AOT always wins lookup.
       * Each interpreted PPC instruction consumes normal guest budget. */
#ifndef ASCENSION_NATIVE_ONLY
      if(fb_elf && fb_eval) {
        if(fb_steps>=fb_cap){
          missing=(uint32_t)pc;trace_pending=(uint32_t)pc;
          result=fault=AR_PPC_LIMIT;break;
        }
        uint32_t word=0;
        const int step=fb_eval(c,fb_elf,fb_elf_size,
                               (uint32_t)pc,&word);
        if(step==AR_TAIL || step==AR_OK){
          const uint32_t index=fb_steps&(AR_FALLBACK_TRACE_PCS-1u);
          fb_history_pc[index]=(uint32_t)pc;fb_history_op[index]=word;
          fb_steps++;fb_pc=(uint32_t)pc;fb_op=word;
          if(fault){result=fault;break;}
          if(step==AR_TAIL){pc=c->cia;continue;}
          result=AR_OK;break;
        }
        /* Preserve deepest nested dispatch failure, never overwrite with BL. */
        if(fault){result=fault;break;}
        if(step==AR_PPC_UNSUPPORTED){
          fb_bad_pc=(uint32_t)pc;fb_bad_op=word;
          missing=(uint32_t)pc;trace_pending=(uint32_t)pc;
          result=fault=AR_PPC_UNSUPPORTED;break;
        }
        missing=(uint32_t)pc;trace_pending=(uint32_t)pc;
        result=fault=step;break;
      }
#endif
      /* Native-only gate: no callable AOT and no matching HLE means stop
       * here. A static ELF branch can target any PC; it is NEVER executed
       * by decoding PPC at runtime. */
      missing=(uint32_t)pc;trace_pending=(uint32_t)pc;
      /* Snapshot only metadata, never guest data or game assets. This is
       * a real missing ARM64 entry, not a fabricated PPC opcode. */
      triage_stop_prev=trace_total?
        trace_ring[(trace_total-1u)&(AR_AOT_TRACE_PCS-1u)]:0u;
      triage_stop_cr=c->cr;triage_stop_xer=c->xer;
      triage_stop_lr=c->lr;triage_stop_ctr=c->ctr;
      triage_stop_r1=c->gpr[1];triage_stop_r2=c->gpr[2];
      triage_stop_r3=c->gpr[3];
      result=fault=AR_UNRESOLVED;break;
    }
    trace_ring[trace_total & (AR_AOT_TRACE_PCS-1u)]=(uint32_t)pc;
    trace_total++;
    if(!trace_seen[found_index]){
      trace_seen[found_index]=1u;trace_unique++;
      if(triage_first_count<AR_AOT_TRIAGE_FIRST)
        triage_first[triage_first_count++]=(uint32_t)pc;
    }
    if(triage_run_total &&
       triage_run_pcs[(triage_run_total-1u)&(AR_AOT_TRIAGE_RUNS-1u)]==(uint32_t)pc){
      const uint32_t slot=(triage_run_total-1u)&(AR_AOT_TRIAGE_RUNS-1u);
      if(triage_run_hits[slot]!=UINT32_MAX)triage_run_hits[slot]++;
    }else{
      const uint32_t slot=triage_run_total&(AR_AOT_TRIAGE_RUNS-1u);
      triage_run_pcs[slot]=(uint32_t)pc;
      triage_run_hits[slot]=1u;
      triage_run_total++;
    }
    int status=fn(c);
    if(fault){result=fault;break;}
    if(status==AR_TAIL){pc=c->cia;continue;}
    if(status==AR_OK){result=AR_OK;break;}
    result=fault=status;break;
  }
  depth--;return result;
}
int ar_guest_call(ppu_context *c,uint64_t pc){
  if(!c||!depth)return AR_BAD_ARGS;
  return dispatch(c,pc);
}
int ar_run(ppu_context *c,uint32_t pc,uint32_t ticks){
  if(!c||!pc||!ticks||!mem||depth)return AR_BAD_ARGS;
  fault=0;missing=0;missing_nid=0;missing_syscall=0;budget=ticks;
  memset(trace_seen,0,sizeof(trace_seen));memset(trace_ring,0,sizeof(trace_ring));
  trace_total=0;trace_unique=0;trace_hle=0;trace_pending=0;trace_budget=ticks;
  triage_first_count=triage_run_total=0;
  memset(triage_first,0,sizeof(triage_first));
  memset(triage_run_pcs,0,sizeof(triage_run_pcs));
  memset(triage_run_hits,0,sizeof(triage_run_hits));
  triage_stop_prev=triage_stop_cr=triage_stop_xer=0;
  triage_stop_lr=triage_stop_ctr=triage_stop_r1=triage_stop_r2=triage_stop_r3=0;
  fb_steps=0;fb_pc=0;fb_op=0;fb_bad_pc=0;fb_bad_op=0;
  fb_callsite_pc=0;fb_call_target=0;
  lv2_pc_pending=0;lv2_calls=0;lv2_last_number=0;lv2_last_pc=0;
  lv2_missing_number=0;lv2_missing_pc=0;
  barrier_eieio=0;barrier_sync=0;barrier_lwsync=0;barrier_isync=0;
  barrier_last_pc=0;
  fp_loads=fp_stores=fp_converts=fp_divides=fp_last_pc=0;
  return dispatch(c,pc);
}
