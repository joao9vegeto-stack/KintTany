/* M7.31 synthetic verified PowerPC 2-word MT(O)CRF 8,r12; BLR.
 * Tests a signed-ELF-gated true native AOT dispatch (fallback stays ZERO).
 * Does NOT include any original title ELF, game file or keys.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m731_native_0052da5c(ppu_context*);
extern int ar_m731_register_frontier(const uint8_t*,size_t);
#define PC UINT32_C(0x0052da5c)
#define MTOCRF ((UINT32_C(31)<<26)|(UINT32_C(12)<<21)| (UINT32_C(1)<<20)|(UINT32_C(8)<<12)|(UINT32_C(144)<<1))
#define BLR UINT32_C(0x4e800020)
static void b16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void b32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void b64(uint8_t*p,uint64_t x){b32(p,(uint32_t)(x>>32));b32(p+4,(uint32_t)x);}
static uint32_t word(unsigned rs,unsigned l,unsigned mask,unsigned extra){
 return (31u<<26)|(rs<<21)|(l<<20)|(mask<<12)|(144u<<1)|extra;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,PC);b64(ph+32,8);b64(ph+40,8);
 b32(elf+0x200,MTOCRF);b32(elf+0x204,BLR);
 if(MTOCRF!=UINT32_C(0x7d908120))return 1;
 if(ar_bridge_init(PC+0x2000u)!=AR_OK)return 2;
 if(ar_vm_load(PC,elf+0x200,8)!=AR_OK)return 3;
 /* Reject modified code, non-executable segment and unauthenticated VM. */
 b32(elf+0x200,word(12,1,4,0));
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_BAD_ARGS ||
    ar_registered_count()!=0)return 4;
 b32(elf+0x200,MTOCRF);
 b32(elf+0x204,0);
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_BAD_ARGS)return 5;
 b32(elf+0x204,BLR);
 b32(ph+4,4); /* R only, not X */
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_BAD_ARGS)return 6;
 b32(ph+4,5);
 uint8_t mutated[4];b32(mutated,word(12,1,8,1u));
 if(ar_vm_load(PC,mutated,4)!=AR_OK)return 7;
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_BAD_ARGS)return 8;
 if(ar_vm_load(PC,elf+0x200,8)!=AR_OK)return 9;
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_OK ||
    ar_registered_count()!=1u)return 10;
 if(ar_m731_register_frontier(elf,sizeof(elf))!=AR_DUPLICATE)return 11;
 /* Real native function MUST execute and update only CR4, then BLR. */
 ppu_context cpu={0};
 cpu.cr=UINT32_C(0xcafeabcd); /* patched to exact numeric below */
 cpu.gpr[12]=UINT64_C(0xffffffffff234567);
 cpu.gpr[3]=0x1337;
 cpu.lr=0x2007u;cpu.ctr=0x12345678u;cpu.xer=0xe0000000u;
 if(ar_run(&cpu,PC,40)!=AR_OK)return 12;
 const uint32_t before=UINT32_C(0xcafeabcd);
 const uint32_t expected=(before&~UINT32_C(0xf000))|
           ((uint32_t)cpu.gpr[12]&UINT32_C(0xf000));
 if(cpu.cr!=expected||cpu.gpr[12]!=UINT64_C(0xffffffffff234567)||
    cpu.gpr[3]!=0x1337||cpu.cia!=0x2004u||cpu.lr!=0x2007u||
    cpu.ctr!=0x12345678u||cpu.xer!=0xe0000000u)return 13;
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(t.aot_dispatches!=1u||t.unique_aot!=1u ||
    t.trace_count!=1u||t.trace_pcs[0]!=PC||
    t.fallback_steps!=0u||t.hle_dispatches!=0)return 14;
 /* The generic interpreted ISA path agrees for the same exact bytes. */
 cpu.cr=before;cpu.cia=PC;
 uint32_t observed=0;
 if(ar_ppc_fallback_step(&cpu,elf,sizeof(elf),PC,&observed)!=AR_TAIL||
    observed!=MTOCRF||cpu.cr!=expected||cpu.cia!=PC+4u)return 15;
 /* Generic mtcrf can update multiple fields; mtocrf L=1 cannot. */
 const uint32_t multi=word(12,0,0x81,0);
 b32(elf+0x200,multi);
 if(ar_vm_load(PC,elf+0x200,4)!=AR_OK)return 16;
 cpu.cr=before;
 if(ar_ppc_fallback_step(&cpu,elf,sizeof(elf),PC,&observed)!=AR_TAIL)return 17;
 const uint32_t mm=UINT32_C(0xf000000f);
 if(cpu.cr!=((before&~mm)|((uint32_t)cpu.gpr[12]&mm)))return 18;
 const uint32_t bad[]={word(12,1,0x81,0),word(12,1,8,1),
                        word(12,1,8,UINT32_C(0x800)),
                        word(12,1,0,0)};
 for(unsigned i=0;i<4;i++){
    b32(elf+0x200,bad[i]);
    if(ar_vm_load(PC,elf+0x200,4)!=AR_OK)return 19;
    cpu.cr=before;
    if(ar_ppc_fallback_step(&cpu,elf,sizeof(elf),PC,&observed)!=AR_PPC_UNSUPPORTED
        ||cpu.cr!=before)return 20;
 }
 ar_bridge_shutdown();
 puts("M7.31 exact owner-PC CR4 BLR native AOT, 1 dispatch 0 fallback, ISA validation PASS");
 return 0;
}
