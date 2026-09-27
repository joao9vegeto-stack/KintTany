import Foundation

final class ChatService {
    func stream(
        endpoint: String,
        model: String,
        apiKey: String,
        systemPrompt: String,
        history: [ChatMessage]
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let trimmed = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
                        .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                    guard let url = URL(string: trimmed + "/chat/completions") else {
                        throw ChatServiceError.invalidEndpoint
                    }

                    if trimmed.lowercased().contains("router.huggingface.co"),
                       apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        throw ChatServiceError.authenticationRequired
                    }

                    var apiMessages: [APIChatMessage] = []
                    if !systemPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        apiMessages.append(.init(role: "system", content: systemPrompt))
                    }
                    apiMessages.append(contentsOf: history.map {
                        APIChatMessage(role: $0.role, content: $0.content)
                    })

                    let payload = ChatCompletionRequest(
                        model: model,
                        messages: apiMessages,
                        stream: true,
                        temperature: 0.2
                    )

                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                    let cleanKey = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !cleanKey.isEmpty {
                        request.setValue("Bearer \(cleanKey)", forHTTPHeaderField: "Authorization")
                    }

                    request.httpBody = try JSONEncoder().encode(payload)
                    request.timeoutInterval = 180

                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else {
                        throw ChatServiceError.malformedResponse
                    }

                    guard (200...299).contains(http.statusCode) else {
                        switch http.statusCode {
                        case 401:
                            throw ChatServiceError.authenticationRequired
                        case 402, 429:
                            throw ChatServiceError.creditsUnavailable
                        case 403:
                            throw ChatServiceError.forbidden
                        default:
                            throw ChatServiceError.badStatus(http.statusCode)
                        }
                    }

                    for try await line in bytes.lines {
                        if Task.isCancelled { break }
                        guard line.hasPrefix("data:") else { continue }

                        let dataString = line
                            .dropFirst(5)
                            .trimmingCharacters(in: .whitespacesAndNewlines)

                        if dataString == "[DONE]" { break }
                        guard let data = dataString.data(using: .utf8) else { continue }

                        if let envelope = try? JSONDecoder().decode(StreamEnvelope.self, from: data),
                           let token = envelope.choices.first?.delta.content,
                           !token.isEmpty {
                            continuation.yield(token)
                        }
                    }

                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }
}
