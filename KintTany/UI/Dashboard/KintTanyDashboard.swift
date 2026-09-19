import SwiftUI

struct KintTanyDashboard: View {
    @EnvironmentObject private var app: AppStore
    @FocusState private var goalFieldFocused: Bool

    let onOpenSession: () -> Void
    let onOpenFullLog: () -> Void

    private let selectorOrder: [ActivityMode] = [
        .tree, .stone, .coal, .iron, .silver, .cacti,
        .fishing, .chicken, .zombie, .dragon
    ]

    var body: some View {
        GeometryReader { proxy in
            let gap: CGFloat = proxy.size.height < 700 ? 3 : 4
            let edge: CGFloat = 6
            let available = max(610, proxy.size.height - (edge * 2) - (gap * 6))

            ZStack {
                DashboardBackground()

                VStack(spacing: gap) {
                    masthead
                        .frame(height: available * 0.105)

                    connectionStrip
                        .frame(height: available * 0.060)

                    activityHero
                        .frame(height: available * 0.200)

                    controlsRow
                        .frame(height: available * 0.110)

                    activitySelector
                        .frame(height: available * 0.150)

                    insightPanels
                        .frame(height: available * 0.140)

                    eventLogPanel
                        .frame(height: available * 0.205)
                }
                .padding(.horizontal, edge)
                .padding(.vertical, edge)
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
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "80"
    }

    // MARK: - Masthead

    private var masthead: some View {
        GeometryReader { geometry in
            ZStack {
                Image("MastheadNight")
                    .resizable()
                    .interpolation(.none)
                    .scaledToFill()
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()

                LinearGradient(
                    colors: [
                        KintTanyTheme.backgroundBottom.opacity(0.80),
                        KintTanyTheme.backgroundBottom.opacity(0.24),
                        KintTanyTheme.backgroundBottom.opacity(0.08)
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )

                HStack(alignment: .bottom, spacing: 6) {
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("KintTany")
                                .font(.system(size: 32, weight: .black, design: .rounded))
                                .foregroundStyle(
                                    LinearGradient(
                                        colors: [Color.yellow, KintTanyTheme.gold, KintTanyTheme.orange],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    )
                                )
                                .shadow(color: .black.opacity(0.9), radius: 0, x: 1, y: 2)

                            Text("v\(appVersion)")
                                .font(.system(size: 10, weight: .black, design: .monospaced))
                                .foregroundStyle(KintTanyTheme.cyan)
                        }

                        Text("JOGUE MAIS, TRABALHE MENOS")
                            .font(.system(size: 7, weight: .bold, design: .monospaced))
                            .tracking(0.9)
                            .foregroundStyle(.white.opacity(0.92))
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
                .padding(.vertical, 6)
                .frame(maxHeight: .infinity, alignment: .bottom)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(KintTanyTheme.border.opacity(0.72), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
    }

    // MARK: - Connection strip

    private var connectionStrip: some View {
        PixelPanel(accent: connectionPresentation.color, inset: 0) {
            HStack(spacing: 0) {
                Button(action: onOpenSession) {
                    connectionCell
                }
                .buttonStyle(.plain)

                verticalDivider

                TimelineView(.periodic(from: .now, by: 1)) { context in
                    statusCell(
                        icon: "clock.fill",
                        title: "Sessão",
                        value: sessionDurationText(at: context.date),
                        color: KintTanyTheme.cyan
                    )
                }

                verticalDivider

                statusCell(
                    icon: stateIcon,
                    title: "Estado",
                    value: app.state.label,
                    color: app.activity?.accent ?? KintTanyTheme.cyan
                )

                verticalDivider

                statusCell(
                    icon: "globe.americas.fill",
                    title: "Mundo",
                    value: currentRegion,
                    color: .blue
                )
            }
        }
    }

    private var connectionCell: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(connectionPresentation.color)
                .frame(width: 9, height: 9)

            VStack(alignment: .leading, spacing: 0) {
                Text(connectionPresentation.text.uppercased())
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .foregroundStyle(connectionPresentation.color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                Text(app.hasSession ? "KintTany Online" : "Abrir sessão")
                    .font(.system(size: 5, weight: .semibold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private func statusCell(icon: String, title: String, value: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 0) {
                Text(title.uppercased())
                    .font(.system(size: 5, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text(value)
                    .font(.system(size: 7, weight: .black, design: .monospaced))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.48)
            }
        }
        .padding(.horizontal, 5)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var verticalDivider: some View {
        Rectangle()
            .fill(KintTanyTheme.border.opacity(0.42))
            .frame(width: 1)
            .padding(.vertical, 6)
    }

    // MARK: - Activity hero

    private var activityHero: some View {
        GeometryReader { geometry in
            ZStack {
                if let mode = app.activity {
                    Image(mode.artworkName)
                        .resizable()
                        .interpolation(.none)
                        .scaledToFill()
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .clipped()
                } else {
                    LinearGradient(
                        colors: [KintTanyTheme.panelRaised, KintTanyTheme.panelDeep],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                }

                LinearGradient(
                    colors: [
                        KintTanyTheme.backgroundBottom.opacity(0.76),
                        .clear,
                        KintTanyTheme.backgroundBottom.opacity(0.54)
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )

                if let mode = app.activity {
                    activeHeroContent(mode)
                } else {
                    idleHeroContent
                }
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(KintTanyTheme.border.opacity(0.75), lineWidth: 1)
        )
    }

    private func activeHeroContent(_ mode: ActivityMode) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 6) {
                ActivitySpriteIcon(mode: mode)
                    .frame(width: 30, height: 30)

                VStack(alignment: .leading, spacing: 0) {
                    Text("ATIVIDADE ATUAL")
                        .font(.system(size: 7, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.cyan)
                    Text(mode.localizedTitle.uppercased())
                        .font(.system(size: 25, weight: .black, design: .rounded))
                        .foregroundStyle(mode.accent)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }

                Spacer(minLength: 4)

                VStack(alignment: .trailing, spacing: 3) {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        smallBadge(app.formattedRatePerMinute(at: context.date), color: KintTanyTheme.cyan)
                    }
                    smallBadge(app.state.label, color: mode.accent)
                }
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)

            Spacer(minLength: 2)

            HStack(alignment: .bottom, spacing: 6) {
                heroTargetCard(mode)
                    .frame(maxWidth: 178)

                Spacer(minLength: 2)

                Button(role: .destructive) {
                    app.stop()
                } label: {
                    Label("PARAR", systemImage: "stop.fill")
                        .font(.system(size: 7, weight: .black, design: .monospaced))
                        .padding(.horizontal, 8)
                        .frame(height: 27)
                        .background(KintTanyTheme.red, in: RoundedRectangle(cornerRadius: 4))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.white)
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 4)

            operationStatusBanner(mode)
        }
    }

    private func heroTargetCard(_ mode: ActivityMode) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("ALVO ATUAL")
                .font(.system(size: 6, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.cyan)

            Text(app.currentTarget ?? "Aguardando alvo")
                .font(.system(size: 9, weight: .black, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.55)

            HStack(spacing: 6) {
                Text("\(app.stats.successes)/\(app.sessionGoal)")
                    .foregroundStyle(mode.accent)
                Text("•")
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text("\(app.stats.attempts) tent.")
                    .foregroundStyle(.white)
                if mode == .chicken || mode.isWildCombat {
                    Text("• \(app.stats.confirmedHits) hits")
                        .foregroundStyle(KintTanyTheme.cyan)
                }
            }
            .font(.system(size: 6, weight: .bold, design: .monospaced))
            .lineLimit(1)

            PixelProgressBar(progress: app.progress, color: mode.accent)
                .frame(height: 4)
        }
        .padding(6)
        .background(KintTanyTheme.panelDeep.opacity(0.92), in: RoundedRectangle(cornerRadius: 5))
        .overlay(RoundedRectangle(cornerRadius: 5).stroke(KintTanyTheme.border.opacity(0.7), lineWidth: 1))
    }

    private func operationStatusBanner(_ mode: ActivityMode) -> some View {
        HStack(spacing: 6) {
            Image(systemName: stateIcon)
                .font(.system(size: 10, weight: .black))
                .foregroundStyle(mode.accent)

            Text(app.displayStatusMessage)
                .font(.system(size: 10, weight: .black, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.72)

            Spacer(minLength: 4)
        }
        .padding(.horizontal, 9)
        .frame(maxWidth: .infinity, minHeight: 28, maxHeight: 28)
        .background(KintTanyTheme.panelDeep.opacity(0.98))
        .overlay(alignment: .top) {
            Rectangle().fill(mode.accent).frame(height: 1)
        }
    }

    private var idleHeroContent: some View {
        VStack(spacing: 5) {
            Image(systemName: "map.fill")
                .font(.system(size: 21, weight: .black))
                .foregroundStyle(KintTanyTheme.cyan)
            Text("ESCOLHA SUA ATIVIDADE")
                .font(.system(size: 20, weight: .black, design: .monospaced))
                .foregroundStyle(.white)
            Text("As informações aparecerão aqui em tempo real")
                .font(.system(size: 7, weight: .semibold, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
        }
        .multilineTextAlignment(.center)
        .padding(12)
    }

    private func smallBadge(_ text: String, color: Color) -> some View {
        Text(text.uppercased())
            .font(.system(size: 6, weight: .black, design: .monospaced))
            .foregroundStyle(color)
            .lineLimit(1)
            .minimumScaleFactor(0.55)
            .padding(.horizontal, 5)
            .frame(height: 16)
            .background(KintTanyTheme.panelDeep.opacity(0.9), in: RoundedRectangle(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).stroke(color.opacity(0.55), lineWidth: 1))
    }

    // MARK: - Goal and context

    private var controlsRow: some View {
        HStack(spacing: 4) {
            goalPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            contextPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var goalPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 6) {
            VStack(alignment: .leading, spacing: 4) {
                panelHeader("META DA SESSÃO", icon: "trophy.fill")

                HStack(spacing: 4) {
                    goalButton("minus") {
                        app.goal = max(1, app.goal - 1)
                    }

                    TextField("Meta", value: $app.goal, format: .number)
                        .keyboardType(.numberPad)
                        .focused($goalFieldFocused)
                        .font(.system(size: 13, weight: .black, design: .monospaced))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity, minHeight: 24, maxHeight: 24)
                        .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                        .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.border.opacity(0.65), lineWidth: 1))
                        .disabled(app.activity != nil)

                    goalButton("plus") {
                        app.goal = min(100_000, app.goal + 1)
                    }
                }

                PixelProgressBar(
                    progress: app.activity == nil ? 0 : app.progress,
                    color: app.activity?.accent ?? KintTanyTheme.green
                )
                .frame(height: 4)

                Text(app.activity == nil ? "Quantidade desejada" : "\(app.stats.successes) de \(app.sessionGoal)")
                    .font(.system(size: 6, weight: .bold, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func goalButton(_ systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 9, weight: .black))
                .frame(width: 24, height: 24)
                .background(KintTanyTheme.panelRaised, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.border.opacity(0.65), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .foregroundStyle(.white)
        .disabled(app.activity != nil)
        .opacity(app.activity != nil ? 0.45 : 1)
    }

    @ViewBuilder
    private var contextPanel: some View {
        if app.activity == nil || app.activity == .fishing {
            fishingPanel
        } else {
            liveContextPanel
        }
    }

    private var fishingPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 6) {
            VStack(alignment: .leading, spacing: 4) {
                panelHeader("ISCA / EQUIPAMENTO", icon: "figure.fishing")

                Picker("Isca", selection: $app.selectedFishingBait) {
                    ForEach(FishingBait.allCases) { bait in
                        Text(bait.displayName).tag(bait)
                    }
                }
                .pickerStyle(.menu)
                .tint(KintTanyTheme.cyan)
                .disabled(app.activity != nil)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .frame(maxWidth: .infinity, minHeight: 25, maxHeight: 25, alignment: .leading)
                .padding(.horizontal, 5)
                .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.border.opacity(0.65), lineWidth: 1))

                Label(
                    app.selectedFishingBait.supportLabel,
                    systemImage: app.selectedFishingBait.isAutomationValidated ? "checkmark.square.fill" : "exclamationmark.triangle.fill"
                )
                .font(.system(size: 6, weight: .semibold, design: .monospaced))
                .foregroundStyle(app.selectedFishingBait.isAutomationValidated ? KintTanyTheme.green : KintTanyTheme.gold)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var liveContextPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 6) {
            HStack(spacing: 6) {
                if let mode = app.activity {
                    ActivitySpriteIcon(mode: mode)
                        .frame(width: 33, height: 33)
                }

                VStack(alignment: .leading, spacing: 2) {
                    panelHeader("CONTEXTO ATUAL", icon: "scope")
                    compactValueRow("Alvo", app.currentTarget ?? "Aguardando")
                    compactValueRow("Estado", app.state.label)
                    compactValueRow("Região", currentRegion)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    // MARK: - Activity selector

    private var activitySelector: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    panelHeader("SELECIONAR ATIVIDADE", icon: "map.fill")
                    Spacer()
                    Text("10 MISSÕES")
                        .font(.system(size: 6, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.gold)
                }

                GeometryReader { geometry in
                    let spacing: CGFloat = 3
                    let cellWidth = max(40, (geometry.size.width - (spacing * 5)) / 6)
                    let cellHeight = max(30, (geometry.size.height - spacing) / 2)

                    VStack(spacing: spacing) {
                        HStack(spacing: spacing) {
                            ForEach(Array(selectorOrder.prefix(6))) { mode in
                                activityButton(mode)
                                    .frame(width: cellWidth, height: cellHeight)
                            }
                        }

                        HStack(spacing: spacing) {
                            ForEach(Array(selectorOrder.suffix(4))) { mode in
                                activityButton(mode)
                                    .frame(width: cellWidth, height: cellHeight)
                            }

                            VStack(alignment: .leading, spacing: 1) {
                                Text("PEQUENAS AÇÕES")
                                Text("GRANDES CONQUISTAS")
                                    .foregroundStyle(KintTanyTheme.gold)
                            }
                            .font(.system(size: 5, weight: .black, design: .monospaced))
                            .foregroundStyle(KintTanyTheme.mutedText)
                            .padding(.horizontal, 7)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
                            .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.border.opacity(0.55), lineWidth: 1))
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func activityButton(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        let unavailable = app.activity != nil && !selected

        return Button {
            app.start(mode)
        } label: {
            VStack(spacing: 0) {
                ActivitySpriteIcon(mode: mode)
                    .frame(width: 27, height: 27)

                Text(mode.localizedTitle)
                    .font(.system(size: 6, weight: .black, design: .rounded))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.48)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(selected ? KintTanyTheme.green.opacity(0.16) : KintTanyTheme.panelRaised.opacity(0.76))
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(selected ? KintTanyTheme.green : KintTanyTheme.border.opacity(0.56), lineWidth: selected ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(unavailable || selected)
        .opacity(unavailable ? 0.48 : 1)
        .accessibilityLabel("Iniciar \(mode.localizedTitle)")
    }

    // MARK: - Three compact insight panels

    private var insightPanels: some View {
        HStack(spacing: 4) {
            telemetryPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            characterStatusPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            statisticsPanel
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var telemetryPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 3) {
                panelHeader("TELEMETRIA", icon: "chart.bar.fill")
                insightRow("Região", currentRegion, color: KintTanyTheme.green)
                insightRow(
                    "Posição",
                    String(format: "%.1f, %.1f", app.player.position.x, app.player.position.z),
                    color: KintTanyTheme.cyan
                )
                insightRow("Recursos", "\(app.resourceCount)", color: KintTanyTheme.gold)
                insightRow("Mobs", "\(app.mobCount)", color: KintTanyTheme.red)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private var characterStatusPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 3) {
                panelHeader("ESTADO ATUAL", icon: stateIcon)

                Text(app.state.label)
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .foregroundStyle(app.activity?.accent ?? KintTanyTheme.cyan)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)

                PixelProgressBar(progress: app.activity == nil ? 0 : app.progress, color: app.activity?.accent ?? KintTanyTheme.cyan)
                    .frame(height: 5)

                insightRow("Alvo", app.currentTarget ?? "Aguardando", color: KintTanyTheme.cyan)
                insightRow("Conexão", connectionPresentation.text, color: connectionPresentation.color)
                insightRow("Evento", compactEventText, color: KintTanyTheme.green)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private var statisticsPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 3) {
                panelHeader("SESSÃO", icon: "chart.line.uptrend.xyaxis")
                insightRow("Tentativas", "\(app.stats.attempts)", color: .white)
                insightRow("Sucessos", "\(app.stats.successes)", color: KintTanyTheme.green)
                insightRow("Falhas", "\(app.stats.failures)", color: KintTanyTheme.red)

                if let mode = app.activity, mode == .chicken || mode.isWildCombat {
                    insightRow("Hits/Kills", "\(app.stats.confirmedHits)/\(app.stats.kills)", color: KintTanyTheme.cyan)
                } else {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        insightRow("Ritmo", app.formattedRatePerMinute(at: context.date), color: KintTanyTheme.cyan)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private func insightRow(_ label: String, _ value: String, color: Color) -> some View {
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
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.42)
                .truncationMode(.tail)
        }
    }

    // MARK: - Event log

    private var eventLogPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 6) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 5) {
                    panelHeader("LOG DE EVENTOS", icon: "doc.text.fill")

                    Spacer()

                    Button(action: onOpenFullLog) {
                        Label("COMPLETO", systemImage: "doc.text.magnifyingglass")
                            .font(.system(size: 6, weight: .black, design: .monospaced))
                            .padding(.horizontal, 7)
                            .frame(height: 20)
                            .background(KintTanyTheme.panelRaised, in: RoundedRectangle(cornerRadius: 4))
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.cyan.opacity(0.68), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.white)
                }

                if app.logs.isEmpty {
                    Label("Nenhum evento registrado ainda", systemImage: "sparkles")
                        .font(.system(size: 7, weight: .semibold, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.mutedText)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                } else {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(app.logs.suffix(6).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.system(size: 6, design: .monospaced))
                                .foregroundStyle(eventColor(for: line))
                                .lineLimit(1)
                                .minimumScaleFactor(0.58)
                                .truncationMode(.tail)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(6)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(KintTanyTheme.border.opacity(0.35), lineWidth: 1))
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    // MARK: - Shared presentation

    private func panelHeader(_ title: String, icon: String) -> some View {
        Label(title, systemImage: icon)
            .font(.system(size: 7, weight: .black, design: .monospaced))
            .foregroundStyle(KintTanyTheme.cyan)
            .lineLimit(1)
            .minimumScaleFactor(0.55)
    }

    private func compactValueRow(_ label: String, _ value: String) -> some View {
        HStack(spacing: 3) {
            Text(label.uppercased())
                .font(.system(size: 5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 6, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.45)
        }
    }

    private var compactEventText: String {
        let value = app.stats.lastEvent.trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? "Aguardando" : value
    }

    private func eventColor(for line: String) -> Color {
        if line.contains("✅") || line.localizedCaseInsensitiveContains("sucesso") { return KintTanyTheme.green }
        if line.contains("⚠️") || line.localizedCaseInsensitiveContains("falha") { return KintTanyTheme.gold }
        if line.contains("🛑") || line.localizedCaseInsensitiveContains("erro") { return KintTanyTheme.red }
        return .white.opacity(0.86)
    }

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

private struct ActivitySpriteIcon: View {
    let mode: ActivityMode

    private var index: Int {
        switch mode {
        case .tree: 0
        case .stone: 1
        case .coal: 2
        case .iron: 3
        case .silver: 4
        case .cacti: 5
        case .fishing: 6
        case .chicken: 7
        case .zombie: 8
        case .dragon: 9
        }
    }

    var body: some View {
        GeometryReader { geometry in
            let column = CGFloat(index % 5)
            let row = CGFloat(index / 5)

            Image("ActivityIconSprite")
                .resizable()
                .interpolation(.none)
                .frame(width: geometry.size.width * 5, height: geometry.size.height * 2)
                .offset(x: -column * geometry.size.width, y: -row * geometry.size.height)
        }
        .clipped()
        .accessibilityHidden(true)
    }
}
