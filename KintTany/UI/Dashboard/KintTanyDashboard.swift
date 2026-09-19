import SwiftUI

struct KintTanyDashboard: View {
    @EnvironmentObject private var app: AppStore
    @FocusState private var goalFieldFocused: Bool

    let onOpenSession: () -> Void
    let onOpenFullLog: () -> Void

    var body: some View {
        GeometryReader { proxy in
            let gap: CGFloat = proxy.size.height < 700 ? 3 : 4
            let edge: CGFloat = 6
            // Never make the dashboard taller than its container. The previous
            // minimum of 580 points made sections overflow one another on compact
            // devices, leaving invisible views on top of the activity buttons.
            let available = max(0, proxy.size.height - (edge * 2) - (gap * 6))

            ZStack {
                DashboardBackground()

                VStack(spacing: gap) {
                    masthead
                        .frame(height: available * 0.105)

                    connectionStrip
                        .frame(height: available * 0.060)

                    activityHero
                        .frame(height: available * 0.190)

                    controlsRow
                        .frame(height: available * 0.110)

                    activitySelector
                        .frame(height: available * 0.160)

                    insightPanels
                        .frame(height: available * 0.130)

                    eventLogPanel
                        .frame(height: available * 0.215)
                }
                .padding(.horizontal, edge)
                .padding(.vertical, edge)
                .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            }
        }
        // The reference artwork continues behind the status bar. The masthead's
        // content is bottom-aligned, so extending only its background into the
        // top safe area keeps the title readable without the large empty band.
        .ignoresSafeArea(edges: .top)
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
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "83"
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
                            ZStack(alignment: .bottomLeading) {
                                Text("KINTTANY")
                                    .foregroundStyle(Color(red: 0.04, green: 0.25, blue: 0.55))
                                    .offset(y: 3)

                                Text("KINTTANY")
                                    .foregroundStyle(
                                        LinearGradient(
                                            colors: [Color.yellow, KintTanyTheme.gold, KintTanyTheme.orange],
                                            startPoint: .top,
                                            endPoint: .bottom
                                        )
                                    )
                            }
                            .font(.system(size: 34, weight: .black, design: .rounded))
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)

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
                .allowsHitTesting(false)
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

                TimelineView(.periodic(from: .now, by: 1)) { context in
                    statusCell(
                        icon: "chart.line.uptrend.xyaxis",
                        title: "Ritmo",
                        value: app.formattedRatePerMinute(at: context.date),
                        color: KintTanyTheme.green
                    )
                }

                verticalDivider

