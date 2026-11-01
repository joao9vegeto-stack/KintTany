#pragma once
#include <stdbool.h>

/// Forces the actual GameStream connection and controller-input entry points
/// to be resolved from the linked Moonlight Common C archive.
bool PandaGameStreamCoreIsAvailable(void);
