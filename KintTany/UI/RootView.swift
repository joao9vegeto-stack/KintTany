import Foundation
import SwiftUI
import UIKit
import WebKit
import SceneKit

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showLogin = false
    @State private var showFullLog = false
    @State private var showCharacterStats = false
    @State private var showDailyQuests = false
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
                    if app.activity == nil || app.activity == .fishing {
                        fishingBaitCard
                    }
                    activityGrid
                    telemetryCard
                    logCard
                }
                .padding(.horizontal, 16)
                .padding(.top, 10)
                .padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)

            if app.hasSession,
               app.characterArtwork == nil,
               let cookie = app.authenticatedCookieForCharacter,
               !cookie.isEmpty {
                CharacterArtworkCaptureView(cookie: cookie) { image in
                    app.storeCharacterArtwork(image)
                }
                .frame(width: 220, height: 260)
                .opacity(0.001)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
            }
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
        .sheet(isPresented: $showCharacterStats) {
            CharacterStatsView()
                .environmentObject(app)
                .preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showDailyQuests) {
            DailyQuestsView()
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
        .onChange(of: scenePhase) { _, newPhase in
            app.handleScenePhase(newPhase)
        }
        .task {
            await app.refreshCharacterProfile()
        }
    }

    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "2.2"
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
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
                connectionBadge
            }

            HStack(spacing: 14) {
                Group {
                    if app.hasSession, let cookie = app.authenticatedCookieForCharacter, !cookie.isEmpty {
                        CharacterVoxel3DView(appearance: app.characterProfile.appearance)
                    } else {
                        ZStack {
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .fill(.cyan.opacity(0.06))
                            Image(systemName: "person.crop.square")
                                .font(.system(size: 38, weight: .semibold))
                                .foregroundStyle(.cyan.opacity(0.8))
                        }
                    }
                }
                .frame(width: 176, height: 202)
                .contentShape(Rectangle())

                VStack(alignment: .leading, spacing: 8) {
                    Text(app.characterProfile.displayName)
                        .font(.system(size: 23, weight: .black, design: .rounded))
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    Text("Lvl \(app.characterProfile.totalLevel)")
                        .font(.headline.bold())
                        .foregroundStyle(.cyan)

                    Text(app.hasSession ? "Arraste para girar" : "Conecte sua sessão")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)

                    Button {
                        if app.hasSession { showCharacterStats = true }
                        else { showLogin = true }
                    } label: {
                        Label("STATS", systemImage: "chart.bar.fill")
                            .font(.subheadline.bold())
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.cyan)

                    HStack(spacing: 7) {
                        Button("QUESTS") {
                            if app.hasSession { showDailyQuests = true }
                            else { showLogin = true }
                        }
                        .font(.caption.bold())
                        .buttonStyle(.bordered)
                        .tint(.yellow)

                        Button("Sessão") { showLogin = true }
                            .font(.caption.bold())
                            .buttonStyle(.bordered)
                    }
                        .tint(.cyan)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(13)
            .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 22).stroke(.white.opacity(0.07), lineWidth: 1))
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
                    Text(app.displayStatusMessage)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 6)

                if mode != nil {
                    VStack(alignment: .trailing, spacing: 3) {
                        Text("\(app.stats.successes)/\(app.sessionGoal)")
                            .font(.system(size: 18, weight: .black, design: .rounded))
                            .foregroundStyle(accent)
                        liveRateBadge
                    }
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

    private var liveRateBadge: some View {
        TimelineView(.periodic(from: .now, by: 1.0)) { context in
            let rateText = app.formattedRatePerMinute(at: context.date)
            HStack(spacing: 4) {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 9, weight: .bold))
                Text(rateText)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .monospacedDigit()
            }
            .foregroundStyle(.secondary)
            .accessibilityLabel("Ritmo \(rateText)")
        }
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

    private var fishingBaitCard: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("PESCA • ISCA")
                        .font(.caption2.bold())
                        .tracking(1.2)
                        .foregroundStyle(.secondary)
                    Text("Escolha antes de iniciar a pesca")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "fish.fill")
                    .foregroundStyle(.cyan)
            }

            Picker("Isca", selection: $app.selectedFishingBait) {
                ForEach(FishingBait.allCases) { bait in
                    Text(bait.displayName).tag(bait)
                }
            }
            .pickerStyle(.menu)
            .tint(.cyan)
            .disabled(app.activity != nil)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(.black.opacity(0.24), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.white.opacity(0.08), lineWidth: 1))

            Text(fishingBaitStatusText)
                .font(.caption2)
                .foregroundStyle(fishingBaitStatusColor)
        }
        .padding(15)
        .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.07), lineWidth: 1))
    }


    private var fishingBaitStatusText: String {
        let prefix = app.activity == .fishing ? "Sessão atual" : "Selecionada"
        let baitName = app.selectedFishingBait.displayName
        let support = app.selectedFishingBait.supportLabel
        return "\(prefix): \(baitName) • \(support)"
    }

    private var fishingBaitStatusColor: Color {
        app.selectedFishingBait.isAutomationValidated ? Color.secondary : Color.orange
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


private struct DailyQuestsView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(colors: [.black, Color(red: 0.02, green: 0.06, blue: 0.10), .black],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                    .ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("DAILY QUESTS")
                                    .font(.system(size: 13, weight: .black, design: .rounded))
                                    .tracking(2)
                                    .foregroundStyle(.yellow)
                                Text("Dados oficiais do Kintara")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if app.dailyQuestsLoading { ProgressView() }
                        }

                        if let error = app.dailyQuestsError {
                            Text(error).font(.subheadline).foregroundStyle(.orange)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        ForEach(app.dailyQuests) { quest in
                            VStack(alignment: .leading, spacing: 10) {
                                HStack(alignment: .top) {
                                    Text(quest.label)
                                        .font(.headline.bold())
                                    Spacer()
                                    Text(quest.claimed ? "RESGATADA" : (quest.isComplete ? "CONCLUÍDA" : "ATIVA"))
                                        .font(.system(size: 10, weight: .black, design: .rounded))
                                        .foregroundStyle(quest.claimed ? .green : (quest.isComplete ? .yellow : .cyan))
                                }
                                ProgressView(value: quest.progressFraction)
                                    .tint(quest.isComplete ? .green : .cyan)
                                HStack {
                                    Text("\(quest.progress) / \(quest.target)")
                                        .font(.subheadline.monospacedDigit().bold())
                                    Spacer()
                                    Text(quest.kind)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.secondary)
                                }
                                Label(quest.rewardSummary, systemImage: "sparkles")
                                    .font(.caption.bold())
                                    .foregroundStyle(.yellow.opacity(0.9))
                            }
                            .padding(15)
                            .background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.white.opacity(0.08), lineWidth: 1))
                        }

                        if !app.dailyQuestsLoading && app.dailyQuests.isEmpty && app.dailyQuestsError == nil {
                            Text("Nenhuma Daily Quest foi publicada pelo servidor.")
                                .foregroundStyle(.secondary)
                                .padding(.top, 24)
                        }

                        VStack(alignment: .leading, spacing: 5) {
                            Text("RESET")
                                .font(.caption2.bold())
                                .foregroundStyle(.secondary)
                            Text("00:00 UTC")
                                .font(.headline.monospacedDigit().bold())
                            if let day = app.dailyQuestDay {
                                Text("Dia do servidor: \(day)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(15)
                        .background(.white.opacity(0.035), in: RoundedRectangle(cornerRadius: 16))
                    }
                    .padding(16)
                }
                .refreshable { await app.refreshDailyQuests() }
            }
            .navigationTitle("Quests")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Fechar") { dismiss() }
                }
            }
            .task { await app.refreshDailyQuests() }
        }
    }
}

