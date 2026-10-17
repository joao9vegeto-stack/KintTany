/* M7.14: owner-observed four-instruction PPU->ARM64 block and read-only
 * batched PC inventory. No interpreter, no JIT, no synthetic game commands. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define AR_M714_PC UINT32_C(0x003c4da4)
#define AR_M714_NEXT UINT32_C(0x003c4db4)

/* PPC64 rldicl r4,r4,0,32; stw r3,24(r29);
 * addis r3,0,-32768; stw r30,16(r29). */
int ar_m714_aot_003c4da4(ppu_context *c) {
    if(!c) return AR_BAD_ARGS;
    c->gpr[4] &= UINT64_C(0xffffffff);
    const uint64_t ea24 = c->gpr[29] + UINT64_C(24);
    ar_write32(ea24,(uint32_t)c->gpr[3]);
    if(ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    c->gpr[3] = UINT64_C(0xffffffff80000000);
    const uint64_t ea16 = c->gpr[29] + UINT64_C(16);
    ar_write32(ea16,(uint32_t)c->gpr[30]);
    if(ar_last_error()!=AR_OK) return AR_MEM_FAULT;
    c->cia = AR_M714_NEXT;
    return AR_TAIL;
}

int ar_m714_register_fragment(const uint8_t *elf,size_t length) {
    const uint32_t expected[4]={
       UINT32_C(0x78840020),UINT32_C(0x907d0018),
       UINT32_C(0x3c608000),UINT32_C(0x93dd0010)
    };
    uint32_t got[6]={0};
    if(ar_m712_exec_window(elf,length,AR_M714_PC,got)!=0 || got[4]!=4 || !(got[5]&1u))
       return AR_BAD_ARGS;
    for(unsigned i=0;i<4;i++)if(got[i]!=expected[i])return AR_BAD_ARGS;
    return ar_register(AR_M714_PC,ar_m714_aot_003c4da4);
}

/* Only copies verified, file-backed executable PPC instruction words.
 * Stops at the first recognized branch/syscall, reporting its PC.
 * Returns -3 only if there are zero available executable words.
 * Reads at most 32 instructions into caller memory; never executes them. */
int ar_m714_frontier_inventory(const uint8_t *elf,size_t length,uint32_t start,
     uint32_t out[32],uint32_t *count,uint32_t *terminal_pc) {
    if(!out || !count || !terminal_pc || (start & 3u) || !start)
       return AR_BAD_ARGS;
    *count=0;*terminal_pc=0;
    memset(out,0,32u*sizeof(*out));
    for(unsigned k=0;k<32u;){
       if(start>UINT32_MAX-4u*k)break;
       uint32_t words[6]={0};
       const int rc=ar_m712_exec_window(elf,length,start+4u*k,words);
       if(rc!=0 || words[4]<1u)break;
       for(unsigned j=0;j<words[4] && k<32u;j++,k++){
          const uint32_t word=words[j];
          out[k]=word;
          *count=k+1u;
          const uint32_t primary=word>>26;
          if(primary==16u || primary==17u || primary==18u || primary==19u){
             *terminal_pc=start+4u*k;
             return AR_OK;
          }
       }
    }
    return *count ? AR_OK : AR_UNRESOLVED;
}
