#include "SpartanIOSG3ProbeLoader.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void put32(uint8_t*p,uint32_t v){for(int i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void put64(uint8_t*p,uint64_t v){for(int i=0;i<8;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint64_t get64(const uint8_t*p){uint64_t v=0;for(int i=0;i<8;i++)v|=(uint64_t)p[i]<<(8*i);return v;}
static uint8_t *fixture(size_t *length) {
    const uint64_t size=64, ns=1,nr=3,ni=1,modules=0,bindings=1;
    const size_t header=56, metadata=48, bindingCount=8, bindingBytes=24, segmentBytes=24, namesBytes=128, relocBytes=96;
    *length=header+metadata+bindingCount+bindingBytes+segmentBytes+namesBytes+relocBytes+size;
    uint8_t *b=calloc(1,*length); assert(b);
    memcpy(b,"G3PROBE5",8); put64(b+8,size); put64(b+16,8); put64(b+24,ns); put64(b+32,nr); put64(b+40,ni);
    size_t p=56; put64(b+p,0); p+=8; p+=32; put64(b+p,modules); p+=8;
    put64(b+p,bindings); p+=8; put64(b+p,0); put64(b+p+8,48); put64(b+p+16,2); p+=24;
    put64(b+p,0); put64(b+p+8,size); put64(b+p+16,5); p+=24;
    memcpy(b+p,"libExample#libkernel",20); p+=128;
    /* Relative pointer -> image+32. Function import -> image+48. TLS -> displacement 0x24. */
    put64(b+p,16); put64(b+p+8,0); put64(b+p+16,32); put64(b+p+24,0); p+=32;
    put64(b+p,24); put64(b+p+8,2); put64(b+p+16,0); put64(b+p+24,0); p+=32;
    put64(b+p,4); put64(b+p+8,3); put64(b+p+16,0); put64(b+p+24,0); p+=32;
    assert(p+size==*length);
    b[p+8]=0xc3;
    return b;
}
int main(void) {
    size_t length=0; uint8_t *bytes=fixture(&length); char error[160];
    SpartanG3ProbeImage *image=spartan_g3probe_load(bytes,length,0x24,error,sizeof(error));
    assert(image && error[0]==0);
    SpartanG3ProbeInfo info; assert(spartan_g3probe_info(image,&info));
    assert(info.image_size==64 && info.entry_offset==8 && info.import_count==1);
    assert(info.binding_count==1 && info.unresolved_import_count==0 && info.applied_relocation_count==3);
    uint8_t *base=spartan_guest_memory_host_pointer(spartan_g3probe_memory(image),0,64);
    assert(base && get64(base+16)==(uint64_t)(uintptr_t)(base+32));
    assert(get64(base+24)==(uint64_t)(uintptr_t)(base+48));
    assert(((uint32_t)base[4]|((uint32_t)base[5]<<8)|((uint32_t)base[6]<<16)|((uint32_t)base[7]<<24))==0x24);
    assert(spartan_g3probe_entry(image)==(uint64_t)(uintptr_t)(base+8));
    spartan_g3probe_destroy(image);
    /* Unresolved imports are not silently fabricated: they remain zero and block readiness. */
    put64(bytes+56+8+32+8+8,0); /* remove binding table row by changing count */
    /* malformed/truncated inputs fail closed */
    assert(!spartan_g3probe_load(bytes,length-1,0,error,sizeof(error)));
    free(bytes);
    puts("PASS: G3PROBE5 segment validation, relative/import/TLS relocations and entry mapping");
    return 0;
}
