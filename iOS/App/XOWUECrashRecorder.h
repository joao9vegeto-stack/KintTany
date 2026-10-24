#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void XOWUECrashRecorderInstall(const char *crashFilePath);
// Fail-closed guest AOT dispatch exception, not an operating-system signal.
void XOWUECrashRecorderWriteFatal(const char *event);
#ifdef __cplusplus
}
#endif
