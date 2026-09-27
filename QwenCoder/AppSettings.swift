import Foundation

@MainActor
final class AppSettings: ObservableObject {
    static let huggingFaceEndpoint = "https://router.huggingface.co/v1"
    static let qwenCoderModel = "Qwen/Qwen3-Coder-30B-A3B-Instruct:preferred"

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

    var requiresAuthentication: Bool {
        endpoint.lowercased().contains("router.huggingface.co")
    }

    var isReadyForChat: Bool {
        let endpointOK = !endpoint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let modelOK = !model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let authOK = !requiresAuthentication || !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return endpointOK && modelOK && authOK
    }

    init() {
        endpoint = UserDefaults.standard.string(forKey: "endpoint")
            ?? Self.huggingFaceEndpoint

        let savedModel = UserDefaults.standard.string(forKey: "model")
        if savedModel == nil || savedModel == "Qwen/Qwen3-Coder-30B-A3B-Instruct" {
            model = Self.qwenCoderModel
        } else {
            model = savedModel!
        }

        apiKey = KeychainStore.load(account: "apiKey")
        systemPrompt = UserDefaults.standard.string(forKey: "systemPrompt")
            ?? "You are Qwen3-Coder, an expert software engineering assistant. Prefer correct, compilable code. When the user asks about Swift or iOS, prioritize current Swift and SwiftUI conventions."
    }

    func restoreHuggingFaceDefaults() {
        endpoint = Self.huggingFaceEndpoint
        model = Self.qwenCoderModel
    }
}
