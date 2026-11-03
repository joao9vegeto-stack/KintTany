#include "SpartanIOSGuestELFLoader.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static void w16(uint8_t*p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void w32(uint8_t*p,uint32_t v){for(int i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void w64(uint8_t*p,uint64_t v){for(int i=0;i<8;i++)p[i]=(uint8_t)(v>>(8*i));}
static void fixture(uint8_t*b){memset(b,0,0x204);memcpy(b,"\x7f""ELF",4);b[4]=2;b[5]=1;b[6]=1;w16(b+16,2);w16(b+18,62);w32(b+20,1);w64(b+24,0x400100);w64(b+32,64);w16(b+52,64);w16(b+54,56);w16(b+56,1);w32(b+64,1);w32(b+68,5);w64(b+72,0x200);w64(b+80,0x400000);w64(b+96,4);w64(b+104,0x2000);w64(b+112,0x1000);b[0x200]=0x90;b[0x201]=0x90;b[0x202]=0xc3;b[0x203]=0xcc;}
int main(void){uint8_t b[0x204];char e[128];fixture(b);SpartanGuestELF*im=spartan_guest_elf_load(b,sizeof(b),e,sizeof(e));assert(im&&e[0]=='\0');assert(spartan_guest_elf_entry(im)==0x400100);assert(spartan_guest_elf_segment_count(im)==1);SpartanGuestELFSegment s;assert(spartan_guest_elf_segment(im,0,&s));assert(s.virtual_address==0x400000&&s.file_size==4&&s.memory_size==0x2000&&(s.flags&1));uint8_t*g=spartan_guest_memory_host_pointer(spartan_guest_elf_memory(im),0x400000,0x2000);assert(g&&g[0]==0x90&&g[2]==0xc3&&g[3]==0xcc);for(size_t i=4;i<0x2000;i++)assert(g[i]==0);spartan_guest_elf_destroy(im);b[0]=0;assert(!spartan_guest_elf_load(b,sizeof(b),e,sizeof(e)));assert(strstr(e,"ELF64"));fixture(b);w64(b+96,0x300);assert(!spartan_guest_elf_load(b,sizeof(b),e,sizeof(e)));assert(strstr(e,"PT_LOAD"));puts("PASS: x86-64 ELF PT_LOAD staging, BSS zeroing and fail-closed validation");return 0;}
