import SwiftUI

struct KintTanyDashboard: View {
    @EnvironmentObject private var app: AppStore
    @FocusState private var goalFieldFocused: Bool

    let onOpenSession: () -> Void
    let onOpenFullLog: () -> Void

    private let columns = [
        GridItem(.flexible(), spacing: 11),
        GridItem(.flexible(), spacing: 11)
    ]

    var body: some View {
        ZStack {
            DashboardBackground()

            ScrollView {
                LazyVStack(spacing: 16) {
                    header
                    activeActivityHero
                    sessionGoalPanel

                    if app.activity == nil || app.activity == .fishing {
                        fishingContextPanel
                    }

                    activitySelector
                    telemetryPanel
                    sessionStatistics
                    eventLogPanel
                }
                .padding(.horizontal, 14)
                .padding(.top, 8)
                .padding(.bottom, 38)
            }
            .scrollIndicators(.hidden)
        }
        .preferredColorScheme(.dark)
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
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "3.3"
    }

    private var buildNumber: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "77"
    }

    private var header: some View {
        VStack(spacing: 13) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text("KintTany")
                            .font(.system(size: 28, weight: .black, design: .rounded))
                            .foregroundStyle(.white)
                        Text("v\(appVersion) • \(buildNumber)")
                            .font(.system(size: 9, weight: .black, design: .monospaced))
                            .foregroundStyle(KintTanyTheme.cyan)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 4)
                            .background(KintTanyTheme.cyan.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
                    }

                    Text("PAINEL DE AVENTURA")
                        .font(.system(size: 10, weight: .black, design: .monospaced))
                        .tracking(2.1)
                        .foregroundStyle(KintTanyTheme.mutedText)
                }

                Spacer(minLength: 4)

                Button(action: onOpenSession) {
                    Image(systemName: app.hasSession ? "person.crop.circle.badge.checkmark" : "person.crop.circle.badge.exclamationmark")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(app.hasSession ? Color.green : KintTanyTheme.gold)
                        .frame(width: 46, height: 46)
                        .background(KintTanyTheme.panelRaised, in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(KintTanyTheme.border.opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Abrir sessão")
            }

            HStack(spacing: 8) {
                PixelStatusChip(text: connectionPresentation.text, color: connectionPresentation.color)
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    headerDatum(icon: "clock.fill", text: sessionDurationText(at: context.date))
                }
                headerDatum(icon: "map.fill", text: currentRegion)
                Spacer(minLength: 0)
            }
        }
        .padding(.horizontal, 2)
    }

    private func headerDatum(icon: String, text: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(KintTanyTheme.cyan)
            Text(text)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .background(.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 7))
    }

    private var activeActivityHero: some View {
        Group {
            if let mode = app.activity {
                activeHero(for: mode)
            } else {
                idleHero
            }
        }
        .frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke((app.activity?.accent ?? KintTanyTheme.border).opacity(0.62), lineWidth: 1)
        )
        .shadow(color: (app.activity?.accent ?? .black).opacity(0.22), radius: 18, y: 8)
    }

    private func activeHero(for mode: ActivityMode) -> some View {
        ZStack(alignment: .bottom) {
            Image(mode.artworkName)
                .resizable()
                .scaledToFill()
                .frame(height: 320)
                .clipped()

            LinearGradient(
                colors: [.black.opacity(0.02), .black.opacity(0.46), KintTanyTheme.backgroundBottom.opacity(0.97)],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 11) {
                HStack {
                    PixelStatusChip(text: mode.categoryLabel, color: mode.accent, systemImage: mode.icon)
                    Spacer()
                    liveRateChip
                }

                Spacer(minLength: 70)

                Text(mode.localizedTitle.uppercased())
                    .font(.system(size: 31, weight: .black, design: .rounded))
                    .foregroundStyle(.white)
                    .shadow(color: .black, radius: 2, y: 2)

                Text(app.displayStatusMessage)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.9))
                    .lineLimit(2)

                if let target = app.currentTarget {
                    Label(target, systemImage: "scope")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(mode.accent)
                        .lineLimit(1)
                }

                HStack(spacing: 12) {
                    PixelStat(value: "\(app.stats.successes)/\(app.sessionGoal)", label: "Progresso", color: mode.accent)
                    PixelStat(value: "\(app.stats.failures)", label: "Falhas")
                    PixelStat(value: app.state.label, label: "Estado")
                }

                PixelProgressBar(progress: app.progress, color: mode.accent)

                Button(role: .destructive) {
                    app.stop()
                } label: {
                    Label("PARAR ATIVIDADE", systemImage: "stop.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PixelIconButtonStyle(color: .red))
            }
            .padding(16)
        }
        .frame(height: 320)
    }

    private var idleHero: some View {
        ZStack {
            LinearGradient(
                colors: [KintTanyTheme.panelRaised, KintTanyTheme.backgroundBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            Circle()
                .fill(KintTanyTheme.cyan.opacity(0.08))
                .frame(width: 190, height: 190)
                .blur(radius: 2)

            VStack(spacing: 14) {
                Image(systemName: "sparkles.rectangle.stack.fill")
                    .font(.system(size: 42, weight: .bold))
                    .foregroundStyle(KintTanyTheme.cyan)
                    .shadow(color: KintTanyTheme.cyan.opacity(0.6), radius: 12)

                Text("PRONTO PARA AVENTURA")
                    .font(.system(size: 20, weight: .black, design: .monospaced))

                Text("Escolha uma atividade abaixo para iniciar.")
                    .font(.subheadline)
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .multilineTextAlignment(.center)

                PixelStatusChip(text: app.state.label, color: connectionPresentation.color, systemImage: stateIcon)
            }
            .padding(24)
        }
        .frame(height: 250)
    }

    private var liveRateChip: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            PixelStatusChip(
                text: app.formattedRatePerMinute(at: context.date),
                color: .white,
                systemImage: "bolt.fill"
            )
        }
    }

    private var sessionGoalPanel: some View {
        PixelPanel(accent: KintTanyTheme.gold) {
            VStack(alignment: .leading, spacing: 14) {
                DashboardSectionTitle(
                    title: "Meta da sessão",
                    subtitle: app.activity == nil ? "Defina antes de iniciar" : "Bloqueada durante a atividade",
                    accent: KintTanyTheme.gold
                )

                HStack(spacing: 10) {
                    Button {
                        app.goal = max(1, app.goal - 1)
                    } label: {
                        Image(systemName: "minus")
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.border))
                    .disabled(app.activity != nil)

                    TextField("Meta", value: $app.goal, format: .number)
                        .keyboardType(.numberPad)
                        .focused($goalFieldFocused)
                        .font(.system(size: 27, weight: .black, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(.black.opacity(0.32), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(goalFieldFocused ? KintTanyTheme.gold : Color.white.opacity(0.1), lineWidth: 1)
                        )
                        .disabled(app.activity != nil)

                    Button {
                        app.goal = min(100_000, app.goal + 1)
                    } label: {
                        Image(systemName: "plus")
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.border))
                    .disabled(app.activity != nil)
                }

                if app.activity != nil {
                    PixelProgressBar(progress: app.progress, color: app.activity?.accent ?? KintTanyTheme.cyan)
                }
            }
        }
    }

    private var fishingContextPanel: some View {
        PixelPanel(accent: .cyan) {
            VStack(alignment: .leading, spacing: 12) {
                DashboardSectionTitle(
                    title: "Equipamento de pesca",
                    subtitle: "Isca selecionada para a próxima sessão",
                    accent: .cyan
                )

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
                .padding(.vertical, 8)
                .background(.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(.cyan.opacity(0.28), lineWidth: 1))

                HStack(spacing: 7) {
                    Image(systemName: app.selectedFishingBait.isAutomationValidated ? "checkmark.shield.fill" : "exclamationmark.triangle.fill")
                    Text(app.selectedFishingBait.supportLabel)
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(app.selectedFishingBait.isAutomationValidated ? Color.green : KintTanyTheme.gold)
            }
        }
    }

    private var activitySelector: some View {
        VStack(alignment: .leading, spacing: 12) {
            DashboardSectionTitle(
                title: "Selecionar atividade",
                subtitle: "Cada toque inicia uma sessão real",
                accent: KintTanyTheme.cyan
            )

            LazyVGrid(columns: columns, spacing: 11) {
                ForEach(ActivityMode.allCases) { mode in
                    activityCard(mode)
                }
            }
        }
    }

    private func activityCard(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        let unavailable = app.activity != nil && !selected

        return Button {
            app.start(mode)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                ZStack(alignment: .topTrailing) {
                    Image(mode.artworkName)
                        .resizable()
                        .scaledToFill()
                        .frame(maxWidth: .infinity)
                        .frame(height: 92)
                        .clipped()

                    LinearGradient(
                        colors: [.clear, .black.opacity(0.72)],
                        startPoint: .top,
                        endPoint: .bottom
                    )

                    PixelStatusChip(text: mode.categoryLabel, color: mode.accent)
                        .scaleEffect(0.82, anchor: .topTrailing)
                        .padding(6)
                }

                HStack(spacing: 8) {
                    Image(systemName: mode.icon)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(mode.accent)
                        .frame(width: 20)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(mode.localizedTitle)
                            .font(.system(size: 14, weight: .black, design: .rounded))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                        Text(selected ? app.state.label : mode.activityDescription)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(KintTanyTheme.mutedText)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 0)
                }
                .padding(10)
            }
            .background(KintTanyTheme.panel)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(selected ? mode.accent : KintTanyTheme.border.opacity(0.34), lineWidth: selected ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(unavailable || selected)
        .opacity(unavailable ? 0.46 : 1)
        .accessibilityLabel("Iniciar \(mode.localizedTitle)")
    }

    private var telemetryPanel: some View {
        PixelPanel(accent: KintTanyTheme.cyan) {
            VStack(alignment: .leading, spacing: 14) {
                DashboardSectionTitle(
                    title: "Telemetria",
                    subtitle: "Estado autoritativo recebido do servidor",
                    accent: KintTanyTheme.cyan
                )

                LazyVGrid(columns: columns, spacing: 10) {
                    telemetryCell(icon: "map.fill", label: "Região", value: currentRegion)
                    telemetryCell(
                        icon: "location.fill",
                        label: "Posição",
                        value: String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z)
                    )
                    telemetryCell(icon: "square.stack.3d.up.fill", label: "Recursos", value: "\(app.resourceCount)")
                    telemetryCell(icon: "figure.2", label: "Mobs", value: "\(app.mobCount)")
                }

                if !app.stats.lastEvent.isEmpty {
                    HStack(alignment: .top, spacing: 9) {
                        Image(systemName: "waveform.path.ecg")
                            .foregroundStyle(KintTanyTheme.cyan)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("ÚLTIMO EVENTO")
                                .font(.system(size: 9, weight: .black, design: .monospaced))
                                .foregroundStyle(KintTanyTheme.mutedText)
                            Text(app.stats.lastEvent)
                                .font(.caption.monospaced())
                                .lineLimit(3)
                        }
                    }
                    .padding(11)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.black.opacity(0.28), in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
    }

    private func telemetryCell(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 9) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(KintTanyTheme.cyan)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(label.uppercased())
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text(value)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .lineLimit(1)
                    .minimumScaleFactor(0.68)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(.black.opacity(0.27), in: RoundedRectangle(cornerRadius: 8))
    }

    private var sessionStatistics: some View {
        PixelPanel(accent: .indigo) {
            VStack(alignment: .leading, spacing: 14) {
                DashboardSectionTitle(
                    title: "Estatísticas da sessão",
                    subtitle: "Somente contadores reais da execução atual",
                    accent: .indigo
                )

                HStack(spacing: 10) {
                    PixelStat(value: "\(app.stats.attempts)", label: "Tentativas", color: .white)
                    PixelStat(value: "\(app.stats.successes)", label: "Sucessos", color: .green)
                    PixelStat(value: "\(app.stats.failures)", label: "Falhas", color: .red)
                }

                if let mode = app.activity, mode == .chicken || mode.isWildCombat {
                    Divider().overlay(.white.opacity(0.08))
                    HStack(spacing: 10) {
                        PixelStat(value: "\(app.stats.confirmedHits)", label: "Hits", color: mode.accent)
                        PixelStat(value: "\(app.stats.kills)", label: "Kills", color: KintTanyTheme.gold)
                        PixelStat(value: "\(app.stats.sessionErrors)", label: "Erros", color: .orange)
                    }
                }
            }
        }
    }

    private var eventLogPanel: some View {
        PixelPanel(accent: KintTanyTheme.border) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top) {
                    DashboardSectionTitle(
                        title: "Eventos",
                        subtitle: "Resumo real da sessão",
                        accent: KintTanyTheme.border
                    )

                    Spacer()

                    Button(action: onOpenFullLog) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .frame(width: 18, height: 18)
                    }
                    .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.border))
                    .accessibilityLabel("Abrir log completo")
                }

                if app.logs.isEmpty {
                    Label("Nenhum evento registrado ainda", systemImage: "sparkles")
                        .font(.caption)
                        .foregroundStyle(KintTanyTheme.mutedText)
                        .padding(.vertical, 8)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(app.logs.suffix(5).enumerated()), id: \.offset) { index, line in
                            Text(line)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(.white.opacity(0.84))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 8)

                            if index < min(app.logs.count, 5) - 1 {
                                Divider().overlay(.white.opacity(0.06))
                            }
                        }
                    }
                    .padding(.horizontal, 10)
                    .background(.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
                }

                Text("Tokens, cookies e chaves continuam ocultados no diagnóstico.")
                    .font(.caption2)
                    .foregroundStyle(KintTanyTheme.mutedText)
            }
        }
    }

    private var connectionPresentation: (text: String, color: Color) {
        if app.connected { return ("Online", .green) }
        switch app.state {
        case .connecting, .syncing: return ("Conectando", .orange)
        case .failed: return ("Erro", .red)
        default: return ("Offline", KintTanyTheme.mutedText)
        }
    }

    private var currentRegion: String {
        app.world.serverRegion ?? app.player.region
    }

    private func sessionDurationText(at now: Date) -> String {
        guard app.activity != nil, let startedAt = app.stats.startedAt else { return "00:00" }
        let elapsed = max(0, Int(now.timeIntervalSince(startedAt)))
        return String(format: "%02d:%02d", elapsed / 60, elapsed % 60)
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
