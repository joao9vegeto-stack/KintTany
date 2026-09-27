import Foundation

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var input = ""
    @Published var isGenerating = false
    @Published var errorMessage: String?

    private let service = ChatService()
    private var generationTask: Task<Void, Never>?

    func send(using settings: AppSettings) {
        let prompt = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty, !isGenerating else { return }

        input = ""
        errorMessage = nil

        messages.append(ChatMessage(role: "user", content: prompt))
        let assistantID = UUID()
        messages.append(ChatMessage(id: assistantID, role: "assistant", content: ""))
        isGenerating = true

        let history = messages.filter { $0.id != assistantID }

        generationTask = Task {
            do {
                let stream = service.stream(
                    endpoint: settings.endpoint,
                    model: settings.model,
                    apiKey: settings.apiKey,
                    systemPrompt: settings.systemPrompt,
                    history: history
                )

                for try await token in stream {
                    guard !Task.isCancelled else { break }
                    if let index = messages.firstIndex(where: { $0.id == assistantID }) {
                        messages[index].content += token
                    }
                }

                if let index = messages.firstIndex(where: { $0.id == assistantID }),
                   messages[index].content.isEmpty {
                    messages[index].content = "Sem conteúdo retornado pelo servidor."
                }
            } catch {
                if let index = messages.firstIndex(where: { $0.id == assistantID }) {
                    messages.remove(at: index)
                }
                errorMessage = error.localizedDescription
            }

            isGenerating = false
            generationTask = nil
        }
    }

    func stop() {
        generationTask?.cancel()
        generationTask = nil
        isGenerating = false
    }

    func clear() {
        stop()
        messages.removeAll()
        errorMessage = nil
    }
}
