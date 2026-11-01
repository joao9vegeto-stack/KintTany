import Foundation

/// Small Swift-facing probe for the upstream GameStream core.
/// The actual stream lifecycle is connected only after Panda's session broker
/// supplies a host, port, certificate, app identifier, and session key.
enum MoonlightCore {
    static var launchQueryParameters: String {
        guard let value = LiGetLaunchUrlQueryParameters() else {
            return ""
        }
        return String(cString: value)
    }

    static var isLinked: Bool {
        !launchQueryParameters.isEmpty
    }
}
