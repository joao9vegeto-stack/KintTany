import Foundation
import SwiftUI
import UIKit

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @State private var showLogin = false
    @State private var showFullLog = false
    @FocusState private var goalFieldFocused: Bool

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color.black, Color(red: 0.015, green: 0.045, blue: 0.075), Color.black],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 18) {
                    header
                    activeCard
                    goalCard
                    activityGrid
                    telemetryCard
                    logCard
                }
                .padding(.horizontal, 16)
                .padding(.top, 10)
                .padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)
        }
        .preferredColorScheme(.dark)
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
            .preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showFullLog) {
            FullLogView()
                .environmentObject(app)
                .preferredColorScheme(.dark)
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("OK") {
                    app.goal = min(100_000, max(1, app.goal))
                    goalFieldFocused = false
                }
                .fontWeight(.bold)
            }
        }
        .onChange(of: app.goal) { _, newValue in
            let clamped = min(100_000, max(1, newValue))
            if clamped != newValue {
                app.goal = clamped
            }
        }
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "2.0"
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text("KINTARABOT")
                            .font(.system(size: 12, weight: .black, design: .rounded))
                            .tracking(2.6)
                            .foregroundStyle(.cyan)
                        Text("v\(appVersion)")
                            .font(.system(size: 10, weight: .black, design: .rounded))
                            .foregroundStyle(.cyan.opacity(0.78))
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(.cyan.opacity(0.10), in: Capsule())
                            .overlay(Capsule().stroke(.cyan.opacity(0.18), lineWidth: 1))
                    }
                    Text("Painel de controle")
                        .font(.system(size: 32, weight: .black, design: .rounded))
                }

                Spacer()

                Button {
                    showLogin = true
                } label: {
                    Image(systemName: app.hasSession ? "person.crop.circle.badge.checkmark" : "person.crop.circle.badge.exclamationmark")
                        .font(.system(size: 23, weight: .semibold))
                        .frame(width: 48, height: 48)
                        .background(.white.opacity(0.08), in: Circle())
                        .overlay(Circle().stroke(.white.opacity(0.08), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Sessão")
            }

            HStack(spacing: 10) {
                Label("KintTany", systemImage: "bolt.shield.fill")
                    .font(.headline.bold())
                    .foregroundStyle(.white)
                Spacer()
                Button("Sessão") { showLogin = true }
                    .font(.subheadline.bold())
                    .buttonStyle(.bordered)
                    .tint(.cyan)
                connectionBadge
            }
        }
    }

    private var connectionBadge: some View {
        let presentation = connectionPresentation
        return HStack(spacing: 7) {
            Circle()
                .fill(presentation.color)
                .frame(width: 9, height: 9)
                .shadow(color: presentation.color.opacity(0.7), radius: 5)
            Text(presentation.text)
                .font(.caption.bold())
        }
        .foregroundStyle(presentation.color)
        .padding(.horizontal, 11)
        .padding(.vertical, 8)
        .background(presentation.color.opacity(0.12), in: Capsule())
        .overlay(Capsule().stroke(presentation.color.opacity(0.22), lineWidth: 1))
        .accessibilityLabel("Conexão \(presentation.text)")
    }

    private var connectionPresentation: (text: String, color: Color) {
        if app.connected { return ("Online", .green) }
        switch app.state {
        case .connecting, .syncing: return ("Conectando", .orange)
        case .failed: return ("Erro", .red)
        default: return ("Offline", .secondary)
        }
    }

    private var activeCard: some View {
        let mode = app.activity
        let accent = mode?.accent ?? .cyan

        return VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 13) {
                ZStack {
                    RoundedRectangle(cornerRadius: 15, style: .continuous)
                        .fill(accent.opacity(0.17))
                    Image(systemName: mode?.icon ?? "bolt.horizontal.circle.fill")
                        .font(.system(size: 25, weight: .bold))
                        .foregroundStyle(accent)
                }
                .frame(width: 54, height: 54)

                VStack(alignment: .leading, spacing: 3) {
                    Text(mode?.localizedTitle ?? "Nenhuma atividade")
                        .font(.title3.bold())
                    Text(app.statusMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 6)

                if mode != nil {
                    Text("\(app.stats.successes)/\(app.goal)")
                        .font(.system(size: 18, weight: .black, design: .rounded))
                        .foregroundStyle(accent)
                }
            }

            VStack(spacing: 8) {
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.white.opacity(0.08))
                        Capsule()
                            .fill(accent.gradient)
                            .frame(width: proxy.size.width * app.progress)
                    }
                }
                .frame(height: 8)

                HStack {
                    Label(app.state.label, systemImage: stateIcon)
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    Spacer()
                    if let target = app.currentTarget {
                        Text(target)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }

            Divider().overlay(.white.opacity(0.08))

            HStack(spacing: 0) {
                metric(value: app.stats.successes, label: "Sucessos")
                metric(value: app.stats.failures, label: "Falhas")
                if mode == .chicken || mode == .zombie || mode == .dragon {
                    metric(value: app.stats.confirmedHits, label: "Hits")
                    metric(value: app.stats.kills, label: "Kills")
                } else {
                    metric(value: app.stats.attempts, label: "Tentativas")
                }
            }

            if mode != nil {
                Button(role: .destructive) {
                    app.stop()
                } label: {
                    Label("PARAR AGORA", systemImage: "stop.fill")
                        .font(.headline.bold())
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 5)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(Color.white.opacity(0.065))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(accent.opacity(mode == nil ? 0.12 : 0.28), lineWidth: 1)
        )
        .shadow(color: accent.opacity(mode == nil ? 0 : 0.08), radius: 24, y: 8)
    }

    private var goalCard: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 7) {
                Text("META DA SESSÃO")
                    .font(.caption2.bold())
                    .tracking(1.2)
                    .foregroundStyle(.secondary)

                HStack(spacing: 8) {
                    TextField("Meta", value: $app.goal, format: .number)
                        .keyboardType(.numberPad)
                        .focused($goalFieldFocused)
                        .font(.system(size: 25, weight: .black, design: .rounded))
                        .multilineTextAlignment(.leading)
                        .frame(width: 112)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(.black.opacity(0.24), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(goalFieldFocused ? Color.cyan.opacity(0.75) : Color.white.opacity(0.08), lineWidth: 1)
                        )
                        .disabled(app.activity != nil)

                    Image(systemName: "keyboard")
                        .font(.caption.bold())
                        .foregroundStyle(goalFieldFocused ? .cyan : .secondary)
                }
            }

            Spacer()

            Button {
                app.goal = max(1, app.goal - 1)
            } label: {
                Image(systemName: "minus")
                    .frame(width: 38, height: 38)
            }
            .buttonStyle(.bordered)
            .disabled(app.activity != nil)

            Button {
                app.goal = min(100_000, app.goal + 1)
            } label: {
                Image(systemName: "plus")
                    .frame(width: 38, height: 38)
            }
            .buttonStyle(.bordered)
            .disabled(app.activity != nil)
        }
        .padding(15)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07), lineWidth: 1))
    }

    private var activityGrid: some View {
        VStack(alignment: .leading, spacing: 11) {
            sectionTitle("Atividades", subtitle: "Uma atividade por vez")
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(ActivityMode.allCases) { mode in
                    activityCard(mode)
                }
            }
        }
    }

    private func activityCard(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        return Button {
            app.start(mode)
        } label: {
            VStack(alignment: .leading, spacing: 17) {
                HStack {
                    ZStack {
                        Circle().fill(mode.accent.opacity(0.18))
                        Image(systemName: mode.icon)
                            .font(.system(size: 20, weight: .bold))
                            .foregroundStyle(mode.accent)
                    }
                    .frame(width: 43, height: 43)
                    Spacer()
                    Image(systemName: selected ? "waveform.path.ecg" : "chevron.right")
                        .font(.caption.bold())
                        .foregroundStyle(selected ? mode.accent : .secondary)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(mode.localizedTitle)
                        .font(.headline.bold())
                    Text(selected ? app.state.label : "Meta \(app.goal)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 112, alignment: .leading)
            .padding(15)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(selected ? mode.accent.opacity(0.13) : Color.white.opacity(0.045))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(selected ? mode.accent.opacity(0.45) : .white.opacity(0.07), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(app.activity != nil && !selected)
        .opacity(app.activity != nil && !selected ? 0.58 : 1)
    }

    private var telemetryCard: some View {
        VStack(alignment: .leading, spacing: 13) {
            sectionTitle("Telemetria", subtitle: "Estado autoritativo recebido do servidor")

            HStack(spacing: 10) {
                telemetryItem(icon: "map.fill", title: "Região", value: app.world.serverRegion ?? app.player.region)
                telemetryItem(icon: "location.fill", title: "Posição", value: String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z))
            }

            HStack(spacing: 10) {
                telemetryItem(icon: "square.stack.3d.up.fill", title: "Recursos", value: "\(app.resourceCount)")
                telemetryItem(icon: "figure.2", title: "Mobs", value: "\(app.mobCount)")
            }

            if !app.stats.lastEvent.isEmpty {
                HStack(alignment: .top, spacing: 9) {
                    Image(systemName: "waveform")
                        .foregroundStyle(.cyan)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Último evento")
                            .font(.caption2.bold())
                            .foregroundStyle(.secondary)
                        Text(app.stats.lastEvent)
                            .font(.caption.monospaced())
                            .lineLimit(2)
                    }
                }
                .padding(.top, 2)
            }
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(.white.opacity(0.07), lineWidth: 1))
    }

    private func telemetryItem(icon: String, title: String, value: String) -> some View {
        HStack(spacing: 9) {
            Image(systemName: icon)
                .foregroundStyle(.cyan)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.caption.bold())
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity)
        .padding(11)
        .background(.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 13))
    }

    private var logCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                sectionTitle("Eventos", subtitle: "Resumo da sessão")
                Spacer()
                Button {
                    showFullLog = true
                } label: {
                    Label("Log completo", systemImage: "doc.text.magnifyingglass")
                        .font(.caption.bold())
                }
                .buttonStyle(.bordered)
                .tint(.cyan)
            }

            if app.logs.isEmpty {
                Label("Nenhum evento registrado ainda", systemImage: "sparkles")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(app.logs.suffix(5).enumerated()), id: \.offset) { index, line in
                        Text(line)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.white.opacity(0.82))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                        if index < min(app.logs.count, 5) - 1 {
                            Divider().overlay(.white.opacity(0.06))
                        }
                    }
                }
                .padding(.horizontal, 11)
                .background(.black.opacity(0.28), in: RoundedRectangle(cornerRadius: 14))
            }

            Text("Tokens, cookies e chaves são ocultados no diagnóstico.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(.white.opacity(0.07), lineWidth: 1))
    }

    private func sectionTitle(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.headline.bold())
            Text(subtitle).font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func metric(value: Int, label: String) -> some View {
        VStack(spacing: 2) {
            Text("\(value)")
                .font(.system(size: 18, weight: .black, design: .rounded))
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var stateIcon: String {
        switch app.state {
        case .moving: "location.fill"
        case .acting, .waitingProof, .waitingResult: "waveform.path.ecg"
        case .completed: "checkmark.circle.fill"
        case .failed: "exclamationmark.triangle.fill"
        case .cancelled: "stop.circle.fill"
        case .connecting, .syncing, .recovering: "arrow.triangle.2.circlepath"
        default: "scope"
        }
    }
}

private struct FullLogView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false
    @State private var exportedLogFile: ExportedLogFile?
    @State private var exportError: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
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
            ShareSheet(activityItems: [file.url])
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

private struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
