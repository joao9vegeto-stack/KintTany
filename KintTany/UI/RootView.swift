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
    @State private var showBaitPicker = false
    @FocusState private var goalFieldFocused: Bool

    private let copper = Color(red: 0.67, green: 0.34, blue: 0.23)
    private let ink = Color(red: 0.16, green: 0.15, blue: 0.14)
    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { proxy in
                let designWidth: CGFloat = 430
                let designHeight: CGFloat = 875
                let scale = min(proxy.size.width / designWidth, proxy.size.height / designHeight)

                VStack(spacing: 9) {
                    topStatusBar
                    heroSection.frame(height: 292)
                    statsSection.frame(height: 224)
                    sessionMetrics.frame(height: 62)
                    pauseButton.frame(height: 66)
                    bottomNavigation.frame(height: 54)
                    fullLogButton.frame(height: 48)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 5)
                .frame(width: designWidth, height: designHeight, alignment: .top)
                .scaleEffect(scale, anchor: .top)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }

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
                onDiagnostic: { line in app.diagnostic(line) }
            )
            .preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showFullLog) {
            FullLogView().environmentObject(app).preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showCharacterStats) {
            CharacterStatsView().environmentObject(app).preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showDailyQuests) {
            DailyQuestsView().environmentObject(app).preferredColorScheme(.dark)
        }
        .confirmationDialog("Selecionar isca", isPresented: $showBaitPicker, titleVisibility: .visible) {
            ForEach(FishingBait.allCases) { bait in
                Button(app.selectedFishingBait == bait ? "✓ \(bait.displayName)" : bait.displayName) {
                    app.selectedFishingBait = bait
                    app.start(.fishing)
                }
            }
            Button("Cancelar", role: .cancel) {}
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
            if clamped != newValue { app.goal = clamped }
        }
        .onChange(of: scenePhase) { _, newPhase in app.handleScenePhase(newPhase) }
        .task { await app.refreshCharacterProfile() }
    }

    private var topStatusBar: some View {
        ZStack {
            Text("KintTany")
                .font(.system(size: 29, weight: .semibold, design: .rounded))
                .foregroundStyle(ink)
            HStack {
                HStack(spacing: 8) {
                    Circle()
                        .fill(connectionColor)
                        .frame(width: 13, height: 13)
                        .overlay(Circle().stroke(ink.opacity(0.35), lineWidth: 1))
                        .shadow(color: .white.opacity(0.8), radius: 1, x: -1, y: -1)
                        .shadow(color: .black.opacity(0.18), radius: 1, x: 1, y: 1)
                    Text(connectionTitle.uppercased())
                        .font(.system(size: 16, weight: .medium, design: .rounded))
                        .foregroundStyle(ink)
                }
                Spacer()
            }
        }
        .frame(height: 38)
        .padding(.horizontal, 10)
    }

    private var connectionTitle: String {
        if app.connected { return "Online" }
        switch app.state {
        case .connecting, .syncing, .recovering: return "Conectando"
        case .failed: return "Erro"
        default: return app.hasSession ? "Pronto" : "Offline"
        }
    }

    private var connectionColor: Color {
        if app.connected { return Color(red: 0.42, green: 0.54, blue: 0.39) }
        if app.state == .failed { return Color(red: 0.66, green: 0.28, blue: 0.22) }
        if app.hasSession { return Color(red: 0.70, green: 0.55, blue: 0.31) }
        return .gray
    }

    private var heroSection: some View {
        HStack(spacing: 12) {
            characterPanel.frame(width: 128)
            VStack(spacing: 6) {
                activeSummary
                activitySelector
            }
        }
    }

    private var characterPanel: some View {
        ZStack {
            if app.hasSession {
                CharacterVoxel3DView(appearance: app.characterProfile.appearance)
                    .padding(.horizontal, 1)
                    .padding(.vertical, 5)
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "person.crop.square").font(.system(size: 48, weight: .medium))
                    Text("SESSÃO").font(.caption.bold())
                }
                .foregroundStyle(ink.opacity(0.55))
            }
        }
        .frame(maxHeight: .infinity)
        .contentShape(Rectangle())
        .onTapGesture {
            if app.hasSession { showCharacterStats = true } else { showLogin = true }
        }
        .embossedPanel(cornerRadius: 20, fill: paper)
    }

    private var activeSummary: some View {
        VStack(spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(app.activity?.localizedTitle ?? "Selecione")
                    .font(.system(size: 24, weight: .semibold, design: .rounded))
                    .foregroundStyle(ink)
                    .lineLimit(1)
                Spacer()
                Text("\(app.stats.successes)/\(app.activity == nil ? app.goal : app.sessionGoal)")
                    .font(.system(size: 21, weight: .regular, design: .rounded))
                    .foregroundStyle(ink)
                    .monospacedDigit()
            }
            progressBeads
            HStack {
                Text(progressDetail)
                    .font(.system(size: 13.5, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.92))
                    .lineLimit(1)
                Spacer()
                Text(app.activity == nil ? "Aguardando atividade" : app.state.label)
                    .font(.system(size: 13.5, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.82))
                     .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
        }
        .padding(.horizontal, 6)
    }

    private var progressDetail: String {
        guard app.activity != nil else { return "Progresso 0/\(app.goal)" }
        return "Progresso \(app.stats.successes)/\(app.sessionGoal)"
    }

    private var progressBeads: some View {
        let filled: Int = {
            guard app.stats.successes > 0 else { return 0 }
            return max(1, min(12, Int(ceil(app.progress * 12.0))))
        }()
        return HStack(spacing: 8) {
            ForEach(0..<12, id: \.self) { index in
                Circle()
                    .fill(index < filled ? copper : Color(red: 0.83, green: 0.81, blue: 0.76))
                    .frame(width: 19, height: 19)
                    .overlay(Circle().stroke(index < filled ? copper.opacity(0.9) : ink.opacity(0.13), lineWidth: 1))
                    .shadow(color: .white.opacity(index < filled ? 0.35 : 0.8), radius: 1, x: -1, y: -1)
                    .shadow(color: .black.opacity(0.16), radius: 1.5, x: 1, y: 1)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 5)
        .padding(.horizontal, 7)
        .background(
            Capsule().fill(Color(red: 0.87, green: 0.85, blue: 0.80))
                .shadow(color: .black.opacity(0.15), radius: 2, x: 1, y: 1)
        )
    }

    private var visibleModes: [ActivityMode] {
        ActivityMode.allCases
    }

    private var activitySelector: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 4), count: 5)
        return LazyVGrid(columns: columns, spacing: 8) {
            ForEach(visibleModes) { mode in resourceTile(mode) }
        }
        .padding(.horizontal, 0)
        .padding(.vertical, 5)
        .frame(maxHeight: .infinity)
    }

    @ViewBuilder
    private func resourceTile(_ mode: ActivityMode) -> some View {
        let tile = Button {
            guard app.activity == nil else { return }
            if mode == .fishing {
                showBaitPicker = true
            } else {
                app.start(mode)
            }
        } label: {
            VStack(spacing: 4) {
                Image(activitySprite(mode))
                    .resizable()
                    .scaledToFit()
                    .frame(width: 42, height: 42)
                    .shadow(color: .black.opacity(0.20), radius: 1.2, x: 1, y: 1)
                Text(mode.localizedTitle)
                    .font(.system(size: 12.2, weight: .medium, design: .rounded))
                    .foregroundStyle(ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                if mode == .fishing {
                    Text(shortBaitName)
                        .font(.system(size: 8.5, weight: .medium, design: .rounded))
                        .foregroundStyle(ink.opacity(0.55))
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 68)
        }
        .buttonStyle(.plain)
        .disabled(app.activity != nil)
        .opacity(app.activity == nil ? 1 : 0.68)

        if mode == .fishing {
            tile.contextMenu {
                ForEach(FishingBait.allCases) { bait in
                    Button {
                        app.selectedFishingBait = bait
                    } label: {
                        if app.selectedFishingBait == bait {
                            Label(bait.displayName, systemImage: "checkmark")
                        } else {
                            Text(bait.displayName)
                        }
                    }
                }
            }
        } else {
            tile
        }
    }

    private var shortBaitName: String {
        switch app.selectedFishingBait {
        case .feather: "Feather"
        case .trout: "Trout"
        case .bass: "Bass"
        case .tuna: "Tuna"
        case .squid: "Squid"
        }
    }

    private func activitySprite(_ mode: ActivityMode) -> String {
        switch mode {
        case .tree: "EmbossWood"
        case .coal: "EmbossCoal"
        case .stone: "EmbossStone"
        case .iron: "EmbossIron"
        case .silver: "EmbossSilver"
        case .cacti: "EmbossCacti"
        case .fishing: "EmbossFishing"
        case .chicken: "EmbossChicken"
        case .zombie: "EmbossZombie"
        case .dragon: "EmbossDragon"
        }
    }

    private var statsSection: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("STATS")
                .font(.system(size: 21, weight: .semibold, design: .rounded))
                .foregroundStyle(ink)
            HStack(alignment: .top, spacing: 10) {
                VStack(spacing: 4) {
                    ForEach(CharacterSkill.allCases) { skill in skillRow(skill) }
                    Divider().overlay(ink.opacity(0.28))
                    HStack(spacing: 9) {
                        Text("Total Level")
                            .font(.system(size: 15, weight: .medium, design: .rounded))
                            .foregroundStyle(ink)
                            .frame(width: 76, alignment: .leading)
                        skillBar(progress: Double(app.characterProfile.totalLevel) / 40.0).frame(height: 15)
                        Text("\(app.characterProfile.totalLevel)")
                            .font(.system(size: 15, weight: .medium, design: .rounded))
                            .foregroundStyle(ink)
                            .frame(width: 32, alignment: .trailing)
                    }
                }
                .frame(maxWidth: .infinity)
                Rectangle().fill(ink.opacity(0.22)).frame(width: 1).padding(.vertical, 3)
                telemetryColumn.frame(width: 154)
            }
        }
        .padding(10)
        .embossedPanel(cornerRadius: 18, fill: paper)
    }

    private func skillRow(_ skill: CharacterSkill) -> some View {
        let level = app.characterProfile.skills.level(for: skill)
        return HStack(spacing: 9) {
            Text(skill.localizedName)
                .font(.system(size: 13.5, weight: .medium, design: .rounded))
                .foregroundStyle(ink)
                .frame(width: 95, alignment: .leading)
                .lineLimit(1)
            skillBar(progress: Double(level) / 40.0).frame(height: 15)
            Text("\(level)/40")
                .font(.system(size: 13.5, weight: .medium, design: .rounded))
                .foregroundStyle(ink.opacity(0.9))
                .monospacedDigit()
                .frame(width: 48, alignment: .trailing)
        }
    }

    private func skillBar(progress: Double) -> some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color(red: 0.83, green: 0.81, blue: 0.76))
                    .shadow(color: .black.opacity(0.16), radius: 1.6, x: 1, y: 1)
                Capsule()
                    .fill(copper)
                    .frame(width: max(8, proxy.size.width * max(0, min(1, progress))))
                    .overlay(Capsule().stroke(Color.white.opacity(0.16), lineWidth: 0.8))
                    .shadow(color: .black.opacity(0.14), radius: 1, x: 1, y: 1)
            }
        }
    }

    private var telemetryColumn: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Spacer()
                Image(systemName: "mountain.2.fill")
                    .font(.system(size: 36, weight: .medium))
                    .foregroundStyle(Color(red: 0.39, green: 0.43, blue: 0.34))
                    .shadow(color: .black.opacity(0.20), radius: 1, x: 1, y: 1)
                Spacer()
            }
            telemetryLine("Região", app.world.serverRegion ?? app.player.region)
            telemetryLine("Posição", String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z))
            telemetryLine("Recursos", "\(app.resourceCount)")
            telemetryLine("Mobs", "\(app.mobCount)")
            Text("Último evento")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(ink.opacity(0.9))
            Text(app.stats.lastEvent.isEmpty ? "—" : app.stats.lastEvent)
                .font(.system(size: 11.5, weight: .regular, design: .rounded))
                .foregroundStyle(ink.opacity(0.78))
                .lineLimit(1)
                .minimumScaleFactor(0.74)
        }
    }

    private func telemetryLine(_ title: String, _ value: String) -> some View {
        HStack(spacing: 4) {
            Text(title).font(.system(size: 12, weight: .medium, design: .rounded))
            Text(value)
                .font(.system(size: 12, weight: .regular, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
        .foregroundStyle(ink.opacity(0.88))
    }

    private var sessionMetrics: some View {
        HStack(spacing: 0) {
            goalMetric
            metricDivider
            sessionMetric(title: "Sucessos", value: "\(app.stats.successes)")
            metricDivider
            sessionMetric(title: "Falhas", value: "\(app.stats.failures)")
            metricDivider
            sessionMetric(title: "Tentativas", value: "\(app.stats.attempts)")
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 4)
        .embossedPanel(cornerRadius: 16, fill: paper)
    }

    private var goalMetric: some View {
        VStack(spacing: 2) {
            Text("Meta da sessão")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(ink.opacity(0.84))
                .lineLimit(1)
                .minimumScaleFactor(0.76)
            if app.activity == nil {
                TextField("", value: $app.goal, format: .number)
                    .keyboardType(.numberPad)
                    .focused($goalFieldFocused)
                    .font(.system(size: 24, weight: .medium, design: .rounded))
                    .foregroundStyle(ink)
                    .multilineTextAlignment(.center)
                    .monospacedDigit()
            } else {
                Text("\(app.sessionGoal)")
                    .font(.system(size: 24, weight: .medium, design: .rounded))
                    .foregroundStyle(ink)
                    .monospacedDigit()
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func sessionMetric(title: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(title)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(ink.opacity(0.84))
            Text(value)
                .font(.system(size: 24, weight: .medium, design: .rounded))
                .foregroundStyle(ink)
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity)
    }

    private var metricDivider: some View {
        Rectangle().fill(ink.opacity(0.22)).frame(width: 1, height: 52)
    }

    private var pauseButton: some View {
        Button {
            if app.activity != nil { app.stop() }
        } label: {
            HStack(spacing: 22) {
                Image(systemName: "stop.fill").font(.system(size: 25, weight: .semibold))
                Text(app.activity == nil ? "PRONTO" : "PARAR")
                    .font(.system(size: 24, weight: .semibold, design: .rounded))
            }
            .foregroundStyle(Color(red: 0.92, green: 0.88, blue: 0.82))
            .frame(maxWidth: .infinity)
            .frame(height: 74)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(app.activity == nil ? copper.opacity(0.62) : copper)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(ink.opacity(0.65), lineWidth: 1.4)
            )
            .shadow(color: .white.opacity(0.65), radius: 1.4, x: -1.5, y: -1.5)
            .shadow(color: .black.opacity(0.26), radius: 2.5, x: 2, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(app.activity == nil)
        .opacity(app.activity == nil ? 0.62 : 1)
        .accessibilityLabel(app.activity == nil ? "Nenhuma atividade em execução" : "Encerrar atividade")
    }

    private var bottomNavigation: some View {
        HStack(spacing: 0) {
            navButton(title: "STATS", icon: "chart.bar.fill") {
                if app.hasSession { showCharacterStats = true } else { showLogin = true }
            }
            navDivider
            navButton(title: "QUESTS", icon: "list.bullet.rectangle") {
                if app.hasSession { showDailyQuests = true } else { showLogin = true }
            }
            navDivider
            navButton(title: "SESSÃO", icon: "slider.horizontal.3") { showLogin = true }
        }
        .frame(height: 58)
        .padding(.horizontal, 2)
        .embossedPanel(cornerRadius: 14, fill: paper)
    }

    private func navButton(title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon).font(.system(size: 22, weight: .medium))
                Text(title).font(.system(size: 15, weight: .medium, design: .rounded))
            }
            .foregroundStyle(ink)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(.plain)
    }

    private var navDivider: some View {
        Rectangle().fill(ink.opacity(0.25)).frame(width: 1, height: 34)
    }

    private var fullLogButton: some View {
        Button { showFullLog = true } label: {
            HStack(spacing: 12) {
                Image(systemName: "doc.text").font(.system(size: 22, weight: .medium))
                Text("Log completo").font(.system(size: 16, weight: .medium, design: .rounded))
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 18, weight: .semibold))
            }
            .foregroundStyle(ink)
            .padding(.horizontal, 18)
            .frame(height: 52)
        }
        .buttonStyle(.plain)
        .embossedPanel(cornerRadius: 14, fill: paper)
    }
}

private struct PaperTexture: View {
    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.94, green: 0.925, blue: 0.89),
                    paper,
                    Color(red: 0.88, green: 0.865, blue: 0.825)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Canvas { context, size in
                for i in 0..<260 {
                    let x = CGFloat((i * 73) % 997) / 997.0 * size.width
                    let y = CGFloat((i * 149) % 991) / 991.0 * size.height
                    let radius = CGFloat((i % 4) + 1) * 0.28
                    let rect = CGRect(x: x, y: y, width: radius, height: radius)
                    context.fill(Path(ellipseIn: rect), with: .color(.black.opacity(0.022)))
                }
            }
            .blendMode(.multiply)
            .allowsHitTesting(false)
        }
        .ignoresSafeArea()
    }
}

