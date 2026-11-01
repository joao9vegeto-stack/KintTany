import SwiftUI

struct PandaSessionImportView: View {
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var json = ""
    @State private var message: String?
    @State private var saved = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Sessão GameStream") {
                    Text("Cole um JSON exportado pelo adaptador Panda ou por uma ferramenta de diagnóstico. A tela não faz chamadas de rede.")
                        .font(.footnote).foregroundStyle(.secondary)
                    TextEditor(text: $json)
                        .font(.system(.footnote, design: .monospaced))
                        .frame(minHeight: 240)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Button { importSession() } label: {
                        Label("Validar e guardar no Chaves", systemImage: "lock.fill")
                    }
                    .disabled(json.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    if let message {
                        Text(message).font(.footnote).foregroundStyle(saved ? .green : .orange)
                    }
                }
            }
            .navigationTitle("Importar sessão")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Fechar") { dismiss() } }
            }
        }
    }

    private func importSession() {
        do {
            let value = try JSONDecoder().decode(PandaSessionDescriptor.self, from: Data(json.utf8))
            try value.validate()
            try PandaSessionVault.save(value)
            saved = true
            message = "Sessão validada e protegida no Chaves deste iPhone."
            onSaved()
        } catch {
            saved = false
            message = error.localizedDescription
        }
    }
}
