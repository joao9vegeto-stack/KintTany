/* M7.51 synthetic guest API test. No commercial data. */
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "ppu_guest_fs.h"
static uint8_t guest[4096];
static unsigned binds;
int ar_vm_read_bytes(uint64_t at,void *dst,size_t n){
 if(at>sizeof(guest)||n>sizeof(guest)-at)return AR_MEM_FAULT;
 memcpy(dst,guest+at,n);return AR_OK;
}
int ar_vm_load(uint64_t at,const void *src,size_t n){
 if(at>sizeof(guest)||n>sizeof(guest)-at)return AR_MEM_FAULT;
 memcpy(guest+at,src,n);return AR_OK;
}
int ar_bind_syscall(uint32_t code,ar_hle_fn fn){
 if(!fn||(binds==0 && code!=801)||(binds==1 && code!=802)||
    (binds==2 && code!=804))return AR_BAD_ARGS;
 binds++;return AR_OK;
}
static int host(const char *path,uint64_t offset,void *dst,size_t count,
                size_t *actual,uint64_t *sz){
 static const char payload[]="0123456789abcdef";
 if(strcmp(path,"USRDIR/test.psarc"))return -1;
 *sz=16u;*actual=0u;
 if(count){
  if(offset>16u)return -1;
  size_t n=count<16u-offset?count:(size_t)(16u-offset);
  memcpy(dst,payload+offset,n);*actual=n;
 }
 return 0;
}
static uint32_t be32(const uint8_t *p){
 return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
int main(void){
 ppu_context cpu={0};
 strcpy((char*)guest+64,"/dev_hdd0/game/NPUA80918/USRDIR/test.psarc");
 ar_fs_reset();ar_fs_set_host_io(host);
 if(ar_fs_bind_syscalls()!=AR_OK||binds!=3u)return 1;
 cpu.gpr[3]=64;cpu.gpr[4]=0;cpu.gpr[5]=512;
 if(ar_fs_guest_open(&cpu)!=AR_OK||cpu.gpr[3]!=0||be32(guest+512)!=3u)return 2;
 cpu.gpr[3]=3;cpu.gpr[4]=1024;cpu.gpr[5]=8;cpu.gpr[6]=768;
 if(ar_fs_guest_read(&cpu)!=AR_OK||cpu.gpr[3]!=0||
    memcmp(guest+1024,"01234567",8)||guest[775]!=8u)return 3;
 cpu.gpr[3]=3;cpu.gpr[4]=1032;cpu.gpr[5]=16;cpu.gpr[6]=768;
 if(ar_fs_guest_read(&cpu)!=AR_OK||cpu.gpr[3]!=0||
    memcmp(guest+1032,"89abcdef",8)||guest[775]!=8u)return 4;
 ar_fs_trace t={0};ar_fs_snapshot(&t);
 if(t.open_ok!=1||t.read_ok!=2||t.bytes_read!=16||
    strcmp(t.last_path,"USRDIR/test.psarc")!=0)return 5;
 cpu.gpr[3]=3;
 if(ar_fs_guest_close(&cpu)!=AR_OK||cpu.gpr[3]!=0)return 6;
 strcpy((char*)guest+64,"/app_home/test.psarc");
 cpu.gpr[3]=64;cpu.gpr[4]=0;cpu.gpr[5]=512;
 if(ar_fs_guest_open(&cpu)!=AR_OK||cpu.gpr[3]!=0||be32(guest+512)!=3u)return 7;
 ar_fs_trace app_home={0};ar_fs_snapshot(&app_home);
 if(strcmp(app_home.last_path,"USRDIR/test.psarc")!=0)return 8;
 cpu.gpr[3]=3;
 if(ar_fs_guest_close(&cpu)!=AR_OK||cpu.gpr[3]!=0)return 9;
 cpu.gpr[3]=3;cpu.gpr[4]=1024;cpu.gpr[5]=1;
 if(ar_fs_guest_read(&cpu)!=AR_OK||cpu.gpr[3]!=UINT32_C(0x8001002a))return 10;
 strcpy((char*)guest+64,"/dev_hdd0/game/NPUA80918/USRDIR/../test.psarc");
 cpu.gpr[3]=64;cpu.gpr[4]=0;cpu.gpr[5]=512;
 if(ar_fs_guest_open(&cpu)!=AR_OK||cpu.gpr[3]==0)return 11;
 puts("M7.51 guest FS: /app_home -> USRDIR; BE FD/read count, offset, close, traversal fail-closed PASS (SYNTHETIC; no guest game call)");
 return 0;
}