private struct EmbossedPanelModifier: ViewModifier {
    let cornerRadius: CGFloat
    let fill: Color
    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(fill)
                    .shadow(color: .white.opacity(0.85), radius: 2, x: -2, y: -2)
                    .shadow(color: .black.opacity(0.17), radius: 3, x: 2, y: 2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .stroke(
                        LinearGradient(
                            colors: [.white.opacity(0.72), .black.opacity(0.17)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
            )
    }
}

private extension View {
    func embossedPanel(cornerRadius: CGFloat, fill: Color) -> some View {
        modifier(EmbossedPanelModifier(cornerRadius: cornerRadius, fill: fill))
    }
}

private struct DailyQuestsView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.dismiss) private var dismiss

    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)
    private let ink = Color(red: 0.16, green: 0.15, blue: 0.14)
    private let copper = Color(red: 0.67, green: 0.34, blue: 0.23)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { proxy in
                let designWidth: CGFloat = 430
                let designHeight: CGFloat = 860
                let scale = min(proxy.size.width / designWidth, proxy.size.height / designHeight)

                VStack(spacing: 12) {
                    HStack {
                        Button("Fechar") { dismiss() }
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                            .foregroundStyle(ink)
                        Spacer()
                        Text("QUESTS")
                            .font(.system(size: 23, weight: .bold, design: .rounded))
                            .foregroundStyle(ink)
                        Spacer()
                        Button {
                            Task { await app.refreshDailyQuests() }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundStyle(ink)
                        }
                    }
                    .padding(.horizontal, 6)
                    .frame(height: 42)

                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("DAILY QUESTS")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                            Text("Dados oficiais do Kintara")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(ink.opacity(0.58))
                        }
                        Spacer()
                        if app.dailyQuestsLoading { ProgressView().tint(copper) }
                    }
                    .foregroundStyle(ink)
                    .padding(.horizontal, 4)

                    if let error = app.dailyQuestsError {
                        Text(error)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(copper)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    ForEach(app.dailyQuests.prefix(3)) { quest in
                        questCard(quest)
                    }

                    if !app.dailyQuestsLoading && app.dailyQuests.isEmpty && app.dailyQuestsError == nil {
                        Text("Nenhuma Daily Quest publicada pelo servidor.")
                            .font(.system(size: 13.5, weight: .medium, design: .rounded))
                            .foregroundStyle(ink.opacity(0.62))
                            .frame(maxWidth: .infinity)
                            .padding(24)
                            .embossedPanel(cornerRadius: 18, fill: paper)
                    }

                    Spacer(minLength: 2)

                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("RESET")
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .foregroundStyle(ink.opacity(0.55))
                            Text("00:00 UTC")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .foregroundStyle(ink)
                        }
                        Spacer()
                        if let day = app.dailyQuestDay {
                            Text(day)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(ink.opacity(0.58))
                        }
                    }
                    .padding(14)
                    .embossedPanel(cornerRadius: 16, fill: paper)
                }
                .padding(16)
                .frame(width: designWidth, height: designHeight, alignment: .top)
                .scaleEffect(scale, anchor: .top)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
        }
        .preferredColorScheme(.light)
        .task { await app.refreshDailyQuests() }
    }

    private func questCard(_ quest: DailyQuest) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(quest.label)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                    .foregroundStyle(ink)
                    .lineLimit(1)
                Spacer()
                Text(quest.claimed ? "RESGATADA" : (quest.isComplete ? "CONCLUÍDA" : "ATIVA"))
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(copper)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color(red: 0.82, green: 0.80, blue: 0.75))
                    Capsule().fill(copper)
                        .frame(width: max(0, geo.size.width * quest.progressFraction))
                }
            }
            .frame(height: 8)

            HStack {
                Text("\(quest.progress) / \(quest.target)")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                Spacer()
                Text(quest.kind)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.5))
            }
            .foregroundStyle(ink)

            Label(quest.rewardSummary, systemImage: "sparkles")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(copper)
                .lineLimit(1)
        }
        .padding(14)
        .embossedPanel(cornerRadius: 18, fill: paper)
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

        // Exact base hat assets captured from pc_hatHolder.
        if a.hat > 0 && a.hat <= 9 {
            let holder = SCNNode()
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

    private let paper = Color(red: 0.91, green: 0.895, blue: 0.855)
    private let ink = Color(red: 0.16, green: 0.15, blue: 0.14)
    private let copper = Color(red: 0.67, green: 0.34, blue: 0.23)

    var body: some View {
        ZStack {
            PaperTexture()
            GeometryReader { proxy in
                let designWidth: CGFloat = 430
                let designHeight: CGFloat = 860
                let scale = min(proxy.size.width / designWidth, proxy.size.height / designHeight)

                VStack(spacing: 12) {
                    HStack {
                        Button("Fechar") { dismiss() }
                            .font(.system(size: 15, weight: .semibold, design: .rounded))
                        Spacer()
                        Text("STATS")
                            .font(.system(size: 23, weight: .bold, design: .rounded))
                        Spacer()
                        Button {
                            Task { await app.refreshCharacterProfile(force: true) }
                        } label: {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 18, weight: .bold))
                        }
                    }
                    .foregroundStyle(ink)
                    .padding(.horizontal, 6)
                    .frame(height: 42)

                    HStack(spacing: 14) {
                        ZStack {
                            CharacterVoxel3DView(appearance: app.characterProfile.appearance)
                                .padding(5)
                        }
                        .frame(width: 104, height: 126)
                        .embossedPanel(cornerRadius: 18, fill: paper)

                        VStack(alignment: .leading, spacing: 6) {
                            Text(app.characterProfile.displayName)
                                .font(.system(size: 25, weight: .bold, design: .rounded))
                                .foregroundStyle(ink)
                                .lineLimit(1)
                            Text("Lvl \(app.characterProfile.totalLevel)")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .foregroundStyle(copper)
                            HStack(spacing: 7) {
                                Circle()
                                    .fill(app.hasSession ? Color(red: 0.42, green: 0.54, blue: 0.39) : .gray)
                                    .frame(width: 9, height: 9)
                                Text(app.hasSession ? "Conta conectada" : "Sem sessão")
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                            }
                            .foregroundStyle(ink.opacity(0.72))
                        }
                        Spacer()
                    }

                    if app.characterProfileLoading && !app.characterProfile.loaded {
                        ProgressView("Carregando Stats…").tint(copper)
                        Spacer()
                    } else {
                        VStack(spacing: 8) {
                            ForEach(CharacterSkill.allCases) { skill in
                                statRow(skill)
                            }
                        }
                        .padding(14)
                        .embossedPanel(cornerRadius: 20, fill: paper)

                        HStack {
                            Text("Total Level")
                                .font(.system(size: 19, weight: .bold, design: .rounded))
                            Spacer()
                            Text("\(app.characterProfile.totalLevel)")
                                .font(.system(size: 28, weight: .bold, design: .rounded))
                                .foregroundStyle(copper)
                        }
                        .foregroundStyle(ink)
                        .padding(.horizontal, 18)
                        .frame(height: 66)
                        .embossedPanel(cornerRadius: 18, fill: paper)
                        Spacer(minLength: 0)
                    }
                }
                .padding(16)
                .frame(width: designWidth, height: designHeight, alignment: .top)
                .scaleEffect(scale, anchor: .top)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
        }
        .preferredColorScheme(.light)
        .task { await app.refreshCharacterProfile(force: true) }
    }

    private func statRow(_ skill: CharacterSkill) -> some View {
        let stats = app.characterProfile.skills
        let level = stats.level(for: skill)
        return VStack(spacing: 5) {
            HStack {
                Text(skill.localizedName)
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(ink)
                    .frame(width: 86, alignment: .leading)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color(red: 0.82, green: 0.80, blue: 0.75))
                        Capsule().fill(copper)
                            .frame(width: max(6, geo.size.width * stats.progress(for: skill)))
                    }
                }
                .frame(height: 12)
                Text("\(level)/40")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(ink)
                    .monospacedDigit()
                    .frame(width: 42, alignment: .trailing)
            }
            HStack {
                Spacer().frame(width: 94)
                Text("\(stats.currentLevelXP(for: skill)) / \(stats.currentLevelXPGoal(for: skill)) XP")
                    .font(.system(size: 10.5, weight: .medium, design: .rounded))
                    .foregroundStyle(ink.opacity(0.55))
                    .monospacedDigit()
                Spacer()
            }
        }
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
