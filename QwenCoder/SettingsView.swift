import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Servidor") {
                    TextField("Endpoint", text: $settings.endpoint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    SecureField("API key / token", text: $settings.apiKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    TextField("Modelo", text: $settings.model)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section("Prompt do sistema") {
                    TextEditor(text: $settings.systemPrompt)
                        .frame(minHeight: 140)
                }

                Section("Qwen3-Coder") {
                    LabeledContent("Padrão", value: "30B-A3B-Instruct")
                    Text("O app fala com qualquer endpoint compatível com a API OpenAI. Para Hugging Face, cole um token no campo acima. Para vLLM/SGLang próprio, troque o endpoint.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                Section {
                    Button("Restaurar padrão") {
                        settings.endpoint = "https://router.huggingface.co/v1"
                        settings.model = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
                    }
                }
            }
            .navigationTitle("Configurações")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("OK") { dismiss() }
                }
            }
        }
    }
}
