/* Synthetic ET_EXEC and libstub: NO real game or firmware bytes. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_import_match(const uint8_t*,size_t,uint32_t,uint32_t[4],char[48]);
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
static void p16(uint8_t*d,unsigned i,uint16_t v){d[i]=v>>8;d[i+1]=(uint8_t)v;}
static void p32(uint8_t*d,unsigned i,uint32_t v){
 d[i]=v>>24;d[i+1]=v>>16;d[i+2]=v>>8;d[i+3]=v;
}
static void p64(uint8_t*d,unsigned i,uint64_t v){
 p32(d,i,(uint32_t)(v>>32));p32(d,i+4,(uint32_t)v);
}
int main(void){
 uint8_t d[0x600]={0};uint32_t info[5]={0},out[4]={0};char name[48]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,3);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0xc0);p64(d,104,0xc0);
 p32(d,120,1);p32(d,124,6);p64(d,128,0x240);p64(d,136,0x20000);
 p64(d,152,0x240);p64(d,160,0x240);
 /* proc_prx_param segment is contained in data PT_LOAD. */
 p32(d,176,0x60000002u);p32(d,180,4);p64(d,184,0x2c0);
 p64(d,192,0x20080);p64(d,208,32);p64(d,216,32);
 p32(d,0x240,0x10000);p32(d,0x244,0x20010);
 p32(d,0x100,0x39800000);
 p32(d,0x2c4,0x1b434cecu);
 p32(d,0x2d8,0x200a0);p32(d,0x2dc,0x200cc);
 /* 0x2c-byte libstub for two synthetic NIDs/stubs */
 d[0x2e0]=0x2c;p16(d,0x2e6,2);
 p32(d,0x2f0,0x200d0);p32(d,0x2f4,0x20100);p32(d,0x2f8,0x20120);
 memcpy(d+0x310,"sysPrxForUser",14);
 p32(d,0x340,0x744680a2u);p32(d,0x344,0x12345678u);
 p32(d,0x360,0x1006cu);p32(d,0x364,0x1007cu);
 if(ar_private_elf_inspect(d,sizeof(d),info))return 1;
 int rc=ar_private_import_match(d,sizeof(d),0x1006cu,out,name);
 if(rc||out[0]!=0x744680a2u||out[1]!=0x1006cu||
    out[2]!=1u||out[3]!=1u||strcmp(name,"sysPrxForUser")){
   fprintf(stderr,"import rc=%d NID=%08x stub=%08x seen=%u libs=%u name=%s\n",
            rc,out[0],out[1],out[2],out[3],name);return 2;
 }
 rc=ar_private_import_match(d,sizeof(d),0x1007cu,out,name);
 if(rc||out[0]!=0x12345678u||out[2]!=2u)return 3;
 rc=ar_private_import_match(d,sizeof(d),0x1008cu,out,name);
 if(rc!=-1||out[0]!=0u||out[2]!=2u)return 4;
 if(ar_private_import_match(d,sizeof(d),0x1006cu,NULL,name)!=-2)return 5;
 p32(d,0x2c4,0);
 if(ar_private_import_match(d,sizeof(d),0x1006cu,out,name)!=-3)return 6;
 p32(d,0x2c4,0x1b434cecu);
 d[0x2e0]=0;
 if(ar_private_import_match(d,sizeof(d),0x1006cu,out,name)!=-4)return 7;
 puts("M6.7.3 private import metadata PASS");
 return 0;
}
