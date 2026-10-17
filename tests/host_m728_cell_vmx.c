/* M7.28: synthetic Cell PPU vector ABI tests, exact big-endian data.
 * This is not commercial game code and contains no private user payload.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
static void b16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void b32(uint8_t*p,uint32_t x){p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;}
static void b64(uint8_t*p,uint64_t x){b32(p,(uint32_t)(x>>32));b32(p+4,(uint32_t)x);}
static uint32_t opvec(unsigned vd,unsigned va,unsigned vb,unsigned xo){
 return (4u<<26)|(vd<<21)|(va<<16)|(vb<<11)|xo;
}
static uint32_t opx(unsigned vd,unsigned ra,unsigned rb,unsigned xo){
 return (31u<<26)|(vd<<21)|(ra<<16)|(rb<<11)|(xo<<1);
}
static int single(uint8_t*elf,ppu_context*c,uint32_t op){
 b32(elf+0x200,op);
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return -99;
 uint32_t observed=0;
 int rc=ar_ppc_fallback_step(c,elf,1024,0x1000,&observed);
 return observed==op?rc:-98;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t *ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,0x1000);
 b64(ph+32,0x100);b64(ph+40,0x100);
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 ppu_context c={0};
 if(single(elf,&c,opvec(5,0,0,908))!=AR_TAIL)return 2;
 for(unsigned k=0;k<16;k++)if(ar_vmx_byte(&c,5,k)!=0)return 3;
 if(single(elf,&c,opvec(5,31,0,908))!=AR_TAIL)return 4;
 for(unsigned k=0;k<16;k++)if(ar_vmx_byte(&c,5,k)!=255)return 5;
 if(single(elf,&c,opvec(6,31,0,844))!=AR_TAIL)return 6;
 for(unsigned k=0;k<16;k++)if(ar_vmx_byte(&c,6,k)!=255)return 7;
 if(single(elf,&c,opvec(7,31,0,780))!=AR_TAIL)return 8;
 for(unsigned k=0;k<16;k++)if(ar_vmx_byte(&c,7,k)!=255)return 9;
 uint8_t seq[32];
 for(unsigned k=0;k<32;k++)seq[k]=(uint8_t)(0x10u+k);
 if(ar_vm_load(0x1800,seq,32)!=AR_OK)return 10;
 c.gpr[8]=0x1805;
 if(single(elf,&c,opx(3,0,8,103))!=AR_TAIL)return 11; /* LVX aligns down */
 for(unsigned k=0;k<16;k++)if(ar_vmx_byte(&c,3,k)!=seq[k])return 12;
 /* VSPLTW from v3's third word, alias vD==vB must not smudge input. */
 if(single(elf,&c,opvec(3,2,3,652))!=AR_TAIL)return 13;
 for(unsigned k=0;k<16;k++)
   if(ar_vmx_byte(&c,3,k)!=seq[8+(k&3)])return 14;
 /* STVX writes full vector at effective address rounded down. */
 c.gpr[9]=0x1819;
 if(single(elf,&c,opx(3,0,9,231))!=AR_TAIL)return 15;
 uint8_t out[16]={0};
 if(ar_vm_read_bytes(0x1810,out,16)!=AR_OK)return 16;
 for(unsigned k=0;k<16;k++)if(out[k]!=seq[8+(k&3)])return 17;
 /* Restore sequential test bytes; Cell LVLX zero-fills right lanes. */
 if(ar_vm_load(0x1800,seq,32)!=AR_OK)return 18;
 for(unsigned offset=0;offset<16;offset++){
   c.gpr[8]=0x1800u+offset;
   if(single(elf,&c,opx(4,0,8,519))!=AR_TAIL)return 19;
   for(unsigned k=0;k<16;k++){
     const uint8_t expected=k<16-offset?seq[k+offset]:0u;
     if(ar_vmx_byte(&c,4,k)!=expected)return 20;
   }
   if(single(elf,&c,opx(10,0,8,551))!=AR_TAIL)return 21;
   for(unsigned k=0;k<16;k++){
     const uint8_t expected=k<16-offset?0u:seq[k-(16-offset)];
     if(ar_vmx_byte(&c,10,k)!=expected)return 22;
   }
 }
 /* Partial stores modify only requested guest bytes. */
 uint8_t init[32];memset(init,0xaa,sizeof(init));
 if(ar_vm_load(0x1800,init,32)!=AR_OK)return 23;
 c.gpr[8]=0x1805;
 if(single(elf,&c,opx(3,0,8,647))!=AR_TAIL)return 24; /* STVLX */
 if(ar_vm_read_bytes(0x1800,out,16)!=AR_OK)return 25;
 for(unsigned k=0;k<16;k++){
   const uint8_t expected=k<5?0xaa:seq[8+((k-5)&3)];
   if(out[k]!=expected)return 26;
 }
 if(ar_vm_load(0x1800,init,32)!=AR_OK)return 27;
 if(single(elf,&c,opx(3,0,8,679))!=AR_TAIL)return 28; /* STVRX */
 if(ar_vm_read_bytes(0x1800,out,16)!=AR_OK)return 29;
 for(unsigned k=0;k<16;k++){
   const uint8_t expected=k<5?seq[8+((k+11)&3)]:0xaa;
   if(out[k]!=expected)return 30;
 }
 /* Underflow/unmapped VM must fail closed with unmodified registers. */
 c.gpr[8]=0xfffffff0ULL;c.vr[1]._u64[0]=0x8877665544332211ULL;
 c.vr[1]._u64[1]=0xdeadbeefdeadbeefULL;
 if(single(elf,&c,opx(1,0,8,103))!=AR_MEM_FAULT)return 31;
 if(c.vr[1]._u64[0]!=0x8877665544332211ULL||
    c.vr[1]._u64[1]!=0xdeadbeefdeadbeefULL)return 32;
 ar_bridge_shutdown();
 /* Isolate expected sticky memory error before reserved-opcode checks. */
 if(ar_bridge_init(0x3000)!=AR_OK)return 33;
 const uint32_t invalid[]={opvec(3,0,1,908),opvec(3,4,3,652),
                          opx(3,0,3,103)|1u,
                          opvec(3,0,0,0x6cc)};
 for(unsigned j=0;j<sizeof(invalid)/sizeof(invalid[0]);j++){
   memset(&c,0,sizeof(c));c.vr[3]._u64[0]=0x1234567812345678ULL;
   if(single(elf,&c,invalid[j])!=AR_PPC_UNSUPPORTED)return 34;
   if(c.vr[3]._u64[0]!=0x1234567812345678ULL)return 35;
 }
 ar_bridge_shutdown();
 puts("M7.28 Cell VMX 128-bit signed splats, VSPLTW, LVX, STVX, LVLX, LVRX and partial stores PASS");
 return 0;
}
