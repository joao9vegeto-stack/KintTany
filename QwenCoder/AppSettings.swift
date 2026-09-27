import Foundation

@MainActor
final class AppSettings: ObservableObject {
    @Published var endpoint: String {
        didSet { UserDefaults.standard.set(endpoint, forKey: "endpoint") }
    }

    @Published var model: String {
        didSet { UserDefaults.standard.set(model, forKey: "model") }
    }

    @Published var apiKey: String {
        didSet { KeychainStore.save(apiKey, account: "apiKey") }
    }

    @Published var systemPrompt: String {
        didSet { UserDefaults.standard.set(systemPrompt, forKey: "systemPrompt") }
    }

    init() {
        endpoint = UserDefaults.standard.string(forKey: "endpoint")
            ?? "https://router.huggingface.co/v1"
        model = UserDefaults.standard.string(forKey: "model")
            ?? "Qwen/Qwen3-Coder-30B-A3B-Instruct"
        apiKey = KeychainStore.load(account: "apiKey")
        systemPrompt = UserDefaults.standard.string(forKey: "systemPrompt")
            ?? "You are Qwen3-Coder, an expert software engineering assistant. Prefer correct, compilable code. When the user asks about Swift or iOS, prioritize current Swift and SwiftUI conventions."
    }
}
