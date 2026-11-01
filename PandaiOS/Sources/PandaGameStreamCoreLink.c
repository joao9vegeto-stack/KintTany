#include "PandaGameStreamCoreLink.h"
#include <Limelight.h>

static __typeof__(&LiStartConnection) volatile pandaStartConnection = &LiStartConnection;
static __typeof__(&LiSendControllerEvent) volatile pandaSendControllerEvent = &LiSendControllerEvent;

bool PandaGameStreamCoreIsAvailable(void) {
    return pandaStartConnection != NULL && pandaSendControllerEvent != NULL;
}
