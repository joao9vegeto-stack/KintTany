import SwiftUI

struct KintTanyDashboard: View {
    @EnvironmentObject private var app: AppStore
    @FocusState private var goalFieldFocused: Bool

    let onOpenSession: () -> Void
    let onOpenFullLog: () -> Void

    private let activityColumns = Array(
        repeating: GridItem(.flexible(), spacing: 6),
        count: 5
    )

    var body: some View {
        ZStack {
            DashboardBackground()

            ScrollView {
                LazyVStack(spacing: 12) {
                    masthead
                    connectionStrip
                    activeActivityHero
                    controlsRow
                    activitySelector
                    informationPanels
                    eventLogPanel
                    footer
                }
                .padding(.horizontal, 10)
                .padding(.top, 6)
                .padding(.bottom, 30)
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
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "78"
    }

    // MARK: - Masthead

    private var masthead: some View {
        ZStack(alignment: .bottomLeading) {
            Image("ActivityZombie")
                .resizable()
                .scaledToFill()
                .frame(height: 154)
                .clipped()

            LinearGradient(
                colors: [
                    KintTanyTheme.backgroundBottom.opacity(0.35),
                    KintTanyTheme.backgroundBottom.opacity(0.78),
                    KintTanyTheme.backgroundBottom.opacity(0.98)
                ],
                startPoint: .topTrailing,
                endPoint: .bottomLeading
            )

            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("KintTany")
                        .font(.system(size: 42, weight: .black, design: .rounded))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [Color.yellow, KintTanyTheme.gold, KintTanyTheme.orange],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .shadow(color: .black, radius: 0, x: 2, y: 3)

                    Text("v\(appVersion)")
                        .font(.system(size: 12, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.cyan)
                }

                Text("PAINEL DE CONTROLE")
                    .font(.system(size: 13, weight: .black, design: .monospaced))
                    .tracking(2.0)
                    .foregroundStyle(.white)

                Text("JOGUE MAIS • TRABALHE MENOS")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .tracking(1.2)
                    .foregroundStyle(KintTanyTheme.mutedText)
            }
            .padding(14)

            VStack(alignment: .trailing, spacing: 5) {
                Image(systemName: "crown.fill")
                    .foregroundStyle(KintTanyTheme.gold)
                Text("BUILD \(buildNumber)")
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.cyan)
            }
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
        }
        .frame(height: 154)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(KintTanyTheme.cyan.opacity(0.5), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
    }

    private var connectionStrip: some View {
        PixelPanel(accent: connectionPresentation.color) {
            HStack(spacing: 8) {
                Button(action: onOpenSession) {
                    connectionDatum
                }
                .buttonStyle(.plain)

                stripDivider

                TimelineView(.periodic(from: .now, by: 1)) { context in
                    stripDatum(
                        icon: "clock.fill",
                        label: "Sessão",
                        value: sessionDurationText(at: context.date),
                        color: KintTanyTheme.cyan
                    )
                }

                stripDivider

                stripDatum(
                    icon: "globe.americas.fill",
                    label: "Mundo",
                    value: currentRegion,
                    color: .blue
                )
            }
        }
    }

    private var connectionDatum: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(connectionPresentation.color)
                .frame(width: 12, height: 12)
                .shadow(color: connectionPresentation.color, radius: 5)

            VStack(alignment: .leading, spacing: 1) {
                Text(connectionPresentation.text.uppercased())
                    .font(.system(size: 11, weight: .black, design: .monospaced))
                    .foregroundStyle(connectionPresentation.color)
                Text(app.hasSession ? "KintTany Online" : "Abrir sessão")
                    .font(.system(size: 8, weight: .semibold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func stripDatum(icon: String, label: String, value: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 1) {
                Text(label.uppercased())
                    .font(.system(size: 7, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text(value)
                    .font(.system(size: 10, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var stripDivider: some View {
        Rectangle()
            .fill(KintTanyTheme.border.opacity(0.42))
            .frame(width: 1, height: 34)
    }

    // MARK: - Current activity

    private var activeActivityHero: some View {
        Group {
            if let mode = app.activity {
                activeHero(for: mode)
            } else {
                idleHero
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke((app.activity?.accent ?? KintTanyTheme.cyan).opacity(0.7), lineWidth: 1.2)
        )
        .shadow(color: (app.activity?.accent ?? KintTanyTheme.cyan).opacity(0.18), radius: 12, y: 5)
    }

    private func activeHero(for mode: ActivityMode) -> some View {
        ZStack(alignment: .bottom) {
            Image(mode.artworkName)
                .resizable()
                .scaledToFill()
                .frame(height: 318)
                .clipped()

            LinearGradient(
                colors: [.black.opacity(0.02), .black.opacity(0.34), KintTanyTheme.backgroundBottom.opacity(0.97)],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 9) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("ATIVIDADE ATUAL", systemImage: mode.icon)
                            .font(.system(size: 9, weight: .black, design: .monospaced))
                            .tracking(1)
                            .foregroundStyle(KintTanyTheme.cyan)

                        Text(mode.localizedTitle.uppercased())
                            .font(.system(size: 34, weight: .black, design: .rounded))
                            .foregroundStyle(mode.accent)
                            .shadow(color: .black, radius: 2, y: 2)
                    }

                    Spacer()

                    liveRateChip
                }

                Spacer(minLength: 74)

                HStack(alignment: .bottom, spacing: 10) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(app.displayStatusMessage)
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white)
                            .lineLimit(2)

                        if let target = app.currentTarget {
                            Label(target, systemImage: "scope")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                .foregroundStyle(mode.accent)
                                .lineLimit(1)
                        }
                    }

                    Spacer(minLength: 4)

                    PixelStatusChip(text: app.state.label, color: mode.accent, systemImage: stateIcon)
                }

                PixelProgressBar(progress: app.progress, color: mode.accent)

                HStack(spacing: 11) {
                    PixelStat(value: "\(app.stats.successes)/\(app.sessionGoal)", label: "Meta", color: mode.accent)
                    PixelStat(value: "\(app.stats.attempts)", label: "Tentativas")

                    if mode == .chicken || mode.isWildCombat {
                        PixelStat(value: "\(app.stats.confirmedHits)", label: "Hits", color: KintTanyTheme.cyan)
                        PixelStat(value: "\(app.stats.kills)", label: "Kills", color: KintTanyTheme.gold)
                    } else {
                        PixelStat(value: "\(app.stats.failures)", label: "Falhas", color: KintTanyTheme.red)
                    }
                }

                Button(role: .destructive) {
                    app.stop()
                } label: {
                    Label("PARAR ATIVIDADE", systemImage: "stop.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.red))
            }
            .padding(14)
        }
        .frame(height: 318)
    }

    private var idleHero: some View {
        ZStack {
            Image("ActivityZombie")
                .resizable()
                .scaledToFill()
                .frame(height: 242)
                .clipped()
                .saturation(0.65)

            KintTanyTheme.backgroundBottom.opacity(0.76)

            VStack(spacing: 11) {
                PixelStatusChip(text: "ATIVIDADE ATUAL", color: KintTanyTheme.cyan, systemImage: "flag.fill")

                Text("ESCOLHA SUA MISSÃO")
                    .font(.system(size: 24, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)

                Text("As cenas e os dados mudam conforme a atividade real.")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .multilineTextAlignment(.center)

                PixelStatusChip(text: app.state.label, color: connectionPresentation.color, systemImage: stateIcon)
            }
            .padding(20)
        }
        .frame(height: 242)
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

    // MARK: - Session controls

    private var controlsRow: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 10) {
                sessionGoalPanel
                activityContextPanel
            }

            VStack(spacing: 10) {
                sessionGoalPanel
                activityContextPanel
            }
        }
    }

    private var sessionGoalPanel: some View {
        PixelPanel(accent: KintTanyTheme.gold) {
            VStack(alignment: .leading, spacing: 11) {
                DashboardSectionTitle(
                    title: "Meta da sessão",
                    subtitle: app.activity == nil ? "Quantidade desejada" : "Progresso atual",
                    accent: KintTanyTheme.gold
                )

                HStack(spacing: 7) {
                    compactGoalButton(systemImage: "minus") {
                        app.goal = max(1, app.goal - 1)
                    }

                    TextField("Meta", value: $app.goal, format: .number)
                        .keyboardType(.numberPad)
                        .focused($goalFieldFocused)
                        .font(.system(size: 22, weight: .black, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .padding(.vertical, 9)
                        .frame(maxWidth: .infinity)
                        .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 6))
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(goalFieldFocused ? KintTanyTheme.gold : KintTanyTheme.border.opacity(0.45), lineWidth: 1)
                        )
                        .disabled(app.activity != nil)

                    compactGoalButton(systemImage: "plus") {
                        app.goal = min(100_000, app.goal + 1)
                    }
                }

                if app.activity != nil {
                    PixelProgressBar(progress: app.progress, color: app.activity?.accent ?? KintTanyTheme.green)
                    Text("\(app.stats.successes) / \(app.sessionGoal)")
                        .font(.system(size: 9, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.mutedText)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func compactGoalButton(systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 14, weight: .black))
                .frame(width: 24, height: 24)
        }
        .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.border))
        .disabled(app.activity != nil)
    }

    @ViewBuilder
    private var activityContextPanel: some View {
        if app.activity == nil || app.activity == .fishing {
            fishingContextPanel
        } else {
            currentContextPanel
        }
    }

    private var fishingContextPanel: some View {
        PixelPanel(accent: KintTanyTheme.cyan) {
            VStack(alignment: .leading, spacing: 11) {
                DashboardSectionTitle(
                    title: "Isca / equipamento",
                    subtitle: "Configuração real de pesca",
                    accent: KintTanyTheme.cyan
                )

                Picker("Isca", selection: $app.selectedFishingBait) {
                    ForEach(FishingBait.allCases) { bait in
                        Text(bait.displayName).tag(bait)
                    }
                }
                .pickerStyle(.menu)
                .tint(KintTanyTheme.cyan)
                .disabled(app.activity != nil)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(KintTanyTheme.cyan.opacity(0.4), lineWidth: 1))

                Label(
                    app.selectedFishingBait.supportLabel,
                    systemImage: app.selectedFishingBait.isAutomationValidated ? "checkmark.shield.fill" : "exclamationmark.triangle.fill"
                )
                .font(.system(size: 8, weight: .semibold, design: .monospaced))
                .foregroundStyle(app.selectedFishingBait.isAutomationValidated ? KintTanyTheme.green : KintTanyTheme.gold)
                .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var currentContextPanel: some View {
        PixelPanel(accent: app.activity?.accent ?? KintTanyTheme.cyan) {
            VStack(alignment: .leading, spacing: 11) {
                DashboardSectionTitle(
                    title: "Contexto atual",
                    subtitle: app.activity?.activityDescription ?? "Atividade",
                    accent: app.activity?.accent ?? KintTanyTheme.cyan
                )

                contextLine(icon: "scope", label: "Alvo", value: app.currentTarget ?? "Aguardando")
                contextLine(icon: stateIcon, label: "Estado", value: app.state.label)
                contextLine(icon: "map.fill", label: "Região", value: currentRegion)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func contextLine(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(app.activity?.accent ?? KintTanyTheme.cyan)
                .frame(width: 15)
            Text(label.uppercased())
                .font(.system(size: 7, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.65)
        }
    }

    // MARK: - Activity selector

    private var activitySelector: some View {
        PixelPanel(accent: KintTanyTheme.cyan) {
            VStack(alignment: .leading, spacing: 11) {
                HStack(alignment: .top) {
                    DashboardSectionTitle(
                        title: "Selecionar atividade",
                        subtitle: "Uma atividade real por vez",
                        accent: KintTanyTheme.cyan
                    )
                    Spacer()
                    Text("10 MISSÕES")
                        .font(.system(size: 8, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.gold)
                }

                LazyVGrid(columns: activityColumns, spacing: 7) {
                    ForEach(ActivityMode.allCases) { mode in
                        compactActivityCard(mode)
                    }
                }
            }
        }
    }

    private func compactActivityCard(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        let unavailable = app.activity != nil && !selected

        return Button {
            app.start(mode)
        } label: {
            VStack(spacing: 4) {
                ZStack {
                    Image(mode.artworkName)
                        .resizable()
                        .scaledToFill()
                        .frame(height: 52)
                        .clipped()

                    LinearGradient(
                        colors: [.clear, .black.opacity(0.72)],
                        startPoint: .top,
                        endPoint: .bottom
                    )

                    Image(systemName: mode.icon)
                        .font(.system(size: 16, weight: .black))
                        .foregroundStyle(mode.accent)
                        .shadow(color: .black, radius: 2)
                }
                .clipShape(RoundedRectangle(cornerRadius: 5))

                Text(mode.localizedTitle)
                    .font(.system(size: 8, weight: .black, design: .rounded))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.62)
            }
            .padding(4)
            .background(selected ? mode.accent.opacity(0.22) : KintTanyTheme.panelDeep)
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(selected ? mode.accent : KintTanyTheme.border.opacity(0.52), lineWidth: selected ? 2 : 1)
            )
            .shadow(color: selected ? mode.accent.opacity(0.5) : .clear, radius: 5)
        }
        .buttonStyle(.plain)
        .disabled(unavailable || selected)
        .opacity(unavailable ? 0.42 : 1)
        .accessibilityLabel("Iniciar \(mode.localizedTitle)")
    }

    // MARK: - Real data panels

    private var informationPanels: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: 10) {
                telemetryPanel
                sessionStatistics
            }

            VStack(spacing: 10) {
                telemetryPanel
                sessionStatistics
            }
        }
    }

    private var telemetryPanel: some View {
        PixelPanel(accent: KintTanyTheme.cyan) {
            VStack(alignment: .leading, spacing: 10) {
                DashboardSectionTitle(
                    title: "Telemetria",
                    subtitle: "Dados do servidor",
                    accent: KintTanyTheme.cyan
                )

                telemetryRow(icon: "map.fill", label: "Região", value: currentRegion, color: KintTanyTheme.green)
                telemetryRow(
                    icon: "location.fill",
                    label: "Posição",
                    value: String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z),
                    color: KintTanyTheme.cyan
                )
                telemetryRow(icon: "square.stack.3d.up.fill", label: "Recursos", value: "\(app.resourceCount)", color: KintTanyTheme.gold)
                telemetryRow(icon: "figure.2", label: "Mobs", value: "\(app.mobCount)", color: KintTanyTheme.red)

                if !app.stats.lastEvent.isEmpty {
                    telemetryRow(icon: "waveform.path.ecg", label: "Evento", value: app.stats.lastEvent, color: KintTanyTheme.green)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func telemetryRow(icon: String, label: String, value: String, color: Color) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(color)
                .frame(width: 16)
            Text(label.uppercased())
                .font(.system(size: 7, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 3)
            Text(value)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
        }
        .padding(.vertical, 2)
    }

    private var sessionStatistics: some View {
        PixelPanel(accent: .indigo) {
            VStack(alignment: .leading, spacing: 10) {
                DashboardSectionTitle(
                    title: "Sessão",
                    subtitle: "Contadores reais",
                    accent: .indigo
                )

                statRow(label: "Tentativas", value: "\(app.stats.attempts)", color: .white)
                statRow(label: "Sucessos", value: "\(app.stats.successes)", color: KintTanyTheme.green)
                statRow(label: "Falhas", value: "\(app.stats.failures)", color: KintTanyTheme.red)
                statRow(label: "Erros", value: "\(app.stats.sessionErrors)", color: KintTanyTheme.orange)

                if let mode = app.activity, mode == .chicken || mode.isWildCombat {
                    statRow(label: "Hits", value: "\(app.stats.confirmedHits)", color: KintTanyTheme.cyan)
                    statRow(label: "Kills", value: "\(app.stats.kills)", color: KintTanyTheme.gold)
                }

                TimelineView(.periodic(from: .now, by: 1)) { context in
                    statRow(
                        label: "Ritmo",
                        value: app.formattedRatePerMinute(at: context.date),
                        color: KintTanyTheme.cyan
                    )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func statRow(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 6) {
            Rectangle()
                .fill(color)
                .frame(width: 5, height: 5)
            Text(label.uppercased())
                .font(.system(size: 7, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 3)
            Text(value)
                .font(.system(size: 10, weight: .black, design: .monospaced))
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
        }
        .padding(.vertical, 2)
    }

    // MARK: - Events

    private var eventLogPanel: some View {
        PixelPanel(accent: KintTanyTheme.border) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top) {
                    DashboardSectionTitle(
                        title: "Log de eventos",
                        subtitle: "Atividade e sistema",
                        accent: KintTanyTheme.border
                    )

                    Spacer()

                    Button(action: onOpenFullLog) {
                        Label("COMPLETO", systemImage: "doc.text.magnifyingglass")
                    }
                    .buttonStyle(PixelIconButtonStyle(color: KintTanyTheme.border))
                    .accessibilityLabel("Abrir log completo")
                }

                if app.logs.isEmpty {
                    Label("Nenhum evento registrado ainda", systemImage: "sparkles")
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.mutedText)
                        .padding(.vertical, 9)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(app.logs.suffix(6).enumerated()), id: \.offset) { index, line in
                            Text(line)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(eventColor(for: line))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 6)

                            if index < min(app.logs.count, 6) - 1 {
                                Divider().overlay(.white.opacity(0.05))
                            }
                        }
                    }
                    .padding(.horizontal, 9)
                    .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 7))
                }

                Text("Tokens, cookies e chaves permanecem ocultados.")
                    .font(.system(size: 7, weight: .medium, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
            }
        }
    }

    private func eventColor(for line: String) -> Color {
        if line.contains("✅") || line.localizedCaseInsensitiveContains("sucesso") { return KintTanyTheme.green }
        if line.contains("⚠️") || line.localizedCaseInsensitiveContains("falha") { return KintTanyTheme.gold }
        if line.contains("🛑") || line.localizedCaseInsensitiveContains("erro") { return KintTanyTheme.red }
        return .white.opacity(0.84)
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Image(systemName: "crown.fill")
                .foregroundStyle(KintTanyTheme.gold)
            Text("KintTany")
                .font(.system(size: 10, weight: .black, design: .monospaced))
            Spacer()
            Text("PEQUENAS AÇÕES • GRANDES CONQUISTAS")
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 12)
        .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(KintTanyTheme.border.opacity(0.42), lineWidth: 1))
    }

    // MARK: - Presentation helpers

    private var connectionPresentation: (text: String, color: Color) {
        if app.connected { return ("Conectado", KintTanyTheme.green) }
        switch app.state {
        case .connecting, .syncing: return ("Conectando", KintTanyTheme.orange)
        case .failed: return ("Erro", KintTanyTheme.red)
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
