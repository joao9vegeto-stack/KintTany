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
            ReplicaDashboardHost(
                showLogin: $showLogin,
                showFullLog: $showFullLog,
                showCharacterStats: $showCharacterStats,
                showDailyQuests: $showDailyQuests
            )
            .environmentObject(app)

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
        .preferredColorScheme(.light)
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
        .onChange(of: app.goal) { _, newValue in
            let clamped = min(100_000, max(1, newValue))
            if clamped != newValue {
                app.goal = clamped
            }
        }
        .onChange(of: scenePhase) { _, newPhase in
            app.handleScenePhase(newPhase)
            if newPhase == .active {
                app.invalidateCharacterArtwork()
                Task { await app.refreshCharacterProfile(force: true) }
            }
        }
        .task {
            app.invalidateCharacterArtwork()
            await app.refreshCharacterProfile(force: true)
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
                    if app.hasSession, let artwork = app.characterArtwork {
                        Image(uiImage: artwork)
                            .resizable()
                            .interpolation(.high)
                            .scaledToFit()
                            .accessibilityLabel("Render oficial do personagem da conta conectada")
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
                KintTanyTheme.surface.ignoresSafeArea()
                KintResourceImage.image("KintPaperTexture").resizable(resizingMode: .tile).opacity(0.54).ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 12) {
                        HStack {
                            Text("DAILY QUESTS").font(KintTanyTheme.titleFont(18, weight: .semibold))
                            Spacer()
                            if app.dailyQuestsLoading { ProgressView().tint(KintTanyTheme.terracotta) }
                        }
                        .foregroundStyle(KintTanyTheme.ink)

                        if let error = app.dailyQuestsError {
                            Text(error).font(KintTanyTheme.bodyFont(12)).foregroundStyle(KintTanyTheme.terracotta)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        ForEach(app.dailyQuests) { quest in
                            VStack(alignment: .leading, spacing: 9) {
                                HStack {
                                    Text(quest.label).font(KintTanyTheme.titleFont(16, weight: .medium))
                                    Spacer()
                                    Text(quest.claimed ? "RESGATADA" : (quest.isComplete ? "CONCLUÍDA" : "ATIVA"))
                                        .font(KintTanyTheme.bodyFont(10, weight: .semibold))
                                }
                                ProgressView(value: quest.progressFraction).tint(KintTanyTheme.terracotta)
                                HStack {
                                    Text("\(quest.progress) / \(quest.target)").font(KintTanyTheme.bodyFont(13, weight: .semibold).monospacedDigit())
                                    Spacer()
                                    Text(quest.kind).font(KintTanyTheme.bodyFont(10)).foregroundStyle(KintTanyTheme.mutedInk)
                                }
                                Label(quest.rewardSummary, systemImage: "sparkles")
                                    .font(KintTanyTheme.bodyFont(11, weight: .medium))
                            }
                            .foregroundStyle(KintTanyTheme.ink)
                            .padding(14)
                            .background(KintTanyTheme.surface.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
                            .kintRaised(radius: 14)
                        }

                        VStack(alignment: .leading, spacing: 5) {
                            Text("RESET").font(KintTanyTheme.bodyFont(10, weight: .semibold))
                            Text("00:00 UTC").font(KintTanyTheme.titleFont(17, weight: .medium))
                            if let day = app.dailyQuestDay { Text("Dia do servidor: \(day)").font(KintTanyTheme.bodyFont(11)) }
                        }
                        .foregroundStyle(KintTanyTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(KintTanyTheme.surface.opacity(0.72), in: RoundedRectangle(cornerRadius: 14))
                        .kintRaised(radius: 14)
                    }
                    .padding(18)
                }
                .refreshable { await app.refreshDailyQuests() }
            }
            .navigationTitle("Quests")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Fechar") { dismiss() } } }
            .task { await app.refreshDailyQuests() }
        }
        .preferredColorScheme(.light)
    }
}

struct CharacterVoxel3DView: UIViewRepresentable {
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

