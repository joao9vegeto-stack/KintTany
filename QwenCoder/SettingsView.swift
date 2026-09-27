import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Hugging Face") {
                    if settings.requiresAuthentication {
                        Label(
                            settings.apiKey.isEmpty ? "Token necessário" : "Token configurado",
                            systemImage: settings.apiKey.isEmpty ? "exclamationmark.triangle.fill" : "checkmark.circle.fill"
                        )
                        .foregroundStyle(settings.apiKey.isEmpty ? .orange : .green)

                        SecureField("Token HF (hf_…)", text: $settings.apiKey)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()

                        Link(
                            "Criar ou copiar token na Hugging Face",
                            destination: URL(string: "https://huggingface.co/settings/tokens")!
                        )

                        Text("O roteador da Hugging Face exige autenticação. Uma conta gratuita recebe créditos mensais limitados para Inference Providers.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Servidor") {
                    TextField("Endpoint", text: $settings.endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    TextField("Modelo", text: $settings.model)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Text("Você também pode usar um servidor próprio vLLM/SGLang/OpenAI-compatible. Nesse caso, o token pode ficar vazio se o seu servidor não exigir autenticação.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section("Prompt do sistema") {
                    TextEditor(text: $settings.systemPrompt)
                        .frame(minHeight: 130)
                }

                Section("Qwen3-Coder") {
                    LabeledContent("Modelo", value: "30B-A3B-Instruct")
                    LabeledContent("Conexão", value: settings.isReadyForChat ? "Pronta" : "Falta configurar")
                }

                Section {
                    Button("Restaurar Hugging Face + Qwen3-Coder") {
                        settings.restoreHuggingFaceDefaults()
                    }
                }
            }
            .navigationTitle("Configurações")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") { dismiss() }
                        .disabled(!settings.isReadyForChat)
                }
            }
        }
    }
}