private struct CharacterVoxel3DView: UIViewRepresentable {
    let appearance: CharacterAppearance

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject {
        weak var view: SCNView?
        private var lastX: CGFloat = 0
        @objc func pan(_ gesture: UIPanGestureRecognizer) {
            guard let avatar = view?.scene?.rootNode.childNode(withName: "avatar", recursively: false) else { return }
            let x = gesture.translation(in: view).x
            if gesture.state == .began { lastX = x; return }
            let dx = x - lastX; lastX = x
            avatar.eulerAngles.y += Float(dx) * 0.012
        }
    }

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.backgroundColor = .clear
        view.isOpaque = false
        view.autoenablesDefaultLighting = false
        view.allowsCameraControl = false
        view.antialiasingMode = .multisampling4X
        let pan = UIPanGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.pan(_:)))
        view.addGestureRecognizer(pan)
        context.coordinator.view = view
        view.scene = Self.scene(for: appearance)
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        let yaw = view.scene?.rootNode.childNode(withName: "avatar", recursively: false)?.eulerAngles.y ?? 0
        view.scene = Self.scene(for: appearance)
        view.scene?.rootNode.childNode(withName: "avatar", recursively: false)?.eulerAngles.y = yaw
    }

    private static func scene(for a: CharacterAppearance) -> SCNScene {
        let scene = SCNScene()
        let root = SCNNode()
        root.name = "avatar"
        scene.rootNode.addChildNode(root)

        // Values below come from Kintara outfit schema 15. Colors are server-authoritative
        // 0xRRGGBB values; no character-specific colors are invented here.
        let skinHex: [Int] = [15853791, 14926238, 13935988, 8281929, 6046514]
        func color(_ value: Int?, fallback: Int) -> UIColor {
            let v = value ?? fallback
            return UIColor(red: CGFloat((v >> 16) & 255) / 255,
                           green: CGFloat((v >> 8) & 255) / 255,
                           blue: CGFloat(v & 255) / 255, alpha: 1)
        }
        let skin = color(skinHex[max(0, min(skinHex.count - 1, a.skinTone))], fallback: 14926238)
        let hatColor = color(a.hatColor, fallback: 3816778)
        let topColor = color(a.topColor, fallback: 2450411)
        let pantsColor = color(a.pantsColor, fallback: 2450411)
        let strapColor = color(a.strapColor, fallback: 1790656)
        let shoeColor = color(a.shoeColor, fallback: 16777215)

        func material(_ c: UIColor) -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = c
            m.ambient.contents = c
            m.lightingModel = .lambert
            m.isDoubleSided = false
            return m
        }
        func outlineMaterial() -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = UIColor.black
            m.ambient.contents = UIColor.black
            m.lightingModel = .constant
            m.cullMode = .front
            return m
        }
        @discardableResult
        func box(_ w: CGFloat, _ h: CGFloat, _ d: CGFloat, _ p: SCNVector3, _ c: UIColor, parent: SCNNode? = nil, outlined: Bool = true) -> SCNNode {
            let host = parent ?? root
            if outlined {
                let shell = SCNBox(width: w * 1.075, height: h * 1.075, length: d * 1.075, chamferRadius: 0)
                shell.materials = [outlineMaterial()]
                let sn = SCNNode(geometry: shell)
                sn.position = p
                sn.renderingOrder = -1
                host.addChildNode(sn)
            }
            let g = SCNBox(width: w, height: h, length: d, chamferRadius: 0)
            g.materials = [material(c)]
            let n = SCNNode(geometry: g)
            n.position = p
            host.addChildNode(n)
            return n
        }
        @discardableResult
        func cylinder(_ r: CGFloat, _ h: CGFloat, _ p: SCNVector3, _ c: UIColor, parent: SCNNode? = nil) -> SCNNode {
            let g = SCNCylinder(radius: r, height: h); g.radialSegmentCount = 12
            g.materials = [material(c)]
            let n = SCNNode(geometry: g); n.position = p
            (parent ?? root).addChildNode(n); return n
        }

        // Base player body: separate meshes, matching the game's material ownership:
        // head/arms/leg-skin receive skin tone; torso, pants, straps and shoes receive outfit colors.
        box(0.76, 0.72, 0.72, SCNVector3(0, 2.48, 0), skin)
        let eye = UIColor(white: 0.035, alpha: 1)
        box(0.10, 0.15, 0.025, SCNVector3(-0.18, 2.49, 0.372), eye, outlined: false)
        box(0.10, 0.15, 0.025, SCNVector3( 0.18, 2.49, 0.372), eye, outlined: false)

        // Top schema: 0 none, 1 wife beater, 2 T-shirt, 3 long sleeve, 4 hoodie.
        let renderedTopColor: UIColor = a.topFX == "season1" ? color(0x3E2370, fallback: 0x3E2370) : topColor
        box(0.76, 0.68, 0.50, SCNVector3(0, 1.76, 0), renderedTopColor)
        let sleeveH: CGFloat = a.top == 3 || a.top == 4 ? 0.66 : (a.top == 2 ? 0.30 : 0.10)
        let sleeveY: Float = a.top == 3 || a.top == 4 ? 1.75 : 1.94
        if a.top > 0 {
            box(0.25, sleeveH, 0.34, SCNVector3(-0.55, sleeveY, 0), renderedTopColor)
            box(0.25, sleeveH, 0.34, SCNVector3( 0.55, sleeveY, 0), renderedTopColor)
        }
        let exposedArmH: CGFloat = max(0.12, 0.72 - sleeveH)
        let exposedArmY = Float(1.45 + Double(exposedArmH) / 2)
        box(0.23, exposedArmH, 0.32, SCNVector3(-0.55, exposedArmY, 0), skin)
        box(0.23, exposedArmH, 0.32, SCNVector3( 0.55, exposedArmY, 0), skin)
        if a.top == 4 {
            box(0.68, 0.22, 0.34, SCNVector3(0, 2.18, -0.20), renderedTopColor)
        }
        if a.topFX == "season1" {
            let gold = color(0xF2B632, fallback: 0xF2B632)
            let badge = SCNNode()
            badge.position = SCNVector3(0, 1.78, 0.267)
            root.addChildNode(badge)
            box(0.055, 0.31, 0.025, SCNVector3(0, 0, 0), gold, parent: badge, outlined: false)
            box(0.23, 0.055, 0.025, SCNVector3(0, -0.11, 0), gold, parent: badge, outlined: false)
            box(0.055, 0.15, 0.025, SCNVector3(-0.105, -0.055, 0), gold, parent: badge, outlined: false)
            box(0.055, 0.15, 0.025, SCNVector3(0.105, -0.055, 0), gold, parent: badge, outlined: false)
        }

        // Pants schema: 0 none, 1 straight, 2 baggy, 3 shorts, 4 cargo.
        let shorts = a.pants == 3
        let legClothH: CGFloat = shorts ? 0.28 : 0.62
        let legClothY: Float = shorts ? 1.23 : 1.06
        let legW: CGFloat = a.pants == 2 || a.pants == 4 ? 0.36 : 0.31
        box(legW, legClothH, 0.40, SCNVector3(-0.20, legClothY, 0), pantsColor)
        box(legW, legClothH, 0.40, SCNVector3( 0.20, legClothY, 0), pantsColor)
        if shorts {
            box(0.28, 0.34, 0.36, SCNVector3(-0.20, 0.88, 0), skin)
            box(0.28, 0.34, 0.36, SCNVector3( 0.20, 0.88, 0), skin)
        }
        if a.pants == 4 {
            box(0.10, 0.22, 0.42, SCNVector3(-0.39, 1.08, 0), pantsColor)
            box(0.10, 0.22, 0.42, SCNVector3( 0.39, 1.08, 0), pantsColor)
        }
        box(0.84, 0.08, 0.56, SCNVector3(0, 1.34, 0), strapColor)

        // Shoe schema: 0 none, 1 boots, 2 shoes.
        if a.shoe > 0 {
            let shoeH: CGFloat = a.shoe == 1 ? 0.30 : 0.20
            box(0.34, shoeH, 0.52, SCNVector3(-0.20, 0.58, 0.06), shoeColor)
            box(0.34, shoeH, 0.52, SCNVector3( 0.20, 0.58, 0.06), shoeColor)
        } else {
            box(0.29, 0.18, 0.42, SCNVector3(-0.20, 0.58, 0.03), skin)
            box(0.29, 0.18, 0.42, SCNVector3( 0.20, 0.58, 0.03), skin)
        }

        // Hat IDs 1...9 are the exact base catalog captured from Kintara.
        switch a.hat {
        case 1: // Baseball Cap
            cylinder(0.39, 0.24, SCNVector3(0, 3.04, 0), hatColor)
            box(0.52, 0.08, 0.36, SCNVector3(0, 2.96, 0.24), hatColor)
        case 2: // Sun Hat
            cylinder(0.54, 0.09, SCNVector3(0, 2.99, 0), hatColor)
            cylinder(0.34, 0.27, SCNVector3(0, 3.12, 0), hatColor)
        case 3: // Cowboy Hat
            box(1.02, 0.09, 0.72, SCNVector3(0, 3.00, 0), hatColor)
            box(0.60, 0.34, 0.55, SCNVector3(0, 3.17, 0), hatColor)
        case 4: // Mohawk
            box(0.13, 0.52, 0.70, SCNVector3(0, 3.16, 0), hatColor)
        case 5: // French Hat
            cylinder(0.43, 0.13, SCNVector3(0, 3.04, 0), hatColor)
            cylinder(0.05, 0.12, SCNVector3(0, 3.16, 0), hatColor)
        case 6: // Buzzcut
            box(0.78, 0.12, 0.78, SCNVector3(0, 3.00, 0), hatColor)
        case 7: // Backwards Cap
            cylinder(0.39, 0.24, SCNVector3(0, 3.04, 0), hatColor)
            box(0.52, 0.08, 0.36, SCNVector3(0, 2.96, -0.24), hatColor)
        case 8: // Bucket Hat
            cylinder(0.47, 0.30, SCNVector3(0, 3.08, 0), hatColor)
            cylinder(0.55, 0.08, SCNVector3(0, 2.96, 0), hatColor)
        case 9: // Top Hat
            box(0.92, 0.12, 0.78, SCNVector3(0, 2.91, 0), hatColor)
            box(0.62, 0.58, 0.60, SCNVector3(0, 3.20, 0), hatColor)
        default: break
        }

        // Cosmetic flags remain data-driven. Native base renderer never substitutes a
        // different cosmetic when an asset is not locally available.
        if a.cape != nil { box(0.76, 0.98, 0.08, SCNVector3(0, 1.68, -0.33), renderedTopColor) }

        let camera = SCNNode(); camera.camera = SCNCamera()
        camera.camera?.usesOrthographicProjection = true
        camera.camera?.orthographicScale = 3.95
        camera.camera?.zNear = 0.1; camera.camera?.zFar = 100
        camera.position = SCNVector3(0, 2.02, 7.0)
        camera.look(at: SCNVector3(0, 1.88, 0))
        scene.rootNode.addChildNode(camera)

        let ambient = SCNNode(); ambient.light = SCNLight()
        ambient.light?.type = .ambient; ambient.light?.intensity = 650
        ambient.light?.color = UIColor(white: 0.82, alpha: 1)
        scene.rootNode.addChildNode(ambient)
        let key = SCNNode(); key.light = SCNLight()
        key.light?.type = .directional; key.light?.intensity = 700
        key.eulerAngles = SCNVector3(-0.55, 0.65, 0)
        scene.rootNode.addChildNode(key)
        return scene
    }
}

