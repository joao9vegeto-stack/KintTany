import Foundation

struct GroqClient {
    let apiKey: String
    let model: String

    func complete(
        messages: [[String: Any]],
        tools: [[String: Any]]
    ) async throws -> [String: Any] {
        guard let url = URL(string: "https://api.groq.com/openai/v1/chat/completions") else {
            throw AppError.message("URL da Groq inválida.")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 90
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1
        ])

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw AppError.message("Resposta HTTP inválida da Groq.")
        }

        guard (200..<300).contains(http.statusCode) else {
            let text = String(data: data, encoding: .utf8) ?? "sem detalhes"
            throw AppError.message("Groq HTTP \(http.statusCode): \(text)")
        }

        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AppError.message("JSON inválido da Groq.")
        }

        return object
    }
}
