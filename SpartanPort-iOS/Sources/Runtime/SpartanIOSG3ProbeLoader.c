#include "SpartanIOSG3ProbeLoader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#define HEADER_SIZE 56u
#define MODULE_SIZE 56u
#define BINDING_SIZE 24u
#define SEGMENT_SIZE 24u
#define NAME_SIZE 128u
#define RELOCATION_SIZE 32u
#define MAX_RECORDS 1000000u
typedef struct { uint64_t offset,value; uint32_t kind; } Binding;
struct SpartanG3ProbeImage { SpartanGuestMemory *memory; uint64_t entry; SpartanG3ProbeInfo info; SpartanG3ProbeModule *modules; SpartanG3ProbeSegment *segments; };
static uint64_t u64(const uint8_t*p){uint64_t v=0;for(unsigned i=0;i<8;i++)v|=(uint64_t)p[i]<<(i*8);return v;}
static void w64(uint8_t*p,uint64_t v){for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(v>>(i*8));}
static int range(uint64_t at,uint64_t n,uint64_t limit){return at<=limit&&n<=limit-at;}
static int advance(uint64_t*at,uint64_t count,uint64_t stride,uint64_t limit){if(count>MAX_RECORDS||(stride&&count>(UINT64_MAX-*at)/stride))return 0;uint64_t n=count*stride;if(!range(*at,n,limit))return 0;*at+=n;return 1;}
static void seterr(char*out,size_t cap,const char*s){if(out&&cap)snprintf(out,cap,"%s",s);}
SpartanG3ProbeImage *spartan_g3probe_load(const void*input,size_t length,char*error,size_t error_capacity){
 const uint8_t*b=input;uint64_t size,entry,ns,nr,ni,flags,modules,bindings_count,pos;Binding*bindings=NULL;SpartanG3ProbeImage*result=NULL;uint8_t*image=NULL;int entry_executable=0;
 seterr(error,error_capacity,"invalid G3PROBE5 image");
 if(!b||length<HEADER_SIZE){seterr(error,error_capacity,"truncated G3PROBE5 header");return NULL;}
 if(memcmp(b,"G3PROBE5",8)){seterr(error,error_capacity,"expected G3PROBE5 linked image");return NULL;}
 size=u64(b+8);entry=u64(b+16);ns=u64(b+24);nr=u64(b+32);ni=u64(b+40);flags=u64(b+48);
 if(!size||size>SIZE_MAX||!ns||ns>MAX_RECORDS||nr>MAX_RECORDS||ni>MAX_RECORDS){seterr(error,error_capacity,"invalid G3PROBE5 image or record counts");return NULL;}
 pos=HEADER_SIZE;if(!range(pos,48,length)){seterr(error,error_capacity,"truncated G3PROBE5 process/TLS metadata");return NULL;}
 const uint64_t procparam=u64(b+pos);pos+=8;
 const uint64_t main_tls_address=u64(b+pos),main_tls_filesz=u64(b+pos+8),main_tls_memsz=u64(b+pos+16),main_tls_align=u64(b+pos+24);pos+=32;
 modules=u64(b+pos);pos+=8;
 if(!advance(&pos,modules,MODULE_SIZE,length)){seterr(error,error_capacity,"invalid module table");return NULL;}
 const uint64_t modules_at=pos-8;
 pos=modules_at;
 if(!range(pos,8,length)){seterr(error,error_capacity,"missing binding count");return NULL;}
 bindings_count=u64(b+pos);pos+=8;
 if(bindings_count>ni||!advance(&pos,bindings_count,BINDING_SIZE,length)){seterr(error,error_capacity,"invalid binding table");return NULL;}
 const uint64_t bindings_at=pos-bindings_count*BINDING_SIZE,segments_at=pos;
 if(!advance(&pos,ns,SEGMENT_SIZE,length)){seterr(error,error_capacity,"invalid segment table");return NULL;}
 const uint64_t names_at=pos;
 if(!advance(&pos,ni,NAME_SIZE,length)){seterr(error,error_capacity,"invalid import-name table");return NULL;}
 const uint64_t relocs_at=pos;
 if(!advance(&pos,nr,RELOCATION_SIZE,length)||!range(pos,size,length)||pos+size!=length){seterr(error,error_capacity,"invalid relocation table or image payload size");return NULL;}
 if(main_tls_filesz>main_tls_memsz||(main_tls_memsz&&!range(main_tls_address,main_tls_filesz,size))||(main_tls_align&&(main_tls_align&(main_tls_align-1)))){seterr(error,error_capacity,"invalid main executable TLS metadata");return NULL;}
 if(procparam>=size){seterr(error,error_capacity,"process parameter address is outside linked image");return NULL;}
 result=calloc(1,sizeof(*result));bindings=calloc((size_t)(ni?ni:1),sizeof(*bindings));
 if(result){result->modules=calloc((size_t)(modules?modules:1),sizeof(*result->modules));result->segments=calloc((size_t)ns,sizeof(*result->segments));}
 if(!result||!bindings||!result->modules||!result->segments){seterr(error,error_capacity,"out of memory parsing G3PROBE5");goto fail;}
 for(uint64_t i=0;i<ni;i++)bindings[i].offset=UINT64_MAX;
 for(uint64_t i=0;i<bindings_count;i++){const uint8_t*p=b+bindings_at+i*BINDING_SIZE;uint64_t index=u64(p),value=u64(p+8),kind=u64(p+16);if(index>=ni||(kind!=1&&kind!=2)||bindings[index].offset!=UINT64_MAX||value>=size){seterr(error,error_capacity,"invalid or duplicate import binding");goto fail;}bindings[index]=(Binding){index,value,(uint32_t)kind};}
 for(uint64_t i=0;i<ni;i++)if(!memchr(b+names_at+i*NAME_SIZE,0,NAME_SIZE)){seterr(error,error_capacity,"unterminated import name");goto fail;}
 for(uint64_t i=0;i<modules;i++){const uint8_t*p=b+modules_at+i*MODULE_SIZE;SpartanG3ProbeModule m={u64(p),u64(p+8),u64(p+16),u64(p+24),u64(p+32),u64(p+40),u64(p+48)};if(!m.size||!range(m.base,m.size,size)||m.tls_file_size>m.tls_memory_size||(m.tls_module_id&&m.tls_memory_size&&!range(m.tls_address,m.tls_memory_size,size))||(m.init&&!range(m.init,1,size))){seterr(error,error_capacity,"invalid linked PRX module or TLS metadata");goto fail;}result->modules[i]=m;}
 for(uint64_t i=0;i<ns;i++){const uint8_t*p=b+segments_at+i*SEGMENT_SIZE;SpartanG3ProbeSegment seg={u64(p),u64(p+8),u64(p+16)};if(!seg.size||!range(seg.offset,seg.size,size)){seterr(error,error_capacity,"segment exceeds linked image");goto fail;}if((seg.flags&1)&&entry>=seg.offset&&entry-seg.offset<seg.size)entry_executable=1;result->segments[i]=seg;}
 if(!entry_executable){seterr(error,error_capacity,"entry point is not inside an executable segment");goto fail;}
 result->memory=spartan_guest_memory_create(size);
 if(!result->memory||spartan_guest_memory_protect(result->memory,0,size,PROT_READ|PROT_WRITE)){seterr(error,error_capacity,"unable to allocate writable linked-image arena");goto fail;}
 image=spartan_guest_memory_host_pointer(result->memory,0,size);if(!image){seterr(error,error_capacity,"linked-image arena is not addressable");goto fail;}memcpy(image,b+pos,(size_t)size);
 const uint64_t host_base=(uint64_t)(uintptr_t)image;
 for(uint64_t i=0;i<nr;i++){const uint8_t*p=b+relocs_at+i*RELOCATION_SIZE;const uint64_t target=u64(p),kind=u64(p+8),symbol=u64(p+16);const int64_t addend=(int64_t)u64(p+24);if(!range(target,8,size)){seterr(error,error_capacity,"relocation target is out of range");goto fail;}uint64_t value=0;
  if(kind==0){if(symbol>=size||addend!=0){seterr(error,error_capacity,"invalid image-relative relocation");goto fail;}value=host_base+symbol;}
  else if(kind==1||kind==2){if(symbol>=ni){seterr(error,error_capacity,"import relocation index is out of range");goto fail;}Binding binding=bindings[symbol];if(binding.offset==UINT64_MAX){result->info.unresolved_import_count++;w64(image+target,0);continue;}if(binding.kind!=kind||addend<0||binding.value>=size||(uint64_t)addend>size-binding.value){seterr(error,error_capacity,"import binding type or addend is invalid");goto fail;}value=host_base+binding.value+(uint64_t)addend;}
  else{seterr(error,error_capacity,"unsupported G3PROBE5 relocation kind");goto fail;}w64(image+target,value);result->info.applied_relocation_count++;}
 result->entry=host_base+entry;result->info.image_size=size;result->info.entry_offset=entry;result->info.procparam_offset=procparam;result->info.flags=flags;result->info.import_count=ni;result->info.binding_count=bindings_count;result->info.module_count=modules;result->info.segment_count=ns;result->info.relocation_count=nr;result->info.image_base=host_base;result->info.main_tls_address=main_tls_address;result->info.main_tls_file_size=main_tls_filesz;result->info.main_tls_memory_size=main_tls_memsz;result->info.main_tls_alignment=main_tls_align;free(bindings);seterr(error,error_capacity,"");return result;
fail:free(bindings);if(result){spartan_guest_memory_destroy(result->memory);free(result->modules);free(result->segments);free(result);}return NULL;
}
void spartan_g3probe_destroy(SpartanG3ProbeImage*image){if(!image)return;spartan_guest_memory_destroy(image->memory);free(image->modules);free(image->segments);free(image);}
SpartanGuestMemory*spartan_g3probe_memory(SpartanG3ProbeImage*image){return image?image->memory:NULL;}
uint64_t spartan_g3probe_entry(const SpartanG3ProbeImage*image){return image?image->entry:0;}
int spartan_g3probe_info(const SpartanG3ProbeImage*image,SpartanG3ProbeInfo*info){if(!image||!info)return 0;*info=image->info;return 1;}
int spartan_g3probe_module(const SpartanG3ProbeImage*image,uint64_t index,SpartanG3ProbeModule*module){if(!image||!module||index>=image->info.module_count)return 0;*module=image->modules[index];return 1;}
int spartan_g3probe_segment(const SpartanG3ProbeImage*image,uint64_t index,SpartanG3ProbeSegment*segment){if(!image||!segment||index>=image->info.segment_count)return 0;*segment=image->segments[index];return 1;}
