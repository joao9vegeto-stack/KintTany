/* Safe resolver for the exact Fairy Tail 2 FPSLocker two-level chain.
 * rd has the same signature as hle_fpslock.c's Mach vm_read_overwrite wrapper.
 * Never return an address for a half-constructed object or unexpected value.
 */
static int f2_fps_resolve(int (*read_mem)(uint64_t,void *,size_t),
                         uint64_t global, uint32_t indirect, uint32_t field,
                         uint64_t *address, uint32_t *value) {
    uint64_t a=0,b=0;
    uint32_t v=0;
    if (!read_mem(global,&a,sizeof a) || a<0x1000 || (a&7) ||
        a>UINT64_MAX-indirect || !read_mem(a+indirect,&b,sizeof b) ||
        b<0x1000 || (b&7) || b>UINT64_MAX-field ||
        ((b+field)&3) || !read_mem(b+field,&v,sizeof v) ||
        (v!=30 && v!=60)) return 0;
    *address=b+field; *value=v;
    return 1;
}
