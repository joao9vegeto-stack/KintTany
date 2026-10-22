#!/usr/bin/env python3
"""PoPTST Build17: apply missing original retail mobile disk/file compatibility.
The pinned rePOP Android retail backend generates emulated Partition0..5
and handles title-specific free-space probes; the iOS host must share the
same POSIX behavior. Exact anchors only, never fake successful guest calls.
"""
import sys
from pathlib import Path

MOBILE_RETAIL = "(defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IPHONE)) && RESOT_RUNTIME_RETAIL"
MOBILE = "defined(__ANDROID__) || (defined(__APPLE__) && TARGET_OS_IPHONE)"

def replace(s, old, new, name, count=1):
    n = s.count(old)
    if n != count:
        raise RuntimeError(f"{name}: expected {count} anchor(s), saw {n}")
    return s.replace(old, new)

def main(root):
    kpath=root/'port/third_party/xboxrecomp/src/kernel/kernel_path.c'
    s=kpath.read_text()
    s=replace(s, '#include <ctype.h>', '#include <ctype.h>\n#if defined(__APPLE__)\n#include <TargetConditionals.h>\n#endif', 'platform guard')
    s=replace(s, '#if defined(__ANDROID__) && RESOT_RUNTIME_RETAIL',
              '#if '+MOBILE_RETAIL, 'Retail storage rules, partitions, raw devices, path trace', 5)
    s=replace(s, '#if defined(__ANDROID__)\n#include <dirent.h>',
              '#if '+MOBILE+'\n#include <dirent.h>', 'case-sensitive POSIX input')
    s=replace(s, '#if defined(__ANDROID__)\n        resolve_case',
              '#if '+MOBILE+'\n        resolve_case', 'case-insensitive retail filename resolution')
    # Only iOS adds a persisted result. Android keeps existing logger.
    src='''        fprintf(stderr, "  [DISK] Partition%d backing %s\\n", p, ok ? "ready" : "FAILED");'''
    dst=src+'''
#if defined(__APPLE__) && TARGET_OS_IPHONE
        {
            extern void poptst_engine_trace(const char *);
            char stage[140];
            snprintf(stage, sizeof stage, "XBOX DISK Partition%d backing %s", p,
                     ok ? "ready" : "FAILED");
            poptst_engine_trace(stage);
        }
#endif'''
    s=replace(s,src,dst,'persist partition provisioning result')
    # Xbox retail's Partition1/CACHE is writable E:-side data, not a
    # directory in the installed DVD game tree. rePOP's generic Partition1
    # rule is required by other targets (e.g. Wreckless's Z: assets), so
    # add a more specific iOS retail rule first, preserving the fallback.
    partition1 = r'    { "\\Device\\Harddisk0\\Partition1\\",    0, NULL,         NULL          },'
    cache_rule = r'    { "\\Device\\Harddisk0\\Partition1\\CACHE\\", 1, NULL, "/Cache" },'
    s=replace(s,partition1,cache_rule+"\n"+partition1,
              'B20 Xbox writable Partition1 CACHE before generic title files')
    kpath.write_text(s)

    kfile=root/'port/third_party/xboxrecomp/src/kernel/kernel_file.c'
    s=kfile.read_text()
    s=replace(s,'#include "kernel.h"','#include "kernel.h"\n#if defined(__APPLE__)\n#include <TargetConditionals.h>\n#endif','include Apple target guards')
    s=replace(s,'#if defined(__ANDROID__) && RESOT_RUNTIME_RETAIL',
              '#if '+MOBILE_RETAIL,'retail open/save/Partition1 POSIX parity',10)
    s=replace(s,'#if defined(__ANDROID__)\n        /* RE-SoT: release-build diagnostics',
              '#if '+MOBILE+'\n        /* RE-SoT: release-build diagnostics',
              'enable bounded open failure diagnostics on iPhone')
    anchor='''    if (fd < 0) {
        int e = errno;
        g_xbox_last_file_error = errno_to_win32(e);'''
    repl='''    if (fd < 0) {
        int e = errno;
#if defined(__APPLE__) && TARGET_OS_IPHONE
        /* Sparse one-time boot data: trace only early open failures, plus
           any failure except the expected missing-file probes. */
        static unsigned boot_failed_opens;
        unsigned nth = __atomic_add_fetch(&boot_failed_opens, 1, __ATOMIC_RELAXED);
        if (nth <= 24 || (e != ENOENT && e != ENOTDIR)) {
            char stage[660];
            extern void poptst_engine_trace(const char *);
            snprintf(stage, sizeof stage,
                     "XBOX OPEN FAIL errno=%d disp=%u options=0x%X access=0x%X root=%p guest=%.*s host=%.*s",
                     e, (unsigned)CreateDisposition, (unsigned)CreateOptions,
                     (unsigned)DesiredAccess,
                     (void *)ObjectAttributes->RootDirectory,
                     140, xbox_path ? xbox_path : "(null)", 210, host_path);
            poptst_engine_trace(stage);
        }
#endif
        g_xbox_last_file_error = errno_to_win32(e);'''
    s=replace(s,anchor,repl,'bounded native NtCreateFile errors')
    # B28: Xbox title save files live below UDATA/TDATA (sometimes nested
    # inside the profile's title ID). Original POSIX NtCreateFile only mkdir'd
    # the LAST directory and open(O_CREAT) did not make parent directories.
    # Restrict recursive parent creation to writable Xbox save paths, and to
    # *creation* dispositions; do not mask missing source files on reads.
    s=replace(s, 'static int posix_object_path(PXBOX_OBJECT_ATTRIBUTES oa, char *out, size_t size)',
        '''#if defined(__APPLE__) && TARGET_OS_IPHONE
static int poptst_save_root(const char *host) {
    if (!host) return 0;
    size_t n=strlen(host);
    return strstr(host,"/UDATA/") || strstr(host,"/TDATA/") ||
       (n>=6 && !strcmp(host+n-6,"/UDATA")) ||
       (n>=6 && !strcmp(host+n-6,"/TDATA"));
}
/* The iOS sandbox already owns the prefix. Restrict recursive creation to
 * the translated guest's *save tree*, never to an arbitrary disc path. */
static void poptst_save_parents(char *host) {
    if (!poptst_save_root(host)) return;
    const char *start=strstr(host,"/UDATA/");
    if (!start) start=strstr(host,"/TDATA/");
    if (!start) return;
    char *p=(char *)start+7;
    for (;*p;p++) {
        if (*p!='/') continue;
        char prior=*p; *p=0;
        if (mkdir(host,0755)!=0 && errno!=EEXIST) {
            char msg[270]; extern void poptst_engine_trace(const char *);
            snprintf(msg,sizeof msg,"SAVE B28 PARENT FAIL errno=%d path=%.170s",errno,host);
            poptst_engine_trace(msg);
        }
        *p=prior;
    }
}
#endif
static int posix_object_path(PXBOX_OBJECT_ATTRIBUTES oa, char *out, size_t size)''',
       'B28 POSIX nested UDATA/TDATA parent helper')
    s=replace(s, '    int fd;\n    if (CreateOptions & XBOX_FILE_DIRECTORY_FILE) {',
        '''    int fd;
#if defined(__APPLE__) && TARGET_OS_IPHONE
    int create_save=CreateDisposition==XBOX_FILE_CREATE ||
        CreateDisposition==XBOX_FILE_OPEN_IF ||
        CreateDisposition==XBOX_FILE_SUPERSEDE ||
        CreateDisposition==XBOX_FILE_OVERWRITE_IF;
    if(create_save && poptst_save_root(host_path))
        poptst_save_parents(host_path);
#endif
    if (CreateOptions & XBOX_FILE_DIRECTORY_FILE) {''',
        'B28 create save parents before guest mkdir or open')
    s=replace(s,'    *FileHandle = w32_open_handle(fd, host_path);',
       '''#if defined(__APPLE__) && TARGET_OS_IPHONE
    if(poptst_save_root(host_path)) {
        static unsigned save_opens;
        if(__atomic_fetch_add(&save_opens,1,__ATOMIC_RELAXED)<72) {
            extern void poptst_engine_trace(const char *);
            char msg[390];
            snprintf(msg,sizeof msg,
                "SAVE B28 OPEN SUCCESS disp=%u opt=0x%X fd=%d host=%.235s",
                (unsigned)CreateDisposition,(unsigned)CreateOptions,fd,host_path);
            poptst_engine_trace(msg);
        }
    }
#endif
    *FileHandle = w32_open_handle(fd, host_path);''',
        'B28 persist successful guest save opens')
    s=replace(s, '    if (n < 0) {\n        XBOX_TRACE(XBOX_LOG_FILE, "NtWriteFile(handle=%p) errno=%d", FileHandle, errno);',
       '''#if defined(__APPLE__) && TARGET_OS_IPHONE
    {
        const char *save_name=w32_handle_path(FileHandle);
        if(poptst_save_root(save_name)) {
            static unsigned save_writes;
            if(__atomic_fetch_add(&save_writes,1,__ATOMIC_RELAXED)<72) {
                extern void poptst_engine_trace(const char *);
                char msg[410];
                snprintf(msg,sizeof msg,"SAVE B28 WRITE want=%u wrote=%lld err=%d host=%.235s",
                    (unsigned)Length,(long long)n,n<0?errno:0,save_name);
                poptst_engine_trace(msg);
            }
        }
    }
#endif
    if (n < 0) {
        XBOX_TRACE(XBOX_LOG_FILE, "NtWriteFile(handle=%p) errno=%d", FileHandle, errno);''',
      'B28 guest actual save writes, including errors')
    # Persist file enumeration outcomes as well; game's Load menu may fail
    # even with real saves if directory iteration/metadata is incorrect.
    # Windows and POSIX both contain this branch; patch POSIX ONLY.
    query_pos=s.index('#else /* !_WIN32 */')
    posix=s[query_pos:]
    posix=replace(posix,'    if (FileInformationClass != XboxFileDirectoryInformation) {',
       '''#if defined(__APPLE__) && TARGET_OS_IPHONE
    {
        const char *folder=w32_handle_path(FileHandle);
        if(poptst_save_root(folder)) {
            static unsigned save_queries;
            if(__atomic_fetch_add(&save_queries,1,__ATOMIC_RELAXED)<64) {
                extern void poptst_engine_trace(const char *);
                char msg[320];
                int pattern_len=FileName && FileName->Buffer ? (FileName->Length<70 ? FileName->Length : 70) : 5;
                snprintf(msg,sizeof msg,"SAVE B28 LIST folder=%.180s pattern=%.*s",
                    folder,pattern_len,FileName && FileName->Buffer ? FileName->Buffer : "(all)");
                poptst_engine_trace(msg);
            }
        }
    }
#endif
    if (FileInformationClass != XboxFileDirectoryInformation) {''',
        'B28 observable guest Load menu enumeration')
    s=s[:query_pos]+posix
    kfile.write_text(s)

    # kernel_file.c and kernel_bridge.c reference xbox_dir_context_drop
    # through kernel.h. Its header declaration is separately Android-gated;
    # without enabling it iPhoneOS C99 rejects the real function call.
    hpath=root/'port/third_party/xboxrecomp/src/kernel/kernel.h'
    s=hpath.read_text()
    s=replace(s, '#include <stdbool.h>',
              '#include <stdbool.h>\n#if defined(__APPLE__)\n#include <TargetConditionals.h>\n#endif',
              'kernel declarations Apple target header')
    s=replace(s,
              '#if defined(_WIN32) || (defined(__ANDROID__) && RESOT_RUNTIME_RETAIL)',
              '#if defined(_WIN32) || ('+MOBILE_RETAIL+')',
              'xbox_dir_context_drop declaration on iOS')
    hpath.write_text(s)

    bridge=root/'port/third_party/xboxrecomp/src/kernel/kernel_bridge.c'
    s=bridge.read_text()  # Run AFTER patch_guest_exit_ios.py
    s=replace(s, '#include "kernel.h"',
              '#include "kernel.h"\n#if defined(__APPLE__)\n#include <TargetConditionals.h>\n#endif',
              'bridge Apple target detection')
    s=replace(s, '#if defined(_WIN32) || (defined(__ANDROID__) && RESOT_RUNTIME_RETAIL)',
              '#if defined(_WIN32) || ('+MOBILE_RETAIL+')',
              'release POSIX directory context on guest NtClose')
    anchor='''        poptst_engine_trace(stage);
    }
    /* Routine 2 is a quick reboot'''
    if anchor not in s:
        # The B16 instrumentation is immediately followed by the original
        # blank line before the "Routine 2" comment.
        anchor='''        poptst_engine_trace(stage);
    }

    /* Routine 2 is a quick reboot'''
    repl='''        poptst_engine_trace(stage);
    }
#if defined(__APPLE__) && TARGET_OS_IPHONE
    {
        /* A quick reboot is often an Xbox title initialization failure,
           not a host crash. Snapshot the *guest* launch page + return stack,
           without changing registers or guest control flow. */
        extern void poptst_engine_trace(const char *);
        uint32_t launch_page=BRIDGE_MEM32(XBOX_KERNEL_DATA_BASE + KDATA_LAUNCH_DATA_PAGE);
        uint32_t w[6]={0};
        if (g_esp >= 0x00010000u && g_esp <= 0x03FFFFE8u)
            for (unsigned i=0;i<6;i++) w[i]=BRIDGE_MEM32(g_esp + i*4);
        char snapshot[320];
        snprintf(snapshot,sizeof snapshot,
                 "XBOX BOOT EXIT: routine=%u launch_page=%08X esp=%08X stack=%08X,%08X,%08X,%08X,%08X,%08X",
                 routine,launch_page,g_esp,w[0],w[1],w[2],w[3],w[4],w[5]);
        poptst_engine_trace(snapshot);
        if (launch_page >= 0x00010000u && launch_page <= 0x03FFFFF0u) {
            snprintf(snapshot,sizeof snapshot,
                     "XBOX LAUNCH DATA: type=%08X titleid=%08X",
                     BRIDGE_MEM32(launch_page),BRIDGE_MEM32(launch_page+4));
            poptst_engine_trace(snapshot);
        }
    }
#endif

    /* Routine 2 is a quick reboot'''
    s=replace(s,anchor,repl,'persist firmware launch page and guest exit stack')
    bridge.write_text(s)
    print('PASS B17: Android retail disk partitions/case/saves/Partition1 now available to iOS')

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('usage: patch_retail_disk_ios.py <pinned rePOP checkout>')
    main(Path(sys.argv[1]).resolve())
