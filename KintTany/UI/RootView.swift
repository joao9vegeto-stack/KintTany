import SwiftUI
import UIKit

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @State private var showLogin = false
    @State private var showFullLog = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    HStack(spacing: 10) {
                        Label("KintTany", systemImage: "bolt.shield.fill")
                            .font(.title2.bold())
                        Spacer()
                        Button("Sessão") { showLogin = true }
                            .buttonStyle(.bordered)
                        connectionBadge
                    }

                    statusCard

                    LazyVGrid(
                        columns: [GridItem(.flexible()), GridItem(.flexible())],
                        spacing: 12
                    ) {
                        ForEach(ActivityMode.allCases) { mode in
                            activityCard(mode)
                        }
                    }

                    logCard
                }
                .padding()
            }
            .navigationTitle("Dashboard")
            .sheet(isPresented: $showLogin) {
                LoginWebView(
                    onCookie: { cookie in
                        app.saveCookie(cookie)
                        showLogin = false
                    },
                    onDiagnostic: { line in
                        app.diagnostic(line)
                    }
                )
            }
            .sheet(isPresented: $showFullLog) {
                FullLogView()
                    .environmentObject(app)
            }
        }
    }

    private var connectionBadge: some View {
        let presentation = connectionPresentation
        return HStack(spacing: 6) {
            Circle()
                .fill(presentation.color)
                .frame(width: 9, height: 9)
            Text(presentation.text)
                .font(.caption.bold())
        }
        .foregroundStyle(presentation.color)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(presentation.color.opacity(0.14))
        .clipShape(Capsule())
        .accessibilityLabel("Conexão \(presentation.text)")
    }

    private var connectionPresentation: (text: String, color: Color) {
        if app.connected {
            return ("Online", .green)
        }

        switch app.state {
        case .connecting, .syncing:
            return ("Conectando", .orange)
        case .failed:
            return ("Erro", .red)
        default:
            return ("Offline", .gray)
        }
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.activity?.title ?? "Nenhuma atividade")
                .font(.headline)
            Text(app.state.rawValue)
            ProgressView(
                value: Double(app.stats.successes),
                total: Double(max(app.goal, 1))
            )
            HStack {
                Text("Sucessos: \(app.stats.successes)")
                Spacer()
                Text("Falhas: \(app.stats.failures)")
            }
            Button("STOP", role: .destructive) { app.stop() }
                .buttonStyle(.borderedProminent)
        }
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func activityCard(_ mode: ActivityMode) -> some View {
        Button { app.start(mode) } label: {
            VStack(alignment: .leading, spacing: 8) {
                Label(mode.title, systemImage: mode.icon)
                    .font(.headline)
                Text("Meta \(app.goal)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color.blue.opacity(0.10))
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }

    private var logCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Logs")
                    .font(.headline)
                Spacer()
                Button {
                    showFullLog = true
                } label: {
                    Label("Log completo", systemImage: "doc.text.magnifyingglass")
                        .font(.caption.bold())
                }
                .buttonStyle(.bordered)
            }

            if app.logs.isEmpty {
                Text("Nenhum evento registrado ainda.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(app.logs.suffix(5).enumerated()), id: \.offset) { item in
                    Text(item.element)
                        .font(.caption.monospaced())
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            Text("O log completo inclui HTTP, WebSocket, mensagens IN/OUT, estados e erros. Cookies, tokens e chaves são ocultados.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

private struct FullLogView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false

    var body: some View {
        NavigationStack {
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
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .id(index)
                            }
                        }
                    }
                    .padding()
                }
                .onAppear {
                    scrollToBottom(proxy)
                }
                .onChange(of: app.diagnosticLogs.count) { _, _ in
                    scrollToBottom(proxy)
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
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        guard !app.diagnosticLogs.isEmpty else { return }
        let last = app.diagnosticLogs.count - 1
        DispatchQueue.main.async {
            proxy.scrollTo(last, anchor: .bottom)
        }
    }
}
