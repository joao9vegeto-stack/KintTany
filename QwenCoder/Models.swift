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
    case badStatus(Int, String)
    case malformedResponse

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "Endpoint inválido."
        case .badStatus(let code, let body):
            return "Servidor respondeu HTTP \(code): \(body)"
        case .malformedResponse:
            return "Resposta do servidor em formato inesperado."
        }
    }
}
