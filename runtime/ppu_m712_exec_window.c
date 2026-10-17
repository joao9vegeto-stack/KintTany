/* M7.12: read-only instruction inventory at a missing AOT entry.
 * NOT PPC interpretation, JIT, nor untrusted guest-code execution.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
static uint16_t rd16(const uint8_t*p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint32_t rd32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t rd64(const uint8_t*p){return ((uint64_t)rd32(p)<<32)|rd32(p+4);}
/* On success out[0..3] are original big-endian PPC words, out[4] is
 * the number of file-backed executable words present, out[5] PT_LOAD flags.
 * 0=success; -1=bad args; -2=malformed ELF; -3=not executable/available.
 */
int ar_m712_exec_window(const uint8_t *elf,size_t len,uint32_t pc,uint32_t out[6]){
 if(!out)return -1;
 memset(out,0,6u*sizeof(*out));
 if(!elf||len<64u||(pc&3u))return -1;
 if(memcmp(elf,"\177ELF",4)||elf[4]!=2u||elf[5]!=2u||elf[6]!=1u||
    rd16(elf+16)!=2u||rd16(elf+18)!=21u||rd32(elf+20)!=1u)return -2;
 const uint64_t phoff=rd64(elf+32);
 const uint16_t entsize=rd16(elf+54),count=rd16(elf+56);
 if(entsize<56u||!count||count>64u||phoff>len||
    (uint64_t)entsize*count>(uint64_t)len-phoff)return -2;
 for(unsigned i=0;i<count;i++){
   const uint8_t*p=elf+(size_t)phoff+(size_t)i*entsize;
   if(rd32(p)!=1u)continue;
   const uint32_t flags=rd32(p+4);
   const uint64_t offset=rd64(p+8),va=rd64(p+16);
   const uint64_t fs=rd64(p+32),ms=rd64(p+40);
   if(offset>len||fs>(uint64_t)len-offset||fs>ms||va>UINT64_MAX-ms)
     return -2;
   if(!(flags&1u)||(uint64_t)pc<va||(uint64_t)pc-va>=fs)continue;
   const uint64_t delta=(uint64_t)pc-va;
   const uint64_t avail=fs-delta;
   if(avail<4u)return -3;
   const unsigned n=(unsigned)((avail/4u<4u)?avail/4u:4u);
   for(unsigned j=0;j<n;j++)
     out[j]=rd32(elf+(size_t)(offset+delta+4u*j));
   out[4]=n;out[5]=flags;return 0;
 }
 return -3;
}
