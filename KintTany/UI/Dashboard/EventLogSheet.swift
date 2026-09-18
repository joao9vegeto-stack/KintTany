import SwiftUI
import UIKit

struct EventLogSheet: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false
    @State private var exportedLogFile: ExportedLogFile?
    @State private var exportError: String?

    var body: some View {
        NavigationStack {
            ZStack {
                DashboardBackground()

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 7) {
                            if app.diagnosticLogs.isEmpty {
                                ContentUnavailableView(
                                    "Sem logs",
                                    systemImage: "doc.text",
                                    description: Text("Inicie uma sessão ou atividade para registrar o diagnóstico.")
                                )
                                .frame(maxWidth: .infinity)
                                .padding(.top, 50)
                            } else {
                                ForEach(Array(app.diagnosticLogs.enumerated()), id: \.offset) { index, line in
                                    Text(line)
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundStyle(.white.opacity(0.86))
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .id(index)
                                }
                            }
                        }
                        .padding()
                    }
                    .onAppear { scrollToBottom(proxy) }
                    .onChange(of: app.diagnosticLogs.count) { _, _ in scrollToBottom(proxy) }
                }
            }
            .navigationTitle("Log completo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fechar") { dismiss() }
                }
                ToolbarItemGroup(placement: .primaryAction) {
                    Button {
                        UIPasteboard.general.string = app.fullLogText
                        copied = true
                    } label: {
                        Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Copiar log completo")

                    Button {
                        exportLogAsTXT()
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Exportar log em TXT")

                    Button(role: .destructive) {
                        app.clearDiagnosticLogs()
                    } label: {
                        Image(systemName: "trash")
                    }
                    .disabled(app.diagnosticLogs.isEmpty)
                    .accessibilityLabel("Limpar log completo")
                }
            }
        }
        .sheet(item: $exportedLogFile, onDismiss: cleanupExportedLogFile) { file in
            ActivityShareSheet(activityItems: [file.url])
        }
        .alert(
            "Não foi possível exportar o log",
            isPresented: Binding(
                get: { exportError != nil },
                set: { if !$0 { exportError = nil } }
            )
        ) {
            Button("OK", role: .cancel) { exportError = nil }
        } message: {
            Text(exportError ?? "Erro desconhecido")
        }
    }

    private func exportLogAsTXT() {
        guard !app.diagnosticLogs.isEmpty else { return }

        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"

        let fileName = "KintTany-log-\(formatter.string(from: Date())).txt"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(fileName)

        do {
            try app.fullLogText.write(to: url, atomically: true, encoding: .utf8)
            exportedLogFile = ExportedLogFile(url: url)
        } catch {
            exportError = error.localizedDescription
        }
    }

    private func cleanupExportedLogFile() {
        guard let url = exportedLogFile?.url else { return }
        try? FileManager.default.removeItem(at: url)
        exportedLogFile = nil
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        guard !app.diagnosticLogs.isEmpty else { return }
        let last = app.diagnosticLogs.count - 1
        DispatchQueue.main.async {
            proxy.scrollTo(last, anchor: .bottom)
        }
    }
}

private struct ExportedLogFile: Identifiable {
    let id = UUID()
    let url: URL
}

private struct ActivityShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