private struct CharacterThumbnail: View {
    let image: UIImage?
    let hasSession: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(.white.opacity(0.08))

            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .padding(2)
            } else {
                Image(systemName: hasSession
                      ? "person.crop.circle.badge.checkmark"
                      : "person.crop.circle.badge.exclamationmark")
                    .font(.system(size: 23, weight: .semibold))
            }
        }
        .frame(width: 48, height: 48)
        .clipShape(Circle())
        .overlay(Circle().stroke(.white.opacity(0.10), lineWidth: 1))
    }
}

private struct CharacterStatsView: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss

    private let columns = [
        GridItem(.flexible(), spacing: 10),
        GridItem(.flexible(), spacing: 10)
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color.black, Color(red: 0.015, green: 0.045, blue: 0.075), Color.black],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .ignoresSafeArea()

                GeometryReader { proxy in
                    let compact = proxy.size.height < 700
                    VStack(spacing: compact ? 10 : 14) {
                        characterHeader(compact: compact)

                        if app.characterProfileLoading && !app.characterProfile.loaded {
                            ProgressView("Carregando personagem e Stats…")
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if !app.characterProfile.skills.loaded {
                            ContentUnavailableView(
                                "Stats indisponíveis",
                                systemImage: "chart.bar.xaxis",
                                description: Text(app.characterProfileError ?? "Abra novamente após autenticar a sessão.")
                            )
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else {
                            LazyVGrid(columns: columns, spacing: compact ? 8 : 10) {
                                ForEach(CharacterSkill.allCases) { skill in
                                    CharacterSkillCard(
                                        skill: skill,
                                        stats: app.characterProfile.skills,
                                        compact: compact
                                    )
                                }
                            }

                            HStack {
                                Label("Total Level", systemImage: "star.fill")
                                    .font(.headline.bold())
                                Spacer()
                                Text("\(app.characterProfile.totalLevel)")
                                    .font(.system(size: compact ? 24 : 28, weight: .black, design: .rounded))
                                    .foregroundStyle(.cyan)
                            }
                            .padding(.horizontal, 16)
                            .frame(height: compact ? 50 : 58)
                            .background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .stroke(.white.opacity(0.08), lineWidth: 1)
                            )
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, compact ? 8 : 12)
                }
            }
            .navigationTitle("Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fechar") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await app.refreshCharacterProfile(force: true) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(app.characterProfileLoading)
                    .accessibilityLabel("Atualizar personagem e Stats")
                }
            }
        }
        .task {
            await app.refreshCharacterProfile(force: true)
        }
    }

    private func characterHeader(compact: Bool) -> some View {
        HStack(spacing: compact ? 12 : 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(.cyan.opacity(0.08))

                if let image = app.characterArtwork {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .padding(5)
                } else {
                    Image(systemName: "person.crop.square.filled.and.at.rectangle")
                        .font(.system(size: 36, weight: .semibold))
                        .foregroundStyle(.cyan)
                }
            }
            .frame(width: compact ? 88 : 108, height: compact ? 100 : 124)
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(.cyan.opacity(0.22), lineWidth: 1)
            )

            VStack(alignment: .leading, spacing: 7) {
                Text(app.characterProfile.displayName)
                    .font(.system(size: compact ? 24 : 28, weight: .black, design: .rounded))
                    .lineLimit(1)

                Text("Lvl \(app.characterProfile.totalLevel)")
                    .font(.headline.bold())
                    .foregroundStyle(.cyan)

                HStack(spacing: 7) {
                    Circle()
                        .fill(app.hasSession ? Color.green : Color.secondary)
                        .frame(width: 8, height: 8)
                    Text(app.hasSession ? "Conta conectada" : "Sem sessão")
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                }

                Text("Personagem da sessão autenticada")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct CharacterSkillCard: View {
    let skill: CharacterSkill
    let stats: CharacterSkillStats
    let compact: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 9) {
            HStack(spacing: 8) {
                Image(systemName: skill.icon)
                    .foregroundStyle(.cyan)
                    .frame(width: 20)
                Text(skill.localizedName)
                    .font(.subheadline.bold())
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text("\(stats.level(for: skill))/\(CharacterSkillStats.maxLevel)")
                    .font(.caption.bold().monospacedDigit())
            }

            ProgressView(value: stats.progress(for: skill))
                .tint(.green)

            if stats.level(for: skill) >= CharacterSkillStats.maxLevel {
                Text("Nível máximo")
                    .font(.caption2.bold())
                    .foregroundStyle(.green)
            } else {
                Text("\(stats.currentLevelXP(for: skill).formatted()) / \(stats.currentLevelXPGoal(for: skill).formatted()) XP no nível")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.white.opacity(0.82))
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }

            Text("\(stats.totalXP(for: skill).formatted()) XP total")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .padding(compact ? 11 : 13)
        .frame(maxWidth: .infinity, minHeight: compact ? 88 : 98, alignment: .leading)
        .background(.white.opacity(0.065), in: RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(.white.opacity(0.075), lineWidth: 1)
        )
    }
}

