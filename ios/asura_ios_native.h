#pragma once
#include <functional>
#include <string>
std::string AsuraIOSDocumentsPath();
void AsuraIOSLog(const std::string& message);
void AsuraIOSShowLauncher(std::string detected, std::function<std::string()> rescan,
                          std::function<void(std::string)> start);
std::string AsuraIOSWaitForGameSelection(std::string detected,
                                         std::function<std::string()> rescan);

void AsuraIOSDismissLauncher();
void AsuraIOSSetLauncherStatus(const std::string& message);
