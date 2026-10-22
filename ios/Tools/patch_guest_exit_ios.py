#!/usr/bin/env python3
"""PoPTST B16: do not let Xbox ExitProcess terminate LiveContainer host."""
from pathlib import Path
import sys

def one(s,old,new,label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected 1 anchor, found {n}')
    return s.replace(old,new,1)

def main(root):
    path=root/'port/third_party/xboxrecomp/src/platform/win32_compat.c'
    s=path.read_text()
    s=one(s,'''VOID ExitProcess(UINT exitCode)
{
#if defined(__ANDROID__)''','''VOID ExitProcess(UINT exitCode)
{
#if defined(__APPLE__) && TARGET_OS_IPHONE
    /* Recompiled Xbox guest may request firmware exit. Keep the real
       SwiftUI host/LiveContainer process alive and stop this guest thread.
       Guest background GPU resources are retained until app teardown. */
    extern void poptst_engine_guest_request_exit(unsigned, uintptr_t);
    poptst_engine_guest_request_exit((unsigned)exitCode,
                                     (uintptr_t)__builtin_return_address(0));
    pthread_exit(NULL);
#elif defined(__ANDROID__)''','iOS Xbox ExitProcess')
    s=one(s,'''BOOL TerminateProcess(HANDLE process, UINT exitCode)
{
    (void)process;
    exit((int)exitCode);
}''','''BOOL TerminateProcess(HANDLE process, UINT exitCode)
{
    (void)process;
#if defined(__APPLE__) && TARGET_OS_IPHONE
    ExitProcess(exitCode);
    return TRUE;
#else
    exit((int)exitCode);
#endif
}''','iOS Xbox TerminateProcess')
    path.write_text(s)
    path=root/'port/third_party/xboxrecomp/src/kernel/kernel_bridge.c'
    s=path.read_text()
    s=one(s,'''static void bridge_HalReturnToFirmware(void)
{
    uint32_t routine = STACK_ARG(0);''','''static void bridge_HalReturnToFirmware(void)
{
    uint32_t routine = STACK_ARG(0);
    {
        extern void poptst_engine_trace(const char *);
        char stage[112];
        snprintf(stage,sizeof stage,"XBOX HalReturnToFirmware routine=%u ESP=0x%08X",
                 routine,g_esp);
        poptst_engine_trace(stage);
    }''','Xbox firmware bridge')
    path.write_text(s)
    path=root/'port/third_party/xboxrecomp/src/kernel/kernel_hal.c'
    s=path.read_text()
    s=one(s,'''VOID __stdcall xbox_HalReturnToFirmware(ULONG Routine)
{''','''VOID __stdcall xbox_HalReturnToFirmware(ULONG Routine)
{
    extern void poptst_engine_trace(const char *);
    char stage[100];
    snprintf(stage,sizeof stage,"XBOX HAL firmware exit requested, routine=%u",
             (unsigned)Routine);
    poptst_engine_trace(stage);''','Xbox HAL firmware')
    path.write_text(s)
    print('PASS B16: Xbox exit traced, host retained; other platforms unchanged')

if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: patch_guest_exit_ios.py <rePOP>')
    main(Path(sys.argv[1]).resolve())