private struct CharacterArtworkCaptureView: UIViewRepresentable {
    let cookie: String
    let onCapture: (UIImage) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onCapture: onCapture)
    }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: Coordinator.handlerName)
        controller.addUserScript(WKUserScript(
            source: Coordinator.bridgeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController = controller

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        context.coordinator.webView = webView
        context.coordinator.load(cookie: cookie)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {}

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.configuration.userContentController.removeScriptMessageHandler(forName: Coordinator.handlerName)
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        static let handlerName = "kintaraCharacter"
        static let bridgeScript = """
        (() => {
          if (window.__kintaraIOSCharacterBridge) return;
          window.__kintaraIOSCharacterBridge = true;
          window.addEventListener('message', (event) => {
            const value = event && event.data;
            if (value && value.t === 'kintara_outfit_embed_ready') {
              window.webkit.messageHandlers.kintaraCharacter.postMessage({ t: 'ready' });
            }
          });
        })();
        """

        weak var webView: WKWebView?
        private let onCapture: (UIImage) -> Void
        private var captured = false
        private var attempts = 0

        init(onCapture: @escaping (UIImage) -> Void) {
            self.onCapture = onCapture
        }

        func load(cookie rawCookie: String) {
            guard let webView,
                  let cookie = Self.makeSessionCookie(rawCookie),
                  let url = URL(string: "https://kintara.com/play?embed=outfit")
            else { return }

            webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak webView] in
                var request = URLRequest(url: url)
                request.cachePolicy = .reloadIgnoringLocalCacheData
                webView?.load(request)
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard !captured,
                  let body = message.body as? [String: Any],
                  body["t"] as? String == "ready"
            else { return }
            captureAfterRenderDelay()
        }

        private func captureAfterRenderDelay() {
            guard !captured, attempts < 8 else { return }
            attempts += 1
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
                self?.captureCanvas()
            }
        }

        private func captureCanvas() {
            guard let webView, !captured else { return }
            let script = """
            (() => {
              const canvas = document.querySelector('#kintara-dash-outfit-letter canvas');
              if (!canvas || canvas.width < 64 || canvas.height < 64) return null;
              try { return canvas.toDataURL('image/png'); } catch (_) { return null; }
            })();
            """
            webView.evaluateJavaScript(script) { [weak self] result, _ in
                guard let self else { return }
                guard let dataURL = result as? String,
                      let comma = dataURL.firstIndex(of: ","),
                      let data = Data(base64Encoded: String(dataURL[dataURL.index(after: comma)...])),
                      let image = UIImage(data: data)
                else {
                    self.captureAfterRenderDelay()
                    return
                }
                self.captured = true
                self.onCapture(image)
            }
        }

        private static func makeSessionCookie(_ raw: String) -> HTTPCookie? {
            let pair = raw.split(separator: ";", maxSplits: 1).first.map(String.init) ?? raw
            let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
            guard parts.count == 2,
                  parts[0] == "kintara_session",
                  !parts[1].isEmpty
            else { return nil }

            return HTTPCookie(properties: [
                .domain: ".kintara.com",
                .path: "/",
                .name: parts[0],
                .value: parts[1],
                .secure: "TRUE"
            ])
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
