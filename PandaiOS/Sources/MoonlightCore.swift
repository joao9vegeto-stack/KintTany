import Foundation

/// Link-time probe for the upstream GameStream client.
/// Session creation remains behind the Panda provider adapter.
enum MoonlightCore {
    static var launchQueryParameters: String {
        guard let value = LiGetLaunchUrlQueryParameters() else {
            return ""
        }
        return String(cString: value)
    }

    static var isLinked: Bool {
        PandaGameStreamCoreIsAvailable() && !launchQueryParameters.isEmpty
    }
}
