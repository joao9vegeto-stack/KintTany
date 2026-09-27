import Foundation

struct ChatMessage: Identifiable, Codable, Equatable {
    let id: UUID
    var role: String
    var content: String

    init(id: UUID = UUID(), role: String, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }
}

struct APIChatMessage: Codable {
    let role: String
    let content: String
}

struct ChatCompletionRequest: Codable {
    let model: String
    let messages: [APIChatMessage]
    let stream: Bool
    let temperature: Double
}

struct StreamEnvelope: Decodable {
    struct Choice: Decodable {
        struct Delta: Decodable {
            let content: String?
        }
        let delta: Delta
    }

    let choices: [Choice]
}

enum ChatServiceError: LocalizedError {
    case invalidEndpoint
    case authenticationRequired
    case forbidden
    case creditsUnavailable
    case badStatus(Int)
    case malformedResponse

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "Endpoint inválido. Confira a URL em Configurações."
        case .authenticationRequired:
            return "A Hugging Face recusou a conexão porque não há um token válido. Abra Configurações e cole um token HF."
        case .forbidden:
            return "O token não tem acesso a esta solicitação. Confira o token ou o provedor selecionado."
        case .creditsUnavailable:
            return "O provedor recusou a inferência por falta de créditos disponíveis. Tente outro provedor/endpoint."
        case .badStatus(let code):
            return "O servidor respondeu HTTP \(code). Confira endpoint, modelo e credenciais."
        case .malformedResponse:
            return "O servidor respondeu em um formato inesperado."
        }
    }
}