        // Port nativo do rig real buildCharacter/applyOutfit do Kintara.
        let S: CGFloat = 2.0
        let yOffset: Float = 0.45
        let outlineExp: CGFloat = 0.018
        func sc(_ v: CGFloat) -> CGFloat { v * S }
        func mat(_ color: UIColor, constant: Bool = false, image: UIImage? = nil) -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = image ?? color
            m.ambient.contents = image ?? color
            m.lightingModel = constant ? .constant : .lambert
            m.isDoubleSided = false
            m.diffuse.magnificationFilter = .nearest
            m.diffuse.minificationFilter = .nearest
            return m
        }
        func outlineMat() -> SCNMaterial {
            let m = SCNMaterial()
            m.diffuse.contents = UIColor.black
            m.ambient.contents = UIColor.black
            m.lightingModel = .constant
            m.cullMode = .front
            return m
        }
        @discardableResult
        func part(_ w: CGFloat, _ h: CGFloat, _ d: CGFloat,
                  _ x: CGFloat, _ y: CGFloat, _ z: CGFloat,
                  _ material: SCNMaterial, parent: SCNNode = root,
                  local: Bool = false, outlined: Bool = true) -> SCNNode {
            let g = SCNBox(width: sc(w), height: sc(h), length: sc(d), chamferRadius: 0)
            g.materials = [material]
            let n = SCNNode(geometry: g)
            n.position = SCNVector3(Float(sc(x)), Float(sc(y)) + (local ? 0 : yOffset), Float(sc(z)))
            n.renderingOrder = 1
            parent.addChildNode(n)
            if outlined {
                let og = SCNBox(width: sc(w + outlineExp * 2),
                                height: sc(h + outlineExp * 2),
                                length: sc(d + outlineExp * 2),
                                chamferRadius: 0)
                og.materials = [outlineMat()]
                let o = SCNNode(geometry: og)
                o.renderingOrder = 0
                n.addChildNode(o)
            }
            return n
        }

        let skinHex = [15853791, 14926238, 13935988, 8281929, 6046514]
        let skin = Self.kintaraColor(skinHex[max(0, min(skinHex.count - 1, a.skinTone))])
        let skinMat = mat(skin)
        let eyeMat = mat(Self.kintaraColor(0x20120F), constant: true)
        let hatMat = mat(Self.kintaraColor(a.hatColor ?? 3816778))
        let topMat = mat(Self.kintaraColor(a.topColor ?? 2450411))
        let pantsMat = mat(Self.kintaraColor(a.pantsColor ?? 2450411))
        let strapMat = mat(Self.kintaraColor(a.strapColor ?? 1790656))
        let shoeMat = mat(Self.kintaraColor(a.shoeColor ?? 16777215))

        // Exact pc_head + eyes from Kintara uHt/buildCharacter.
        part(0.44,0.34,0.44,0,0.88,0,skinMat)

        // pc_eyeL / pc_eyeR are face pixels, not volumetric blocks.
        // Keep them flush with the head so rotation never exposes black side faces.
        func eye(_ x: CGFloat) {
            let plane = SCNPlane(width: sc(0.07), height: sc(0.13))
            plane.materials = [eyeMat]
            let node = SCNNode(geometry: plane)
            node.name = x < 0 ? "pc_eyeL" : "pc_eyeR"
            node.position = SCNVector3(Float(sc(x)), Float(sc(0.90)) + yOffset, Float(sc(0.221)))
            node.renderingOrder = 6
            root.addChildNode(node)
        }
        eye(-0.09)
        eye(0.09)

        // Exact oUe top geometry table used by applyOutfitToGroup.
        let tops: [(CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool,CGFloat,CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool)] = [
            (0.300,0.280,0.170,0.500,false,false,0.720,0.260,0.110,0.170,0.510,false,false),
            (0.348,0.368,0.212,0.518,true, false,0.718,0.260,0.110,0.170,0.505,false,false),
            (0.340,0.340,0.200,0.508,false,false,0.705,0.260,0.110,0.170,0.508,false,true),
            (0.360,0.385,0.215,0.525,false,false,0.715,0.305,0.112,0.172,0.498,true, false),
            (0.375,0.368,0.228,0.518,false,true, 0.748,0.325,0.118,0.176,0.488,true, false)
        ]
        let ti = max(0, min(4, a.top))
        let T = tops[ti]
        let isSeason = (a.topFX == "season1" || a.topFX == "season1gold") && ti == 2
        let seasonImage = isSeason ? Self.kintaraSeasonOneTee(gold: a.topFX == "season1gold") : nil
        let torsoMat = isSeason ? mat(.white, constant: true, image: seasonImage) : (ti == 0 ? skinMat : topMat)
        let torso = part(T.0,T.1,T.2,0,T.3,0,torsoMat)

        let armMat = T.11 && ti > 0 ? torsoMat : skinMat
        let armL = part(T.8,T.7,T.9,-0.225,T.10,0,armMat)
        let armR = part(T.8,T.7,T.9, 0.225,T.10,0,armMat)
        if T.12 {
            part(0.138,0.136,0.206,0,0.066,0.004,torsoMat,parent:armL,local:true)
            part(0.138,0.136,0.206,0,0.066,0.004,torsoMat,parent:armR,local:true)
        }
        if T.4 {
            part(0.05,0.20,0.06,-0.09,T.6,0.08,strapMat)
            part(0.05,0.20,0.06, 0.09,T.6,0.08,strapMat)
        }
        if T.5 {
            part(T.0 + 0.05,0.21,0.27,0,T.3 + 0.20,-0.13,torsoMat)
        }

        // Exact rUe pants geometry table.
        let pants: [(CGFloat,CGFloat,CGFloat,CGFloat,Bool,Bool)] = [
            (0.140,0.300,0.170,0.09,false,false),
            (0.140,0.300,0.170,0.09,false,false),
            (0.175,0.300,0.215,0.09,false,false),
            (0.150,0.130,0.200,0.09,true, false),
            (0.140,0.300,0.170,0.09,false,true)
        ]
        let pi = max(0, min(4, a.pants))
        let P = pants[pi]
        let legY = CGFloat(0.36) - P.1 * 0.5
        let legMat = pi == 0 ? skinMat : pantsMat
        let legL = part(P.0,P.1,P.2,-P.3,legY,0,legMat)
        let legR = part(P.0,P.1,P.2, P.3,legY,0,legMat)

        var legSkinH: CGFloat = 0.195
        if P.4 {
            let g = legY - P.1 * 0.5
            legSkinH = max(0.12, g - 0.008 - 0.06)
            let localY = -P.1 * 0.5 - 0.008 - legSkinH * 0.5
            part(0.11,legSkinH,0.165,0,localY,0,skinMat,parent:legL,local:true)
            part(0.11,legSkinH,0.165,0,localY,0,skinMat,parent:legR,local:true)
        }
        if P.5 {
            func cargo(_ x: CGFloat) {
                let holder = SCNNode()
                holder.position = SCNVector3(Float(sc(x)),Float(sc(legY + 0.04)) + yOffset,Float(sc(0.102)))
                root.addChildNode(holder)
                part(0.065,0.110,0.032,0,0,0,pantsMat,parent:holder,local:true)
                part(0.070,0.022,0.036,0,0.055,0.012,pantsMat,parent:holder,local:true)
                part(0.050,0.030,0.015,0,-0.010,0.019,pantsMat,parent:holder,local:true)
            }
            cargo(-P.3 - 0.072); cargo(P.3 + 0.072)
        }

        // Exact Nue shoe geometry + UZe anchor formula.
        if a.shoe > 0 {
            let shoes: [(CGFloat,CGFloat,CGFloat,CGFloat)] = [(0.182,0.058,0.234,0.028),(0.178,0.048,0.228,0.030)]
            let sh = shoes[min(shoes.count - 1, a.shoe - 1)]
            let anchor = (P.4 ? -P.1*0.5 - 0.008 - legSkinH + sh.1*0.5 + 0.015
                              : -P.1*0.5 + sh.1*0.5 + 0.015) - 0.018
            let z = sh.3 - 0.006
            part(sh.0,sh.1,sh.2,-0.012,anchor,z,shoeMat,parent:legL,local:true)
            part(sh.0,sh.1,sh.2, 0.012,anchor,z,shoeMat,parent:legR,local:true)
        }

        // Headwear: the base numeric hat selects the primitive silhouette, while
        // newer rewards can override it through hatFx without changing the base id.
        // Keep both paths so old 0...9 outfits and current seasonal cosmetics work.
        let normalizedHatFX = (a.hatFX ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "_", with: "")
            .replacingOccurrences(of: "-", with: "")
        let seasonOneHat = a.hat == 54 || a.hat == 55 ||
            normalizedHatFX == "season1" ||
            normalizedHatFX == "season1gold" ||
            normalizedHatFX == "s1" ||
            normalizedHatFX == "s1gold" ||
            normalizedHatFX.contains("season1")
        let seasonOneHatGold = a.hat == 55 || normalizedHatFX.contains("gold")

        // Exact legacy base hat assets captured from pc_hatHolder.
        // A cosmetic FX replaces the base geometry instead of stacking on top of it.
        if a.hat > 0 && a.hat <= 9 && !seasonOneHat {
            let holder = SCNNode()
            holder.name = "pc_hatHolder"
            holder.position = SCNVector3(0,Float(sc(1.12)) + yOffset,0)
            root.addChildNode(holder)
            func hp(_ w: CGFloat,_ h: CGFloat,_ d: CGFloat,_ x: CGFloat,_ y: CGFloat,_ z: CGFloat,
                    rx: Float = 0, rz: Float = 0) {
                let n = part(w,h,d,x,y,z,hatMat,parent:holder,local:true)
                n.eulerAngles.x = rx; n.eulerAngles.z = rz
            }
            switch a.hat {
            case 1:
                hp(0.42,0.11,0.44,0,0.045,0); hp(0.42,0.024,0.484,0,-0.01,0.122)
            case 2:
                hp(0.64,0.025,0.64,0,-0.03,0); hp(0.28,0.085,0.28,0,0.045,0)
            case 3:
                hp(0.56,0.022,0.50,0,-0.03,0); hp(0.36,0.14,0.34,0,0.065,0)
                hp(0.065,0.03,0.52,-0.28,-0.018,0,rz:-0.58); hp(0.065,0.03,0.52,0.28,-0.018,0,rz:0.58)
                hp(0.44,0.028,0.095,0,-0.008,0.285,rx:-0.62); hp(0.44,0.028,0.095,0,-0.008,-0.285,rx:0.62)
            case 4:
                hp(0.10,0.22,0.38,0,0.04,0); hp(0.045,0.10,0.14,-0.07,-0.02,0.02); hp(0.045,0.10,0.14,0.07,-0.02,0.02)
            case 5:
                let sphere = SCNSphere(radius: sc(0.27)); sphere.segmentCount = 18; sphere.materials = [hatMat]
                let n = SCNNode(geometry:sphere)
                n.scale = SCNVector3(1.38,0.50,1.36)
                n.position = SCNVector3(0,Float(sc(-0.07 + CGFloat(Darwin.cos(0.11)) * 0.135)),0)
                n.eulerAngles = SCNVector3(0.11,0,0.05)
                holder.addChildNode(n)
            case 6:
                hp(0.41,0.052,0.39,0,-0.042,0)
            case 7:
                hp(0.42,0.11,0.44,0,0.045,0); hp(0.42,0.024,0.484,0,-0.01,-0.122)
            case 8:
                hp(0.50,0.045,0.48,0,-0.06,0); hp(0.34,0.16,0.34,0,0.02,0)
            case 9:
                hp(0.50,0.045,0.48,0,-0.06,0); hp(0.34,0.28,0.34,0,0.1025,0)
            default: break
            }
        }

        // Season 1 cap. Current client can expose it either as dedicated hat ids
        // 54/55 or as hatFx on top of a legacy cap id. Both resolve here.
        if seasonOneHat {
            let holder = SCNNode()
            holder.name = "pc_season1HatHolder"
            holder.position = SCNVector3(0, Float(sc(1.108)) + yOffset, 0)
            root.addChildNode(holder)

            let violet = Self.kintaraColor(0x241546)
            let violetMid = Self.kintaraColor(0x35206B)
            let violetLight = Self.kintaraColor(0x443080)
            let gold = Self.kintaraColor(0xD9A83C)
            let goldDark = Self.kintaraColor(0x9D6E20)

            let crownPrimary = seasonOneHatGold ? gold : violetMid
            let crownSecondary = seasonOneHatGold ? goldDark : violet
            let accent = seasonOneHatGold ? violetMid : gold

            let crownGeo = SCNSphere(radius: sc(0.285))
            crownGeo.segmentCount = 18
            crownGeo.materials = [mat(crownPrimary)]
            let crown = SCNNode(geometry: crownGeo)
            crown.name = "pc_season1HatCrown"
            crown.scale = SCNVector3(1.34, 0.57, 1.23)
            crown.position = SCNVector3(0, Float(sc(0.030)), Float(sc(-0.015)))
            crown.eulerAngles = SCNVector3(-0.08, 0, 0.03)
            crown.renderingOrder = 2
            holder.addChildNode(crown)

            // Rear/lower dark band visible in the official cap.
            part(0.410, 0.045, 0.410, 0, -0.080, -0.010, mat(crownSecondary), parent: holder, local: true)

            // Gold side stripe and forward brim.
            part(0.405, 0.020, 0.035, 0, -0.040, 0.205, mat(accent, constant: true), parent: holder, local: true)
            let brim = part(0.39, 0.032, 0.235, 0, -0.072, 0.220, mat(accent), parent: holder, local: true)
            brim.eulerAngles.x = -0.12
            part(0.32, 0.012, 0.205, 0, -0.086, 0.214, mat(seasonOneHatGold ? violet : goldDark, constant: true), parent: holder, local: true)

            // S1 mark on the front/top slope.
            let markPlane = SCNPlane(width: sc(0.185), height: sc(0.115))
            let markMat = SCNMaterial()
            let mark = Self.kintaraSeasonOneHatMark(gold: seasonOneHatGold)
            markMat.diffuse.contents = mark
            markMat.ambient.contents = mark
            markMat.lightingModel = .constant
            markMat.isDoubleSided = true
            markMat.transparencyMode = .aOne
            markPlane.materials = [markMat]
            let badge = SCNNode(geometry: markPlane)
            badge.name = "pc_season1HatMark"
            badge.position = SCNVector3(Float(sc(-0.060)), Float(sc(0.095)), Float(sc(0.270)))
            badge.eulerAngles = SCNVector3(-0.28, 0, -0.08)
            badge.renderingOrder = 8
            holder.addChildNode(badge)

            // Small gold side tab seen on the connected-profile model.
            part(0.075, 0.022, 0.030, -0.205, -0.018, 0.105, mat(accent, constant: true), parent: holder, local: true)
        }

        // Exact Season 1 chest overlay: 0.32 plane at torso depth*0.5*1.04 + .012.
        if isSeason {
            let plane = SCNPlane(width: sc(0.32), height: sc(0.32))
            let em = SCNMaterial()
            let image = Self.kintaraSeasonOneEmblem(gold: a.topFX == "season1gold")
            em.diffuse.contents = image; em.ambient.contents = image
            em.lightingModel = .constant; em.isDoubleSided = true
            plane.materials = [em]
            let badge = SCNNode(geometry:plane)
            badge.position = SCNVector3(0,Float(sc(T.3 + 0.04)) + yOffset,Float(sc(T.2*0.5*1.04 + 0.012)))
            badge.renderingOrder = 5
            root.addChildNode(badge)
            torso.renderingOrder = 4
        }

        let ambient = SCNLight(); ambient.type = .ambient; ambient.intensity = 780
        ambient.color = UIColor(white:0.94,alpha:1)
        let ambientNode = SCNNode(); ambientNode.light = ambient; scene.rootNode.addChildNode(ambientNode)
        let key = SCNLight(); key.type = .directional; key.intensity = 420; key.color = UIColor.white
        let keyNode = SCNNode(); keyNode.light = key; keyNode.eulerAngles = SCNVector3(-0.55,-0.65,0)
        scene.rootNode.addChildNode(keyNode)

        let camera = SCNCamera()
        camera.usesOrthographicProjection = true; camera.orthographicScale = 3.95
        camera.zNear = 0.1; camera.zFar = 100
        let cameraNode = SCNNode(); cameraNode.camera = camera
        cameraNode.position = SCNVector3(0,2.02,7.0)
        cameraNode.look(at: SCNVector3(0,1.88,0))
        scene.rootNode.addChildNode(cameraNode)
        return scene
    }

    private static func kintaraColor(_ value: Int) -> UIColor {
        UIColor(red:CGFloat((value >> 16) & 255)/255,
                green:CGFloat((value >> 8) & 255)/255,
                blue:CGFloat(value & 255)/255,alpha:1)
    }

    private static func kintaraSeasonOneTee(gold: Bool) -> UIImage {
        UIGraphicsImageRenderer(size:CGSize(width:64,height:256)).image { r in
            let c = r.cgContext
            let colors = gold
                ? [kintaraColor(0xF2E3B3).cgColor,kintaraColor(0xD9A83C).cgColor,kintaraColor(0xA87A22).cgColor]
                : [kintaraColor(0x3D2A7D).cgColor,kintaraColor(0x2C1C5E).cgColor,kintaraColor(0x241546).cgColor]
            let locs:[CGFloat] = gold ? [0,0.45,1] : [0,0.55,1]
            let g = CGGradient(colorsSpace:CGColorSpaceCreateDeviceRGB(),colors:colors as CFArray,locations:locs)!
            c.drawLinearGradient(g,start:.zero,end:CGPoint(x:0,y:256),options:[])
            c.setFillColor((gold ? kintaraColor(0x3D2A7D) : kintaraColor(0xD9A83C)).cgColor)
            c.fill(CGRect(x:0,y:244,width:64,height:6))
        }
    }

    private static func kintaraSeasonOneHatMark(gold: Bool) -> UIImage {
        UIGraphicsImageRenderer(size: CGSize(width: 256, height: 160)).image { renderer in
            let c = renderer.cgContext
            c.clear(CGRect(x: 0, y: 0, width: 256, height: 160))
            let primary = gold ? kintaraColor(0x3D2A7D) : kintaraColor(0xF0D27A)
            let shadow = gold ? kintaraColor(0x241546) : kintaraColor(0x8E651F)
            let paragraph = NSMutableParagraphStyle()
            paragraph.alignment = .center
            let attrsShadow: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 86, weight: .black),
                .foregroundColor: shadow,
                .paragraphStyle: paragraph
            ]
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 86, weight: .black),
                .foregroundColor: primary,
                .paragraphStyle: paragraph
            ]
            NSString(string: "S1").draw(in: CGRect(x: 7, y: 18, width: 242, height: 120), withAttributes: attrsShadow)
            NSString(string: "S1").draw(in: CGRect(x: 2, y: 12, width: 242, height: 120), withAttributes: attrs)
        }
    }

    private static func kintaraSeasonOneEmblem(gold: Bool) -> UIImage {
        UIGraphicsImageRenderer(size:CGSize(width:256,height:256)).image { r in
            let c = r.cgContext
            c.clear(CGRect(x:0,y:0,width:256,height:256))
            c.saveGState(); c.translateBy(x:128,y:116); c.scaleBy(x:1.6,y:1.6)
            let main = gold ? kintaraColor(0x3D2A7D) : kintaraColor(0xD9A83C)
            let glyph = gold ? kintaraColor(0x241546) : kintaraColor(0xF2E3B3)
            c.setStrokeColor(main.cgColor); c.setFillColor(main.cgColor)
            c.setLineWidth(13); c.setLineCap(.round)
            for side in [-1.0,1.0] {
                let start = side == -1 ? Double.pi*0.56 : -Double.pi*0.04
                let finish = side == -1 ? Double.pi*1.04 : Double.pi*0.44
                c.addArc(center:CGPoint(x:0,y:10),radius:58,startAngle:CGFloat(start),endAngle:CGFloat(finish),clockwise:false)
                c.strokePath()
                for p in 0..<3 {
                    let angle = side == -1 ? Double.pi*(0.62+Double(p)*0.15) : Double.pi*(0.38-Double(p)*0.15)
                    c.saveGState()
                    c.translateBy(x:CGFloat(Darwin.cos(angle)*64),y:CGFloat(10+Darwin.sin(angle)*64))
                    c.rotate(by:CGFloat(angle + side*0.55))
                    c.fillEllipse(in:CGRect(x:-13,y:-8,width:26,height:16)); c.restoreGState()
                }
            }
            let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center
            let attrs:[NSAttributedString.Key:Any] = [
                .font:UIFont(name:"Verdana-Bold",size:108) ?? UIFont.boldSystemFont(ofSize:108),
                .foregroundColor:glyph,.strokeColor:kintaraColor(0x140B26),.strokeWidth:-10,
                .paragraphStyle:paragraph
            ]
            NSString(string:"1").draw(in:CGRect(x:-70,y:-54,width:140,height:130),withAttributes:attrs)
            c.restoreGState()
        }
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

    private let columns = [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)]

    var body: some View {
        NavigationStack {
            ZStack {
                KintTanyTheme.surface.ignoresSafeArea()
                KintResourceImage.image("KintPaperTexture").resizable(resizingMode: .tile).opacity(0.54).ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 12) {
                        HStack(spacing: 14) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 14).fill(KintTanyTheme.surface.opacity(0.75))
                                if app.hasSession, let artwork = app.characterArtwork {
                                    Image(uiImage: artwork)
                                        .resizable()
                                        .interpolation(.high)
                                        .scaledToFit()
                                        .padding(2)
                                } else {
                                    Image(systemName: "person.crop.square").font(.system(size: 34)).foregroundStyle(KintTanyTheme.mutedInk)
                                }
                            }
                            .frame(width: 92, height: 108).kintRaised(radius: 14)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(app.characterProfile.displayName).font(KintTanyTheme.titleFont(25, weight: .semibold)).lineLimit(1)
                                Text("Lvl \(app.characterProfile.totalLevel)").font(KintTanyTheme.titleFont(16, weight: .medium))
                                Text(app.hasSession ? "● Conta conectada" : "○ Sem sessão").font(KintTanyTheme.bodyFont(11))
                            }
                            .foregroundStyle(KintTanyTheme.ink)
                            Spacer()
                        }

                        if app.characterProfileLoading && !app.characterProfile.loaded {
                            ProgressView("Carregando personagem e Stats…").tint(KintTanyTheme.terracotta).padding(40)
                        } else {
                            LazyVGrid(columns: columns, spacing: 10) {
                                ForEach(CharacterSkill.allCases) { skill in
                                    let stats = app.characterProfile.skills
                                    VStack(alignment: .leading, spacing: 7) {
                                        HStack {
                                            Image(systemName: skill.icon)
                                            Text(skill.localizedName).lineLimit(1)
                                            Spacer()
                                            Text("\(stats.level(for: skill))/\(CharacterSkillStats.maxLevel)").monospacedDigit()
                                        }
                                        .font(KintTanyTheme.bodyFont(12, weight: .semibold))
                                        ProgressView(value: stats.progress(for: skill)).tint(KintTanyTheme.terracotta)
                                        Text("\(stats.currentLevelXP(for: skill).formatted()) / \(stats.currentLevelXPGoal(for: skill).formatted()) XP")
                                            .font(KintTanyTheme.bodyFont(9.5)).lineLimit(1).minimumScaleFactor(0.7)
                                        Text("\(stats.totalXP(for: skill).formatted()) XP total").font(KintTanyTheme.bodyFont(9.5))
                                    }
                                    .foregroundStyle(KintTanyTheme.ink)
                                    .padding(12)
                                    .frame(maxWidth: .infinity, minHeight: 100, alignment: .leading)
                                    .background(KintTanyTheme.surface.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
                                    .kintRaised(radius: 14)
                                }
                            }
                            HStack {
                                Label("Total Level", systemImage: "star.fill").font(KintTanyTheme.titleFont(17, weight: .medium))
                                Spacer()
                                Text("\(app.characterProfile.totalLevel)").font(KintTanyTheme.titleFont(25, weight: .semibold))
                            }
                            .foregroundStyle(KintTanyTheme.ink)
                            .padding(15)
                            .background(KintTanyTheme.surface.opacity(0.75), in: RoundedRectangle(cornerRadius: 14))
                            .kintRaised(radius: 14)
                        }
                    }
                    .padding(18)
                }
            }
            .navigationTitle("Stats")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button { Task { await app.refreshCharacterProfile(force: true) } } label: { Image(systemName: "arrow.clockwise") }
                        .disabled(app.characterProfileLoading)
                }
            }
        }
        .preferredColorScheme(.light)
        .task { await app.refreshCharacterProfile(force: true) }
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
              try {
                const ctx = canvas.getContext('2d');
                if (!ctx) return canvas.toDataURL('image/png');
                const w = canvas.width, h = canvas.height;
                const pixels = ctx.getImageData(0, 0, w, h).data;
                let minX = w, minY = h, maxX = -1, maxY = -1;
                for (let y = 0; y < h; y++) {
                  for (let x = 0; x < w; x++) {
                    const a = pixels[(y * w + x) * 4 + 3];
                    if (a > 2) {
                      if (x < minX) minX = x;
                      if (y < minY) minY = y;
                      if (x > maxX) maxX = x;
                      if (y > maxY) maxY = y;
                    }
                  }
                }
                if (maxX < minX || maxY < minY) return canvas.toDataURL('image/png');
                const pad = 4;
                minX = Math.max(0, minX - pad); minY = Math.max(0, minY - pad);
                maxX = Math.min(w - 1, maxX + pad); maxY = Math.min(h - 1, maxY + pad);
                const out = document.createElement('canvas');
                out.width = maxX - minX + 1; out.height = maxY - minY + 1;
                const outCtx = out.getContext('2d');
                outCtx.drawImage(canvas, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
                return out.toDataURL('image/png');
              } catch (_) {
                try { return canvas.toDataURL('image/png'); } catch (_) { return null; }
              }
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
