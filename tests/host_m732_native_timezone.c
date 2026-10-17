/* M7.32: nine real frontier words executed native + LV2 144
 * host timezone BE memory semantics. Synthetic PT_LOAD X, no game payload.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_lv2_bootstrap.h"
extern int ar_m732_register_block(const uint8_t*,size_t);
#define PC UINT32_C(0x005230e0)
static void b16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void b32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void b64(uint8_t*p,uint64_t x){b32(p,(uint32_t)(x>>32));b32(p+4,(uint32_t)x);}
static const uint32_t words[11]={
 UINT32_C(0xf821ff61),UINT32_C(0x7c0802a6),
 UINT32_C(0xfb810080),UINT32_C(0xfba10088),
 UINT32_C(0x7c7c1b78),UINT32_C(0xf80100b0),
 UINT32_C(0x38810074),UINT32_C(0x38610070),
 UINT32_C(0x39600090),UINT32_C(0x44000002),
 UINT32_C(0x4e800020)
};
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,PC);
 b64(ph+32,sizeof(words));b64(ph+40,sizeof(words));
 for(unsigned i=0;i<11u;i++)b32(elf+0x200+4u*i,words[i]);
 if(ar_bridge_init((size_t)PC+0x10000)!=AR_OK)return 1;
 if(ar_vm_load(PC,elf+0x200,sizeof(words))!=AR_OK)return 2;
 if(ar_ppc_fallback_attach(elf,sizeof(elf),100u,ar_ppc_fallback_step)!=AR_OK)return 3;
 /* Must refuse incorrect original ELF, missing guest bytes, nonexecutable mapping. */
 b32(elf+0x200+32,UINT32_C(0x39600091));
 if(ar_m732_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 4;
 b32(elf+0x200+32,words[8]);
 b32(ph+4,4);
 if(ar_m732_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 5;
 b32(ph+4,5);
 uint8_t mutated[4];b32(mutated,UINT32_C(0x39600091));
 if(ar_vm_load(PC+32,mutated,4)!=AR_OK)return 6;
 if(ar_m732_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 7;
 if(ar_vm_load(PC,elf+0x200,sizeof(words))!=AR_OK)return 8;
 if(ar_m732_register_block(elf,sizeof(elf))!=AR_OK ||
    ar_registered_count()!=1u)return 9;
 if(ar_bind_syscall(144u,ar_lv2_timezone)!=AR_OK)return 10;
 ar_lv2_bootstrap_reset();
 ppu_context c={0};
 c.lr=UINT64_C(0x00524000);
 c.gpr[1]=0x3400;
 c.gpr[3]=UINT64_C(0xdeadbeef12345678);
 c.gpr[28]=UINT64_C(0x88888888aaaaaaaa);
 c.gpr[29]=UINT64_C(0x99999999bbbbbbbb);
 c.gpr[11]=999u;
 c.cr=UINT32_C(0x98765432);c.xer=UINT32_C(0xe0000000);
 if(ar_run(&c,PC,80)!=AR_OK)return 11;
 const uint64_t sp=UINT64_C(0x3400)-160u;
 if(c.gpr[1]!=sp||c.gpr[0]!=UINT64_C(0x00524000)||
    c.gpr[28]!=UINT64_C(0xdeadbeef12345678)||
    c.gpr[29]!=UINT64_C(0x99999999bbbbbbbb)||
    c.gpr[11]!=144u||c.gpr[3]!=0||c.gpr[4]!=sp+116u ||
    c.cr!=UINT32_C(0x98765432)||c.xer!=UINT32_C(0xe0000000)||
    ar_read64(sp)!=0x3400u||
    ar_read64(sp+128)!=UINT64_C(0x88888888aaaaaaaa)||
    ar_read64(sp+136)!=UINT64_C(0x99999999bbbbbbbb)||
    ar_read64(sp+176)!=UINT64_C(0x00524000))return 12;
 const int32_t standard=(int32_t)ar_read32(sp+112u);
 const int32_t summer=(int32_t)ar_read32(sp+116u);
 if(standard<-840||standard>840||summer<0||summer>180 ||
    ar_lv2_timezone_queries()!=1u)return 13;
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(t.aot_dispatches!=1u||t.unique_aot!=1u||
    t.trace_count!=1||t.trace_pcs[0]!=PC||
    t.fallback_steps!=2u||t.fallback_trace_count!=2u||
    t.fallback_trace_pcs[0]!=PC+36u||
    t.fallback_trace_pcs[1]!=PC+40u||
    t.lv2_calls!=1u||t.lv2_last_number!=144u||
    t.lv2_last_pc!=PC+36u||t.lv2_missing_number) return 14;
 /* Deterministic ABI tests independent of system locale/timezone. */
 ppu_context fixed={0};fixed.gpr[3]=0x3900;fixed.gpr[4]=0x3904;
 if(ar_lv2_timezone_values(&fixed,-180,60)!=AR_OK ||
    fixed.gpr[3]!=0||
    ar_read32(0x3900)!=UINT32_C(0xffffff4c)||
    ar_read32(0x3904)!=60u)return 15;
 fixed.gpr[3]=0x3900;fixed.gpr[4]=0xffffffffu;
 if(ar_lv2_timezone_values(&fixed,-180,60)!=AR_BAD_ARGS||
    ar_read32(0x3900)!=UINT32_C(0xffffff4c))return 16;
 fixed.gpr[3]=0x3900;fixed.gpr[4]=0x3900;
 if(ar_lv2_timezone_values(&fixed,0,0)!=AR_BAD_ARGS)return 17;
 fixed.gpr[3]=0x3900;fixed.gpr[4]=0x7ffff000u;
 if(ar_lv2_timezone_values(&fixed,0,0)!=AR_MEM_FAULT||
    ar_read32(0x3900)!=UINT32_C(0xffffff4c))return 18;
 if(ar_lv2_timezone_queries()!=2u)return 19;
 ar_lv2_bootstrap_reset();
 if(ar_lv2_timezone_queries())return 20;
 ar_bridge_shutdown();
 puts("M7.32 owner 9-op ARM64 AOT + LV2 144 timezone BE s32, 1 native 2 PPC fallback, authentic fail-closed PASS");
 return 0;
}
