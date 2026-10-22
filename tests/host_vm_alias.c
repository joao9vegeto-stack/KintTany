/* Build14: Host virtual address model smoke: 4GiB lazy guest reservation,
 * private file-backed RAM and real alias, fixed mappings only in reserved space.
 * Synthetic data only; does not prove iPhone VM policy, AOT, or game frames. */
#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
int main(void) {
    const size_t span=UINT64_C(0x100000000), ram=64u*1024u*1024u;
    unsigned char *base=mmap(NULL,span,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(base==MAP_FAILED){perror("mmap 4GiB PROT_NONE");return 1;}
    char name[]="/tmp/poptst-vm-test-XXXXXX";
    int fd=mkstemp(name);if(fd<0){perror("mkstemp");return 2;}
    unlink(name);
    if(ftruncate(fd,(off_t)ram)){perror("ftruncate 64MiB");return 3;}
    void *a=mmap(base,ram,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0);
    void *b=mmap(base+ram,ram,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,fd,0);
    if(a!=base||b!=base+ram){perror("RAM views");return 4;}
    volatile uint32_t *a1=(volatile uint32_t *)(base+0x2000);
    volatile uint32_t *b1=(volatile uint32_t *)(base+ram+0x2000);
    *a1=0xC0FFEE12u;
    if(*b1!=0xC0FFEE12u){fprintf(stderr,"RAM mirror alias mismatch\n");return 5;}
    if(munmap(base,span)){perror("munmap");return 6;}
    close(fd);
    puts("PASS: 4GiB PROT_NONE reservation + private RAM fd + real fixed alias");
    return 0;
}