                statusCell(
                    icon: "globe.americas.fill",
                    title: "Região",
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
                    .font(.system(size: 9, weight: .black, design: .monospaced))
                    .foregroundStyle(connectionPresentation.color)
                    .lineLimit(1)
                    .minimumScaleFactor(0.55)
                Text(app.hasSession ? "KintTany Online" : "Abrir sessão")
                    .font(.system(size: 6, weight: .semibold, design: .monospaced))
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
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 0) {
                Text(title.uppercased())
                    .font(.system(size: 6, weight: .black, design: .monospaced))
                    .foregroundStyle(KintTanyTheme.mutedText)
                Text(value)
                    .font(.system(size: 8, weight: .black, design: .monospaced))
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
                .allowsHitTesting(false)
        )
    }

    private func activeHeroContent(_ mode: ActivityMode) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 6) {
                ActivityIcon(mode: mode)
                    .frame(width: 34, height: 34)

                VStack(alignment: .leading, spacing: 0) {
                    Text("ATIVIDADE ATUAL")
                        .font(.system(size: 7, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.cyan)
                    Text(mode.localizedTitle.uppercased())
                        .font(.system(size: 28, weight: .black, design: .rounded))
                        .foregroundStyle(mode.accent)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }

                Spacer(minLength: 4)
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
                .font(.system(size: 10, weight: .black, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.55)

            Text("\(mode.categoryLabel) • \(currentRegion)")
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
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
                .lineLimit(2)
                .minimumScaleFactor(0.72)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 4)
        }
        .padding(.horizontal, 9)
        .frame(maxWidth: .infinity, minHeight: 34, maxHeight: 34)
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
            VStack(alignment: .leading, spacing: 3) {
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
                .frame(height: 6)

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
            VStack(alignment: .leading, spacing: 0) {
                panelHeader("CONTEXTO ATUAL", icon: "scope")
                if let mode = app.activity {
                    Spacer(minLength: 2)
                    compactValueRow("Tipo", mode.categoryLabel)
                    Spacer(minLength: 1)
                    compactValueRow("Ação", mode.activityDescription)
                    Spacer(minLength: 1)
                    compactValueRow("Disponíveis", availableTargetsText(for: mode))
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
                    Text("10 ATIVIDADES")
                        .font(.system(size: 6, weight: .black, design: .monospaced))
                        .foregroundStyle(KintTanyTheme.gold)
                }

                GeometryReader { geometry in
                    let spacing: CGFloat = 3
                    let cellWidth = max(0, (geometry.size.width - (spacing * 5)) / 6)
                    let cellHeight = max(0, (geometry.size.height - spacing) / 2)

                    VStack(spacing: spacing) {
                        HStack(spacing: spacing) {
                            ForEach(ActivityMode.dashboardOrder.prefix(6), id: \.self) { mode in
                                activityButton(mode)
                                    .frame(width: cellWidth, height: cellHeight)
                            }
                        }
                        .frame(width: geometry.size.width, height: cellHeight, alignment: .leading)

                        HStack(spacing: spacing) {
                            ForEach(ActivityMode.dashboardOrder.suffix(4), id: \.self) { mode in
                                activityButton(mode)
                                    .frame(width: cellWidth, height: cellHeight)
                            }

                            selectorMotto
                                .frame(
                                    width: cellWidth * 2 + spacing,
                                    height: cellHeight
                                )
                        }
                        .frame(width: geometry.size.width, height: cellHeight, alignment: .leading)
                    }
                    .frame(width: geometry.size.width, height: geometry.size.height, alignment: .top)
                    .clipped()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var selectorMotto: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("MESMA DETERMINAÇÃO")
            HStack(spacing: 4) {
                Text("MAIS CONQUISTAS")
                Spacer(minLength: 2)
                Image(systemName: "crown.fill")
                    .foregroundStyle(KintTanyTheme.gold)
            }
        }
        .font(.system(size: 6, weight: .black, design: .monospaced))
        .foregroundStyle(KintTanyTheme.mutedText)
        .padding(.horizontal, 8)
        .background(KintTanyTheme.panelDeep, in: RoundedRectangle(cornerRadius: 4))
        .overlay {
            RoundedRectangle(cornerRadius: 4)
                .stroke(KintTanyTheme.border.opacity(0.30), lineWidth: 1)
                .allowsHitTesting(false)
        }
        .allowsHitTesting(false)
    }

    private func activityButton(_ mode: ActivityMode) -> some View {
        let selected = app.activity == mode
        let canStart = app.activity == nil

        return Button {
            guard canStart else { return }
            // `mode` is the stable enum value owned by this grid item; no visual
            // index is translated into an activity at tap time.
            app.start(mode)
        } label: {
            VStack(spacing: 1) {
                ActivityIcon(mode: mode)
                    .frame(width: 36, height: 36)

                Text(mode.localizedTitle)
                    .font(.system(size: 8, weight: .black, design: .rounded))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.48)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(selected ? KintTanyTheme.green.opacity(0.18) : KintTanyTheme.panelRaised.opacity(0.92))
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .contentShape(RoundedRectangle(cornerRadius: 4))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(selected ? KintTanyTheme.green : KintTanyTheme.border.opacity(0.52), lineWidth: selected ? 2 : 1)
                    .allowsHitTesting(false)
            )
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .contentShape(RoundedRectangle(cornerRadius: 4))
        .clipped()
        // Do not use `disabled` here: SwiftUI dims every inactive card, unlike
        // the reference where the pixel-art choices remain vivid while running.
        .allowsHitTesting(canStart)
        .accessibilityLabel("Iniciar \(mode.localizedTitle)")
        .accessibilityIdentifier("activity.\(mode.rawValue)")
    }

    // MARK: - Three compact insight panels

    private var insightPanels: some View {
        GeometryReader { geometry in
            let spacing: CGFloat = 4
            let width = max(0, (geometry.size.width - spacing * 2) / 3)

            HStack(spacing: spacing) {
                telemetryPanel.frame(width: width, height: geometry.size.height)
                characterStatusPanel.frame(width: width, height: geometry.size.height)
                statisticsPanel.frame(width: width, height: geometry.size.height)
            }
            .frame(width: geometry.size.width, height: geometry.size.height, alignment: .leading)
        }
    }

    private var telemetryPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 0) {
                panelHeader("TELEMETRIA DA SESSÃO", icon: "chart.bar.fill")
                Spacer(minLength: 2)
                insightRow("Posição X", String(format: "%.1f", app.player.position.x), color: KintTanyTheme.cyan)
                Spacer(minLength: 1)
                insightRow("Posição Z", String(format: "%.1f", app.player.position.z), color: KintTanyTheme.cyan)
                Spacer(minLength: 1)
                insightRow("Recursos", "\(app.resourceCount)", color: KintTanyTheme.gold)
                Spacer(minLength: 1)
                insightRow("Mobs", "\(app.mobCount)", color: KintTanyTheme.red)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private var characterStatusPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 0) {
                panelHeader("STATUS DO PERSONAGEM", icon: "heart.fill")
                Spacer(minLength: 2)
                insightRow("HP", "\(app.player.hp)", color: KintTanyTheme.red)
                Spacer(minLength: 1)
                insightRow("Escudo", "\(app.player.shield)", color: .blue)
                Spacer(minLength: 1)
                insightRow("Conexão", connectionPresentation.text, color: connectionPresentation.color)
                Spacer(minLength: 1)
                insightRow("Sessão", app.hasSession ? "Válida" : "Ausente", color: app.hasSession ? KintTanyTheme.green : KintTanyTheme.gold)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private var statisticsPanel: some View {
        PixelPanel(accent: KintTanyTheme.border, inset: 5) {
            VStack(alignment: .leading, spacing: 0) {
                panelHeader("ESTATÍSTICAS GERAIS", icon: "chart.line.uptrend.xyaxis")
                Spacer(minLength: 2)
                insightRow("Tentativas", "\(app.stats.attempts)", color: .white)
                Spacer(minLength: 1)
                insightRow("Sucessos", "\(app.stats.successes)", color: KintTanyTheme.green)
                Spacer(minLength: 1)
                insightRow("Falhas", "\(app.stats.failures)", color: KintTanyTheme.red)
                Spacer(minLength: 1)
                insightRow("Erros", "\(app.stats.sessionErrors)", color: KintTanyTheme.orange)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .clipped()
    }

    private func insightRow(_ label: String, _ value: String, color: Color) -> some View {
        HStack(spacing: 3) {
            Rectangle()
                .fill(color)
                .frame(width: 5, height: 5)
            Text(label.uppercased())
                .font(.system(size: 6.5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
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
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(Array(app.logs.suffix(6).enumerated()), id: \.offset) { _, line in
                            Text(line)
                                .font(.system(size: 8, design: .monospaced))
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
            .font(.system(size: 9, weight: .black, design: .monospaced))
            .foregroundStyle(KintTanyTheme.cyan)
            .lineLimit(1)
            .minimumScaleFactor(0.55)
    }

    private func compactValueRow(_ label: String, _ value: String) -> some View {
        HStack(spacing: 3) {
            Text(label.uppercased())
                .font(.system(size: 6.5, weight: .black, design: .monospaced))
                .foregroundStyle(KintTanyTheme.mutedText)
            Spacer(minLength: 2)
            Text(value)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.45)
        }
    }

    private func availableTargetsText(for mode: ActivityMode) -> String {
        mode.isGathering ? "\(app.resourceCount) recursos" : "\(app.mobCount) mobs"
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

private struct ActivityIcon: View {
    let mode: ActivityMode

    var body: some View {
        Image(mode.selectorIconName)
            .resizable()
            .interpolation(.none)
            .scaledToFit()
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}
