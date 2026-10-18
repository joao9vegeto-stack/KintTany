/* Static ELF -> guest VA -> actual mapped RAM diagnostic.
 * Distinguish "unmeasured" from opcode 0. Works without interpreter/JIT.
 */
#include "ppu_m756_stop_evidence.h"
#include "ppu_bridge.h"
#include <string.h>
#include <stdint.h>
static uint16_t rd16(const uint8_t*p){return (uint16_t)(((uint16_t)p[0]<<8)|p[1]);}
static uint32_t rd32(const uint8_t*p){return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static uint64_t rd64(const uint8_t*p){return ((uint64_t)rd32(p)<<32)|rd32(p+4);}
void ar_m756_capture_stop(const uint8_t*elf,size_t len,uint32_t pc,
                          ar_m756_stop_evidence*out){
 if(!out)return;
 memset(out,0,sizeof(*out));
 out->pc=pc;out->elf_status=AR_BAD_ARGS;
 out->guest_status=AR_BAD_ARGS;
 out->file_offset=UINT64_MAX;
 if(!elf||len<64u||!pc||(pc&3u)||memcmp(elf,"\177ELF",4)||
    elf[4]!=2u||elf[5]!=2u||elf[6]!=1u)return;
 uint64_t table=rd64(elf+32);
 const uint16_t count=rd16(elf+56),entsz=rd16(elf+54);
 if(!count||count>64u||entsz<56u||table>len||
    (uint64_t)entsz*count>(uint64_t)len-table)return;
 out->elf_status=AR_UNRESOLVED;
 for(unsigned i=0;i<count;i++){
  const uint8_t*p=elf+(size_t)table+i*entsz;
  if(rd32(p)!=1u||!(rd32(p+4)&1u))continue;
  const uint64_t off=rd64(p+8),va=rd64(p+16);
  const uint64_t filesz=rd64(p+32),memsz=rd64(p+40);
  if(off>len||filesz>len-off||filesz>memsz)continue;
  if(pc<va||(uint64_t)pc-va>=filesz)continue;
  const uint64_t delta=(uint64_t)pc-va;
  const uint64_t at=off+delta;
  const size_t remain=(size_t)(filesz-delta);
  if(remain<4u)break;
  const size_t n=remain<AR_M756_SAMPLE_BYTES?remain:AR_M756_SAMPLE_BYTES;
  out->segment_flags=rd32(p+4);
  out->segment_va=va;out->segment_file_offset=off;
  out->segment_file_size=filesz;out->file_offset=at;
  out->count=(uint32_t)n;
  memcpy(out->elf_bytes,elf+(size_t)at,n);
  out->elf_word=rd32(out->elf_bytes);
  out->elf_status=AR_OK;
  /* This reads actual live guest RAM; may differ from the immutable ELF. */
  out->guest_status=ar_vm_read_bytes(pc,out->guest_bytes,n);
  if(out->guest_status==AR_OK){
    out->guest_word=rd32(out->guest_bytes);
    out->match=memcmp(out->elf_bytes,out->guest_bytes,n)==0?1u:0u;
  }
  return;
 }
}
