#include "SpartanIOSGuestELFLoader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define EH 64u
#define PH 56u
#define PT_LOAD 1u
#define PF_X 1u
struct SpartanGuestELF { SpartanGuestMemory *memory; uint64_t entry; SpartanGuestELFSegment *segments; size_t segment_count; };
static uint16_t r16(const uint8_t*p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t r32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t r64(const uint8_t*p){return (uint64_t)r32(p)|((uint64_t)r32(p+4)<<32);}
static int range_ok(uint64_t o,uint64_t n,uint64_t limit){return o<=limit&&n<=limit-o;}
static void err(char*out,size_t n,const char*s){if(out&&n)snprintf(out,n,"%s",s);}
SpartanGuestELF *spartan_guest_elf_load(const void*input,size_t length,char*error,size_t error_capacity){
 const uint8_t*b=input; SpartanGuestELF*im=NULL; uint64_t phoff,entry,max_end=0; uint16_t phentsize,phnum; size_t count=0; int entry_x=0;
 err(error,error_capacity,"invalid ELF image");
 if(!b||length<EH){err(error,error_capacity,"truncated ELF64 header");return NULL;}
 if(memcmp(b,"\x7f""ELF",4)||b[4]!=2||b[5]!=1||b[6]!=1){err(error,error_capacity,"expected ELF64 little-endian");return NULL;}
 if(r16(b+18)!=62){err(error,error_capacity,"expected x86-64 ELF machine");return NULL;}
 if(r16(b+52)<EH){err(error,error_capacity,"invalid ELF header size");return NULL;}
 entry=r64(b+24);phoff=r64(b+32);phentsize=r16(b+54);phnum=r16(b+56);
 if(phentsize<PH||!phnum||phnum>4096||!range_ok(phoff,(uint64_t)phentsize*phnum,length)){err(error,error_capacity,"invalid ELF program-header table");return NULL;}
 for(uint16_t i=0;i<phnum;i++){const uint8_t*p=b+(size_t)phoff+(size_t)i*phentsize;uint32_t t=r32(p),f=r32(p+4);uint64_t o=r64(p+8),v=r64(p+16),fs=r64(p+32),ms=r64(p+40),end;
  if(t!=PT_LOAD)continue;
  if(fs>ms||v>UINT64_MAX-ms||!range_ok(o,fs,length)){err(error,error_capacity,"invalid PT_LOAD range");return NULL;}
  end=v+ms;if(end>max_end)max_end=end;if(ms){count++;if((f&PF_X)&&entry>=v&&entry<end)entry_x=1;}
 }
 if(!count||!max_end||!entry_x){err(error,error_capacity,"missing loadable segment or executable entry point");return NULL;}
 im=calloc(1,sizeof(*im));if(!im){err(error,error_capacity,"out of memory allocating ELF state");return NULL;}
 im->segments=calloc(count,sizeof(*im->segments));if(!im->segments){err(error,error_capacity,"out of memory allocating segment table");free(im);return NULL;}
 im->memory=spartan_guest_memory_create(max_end);
 if(!im->memory||spartan_guest_memory_protect(im->memory,0,spartan_guest_memory_size(im->memory),PROT_READ|PROT_WRITE)!=0){err(error,error_capacity,"unable to allocate writable guest data arena");spartan_guest_elf_destroy(im);return NULL;}
 im->entry=entry;
 for(uint16_t i=0;i<phnum;i++){const uint8_t*p=b+(size_t)phoff+(size_t)i*phentsize;if(r32(p)!=PT_LOAD)continue;
  uint32_t f=r32(p+4);uint64_t o=r64(p+8),v=r64(p+16),fs=r64(p+32),ms=r64(p+40);
  void*dst=spartan_guest_memory_host_pointer(im->memory,v,ms);
  if(!dst){err(error,error_capacity,"PT_LOAD exceeds guest arena");spartan_guest_elf_destroy(im);return NULL;}
  if(fs)memcpy(dst,b+(size_t)o,(size_t)fs);if(ms>fs)memset((uint8_t*)dst+(size_t)fs,0,(size_t)(ms-fs));
  im->segments[im->segment_count++]=(SpartanGuestELFSegment){v,ms,fs,f};
 }
 err(error,error_capacity,"");return im;
}
void spartan_guest_elf_destroy(SpartanGuestELF*im){if(!im)return;spartan_guest_memory_destroy(im->memory);free(im->segments);free(im);}
SpartanGuestMemory*spartan_guest_elf_memory(SpartanGuestELF*im){return im?im->memory:NULL;}
uint64_t spartan_guest_elf_entry(const SpartanGuestELF*im){return im?im->entry:0;}
size_t spartan_guest_elf_segment_count(const SpartanGuestELF*im){return im?im->segment_count:0;}
int spartan_guest_elf_segment(const SpartanGuestELF*im,size_t i,SpartanGuestELFSegment*out){if(!im||!out||i>=im->segment_count)return 0;*out=im->segments[i];return 1;}
