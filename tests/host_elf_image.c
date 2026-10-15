#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include "elf_image.h"
#define VERIFY(x) do{if(!(x)){fprintf(stderr,"ELF_FAIL line %d: %s\n",__LINE__,#x);return 3;}}while(0)
static void write32(unsigned char*p,unsigned v){p[0]=(unsigned char)(v>>24);p[1]=(unsigned char)(v>>16);p[2]=(unsigned char)(v>>8);p[3]=(unsigned char)v;}
int main(int argc,char**argv){
 VERIFY(argc==2);
 FILE*f=fopen(argv[1],"rb");VERIFY(f);
 VERIFY(fseek(f,0,SEEK_END)==0);
 long len=ftell(f);VERIFY(len>0&&len<2000000);
 VERIFY(fseek(f,0,SEEK_SET)==0);
 unsigned char*d=(unsigned char*)malloc((size_t)len);VERIFY(d);
 VERIFY(fread(d,1,(size_t)len,f)==(size_t)len);fclose(f);
 VERIFY(ar_bridge_init(512*1024)==AR_OK);
 ppu_context c={0};ar_elf_image_result r={0};
 VERIFY(ar_load_elf_image(d,(size_t)len,512*1024,&c,&r)==AR_OK);
 VERIFY(r.segments==2&&r.entry_code==0x10000&&r.toc==0x20080);
 VERIFY(c.gpr[2]==0x20080&&c.cia==0x10000);
 VERIFY(ar_read32(0x10000)==0x3860002a);
 VERIFY(ar_read32(0x20000)==0x10000);
 VERIFY(ar_read32(0x20010)==0);
 d[19]=0;
 VERIFY(ar_load_elf_image(d,(size_t)len,512*1024,&c,&r)==AR_BAD_ARGS);
 d[19]=0x15;
 write32(d+64+56+32,0x70000000);
 VERIFY(ar_load_elf_image(d,(size_t)len,512*1024,&c,&r)==AR_BAD_ARGS);
 ar_bridge_shutdown();free(d);
 puts("PASS: PS3 ELF64 PT_LOAD, BSS, OPD, TOC, bad-machine and bad-bound checks");
 return 0;
}
