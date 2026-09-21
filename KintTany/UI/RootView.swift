import Foundation
import SwiftUI
import UIKit
import WebKit

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showLogin = false
    @State private var showFullLog = false
    @State private var showCharacterStats = false
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
                        CharacterInteractiveView(cookie: cookie)
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
                .frame(width: 176, height: 190)
                .contentShape(Rectangle())

                VStack(alignment: .leading, spacing: 8) {
                    Text(app.characterProfile.displayName)
                        .font(.system(size: 23, weight: .black, design: .rounded))
                        .lineLimit(1)
                        .minimumScaleFactor(0.72)

                    Text("Lvl \(app.characterProfile.totalLevel)")
                        .font(.headline.bold())
                        .foregroundStyle(.cyan)

                    Text(app.hasSession ? "Arraste o personagem para girar" : "Conecte sua sessão")
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

                    Button("Sessão") { showLogin = true }
                        .font(.caption.bold())
                        .buttonStyle(.bordered)
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

private struct CharacterInteractiveView: UIViewRepresentable {
    let cookie: String

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "kintaraInteractive")
        controller.addUserScript(WKUserScript(
            source: """
            (() => {
              window.addEventListener('message', (event) => {
                if (event && event.data && event.data.t === 'kintara_outfit_embed_ready') {
                  window.webkit.messageHandlers.kintaraInteractive.postMessage('ready');
                }
              });
            })();
            """,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.userContentController = controller
        let view = WKWebView(frame: .zero, configuration: config)
        view.isOpaque = false
        view.backgroundColor = .clear
        view.scrollView.backgroundColor = .clear
        view.scrollView.isScrollEnabled = false
        view.scrollView.bounces = false
        view.allowsBackForwardNavigationGestures = false
        context.coordinator.webView = view
        context.coordinator.load(cookie: cookie)
        return view
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if context.coordinator.loadedCookie != cookie {
            context.coordinator.load(cookie: cookie)
        }
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "kintaraInteractive")
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        weak var webView: WKWebView?
        var loadedCookie = ""

        func load(cookie rawCookie: String) {
            guard let webView,
                  let cookie = makeCookie(rawCookie),
                  let url = URL(string: "https://kintara.com/play?embed=outfit") else { return }
            loadedCookie = rawCookie
            webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak webView] in
                webView?.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "kintaraInteractive" else { return }
            isolateRenderer()
        }

        private func isolateRenderer() {
            let script = """
            (() => {
              const host = document.querySelector('#kintara-dash-outfit-letter');
              const canvas = host && host.querySelector('canvas');
              if (!host || !canvas) return false;
              const renderer = window.__kintaraOutfitRenderer || window.kintaraOutfitRenderer || host.__renderer || canvas.__renderer || null;
              document.documentElement.style.cssText = 'margin:0!important;padding:0!important;background:transparent!important;overflow:hidden!important;';
              document.body.style.cssText = 'margin:0!important;padding:0!important;background:transparent!important;overflow:hidden!important;';
              [...document.body.children].forEach((el) => { if (el !== host && !el.contains(host)) el.style.display='none'; });
              host.style.cssText = 'position:fixed!important;left:-42vw!important;top:-34vh!important;width:184vw!important;height:184vh!important;margin:0!important;padding:0!important;background:transparent!important;display:block!important;overflow:visible!important;border:0!important;box-shadow:none!important;';
              canvas.style.cssText += ';width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;touch-action:none!important;cursor:grab!important;background:transparent!important;';
              canvas.setAttribute('aria-label','Personagem 3D. Arraste para girar.');
              let dragging=false,lastX=0;
              const rotate=(dx)=>{
                try {
                  if (renderer && typeof renderer.rotate === 'function') renderer.rotate(dx * 0.012);
                  else if (renderer && renderer.model) renderer.model.rotation.y += dx * 0.012;
                  else window.postMessage({t:'kintara_outfit_rotate', deltaX:dx}, '*');
                } catch (_) {}
              };
              canvas.addEventListener('pointerdown',(e)=>{dragging=true;lastX=e.clientX;canvas.setPointerCapture?.(e.pointerId);e.preventDefault();},{passive:false});
              canvas.addEventListener('pointermove',(e)=>{if(!dragging)return;const dx=e.clientX-lastX;lastX=e.clientX;rotate(dx);e.preventDefault();},{passive:false});
              canvas.addEventListener('pointerup',(e)=>{dragging=false;canvas.releasePointerCapture?.(e.pointerId);e.preventDefault();},{passive:false});
              canvas.addEventListener('pointercancel',()=>{dragging=false;});
              let touchX=null;
              canvas.addEventListener('touchstart',(e)=>{if(!e.touches.length)return;touchX=e.touches[0].clientX;e.preventDefault();},{passive:false});
              canvas.addEventListener('touchmove',(e)=>{if(touchX===null||!e.touches.length)return;const x=e.touches[0].clientX;rotate(x-touchX);touchX=x;e.preventDefault();},{passive:false});
              canvas.addEventListener('touchend',(e)=>{touchX=null;e.preventDefault();},{passive:false});
              return true;
            })();
            """
            webView?.evaluateJavaScript(script)
        }

        private func makeCookie(_ raw: String) -> HTTPCookie? {
            let pair = raw.split(separator: ";", maxSplits: 1).first.map(String.init) ?? raw
            let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
            guard parts.count == 2, parts[0] == "kintara_session", !parts[1].isEmpty else { return nil }
            return HTTPCookie(properties: [
                .domain: ".kintara.com", .path: "/", .name: parts[0],
                .value: parts[1], .secure: "TRUE"
            ])
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
