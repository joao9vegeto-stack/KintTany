import Foundation

/// Provider-neutral values must come from a real Panda allocation response.
struct PandaSessionDescriptor: Codable, Equatable {
    let host: String
    let httpsPort: UInt16
    let serverCertificate: Data
    let appID: String
    let appName: String
    let appVersion: String
    let gfeVersion: String
    let rtspSessionURL: String
    let width: Int
    let height: Int
    let frameRate: Int
    let bitRateKbps: Int

    enum CodingKeys: String, CodingKey {
        case host
        case httpsPort = "https_port"
        case serverCertificate = "server_certificate"
        case appID = "app_id"
        case appName = "app_name"
        case appVersion = "app_version"
        case gfeVersion = "gfe_version"
        case rtspSessionURL = "rtsp_session_url"
        case width, height
        case frameRate = "frame_rate"
        case bitRateKbps = "bit_rate_kbps"
    }

    func validate() throws {
        let value = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty, !value.contains("://"), !value.contains("/"), !value.contains(" ") else {
            throw ValidationError.invalidHost
        }
        guard httpsPort > 0, !serverCertificate.isEmpty, !appID.isEmpty,
              !appName.isEmpty, !appVersion.isEmpty, !gfeVersion.isEmpty,
              rtspSessionURL.lowercased().hasPrefix("rtsp://"),
              (320...7680).contains(width), (240...4320).contains(height),
              (15...240).contains(frameRate), (100...200_000).contains(bitRateKbps) else {
            throw ValidationError.invalidParameters
        }
    }

    enum ValidationError: LocalizedError {
        case invalidHost, invalidParameters
        var errorDescription: String? {
            switch self {
            case .invalidHost: return "O host deve ser um endereço ou nome DNS, sem protocolo ou caminho."
            case .invalidParameters: return "A sessão está incompleta ou contém parâmetros inválidos."
            }
        }
    }
}
