/* M7.51: guest-originated read-only sys_fs / cellFs bridge.
 * Executed by actual AOT/HLE dispatch or LV2 syscall, never by UI probes.
 * File descriptors/offsets belong to the guest process; host bytes stay
 * on the iPhone and are copied to validated big-endian guest memory.
 */
#include "ppu_guest_fs.h"
#include <string.h>
#define EINVAL_CELL UINT32_C(0x80010002)
#define ENOENT_CELL UINT32_C(0x80010006)
#define EACCES_CELL UINT32_C(0x80010009)
#define EBADF_CELL UINT32_C(0x8001002a)
#define MAX_FD 32u
#define CHUNK 16384u
typedef struct { int active; char relative[256]; uint64_t offset,size; } ar_fs_descriptor;
static ar_fs_descriptor fds[MAX_FD];
static ar_fs_host_io host;
static ar_fs_trace trace;
static void fail(ppu_context *c,uint32_t error){
 c->gpr[3]=error;trace.last_error=error;
}
void ar_fs_reset(void){
 memset(fds,0,sizeof(fds));memset(&trace,0,sizeof(trace));host=0;
}
void ar_fs_set_host_io(ar_fs_host_io fn){host=fn;}
void ar_fs_snapshot(ar_fs_trace *out){if(out)*out=trace;}
static int guest_path(uint64_t ptr,char relative[256]){
 char path[512]={0};
 if(!ptr||ptr>UINT32_MAX-511u)return -1;
 size_t n=0;
 for(;n<sizeof(path)-1u;n++){
  if(ar_vm_read_bytes(ptr+n,&path[n],1u)!=AR_OK)return -1;
  if(path[n]==0)break;
 }
 if(n==sizeof(path)-1u || n==0u)return -1;
 static const struct {const char *prefix,*relative_root;} mounts[]={
  {"/dev_hdd0/game/NPUA80918/",""},
  {"/dev_bdvd/PS3_GAME/",""},
  /* The selected Files root is NPUA80918; app_home is its USRDIR. */
  {"/app_home/","USRDIR/"},
  {"app_home/","USRDIR/"},
  {"e:/app_home/","USRDIR/"}
 };
 const char *p=0,*relative_root="";
 for(unsigned i=0;i<sizeof(mounts)/sizeof(mounts[0]);i++){
  const size_t s=strlen(mounts[i].prefix);
  if(strncmp(path,mounts[i].prefix,s)==0){
   p=path+s;relative_root=mounts[i].relative_root;break;
  }
 }
 const size_t root_len=strlen(relative_root);
 if(!p || !*p || root_len+strlen(p)>=256u)return -1;
 /* Reject traversal, drive letters, URL-like names, empty segments and
  * backslashes. No absolute host path can be supplied by guest code. */
 if(strchr(p,'\\')||strchr(p,':')||p[0]=='/')return -1;
 for(const char *at=p;*at;){
  const char *end=strchr(at,'/');
  const size_t len=end?(size_t)(end-at):strlen(at);
  if(!len||(len==1u && at[0]=='.')||
     (len==2u&&at[0]=='.'&&at[1]=='.'))return -1;
  if(!end)break;
  at=end+1;
 }
 memcpy(relative,relative_root,root_len);
 memcpy(relative+root_len,p,strlen(p)+1u);
 return 0;
}
static void be32(uint8_t b[4],uint32_t x){
 for(unsigned i=0;i<4u;i++)b[i]=(uint8_t)(x>>(24u-8u*i));
}
static void be64(uint8_t b[8],uint64_t x){
 for(unsigned i=0;i<8u;i++)b[i]=(uint8_t)(x>>(56u-8u*i));
}
int ar_fs_guest_open(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 trace.open_calls++;
 char rel[256]={0};
 const uint64_t fdptr=c->gpr[5];
 const uint32_t flags=(uint32_t)c->gpr[4];
 uint8_t probe[4];
 if(!fdptr || (fdptr&3u) || ar_vm_read_bytes(fdptr,probe,4u)!=AR_OK ||
    guest_path(c->gpr[3],rel)!=0){
   fail(c,EINVAL_CELL);return AR_OK;
 }
 if(flags!=0u){fail(c,EACCES_CELL);return AR_OK;}
 if(!host){fail(c,ENOENT_CELL);return AR_OK;}
 uint64_t size=0;size_t actual=0;
 if(host(rel,0,0,0,&actual,&size)!=0){
   fail(c,ENOENT_CELL);return AR_OK;
 }
 unsigned i=0;
 for(;i<MAX_FD;i++)if(!fds[i].active)break;
 if(i==MAX_FD){fail(c,EINVAL_CELL);return AR_OK;}
 uint8_t result[4];be32(result,i+3u);
 if(ar_vm_load(fdptr,result,4u)!=AR_OK)return AR_MEM_FAULT;
 fds[i].active=1;fds[i].offset=0;fds[i].size=size;
 memcpy(fds[i].relative,rel,strlen(rel)+1u);
 trace.open_ok++;trace.last_fd=i+3u;trace.last_error=0;
 memcpy(trace.last_path,rel,strlen(rel)+1u);
 c->gpr[3]=0u;
 return AR_OK;
}
int ar_fs_guest_read(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 trace.read_calls++;
 const uint64_t fd=c->gpr[3],ptr=c->gpr[4],count=c->gpr[5],np=c->gpr[6];
 if(fd<3u||fd>=MAX_FD+3u||!fds[fd-3u].active){
  fail(c,EBADF_CELL);return AR_OK;
 }
 if(count>UINT32_C(16777216) || (count && (!ptr || ptr>UINT32_MAX ||
    count>UINT32_MAX-ptr+1u))){
  fail(c,EINVAL_CELL);return AR_OK;
 }
 uint8_t scratch[CHUNK];
 uint8_t sink[8]={0};
 if(np && (np>UINT32_MAX-7u ||
    ar_vm_read_bytes(np,sink,8u)!=AR_OK)){
   fail(c,EINVAL_CELL);return AR_OK;
 }
 /* Validate guest destination region ahead of opening/reading host file.
  * Cross-region guest memory is checked per chunk. */
 for(uint64_t pos=0;pos<count;){
  const size_t take=(size_t)((count-pos)>CHUNK?CHUNK:count-pos);
  if(ar_vm_read_bytes(ptr+pos,scratch,take)!=AR_OK)return AR_MEM_FAULT;
  pos+=take;
 }
 uint64_t done=0;
 ar_fs_descriptor *file=&fds[fd-3u];
 while(done<count && file->offset<file->size){
  const uint64_t left=count-done,available=file->size-file->offset;
  const size_t take=(size_t)((left<available?left:available)>CHUNK?
                            CHUNK:(left<available?left:available));
  size_t actual=0;uint64_t verified_size=0;
  if(!host || host(file->relative,file->offset,scratch,take,
                   &actual,&verified_size)!=0 || actual>take ||
     verified_size!=file->size){
    fail(c,ENOENT_CELL);return AR_OK;
  }
  if(!actual)break;
  if(ar_vm_load(ptr+done,scratch,actual)!=AR_OK)return AR_MEM_FAULT;
  file->offset+=actual;done+=actual;
 }
 if(np){be64(sink,done);if(ar_vm_load(np,sink,8u)!=AR_OK)return AR_MEM_FAULT;}
 c->gpr[3]=0u;trace.read_ok++;trace.bytes_read+=done;
 trace.last_fd=(uint32_t)fd;trace.last_error=0;
 memcpy(trace.last_path,file->relative,strlen(file->relative)+1u);
 return AR_OK;
}
int ar_fs_guest_close(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 trace.close_calls++;
 uint64_t fd=c->gpr[3];
 if(fd<3u||fd>=MAX_FD+3u||!fds[fd-3u].active){
   fail(c,EBADF_CELL);return AR_OK;
 }
 memset(&fds[fd-3u],0,sizeof(fds[0]));
 c->gpr[3]=0u;trace.last_error=0;return AR_OK;
}
int ar_fs_bind_syscalls(void){
 if(ar_bind_syscall(801u,ar_fs_guest_open)!=AR_OK)return AR_BAD_ARGS;
 if(ar_bind_syscall(802u,ar_fs_guest_read)!=AR_OK)return AR_BAD_ARGS;
 if(ar_bind_syscall(804u,ar_fs_guest_close)!=AR_OK)return AR_BAD_ARGS;
 return AR_OK;
}
