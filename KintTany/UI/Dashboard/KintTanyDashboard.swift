import SwiftUI

struct KintTanyDashboard: View {
    @EnvironmentObject private var app: AppStore
    @FocusState private var goalFieldFocused: Bool

    let onOpenSession: () -> Void
    let onOpenFullLog: () -> Void

    private let activityColumns = Array(
        repeating: GridItem(.flexible(), spacing: 3),
        count: 5
    )

    var body: some View {
        GeometryReader { proxy in
            let gap: CGFloat = proxy.size.height < 700 ? 3 : 4
            let outerPadding: CGFloat = 6
            let available = max(560, proxy.size.height - (outerPadding * 2) - (gap * 6))

            ZStack {
                DashboardBackground()

                VStack(spacing: gap) {
                    masthead
                        .frame(height: available * 0.115)

                    connectionStrip
                        .frame(height: available * 0.075)

                    activeActivityHero
                        .frame(height: available * 0.22)

                    controlsRow
                        .frame(height: available * 0.13)

                    activitySelector
                        .frame(height: available * 0.16)

                    informationPanels
                        .frame(height: available * 0.14)

                    eventLogPanel
                        .frame(height: available * 0.15)
                }
                .padding(.horizontal, outerPadding)
                .padding(.vertical, outerPadding)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
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
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "79"
    }

    // MARK: - Cabeçalho compacto

    private var masthead: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Image("ActivityZombie")
                    .resizable()
                    .scaledToFill()
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()

                LinearGradient(
                    colors: [
                        KintTanyTheme.backgroundBottom.opacity(0.25),
                        KintTanyTheme.backgroundBottom.opacity(0.72),
                        KintTanyTheme.backgroundBottom.opacity(0.96)
                    ],
                    startPoint: .trailing,
                    endPoint: .leading
                )

                HStack(alignment: .bottom, spacing: 8) {
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("KintTany")
                                .font(.system(size: 28, weight: .black, design: .rounded))
                                .foregroundStyle(
                                    LinearGradient(
                                        colors: [Color.yellow, KintTanyTheme.gold, KintTanyTheme.orange],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    )
                                )
                                .shadow(color: .black, radius: 0, x: 1, y: 2)

                            Text("v\(appVersion)")
                                .font(.system(size: 9, weight: .black, design: .monospaced))
                                .foregroundStyle(KintTanyTheme.cyan)
                        }

                        Text("JOGUE MAIS, TRABALHE MENOS")
                            .font(.system(size: 7, weight: .bold, design: .monospaced))
                            .tracking(0.8)
                            .foregroundStyle(.white.opacity(0.88))
                            .lineLimit(1)
                    }

                    Spacer(minLength: 4)

                    VStack(alignment: .trailing, spacing: 1) {
                        Image(systemName: "crown.fill")
                            .font(.system(size: 12, weight: .black))
                            .foregroundStyle(KintTanyTheme.gold)
                        Text("BUILD \(buildNumber)")
                            .font(.system(size: 7, weight: .black, design: .monospaced))
                            .foregroundStyle(KintTanyTheme.cyan)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .frame(maxHeight: .infinity, alignment: .bottom)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(KintTanyTheme.cyan.opacity(0.56), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
    }

    private var connectionStrip: some View {
        PixelPanel(accent: connectionPresentation.color, inset: 6) {
            HStack(spacing: 5) {
                Button(action: onOpenSession) {
                    compactConnectionDatum
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
            .frame(maxHeight: .infinity)
        }
    }

    private var compactConnectionDatum: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(connectionPresentation.color)
                .frame(width: 10, height: 10)
                .shadow(color: connectionPresentation.color, radius: 4)

            VStack(alignment: .leading, spacing: 0) {
                Text(connectionPresentation.text.uppercased())
                    .font(.system(size: 9, weight: .black, design: .monospaced))
                    .foregroundStyle(connectionPresentation.color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
                Text(app.hasSession ? "KintTany Online" : "Abrir sessão")
                    .font(.system(size: 6, weight: .semibold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func stripDatum(icon: String, label: String, value: String, color: Color) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 0) {
                Text(label.uppercased())
                    .font(.system(size: 6, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text(value)
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var stripDivider: some View {
        Rectangle()
            .fill(KintTanyTheme.border.opacity(0.42))
            .frame(width: 1)
            .padding(.vertical, 2)
    }

    // MARK: - Atividade atual

    private var activeActivityHero: some View {
        GeometryReader { geometry in
            ZStack {
                Image(app.activity?.artworkName ?? "ActivityZombie")
                    .resizable()
                    .scaledToFill()
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
                    .saturation(app.activity == nil ? 0.62 : 1)

                LinearGradient(
                    colors: [
                        .black.opacity(0.22),
                        .clear,
                        KintTanyTheme.backgroundBottom.opacity(0.96)
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )

                if let mode = app.activity {
                    activeHeroOverlay(for: mode)
                } else {
                    idleHeroOverlay
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke((app.activity?.accent ?? KintTanyTheme.cyan).opacity(0.72), lineWidth: 1.2)
        )
    }

    private func activeHeroOverlay(for mode: ActivityMode) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .top, spacing: 5) {
                VStack(alignment: .leading, spacing: 0) {
                    Label("ATIVIDADE ATUAL", systemImage: mode.icon)
                        .font(.system(size: 7, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.cyan)

                    Text(mode.localizedTitle.uppercased())
                        .font(.system(size: 24, weight: .black, design: .rounded))
                        .foregroundStyle(mode.accent)
                        .shadow(color: .black, radius: 1, y: 2)
                        .lineLimit(1)
                        .minimumScaleFactor(0.68)
                }

                Spacer(minLength: 4)

                VStack(alignment: .trailing, spacing: 3) {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        compactChip(
                            app.formattedRatePerMinute(at: context.date),
                            color: KintTanyTheme.cyan,
                            icon: "bolt.fill"
                        )
                    }

                    compactChip(app.state.label, color: mode.accent, icon: stateIcon)
                }
            }

            Spacer(minLength: 2)

            Text(app.displayStatusMessage)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.55)

            if let target = app.currentTarget {
                Label(target, systemImage: "scope")
                    .font(.system(size: 7, weight: .bold, design: .monospaced))
                    .foregroundStyle(mode.accent)
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
            }

            PixelProgressBar(progress: app.progress, color: mode.accent)
                .frame(height: 5)

            HStack(spacing: 5) {
                heroStat("\(app.stats.successes)/\(app.sessionGoal)", label: "META", color: mode.accent)
                heroStat("\(app.stats.attempts)", label: "TENT.", color: .white)

                if mode == .chicken || mode.isWildCombat {
                    heroStat("\(app.stats.confirmedHits)", label: "HITS", color: KintTanyTheme.cyan)
                    heroStat("\(app.stats.kills)", label: "KILLS", color: KintTanyTheme.gold)
                } else {
                    heroStat("\(app.stats.failures)", label: "FALHAS", color: KintTanyTheme.red)
                }

                Button(role: .destructive) {
                    app.stop()
                } label: {
                    Label("PARAR", systemImage: "stop.fill")
                        .font(.system(size: 7, weight: .black, design: .monospaced))
                        .lineLimit(1)
                        .padding(.horizontal, 7)
                        .frame(height: 25)
                        .background(KintTanyTheme.red.opacity(0.9), in: RoundedRectangle(cornerRadius: 5))
                        .overlay(RoundedRectangle(cornerRadius: 5).stroke(KintTanyTheme.red, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.white)
            }
        }
        .padding(8)
    }

    private var idleHeroOverlay: some View {
        VStack(spacing: 4) {
            compactChip("ATIVIDADE ATUAL", color: KintTanyTheme.cyan, icon: "flag.fill")
            Text("ESCOLHA SUA MISSÃO")
                .font(.system(size: 20, weight: .black, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text("Selecione uma atividade abaixo para iniciar")
                .font(.system(size: 7, weight: .semibold, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
            compactChip(app.state.label, color: connectionPresentation.color, icon: stateIcon)
        }
        .padding(8)
    }

    private func compactChip(_ text: String, color: Color, icon: String) -> some View {
        Label(text.uppercased(), systemImage: icon)
            .font(.system(size: 6, weight: .black, design: .monospaced))
            .lineLimit(1)
            .minimumScaleFactor(0.55)
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .frame(height: 17)
            .background(color.opacity(0.14), in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(color.opacity(0.5), lineWidth: 0.8))
    }

    private func heroStat(_ value: String, label: String, color: Color) -> some View {
        VStack(spacing: 0) {
            Text(value)
                .font(.system(size: 9, weight: .black, design: .monospaced))
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            Text(label)
                .font(.system(size: 5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Meta e contexto

    private var controlsRow: some View {
        HStack(spacing: 4) {
            sessionGoalPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            activityContextPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var sessionGoalPanel: some View {
        PixelPanel(accent: KintTanyTheme.gold, inset: 6) {
            VStack(alignment: .leading, spacing: 4) {
                compactPanelTitle("META DA SESSÃO", icon: "trophy.fill", accent: KintTanyTheme.gold)

                HStack(spacing: 4) {
                    goalButton(systemImage: "minus") {
                        app.goal = max(1, app.goal - 1)
                    }

                    TextField("Meta", value: $app.goal, format: .number)
                        .keyboardType(.numberPad)
                        .focused($goalFieldFocused)
                        .font(.system(size: 13, weight: .black, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity, minHeight: 25, maxHeight: 25)
                        .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(goalFieldFocused ? KintTanyTheme.gold : KintTanyTheme.border.opacity(0.45), lineWidth: 1)
                        )
                        .disabled(app.activity != nil)

                    goalButton(systemImage: "plus") {
                        app.goal = min(100_000, app.goal + 1)
                    }
                }

                PixelProgressBar(progress: app.activity == nil ? 0 : app.progress, color: app.activity?.accent ?? KintTanyTheme.gold)
                    .frame(height: 4)

                Text(app.activity == nil ? "Quantidade desejada" : "\(app.stats.successes) / \(app.sessionGoal)")
                    .font(.system(size: 6, weight: .bold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func goalButton(systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 10, weight: .black))
                .frame(width: 25, height: 25)
                .background(KintTanyTheme.border.opacity(0.72), in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.cyan.opacity(0.55), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .foregroundStyle(.white)
        .disabled(app.activity != nil)
        .opacity(app.activity != nil ? 0.48 : 1)
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
        PixelPanel(accent: KintTanyTheme.cyan, inset: 6) {
            VStack(alignment: .leading, spacing: 4) {
                compactPanelTitle("ISCA / EQUIPAMENTO", icon: "figure.fishing", accent: KintTanyTheme.cyan)

                Picker("Isca", selection: $app.selectedFishingBait) {
                    ForEach(FishingBait.allCases) { bait in
                        Text(bait.displayName).tag(bait)
                    }
                }
                .pickerStyle(.menu)
                .tint(KintTanyTheme.cyan)
                .disabled(app.activity != nil)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .frame(maxWidth: .infinity, minHeight: 25, maxHeight: 25, alignment: .leading)
                .padding(.horizontal, 5)
                .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.cyan.opacity(0.4), lineWidth: 1))

                Label(
                    app.selectedFishingBait.supportLabel,
                    systemImage: app.selectedFishingBait.isAutomationValidated ? "checkmark.shield.fill" : "exclamationmark.triangle.fill"
                )
                .font(.system(size: 6, weight: .semibold, design: .monospaced))
                .foregroundStyle(app.selectedFishingBait.isAutomationValidated ? KintTanyTheme.green : KintTanyTheme.gold)
                .lineLimit(1)
                .minimumScaleFactor(0.55)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var currentContextPanel: some View {
        PixelPanel(accent: app.activity?.accent ?? KintTanyTheme.cyan, inset: 6) {
            VStack(alignment: .leading, spacing: 3) {
                compactPanelTitle("CONTEXTO ATUAL", icon: "scope", accent: app.activity?.accent ?? KintTanyTheme.cyan)
                compactContextRow("Alvo", value: app.currentTarget ?? "Aguardando")
                compactContextRow("Estado", value: app.state.label)
                compactContextRow("Região", value: currentRegion)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func compactContextRow(_ label: String, value: String) -> some View {
        HStack(spacing: 3) {
            Text(label.uppercased())
                .font(.system(size: 5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.48)
        }
    }

    // MARK: - Seletor de atividade

    private var activitySelector: some View {
        PixelPanel(accent: KintTanyTheme.cyan, inset: 5) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    compactPanelTitle("SELECIONAR ATIVIDADE", icon: "map.fill", accent: KintTanyTheme.cyan)
                    Spacer(minLength: 3)
                    Text("10 MISSÕES")
                        .font(.system(size: 6, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.gold)
                }

                GeometryReader { geometry in
                    LazyVGrid(columns: activityColumns, spacing: 3) {
                        ForEach(ActivityMode.allCases) { mode in
                            compactActivityCard(mode)
                                .frame(height: max(26, (geometry.size.height - 3) / 2))
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func compactActivityCard(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        let unavailable = app.activity != nil && !selected

        return Button {
            app.start(mode)
        } label: {
            VStack(spacing: 1) {
                Image(systemName: mode.icon)
                    .font(.system(size: 14, weight: .black))
                    .foregroundStyle(mode.accent)
                    .shadow(color: selected ? mode.accent.opacity(0.65) : .clear, radius: 3)

                Text(mode.localizedTitle)
                    .font(.system(size: 6, weight: .black, design: .rounded))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.52)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(selected ? mode.accent.opacity(0.24) : KintTanyTheme.panelDeep)
            .clipShape(RoundedRectangle(cornerRadius: 5))
            .overlay(
                RoundedRectangle(cornerRadius: 5)
                    .stroke(selected ? mode.accent : KintTanyTheme.border.opacity(0.5), lineWidth: selected ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(unavailable || selected)
        .opacity(unavailable ? 0.52 : 1)
        .accessibilityLabel("Iniciar \(mode.localizedTitle)")
    }

    // MARK: - Telemetria e sessão com tamanho fixo

    private var informationPanels: some View {
        HStack(spacing: 4) {
            telemetryPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            sessionStatistics
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var telemetryPanel: some View {
        PixelPanel(accent: KintTanyTheme.cyan, inset: 6) {
            VStack(alignment: .leading, spacing: 2) {
                compactPanelTitle("TELEMETRIA", icon: "chart.bar.fill", accent: KintTanyTheme.cyan)
                telemetryRow("Região", value: currentRegion, color: KintTanyTheme.green)
                telemetryRow(
                    "Posição",
                    value: String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z),
                    color: KintTanyTheme.cyan
                )
                telemetryRow("Recursos", value: "\(app.resourceCount)", color: KintTanyTheme.gold)
                telemetryRow("Mobs", value: "\(app.mobCount)", color: KintTanyTheme.red)
                telemetryRow("Evento", value: telemetryEvent, color: KintTanyTheme.green)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private var sessionStatistics: some View {
        PixelPanel(accent: .indigo, inset: 6) {
            VStack(alignment: .leading, spacing: 2) {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    HStack(spacing: 3) {
                        compactPanelTitle("SESSÃO", icon: "chart.line.uptrend.xyaxis", accent: .indigo)
                        Spacer(minLength: 2)
                        Text(app.formattedRatePerMinute(at: context.date))
                            .font(.system(size: 6, weight: .black, design: .monospaced))
                            .foregroundStyle(KintTanyTheme.cyan)
                            .lineLimit(1)
                            .minimumScaleFactor(0.55)
                    }
                }

                statRow("Tentativas", value: "\(app.stats.attempts)", color: .white)
                statRow("Sucessos", value: "\(app.stats.successes)", color: KintTanyTheme.green)
                statRow("Falhas", value: "\(app.stats.failures)", color: KintTanyTheme.red)
                statRow("Erros", value: "\(app.stats.sessionErrors)", color: KintTanyTheme.orange)

                if let mode = app.activity, mode == .chicken || mode.isWildCombat {
                    statRow("Hits / kills", value: "\(app.stats.confirmedHits) / \(app.stats.kills)", color: KintTanyTheme.cyan)
                } else {
                    statRow("Estado", value: app.state.label, color: KintTanyTheme.cyan)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private func telemetryRow(_ label: String, value: String, color: Color) -> some View {
        HStack(spacing: 3) {
            Rectangle()
                .fill(color)
                .frame(width: 4, height: 4)
            Text(label.uppercased())
                .font(.system(size: 5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 6, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.42)
                .truncationMode(.tail)
        }
    }

    private func statRow(_ label: String, value: String, color: Color) -> some View {
        HStack(spacing: 3) {
            Rectangle()
                .fill(color)
                .frame(width: 4, height: 4)
            Text(label.uppercased())
                .font(.system(size: 5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 6, weight: .black, design: .monospaced))
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.48)
        }
    }

    private var telemetryEvent: String {
        let value = app.stats.lastEvent.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? "Aguardando" : value
    }

    // MARK: - Log compacto

    private var eventLogPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 6) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    compactPanelTitle("LOG DE EVENTOS", icon: "doc.text.fill", accent: KintTanyTheme.border)

                    Spacer(minLength: 3)

                    Button(action: onOpenFullLog) {
                        Label("COMPLETO", systemImage: "doc.text.magnifyingglass")
                            .font(.system(size: 6, weight: .black, design: .monospaced))
                            .padding(.horizontal, 6)
                            .frame(height: 20)
                            .background(KintTanyTheme.border.opacity(0.7), in: RoundedRectangle(cornerRadius: 4))
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.cyan.opacity(0.6), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.white)
                    .accessibilityLabel("Abrir log completo")
                }

                if app.logs.isEmpty {
                    Label("Nenhum evento registrado ainda", systemImage: "sparkles")
                        .font(.system(size: 7, weight: .semibold, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.mutedText)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(app.logs.suffix(3).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.system(size: 6, design: .monospaced))
                                .foregroundStyle(eventColor(for: line))
                                .lineLimit(1)
                                .minimumScaleFactor(0.55)
                                .truncationMode(.tail)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.vertical, 2)
                        }
                    }
                    .padding(.horizontal, 5)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 5))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private func compactPanelTitle(_ title: String, icon: String, accent: Color) -> some View {
        Label(title, systemImage: icon)
            .font(.system(size: 7, weight: .black, design: .monospaced))
            .foregroundStyle(accent)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .symbolRenderingMode(.monochrome)
    }

    private func eventColor(for line: String) -> Color {
        if line.contains("✅") || line.localizedCaseInsensitiveContains("sucesso") { return KintTanyTheme.green }
        if line.contains("⚠️") || line.localizedCaseInsensitiveContains("falha") { return KintTanyTheme.gold }
        if line.contains("🛑") || line.localizedCaseInsensitiveContains("erro") { return KintTanyTheme.red }
        return .white.opacity(0.84)
    }

    // MARK: - Apresentação

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
