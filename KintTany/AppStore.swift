import Foundation
import SwiftUI
import UIKit
import BackgroundTasks

enum ActivityMode: String, CaseIterable, Codable, Identifiable {
    case tree, coal, stone, fishing, chicken, zombie, dragon

    var id: String { rawValue }

    var title: String {
        switch self {
        case .tree: "Tree"
        case .coal: "Coal"
        case .stone: "Stone"
        case .fishing: "Fishing"
        case .chicken: "Chicken"
        case .zombie: "Zombie"
        case .dragon: "Dragon"
        }
    }

    var localizedTitle: String {
        switch self {
        case .tree: "Madeira"
        case .coal: "Carvão"
        case .stone: "Pedra"
        case .fishing: "Pesca"
        case .chicken: "Galinha"
        case .zombie: "Zumbi"
        case .dragon: "Dragão"
        }
    }

    var icon: String {
        switch self {
        case .tree: "tree.fill"
        case .coal: "circle.fill"
        case .stone: "mountain.2.fill"
        case .fishing: "fish.fill"
        case .chicken: "bird.fill"
        case .zombie: "figure.walk"
        case .dragon: "flame.fill"
        }
    }

    var accent: Color {
        switch self {
        case .tree: .green
        case .coal: .gray
        case .stone: .orange
        case .fishing: .cyan
        case .chicken: .yellow
        case .zombie: .mint
        case .dragon: .red
        }
    }

    var isWildCombat: Bool {
        self == .zombie || self == .dragon
    }
}


enum FishingBait: String, CaseIterable, Codable, Identifiable {
    // rawValue is a UI/persistence identifier, not a presumed server item id.
    // Only Feather/Pond is wire-validated by the supplied Node v5.2 baseline.
    case feather
    case trout
    case bass
    case tuna
    case squid

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .feather: "Feather Bait"
        case .trout: "Trout Bait"
        case .bass: "Bass Bait"
        case .tuna: "Tuna Bait"
        case .squid: "Squid Bait"
        }
    }

    var confirmedInventoryKey: String? {
        switch self {
        case .feather: "bait_feather"
        case .trout: "bait_trout"
        case .bass, .tuna, .squid: nil
        }
    }

    var isAutomationValidated: Bool { self == .feather }

    var supportLabel: String {
        isAutomationValidated ? "The Pond • validado" : "protocolo da zona ainda não validado"
    }
}

enum ActivityState: String, Codable {
    case idle, connecting, syncing, searching, selectingTarget, moving, preparingAction, acting, waitingProof, waitingResult, cooldown, recovering, completed, cancelled, failed

    var label: String {
        switch self {
        case .idle: "Pronto"
        case .connecting: "Conectando"
        case .syncing: "Sincronizando"
        case .searching: "Procurando alvo"
        case .selectingTarget: "Selecionando alvo"
        case .moving: "Movendo"
        case .preparingAction: "Preparando"
        case .acting: "Executando"
        case .waitingProof: "Confirmando ação"
        case .waitingResult: "Aguardando resultado"
        case .cooldown: "Cooldown"
        case .recovering: "Recuperando"
        case .completed: "Concluído"
        case .cancelled: "Cancelado"
        case .failed: "Falha"
        }
    }
}


enum ContinuedActivityStatusFormatter {
    /// Única fonte de texto visível para o card do app e para a superfície
    /// de Continued Processing do iOS. Se a engine já forneceu um status
    /// legível (ex.: "Peixe #3 • fisgada em 25.7s"), ele é preservado
    /// literalmente para que a Dynamic Island mostre o mesmo conteúdo.
    static func status(
        mode: ActivityMode,
        state: ActivityState,
        currentTarget: String?,
        rawStatus: String
    ) -> String {
        let visible = rawStatus.trimmingCharacters(in: .whitespacesAndNewlines)
        if !visible.isEmpty { return visible }

        // Fallback somente para o caso anormal de uma engine ainda não ter
        // publicado mensagem. Não substitui uma mensagem real da atividade.
        switch mode {
        case .tree: return "Cortando árvore"
        case .stone: return "Minerando pedra"
        case .coal: return "Minerando carvão"
        case .fishing: return "Preparando pesca"
        case .chicken: return "Combatendo galinha"
        case .zombie: return state == .recovering ? "Saindo do combate com segurança" : "Em combate com zumbi"
        case .dragon: return state == .recovering ? "Saindo do combate com segurança" : "Em combate com dragão"
        }
    }
}

struct Position: Codable, Equatable {
    var x: Double
    var y: Double = 0.25
    var z: Double
    var ry: Double = 0
}

struct ResourceNode: Codable, Identifiable, Equatable {
    var id: String
    var kind: String
    var keys: [String]
    var available: Bool
    var hasCoal: Bool = false
    var proof: String?
}

struct Mob: Codable, Identifiable, Equatable {
    var id: String
    var index: Int
    var type: String
    var level: Int?
    var position: Position
    var hp: Int?
    var alive: Bool
}

struct PlayerState: Codable {
    var id: String?
    var position = Position(x: 22.5, z: -3.5)
    var hp = 100
    var shield = 0
    var lifeEpoch = 1
    var region = "world"
    var resources: [String: Int] = [:]
}

struct WorldState: Codable {
    var nodes: [ResourceNode] = []
    var mobs: [Mob] = []
    var region = "world"
    var serverRegion: String?
}

enum ActivityRateMeter {
    /// Matches the Node v5.2/v7.7 session-rate semantics: authoritative
    /// successes divided by elapsed session minutes, with a 0.01 min floor.
    static func perMinute(successes: Int, startedAt: Date?, now: Date = .now) -> Double {
        guard successes > 0, let startedAt else { return 0 }
        let elapsedMinutes = max(now.timeIntervalSince(startedAt) / 60.0, 0.01)
        return Double(successes) / elapsedMinutes
    }

    static func formatted(successes: Int, startedAt: Date?, now: Date = .now) -> String {
        String(format: "%.2f/min", perMinute(successes: successes, startedAt: startedAt, now: now))
    }
}

struct ActivityStats: Codable {
    var attempts = 0
    var successes = 0
    /// Falhas pertencentes a uma tentativa real da atividade. Erros estruturais
    /// (expiração do iOS, transporte, preflight) ficam separados em sessionErrors.
    var failures = 0
    var sessionErrors = 0
    var hits = 0
    var confirmedHits = 0
    var hitAckTimeouts = 0
    var hitAckTimeoutsForeground = 0
    var hitAckTimeoutsBackground = 0
    var potionAckTimeouts = 0
    var potionAckTimeoutsForeground = 0
    var potionAckTimeoutsBackground = 0
    var kills = 0
    var startedAt: Date?
    var lastEvent = ""
}

@MainActor
final class AppStore: ObservableObject {
    @Published var activity: ActivityMode?
    @Published var state: ActivityState = .idle
    @Published var player = PlayerState()
    @Published var world = WorldState()
    @Published var stats = ActivityStats()
    @Published var goal = 100
    /// Meta congelada da sessão exibida. Alterar `goal` depois que uma sessão
    /// termina não pode reescrever a barra/progresso histórico daquela sessão.
    @Published private(set) var sessionGoal = 100
    @Published var logs: [String] = []
    @Published var diagnosticLogs: [String] = []
    @Published var connected = false
    @Published var currentTarget: String?
    @Published var statusMessage = "Pronto para iniciar"
    @Published var resourceCount = 0
    @Published var mobCount = 0
    @Published var selectedFishingBait: FishingBait = .feather

    private let session = SessionManager()
    private var task: Task<Void, Never>?
    private var receiverTask: Task<Void, Never>?
    private var traceTask: Task<Void, Never>?
    private var engineRunTask: Task<EngineRunResult, Error>?
    private var realtimeFailureMessage: String?
    private var terminalFailureHandled = false
    private let socket = RealtimeSocket()
    private var activeEngine: AutomationEngine?
    private var activeRunID: UUID?
    private var requestedStopReason: EngineStopReason?
    private var connectionRecoveryRequested = false
    private var connectionRecoveryDetail: String?
    private var connectionRecoveryInProgress = false
    private var activeShard: String?

    // MARK: - Execução em segundo plano
    //
    // iOS 26 introduziu BGContinuedProcessingTask exatamente para trabalhos
    // iniciados por uma ação explícita do usuário que precisam continuar quando
    // o app sai do primeiro plano. O Kintarabot inicia uma atividade com um toque
    // e possui progresso mensurável (sucessos/meta), então a engine pode permanecer
    // ativa, inclusive usando rede, enquanto o sistema mantiver a tarefa contínua.
    //
    // O objeto é mantido como AnyObject para que o projeto continue com deployment
    // target iOS 17; o cast para BGContinuedProcessingTask só ocorre dentro de
    // blocos #available(iOS 26.0, *).
    private var continuedTaskObject: AnyObject?
    private var continuedTaskRequested = false
    private var continuedTaskMode: ActivityMode?
    private var continuedTaskIdentifier: String?
    private var continuedTaskActivationWatchdog: Task<Void, Never>?
    private var continuedTaskSubmissionAttempt = 0
    private var continuedProgressSubunit = 0
    private var lastScenePhaseKey: String?
    private var legacyBackgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var lastContinuedTitleSuccesses = -1
    private var lastContinuedPublicStatus = ""

    private var continuedTaskIdentifierPrefix: String {
        let bundleID = Bundle.main.bundleIdentifier ?? "com.joaopedro.kinttany"
        return "\(bundleID).continuedBot"
    }

    var hasSession: Bool {
        guard let cookie = session.cookie else { return false }
        return !cookie.isEmpty
    }

    var progress: Double {
        min(1, Double(stats.successes) / Double(max(sessionGoal, 1)))
    }

    func ratePerMinute(at now: Date = .now) -> Double {
        ActivityRateMeter.perMinute(successes: stats.successes, startedAt: stats.startedAt, now: now)
    }

    func formattedRatePerMinute(at now: Date = .now) -> String {
        ActivityRateMeter.formatted(successes: stats.successes, startedAt: stats.startedAt, now: now)
    }

    /// Texto compartilhado pelo card da atividade e pela Dynamic Island.
    /// Assim, ambos nunca divergem por usarem formatters diferentes.
    var displayStatusMessage: String {
        guard let mode = activity ?? continuedTaskMode else { return statusMessage }
        return ContinuedActivityStatusFormatter.status(
            mode: mode,
            state: state,
            currentTarget: currentTarget,
            rawStatus: statusMessage
        )
    }

    func start(_ mode: ActivityMode) {
        // Single-flight: um segundo toque nunca cancela e substitui uma sessão que
        // ainda está fechando. Isso elimina corrida entre socket/engine antiga e nova.
        guard task == nil, activeRunID == nil, activity == nil else {
            diagnostic("[STATE] start ignorado • já existe execução/encerramento em andamento")
            return
        }

        // O seletor cobre toda a escada de iscas, mas a baseline fornecida
        // comprova wire/rota apenas para Feather Bait em The Pond. Uma opção não
        // validada nunca cai silenciosamente no Feather nem envia grant incorreto.
        if mode == .fishing, !selectedFishingBait.isAutomationValidated {
            state = .failed
            statusMessage = "\(selectedFishingBait.displayName) ainda não validada para automação"
            stats.lastEvent = "isca sem protocolo validado"
            log("🪱 \(selectedFishingBait.displayName) selecionada • automação bloqueada: falta captura/protocolo real da zona correspondente")
            diagnostic("[FISH] nenhuma ação enviada • seletor preservado sem inventar item id/rota/wire")
            return
        }

        goal = min(100_000, max(1, goal))
        sessionGoal = goal

        let runID = UUID()
        activeRunID = runID
        requestedStopReason = nil

        // A solicitação precisa nascer do toque do usuário, antes de o app ser
        // colocado em segundo plano.
        prepareContinuedProcessing(for: mode)

        task = Task { [weak self] in
            guard let self else { return }
            await self.run(mode, runID: runID)
        }
    }

    func stop() {
        stop(silent: false)
    }

    private func stop(silent: Bool) {
        guard let runID = activeRunID else {
            if !silent { log("STOP ignorado — nenhuma atividade está em execução") }
            return
        }
        let stoppedMode = activity
        guard requestedStopReason == nil else { return }
        requestedStopReason = .user

        // Se a Presence já caiu no Wild, o único caminho capaz de tentar uma
        // saída segura é manter a reconexão de emergência viva. STOP aqui apenas
        // confirma a intenção; cancelar a Task impediria justamente o retorno ao
        // World quando a rede reaparecesse.
        if activity?.isWildCombat == true, connectionRecoveryRequested {
            state = .recovering
            statusMessage = "STOP • aguardando rede para saída segura"
            stats.lastEvent = "STOP aguardando reconexão"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                log("STOP registrado durante queda de conexão • reconexão de emergência continuará apenas para voltar ao World")
            }
            return
        }

        // Em Wilderness o STOP é cooperativo: não cancela a Task no meio do Wild.
        // A engine interrompe novos ataques, recua, espera combat timer 0 e confirma
        // World antes de devolver o controle ao AppStore.
        if activity?.isWildCombat == true, connected, let activeEngine {
            activeEngine.requestSafeStop(reason: .user)
            state = .recovering
            statusMessage = "Saindo do combate com segurança"
            stats.lastEvent = "safe stop solicitado"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                log("STOP solicitado — encerrando Wilderness com segurança antes de fechar a conexão")
            }
            return
        }

        // Não-Wild também possui `engineRunTask` independente. Cancelá-la é
        // obrigatório para que STOP de Fishing/Gathering não deixe uma sessão
        // fantasma prendendo o single-flight após a UI voltar a idle.
        terminalFailureHandled = true
        engineRunTask?.cancel()
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = nil
        connected = false
        currentTarget = nil
        activity = nil
        state = .cancelled
        statusMessage = "Atividade interrompida"
        if let stoppedMode { logSessionSummary(mode: stoppedMode, outcome: "STOP") }
        finishContinuedProcessing(success: false, reason: "interrompida")
        endLegacyBackgroundTask()
        if !silent {
            log("STOP confirmado — nenhuma nova ação será enviada")
        }

        Task { [weak self] in
            guard let self else { return }
            await self.socket.close()
            self.completeRunCleanup(runID: runID)
        }
    }

    private func completeRunCleanup(runID: UUID) {
        guard activeRunID == runID else { return }
        receiverTask?.cancel()
        traceTask?.cancel()
        receiverTask = nil
        traceTask = nil
        activeEngine = nil
        engineRunTask = nil
        connectionRecoveryRequested = false
        connectionRecoveryDetail = nil
        connectionRecoveryInProgress = false
        activeShard = nil
        activeRunID = nil
        requestedStopReason = nil
        task = nil
        connected = false
    }

    private func logSessionSummary(mode: ActivityMode, outcome: String) {
        let elapsed = max(0, Date().timeIntervalSince(stats.startedAt ?? Date()))
        let minutes = Int(elapsed) / 60
        let seconds = Int(elapsed) % 60
        let duration = String(format: "%02d:%02d", minutes, seconds)
        let backgroundState: String
        if continuedTaskObject != nil {
            backgroundState = "Continued Processing ativa"
        } else if continuedTaskRequested {
            backgroundState = "Continued Processing pendente"
        } else {
            backgroundState = "foreground/finalizada"
        }

        let finalRate = ActivityRateMeter.perMinute(successes: stats.successes, startedAt: stats.startedAt, now: .now)

        log("📊 RESUMO DA SESSÃO • \(mode.localizedTitle) • \(outcome)")
        log("Meta \(sessionGoal) • sucessos \(stats.successes) • tentativas \(stats.attempts) • falhas \(stats.failures) • tempo \(duration)")
        if stats.sessionErrors > 0 {
            log("Sessão • erros estruturais \(stats.sessionErrors)")
        }
        log(String(format: "⚡ Ritmo médio • %.2f/min", finalRate))
        if mode == .chicken || mode.isWildCombat {
            log("Combate • hits enviados \(stats.hits) • hits confirmados \(stats.confirmedHits) • ACK timeout \(stats.hitAckTimeouts) (FG \(stats.hitAckTimeoutsForeground) / BG \(stats.hitAckTimeoutsBackground)) • kills \(stats.kills)")
            if mode.isWildCombat {
                log("Poções • drink_ack timeout \(stats.potionAckTimeouts) (FG \(stats.potionAckTimeoutsForeground) / BG \(stats.potionAckTimeoutsBackground))")
            }
        }
        log("Background • \(backgroundState)")
    }

    func log(_ value: String) {
        let line = timestamped(value)
        logs.append(line)
        diagnosticLogs.append(line)
        trimLogs()
    }

    func diagnostic(_ value: String) {
        // O "Log completo" é voltado ao uso do bot, não a um espelho do
        // DevTools/Network/WebSocket. Mantemos apenas diagnóstico de conexão,
        // autenticação e erros úteis; payloads IN/OUT e detalhes internos da
        // engine continuam fora da interface.
        guard shouldKeepDiagnostic(value) else { return }
        diagnosticLogs.append(timestamped(value))
        if diagnosticLogs.count > 10_000 {
            diagnosticLogs.removeFirst(diagnosticLogs.count - 10_000)
        }
    }

    private func shouldKeepDiagnostic(_ value: String) -> Bool {
        // Nunca exibir mensagens/payloads brutos do WebSocket.
        if value.hasPrefix("[IN ") || value.hasPrefix("[OUT ") { return false }

        // Conexão e autenticação são úteis para entender em que etapa o bot está.
        if value.hasPrefix("[AUTH]") ||
            value.hasPrefix("[NET]") ||
            value.hasPrefix("[WS]") ||
            value.hasPrefix("[QUEUE]") ||
            value.hasPrefix("[SERVER]") ||
            value.hasPrefix("[BG]") ||
            value.hasPrefix("[WARN]") ||
            value.hasPrefix("[ERROR]") ||
            value.hasPrefix("[STATE]") {
            return true
        }

        // Do HTTP, basta a negociação da conexão e o resultado. Corpos e tokens
        // não agregam ao usuário e podem tornar o log enorme/sensível.
        if value.hasPrefix("[HTTP]") {
            return !value.contains(" body:") && !value.contains("token=<oculto>")
        }

        return false
    }

    func clearDiagnosticLogs() {
        diagnosticLogs.removeAll()
        diagnostic("[UI] Log completo limpo pelo usuário")
    }

    var fullLogText: String {
        diagnosticLogs.joined(separator: "\n")
    }

    func saveCookie(_ cookie: String) {
        session.save(cookie: cookie)
        state = .idle
        connected = false
        statusMessage = "Sessão salva"
        log("Sessão autenticada e salva no Keychain; realtime será conectado ao iniciar uma atividade")
    }

    private func run(_ mode: ActivityMode, runID: UUID) async {
        guard activeRunID == runID else { return }
        guard let cookie = session.cookie, !cookie.isEmpty else {
            activity = nil
            state = .failed
            statusMessage = "Faça login antes de iniciar"
            log("Sessão ausente. Abra Sessão e faça login.")
            finishContinuedProcessing(success: false, reason: "sessão ausente")
            completeRunCleanup(runID: runID)
            return
        }

        goal = min(100_000, max(1, goal))
        sessionGoal = goal
        let runGoal = sessionGoal
        realtimeFailureMessage = nil
        terminalFailureHandled = false
        connectionRecoveryRequested = false
        connectionRecoveryDetail = nil
        connectionRecoveryInProgress = false
        activeShard = nil

        activity = mode
        state = .connecting
        stats = ActivityStats(startedAt: .now)
        connected = false
        currentTarget = nil
        resourceCount = 0
        mobCount = 0
        statusMessage = "Conectando ao Kintara"
        log("Iniciando \(mode.localizedTitle)")
        diagnostic("[UI] activity=\(mode.rawValue) state=connecting goal=\(runGoal)")
        updateContinuedProcessingProgress(forceTitleUpdate: true)

        traceTask?.cancel()
        traceTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.importSocketTrace()
                do {
                    try await Task.sleep(nanoseconds: 100_000_000)
                } catch {
                    break
                }
            }
        }

        let bootstrap = await AutomationEngine.bootstrapForRun(for: mode, cookie: cookie)

        defer {
            receiverTask?.cancel()
            traceTask?.cancel()
            connected = false
            let closingRunID = runID
            Task { [weak self] in
                guard let self else { return }
                await self.socket.close()
                self.completeRunCleanup(runID: closingRunID)
            }
        }

        do {
            let connection = try await socket.connectBestNA(session: session, bootstrap: bootstrap)
            guard activeRunID == runID else { return }
            let stream = connection.stream
            let selectedShard = connection.shard
            activeShard = selectedShard
            await importSocketTrace()

            log("Servidor NA selecionado automaticamente: \(connection.serverName) (\(selectedShard)) • carga \(connection.populationLabel) • fila \(connection.queueLength)")

            let engine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: selectedShard,
                bootstrap: bootstrap,
                fishingBait: selectedFishingBait,
                reporter: { [weak self] event in
                    self?.handleEngineEvent(event, runID: runID)
                }
            )
            activeEngine = engine

            connected = true
            state = .syncing
            statusMessage = "Sincronizando personagem e mundo"
            log("Realtime conectado; engine ativa iniciada")

            await engine.prepareIdentity()
            guard activeRunID == runID else { return }

            receiverTask = Task { [weak self] in
                guard let self else { return }
                for await data in stream {
                    if Task.isCancelled { break }
                    engine.ingest(data)
                    await self.importSocketTrace()
                }

                if !Task.isCancelled {
                    await self.handleUnexpectedRealtimeEnd(for: mode, runID: runID)
                }
            }

            let child = Task { @MainActor in
                try await engine.run(mode: mode, goal: runGoal)
            }
            engineRunTask = child
            let result = try await child.value
            engineRunTask = nil
            await importSocketTrace()
            guard activeRunID == runID else { return }

            if let reason = realtimeFailureMessage {
                connected = false
                currentTarget = nil
                activity = nil
                state = .failed
                statusMessage = reason
            } else if result.stoppedSafely {
                connected = false
                currentTarget = nil
                activity = nil
                state = .cancelled
                let stopReason = result.stopReason ?? requestedStopReason
                switch stopReason {
                case .backgroundExpiration:
                    statusMessage = "Segundo plano encerrado com saída segura"
                    stats.lastEvent = "background encerrado com saída segura"
                    log("Segundo plano encerrado pelo iOS — World confirmado e conexão liberada com segurança")
                    logSessionSummary(mode: mode, outcome: "EXPIRAÇÃO SEGURA")
                    finishContinuedProcessing(success: false, reason: "expiração após saída segura")
                case .connectionLoss:
                    statusMessage = "Conexão recuperada • World seguro"
                    stats.lastEvent = "saída segura após perda de conexão"
                    log("Conexão recuperada — World seguro e nenhuma nova ação será enviada")
                    logSessionSummary(mode: mode, outcome: "RECONEXÃO SEGURA")
                    finishContinuedProcessing(success: false, reason: "conexão recuperada com saída segura")
                case .user, .none:
                    statusMessage = "Atividade encerrada com segurança"
                    stats.lastEvent = "atividade cancelada pelo usuário"
                    log("STOP confirmado — World seguro e nenhuma nova ação será enviada")
                    logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                    finishContinuedProcessing(success: false, reason: "interrompida com saída segura")
                }
            } else if Task.isCancelled {
                state = .cancelled
                statusMessage = "Atividade cancelada"
                diagnostic("[STATE] atividade cancelada")
            } else if result.completedGoal {
                state = .completed
                statusMessage = "Meta concluída"
                currentTarget = nil
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                activity = nil
                log("✅ Meta concluída: \(result.successes)/\(runGoal) • atividade encerrada automaticamente")
                logSessionSummary(mode: mode, outcome: "META CONCLUÍDA")
                finishContinuedProcessing(success: true, reason: "meta concluída")
            } else {
                state = .failed
                statusMessage = "Engine encerrou antes da meta"
                stats.sessionErrors += 1
                currentTarget = nil
                activity = nil
                log("Atividade encerrou antes da meta • bot interrompido automaticamente")
                logSessionSummary(mode: mode, outcome: "ENCERRADA ANTES DA META")
                finishContinuedProcessing(success: false, reason: "engine encerrou antes da meta")
            }
        } catch is CancellationError {
            await importSocketTrace()
            guard activeRunID == runID else { return }
            if mode.isWildCombat, connectionRecoveryRequested, let shard = activeShard {
                _ = await recoverWildAfterUnexpectedDisconnect(mode: mode, runID: runID, shard: shard, cookie: cookie)
                return
            }
            if let reason = realtimeFailureMessage {
                connected = false
                currentTarget = nil
                activity = nil
                state = .failed
                statusMessage = reason
                diagnostic("[STATE] engine cancelada após perda da conexão realtime")
                if !terminalFailureHandled {
                    terminalFailureHandled = true
                    finishContinuedProcessing(success: false, reason: "conexão realtime perdida")
                }
            } else {
                state = .cancelled
                statusMessage = "Atividade cancelada"
                let byUser = requestedStopReason == .user
                diagnostic(byUser ? "[STATE] atividade cancelada pelo usuário" : "[STATE] atividade cancelada")
                if continuedTaskObject != nil || continuedTaskRequested {
                    finishContinuedProcessing(success: false, reason: byUser ? "atividade cancelada pelo usuário" : "atividade cancelada")
                }
            }
        } catch {
            await importSocketTrace()
            guard activeRunID == runID else { return }
            if mode.isWildCombat, connectionRecoveryRequested, let shard = activeShard {
                _ = await recoverWildAfterUnexpectedDisconnect(mode: mode, runID: runID, shard: shard, cookie: cookie)
                return
            }

            // RC3.4: um World sem ACK pode já ter sido aplicado pelo servidor.
            // Reconecte no mesmo shard e deixe snapshot autoritativo decidir se
            // já estamos em World ou se ainda é preciso concluir safe-exit.
            if mode.isWildCombat,
               let engineError = error as? EngineError,
               case .worldExitUnconfirmed = engineError,
               let shard = activeShard {
                requestWildConnectionRecovery(
                    reason: "Saída para World sem confirmação; verificando estado autoritativo por reconexão",
                    runID: runID
                )
                await socket.close()
                _ = await recoverWildAfterUnexpectedDisconnect(mode: mode, runID: runID, shard: shard, cookie: cookie)
                return
            }

            if terminalFailureHandled { return }
            terminalFailureHandled = true
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = error.localizedDescription
            stats.sessionErrors += 1
            diagnostic("[ERROR] \(error.localizedDescription)")
            log("Falha: \(error.localizedDescription) • bot interrompido automaticamente")
            logSessionSummary(mode: mode, outcome: "FALHA")
            finishContinuedProcessing(success: false, reason: "falha da atividade")
        }
    }

    private func handleUnexpectedRealtimeEnd(for mode: ActivityMode, runID: UUID) async {
        guard activeRunID == runID, activity == mode, connected, !terminalFailureHandled else { return }

        await importSocketTrace()
        let detail = await socket.disconnectReason()
        let reason: String
        if let detail, !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            reason = "Conexão realtime perdida: \(detail)"
        } else {
            reason = "Conexão realtime encerrada inesperadamente"
        }

        // RC3: em Wilderness uma queda real de rede não encerra a proteção de
        // imediato. Congela a engine antiga e tenta recuperar a mesma Presence
        // no mesmo shard exclusivamente para voltar ao World com segurança.
        if mode.isWildCombat {
            requestWildConnectionRecovery(reason: reason, runID: runID)
            await socket.close()
            return
        }

        terminalFailureHandled = true
        realtimeFailureMessage = reason
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = reason
        stats.sessionErrors += 1
        diagnostic("[ERROR] \(reason)")
        log("Falha de conexão: \(reason) • bot interrompido automaticamente")
        finishContinuedProcessing(success: false, reason: "conexão realtime perdida")

        engineRunTask?.cancel()
        task?.cancel()
        await socket.close()
    }

    /// Marks a transport loss in Wilderness as a recoverable safety event.
    /// Receive/heartbeat callbacks only request recovery; the parent run Task is
    /// the single owner of the reconnect loop, preventing double reconnects.
    private func requestWildConnectionRecovery(reason: String, runID: UUID) {
        guard activeRunID == runID, activity?.isWildCombat == true, !terminalFailureHandled else { return }

        let lower = reason.lowercased()
        let worldVerification = lower.contains("world") && lower.contains("confirma")
        let degradedPresence = lower.contains("presence degradada") || lower.contains("hits consecutivos")

        if !connectionRecoveryRequested {
            connectionRecoveryDetail = reason
            diagnostic("[WARN] \(reason) • Wilderness: reconexão de emergência solicitada")
            if worldVerification {
                log("🔎 Saída para World sem confirmação • nenhum novo ataque será enviado • verificando região por reconexão")
            } else if degradedPresence {
                log("⚠️ Presence degradada no Wild • ataques suspensos • reconectando para confirmar estado e sair com segurança")
            } else {
                log("⚠️ Conexão perdida no Wild • nenhum novo ataque será enviado • aguardando rede para retornar ao World")
            }
        }
        connectionRecoveryRequested = true
        connected = false
        state = .recovering
        if requestedStopReason == .user {
            statusMessage = "STOP • aguardando rede para saída segura"
        } else if worldVerification {
            statusMessage = "Verificando saída para World"
        } else if degradedPresence {
            statusMessage = "Presence degradada • saída segura"
        } else {
            statusMessage = "Conexão perdida • recuperando saída segura"
        }
        stats.lastEvent = worldVerification ? "verificando região autoritativa" : "reconexão de emergência"
        updateContinuedProcessingProgress(forceTitleUpdate: true)
        engineRunTask?.cancel()
        receiverTask?.cancel()
    }

    @discardableResult
    private func recoverWildAfterUnexpectedDisconnect(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String
    ) async -> Bool {
        guard activeRunID == runID, mode.isWildCombat else { return false }
        guard !connectionRecoveryInProgress else { return false }
        connectionRecoveryInProgress = true
        defer { connectionRecoveryInProgress = false }

        engineRunTask = nil
        receiverTask?.cancel()
        receiverTask = nil
        await socket.close()

        let started = Date()
        // Keep trying while a realistic temporary outage may recover. iOS can
        // still expire the Continued Processing task; no client can send a safe
        // exit while the device has no network at all.
        let recoveryDeadline: TimeInterval = 900
        var attempt = 0
        let lastKnownRegion = player.region.hasPrefix("wild") ? player.region : "wild"
        let recoveryBootstrap = PresenceBootstrap(
            region: lastKnownRegion,
            position: player.position,
            lifeEpoch: max(1, player.lifeEpoch)
        )

        while Date().timeIntervalSince(started) < recoveryDeadline {
            guard activeRunID == runID else { return false }
            attempt += 1
            state = .recovering
            statusMessage = "Reconectando para saída segura • tentativa \(attempt)"
            stats.lastEvent = "reconexão de emergência \(attempt)"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[NET] Reconexão de emergência Wild • \(shard) • tentativa \(attempt)")

            do {
                let stream = try await socket.connect(session: session, shard: shard, bootstrap: recoveryBootstrap)
                await importSocketTrace()
                guard activeRunID == runID else { return false }

                let recoveryEngine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: shard,
                    bootstrap: recoveryBootstrap,
                    fishingBait: selectedFishingBait,
                    reporter: { [weak self] event in
                        self?.handleEngineEvent(event, runID: runID)
                    }
                )
                activeEngine = recoveryEngine
                await recoveryEngine.prepareIdentity()

                receiverTask?.cancel()
                receiverTask = Task { [weak self] in
                    guard let self else { return }
                    for await data in stream {
                        if Task.isCancelled { break }
                        recoveryEngine.ingest(data)
                        await self.importSocketTrace()
                    }
                }

                connected = true
                statusMessage = "Reconectado • saindo do Wild com segurança"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                log("🔁 Conexão restaurada no \(shard) • prioridade absoluta: retornar ao World")

                let outcome = try await recoveryEngine.runEmergencyWildExit(mode: mode)
                receiverTask?.cancel()
                receiverTask = nil
                await importSocketTrace()

                switch outcome {
                case .worldSafe:
                    connected = false
                    currentTarget = nil
                    activity = nil
                    state = .cancelled
                    statusMessage = "Conexão recuperada • World seguro"
                    stats.lastEvent = "World seguro após reconexão"
                    log("✅ Reconexão de emergência concluída • World confirmado • sessão encerrada sem novos ataques")
                    logSessionSummary(mode: mode, outcome: "RECONEXÃO SEGURA")
                    finishContinuedProcessing(success: false, reason: "conexão recuperada com saída segura")
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    return true

                case .alreadyWorld:
                    connected = false
                    currentTarget = nil
                    activity = nil
                    state = .cancelled
                    statusMessage = "Reconectado • personagem já estava no World"
                    stats.lastEvent = "World confirmado após reconexão"
                    log("✅ Reconexão confirmou que o personagem já estava no World • sessão encerrada")
                    logSessionSummary(mode: mode, outcome: "RECONEXÃO • WORLD")
                    finishContinuedProcessing(success: false, reason: "reconexão confirmou World")
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    return true

                case .dead:
                    terminalFailureHandled = true
                    connected = false
                    currentTarget = nil
                    activity = nil
                    state = .failed
                    statusMessage = "Reconectado, mas o servidor confirmou morte"
                    stats.sessionErrors += 1
                    log("💀 Reconexão concluída, porém o servidor já confirmou a morte antes da saída segura")
                    logSessionSummary(mode: mode, outcome: "MORTE APÓS QUEDA")
                    finishContinuedProcessing(success: false, reason: "morte confirmada após queda de conexão")
                    return false
                }
            } catch is CancellationError {
                return false
            } catch {
                await importSocketTrace()
                receiverTask?.cancel()
                receiverTask = nil
                connected = false
                await socket.close()
                let elapsed = Int(Date().timeIntervalSince(started))
                diagnostic("[WARN] Reconexão Wild tentativa \(attempt) falhou após \(elapsed)s: \(error.localizedDescription)")
                let wait = min(6.0, 1.5 + Double(attempt) * 0.5)
                try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
            }
        }

        terminalFailureHandled = true
        realtimeFailureMessage = connectionRecoveryDetail ?? "Conexão realtime perdida no Wild"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Não foi possível reconectar para saída segura"
        stats.sessionErrors += 1
        log("🛑 Reconexão de emergência expirou após 15 minutos • não foi possível confirmar World seguro")
        logSessionSummary(mode: mode, outcome: "FALHA DE RECONEXÃO")
        finishContinuedProcessing(success: false, reason: "reconexão de emergência expirou")
        return false
    }

    private func handleEngineEvent(_ event: EngineEvent, runID: UUID) {
        guard activeRunID == runID else { return }
        // Depois de uma falha terminal a UI já foi encerrada; callbacks atrasados
        // da engine antiga não podem ressuscitar status/contadores nem prender o
        // single-flight. O cleanup do transporte continua em paralelo.
        if activity == nil && (terminalFailureHandled || requestedStopReason != nil) { return }
        switch event {
        case .state(let newState, let message):
            let changed = state != newState || statusMessage != message
            state = newState
            statusMessage = message
            stats.lastEvent = newState.rawValue
            if changed { advanceContinuedProcessingSubprogress() }
            updateContinuedProcessingProgress()

        case .log(let message):
            log(message)

        case .diagnostic(let message):
            diagnostic(message)

        case .target(let target):
            currentTarget = target
            if let target { stats.lastEvent = "target: \(target)" }

        case .attempt:
            stats.attempts += 1
            stats.lastEvent = "tentativa"
            advanceContinuedProcessingSubprogress()
            updateContinuedProcessingProgress()

        case .success(let detail):
            stats.successes += 1
            continuedProgressSubunit = 0
            stats.lastEvent = detail ?? "sucesso"
            if let detail { log("✅ \(detail) • \(stats.successes)/\(sessionGoal)") }
            updateContinuedProcessingProgress(forceTitleUpdate: true)

        case .failure(let reason):
            stats.failures += 1
            stats.lastEvent = reason
            log("⚠️ Falha: \(reason)")
            updateContinuedProcessingProgress()

        case .fatal(let reason):
            guard let currentMode = activity, !terminalFailureHandled else { return }

            // Heartbeat send failure is a transport failure. In Wild it must
            // enter the same emergency-reconnect state machine as a receive-loop
            // close; cancelling the parent here would prevent the eventual safe exit.
            if currentMode.isWildCombat {
                requestWildConnectionRecovery(reason: reason, runID: runID)
                Task { [weak self] in await self?.socket.close() }
                return
            }

            terminalFailureHandled = true
            realtimeFailureMessage = reason
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = reason
            stats.sessionErrors += 1
            stats.lastEvent = "erro fatal"
            diagnostic("[ERROR] \(reason)")
            log("Falha de conexão: \(reason) • bot interrompido automaticamente")
            finishContinuedProcessing(success: false, reason: "erro fatal")
            engineRunTask?.cancel()
            task?.cancel()
            Task { await socket.close() }

        case .hitSent:
            stats.hits += 1
            stats.lastEvent = "ataque enviado"

        case .confirmedHit:
            stats.confirmedHits += 1
            stats.lastEvent = "hit confirmado"
            advanceContinuedProcessingSubprogress()
            updateContinuedProcessingProgress()

        case .hitAckTimeout:
            stats.hitAckTimeouts += 1
            if lastScenePhaseKey == "background" {
                stats.hitAckTimeoutsBackground += 1
            } else {
                stats.hitAckTimeoutsForeground += 1
            }
            stats.lastEvent = "hit ACK timeout"

        case .potionAckTimeout:
            stats.potionAckTimeouts += 1
            if lastScenePhaseKey == "background" {
                stats.potionAckTimeoutsBackground += 1
            } else {
                stats.potionAckTimeoutsForeground += 1
            }
            stats.lastEvent = "drink_ack timeout"

        case .kill:
            stats.kills += 1
            stats.lastEvent = "kill confirmado"

        case .player(let position, let hp, let shield, let region):
            player.position = position
            player.hp = hp
            player.shield = shield
            player.region = region
            world.region = region

        case .world(let nodes, let mobs, let serverRegion):
            resourceCount = nodes
            mobCount = mobs
            world.serverRegion = serverRegion
        }
    }


    // MARK: - Background runtime

    /// Recebe as transições do SwiftUI. No iOS 26, a tarefa contínua é a fonte
    /// principal de runtime em segundo plano. `beginBackgroundTask` é apenas uma
    /// ponte/fallback curta caso o scheduler contínuo ainda não tenha entregue o
    /// handler ou em sistemas anteriores.
    func handleScenePhase(_ phase: ScenePhase) {
        let phaseKey: String
        switch phase {
        case .active: phaseKey = "active"
        case .inactive: phaseKey = "inactive"
        case .background: phaseKey = "background"
        @unknown default: phaseKey = "unknown"
        }
        guard lastScenePhaseKey != phaseKey else { return }
        lastScenePhaseKey = phaseKey

        switch phase {
        case .background:
            guard activity != nil else { return }
            if continuedTaskObject != nil {
                diagnostic("[BG] App em segundo plano • Continued Processing ATIVA • realtime preservado")
            } else if continuedTaskRequested {
                diagnostic("[BG] App em segundo plano • Continued Processing ainda sem confirmação • ativando ponte curta")
                beginLegacyBackgroundTaskIfNeeded()
            } else {
                diagnostic("[BG] App em segundo plano • Continued Processing não ativa • ativando janela curta")
                beginLegacyBackgroundTaskIfNeeded()
            }

        case .active:
            if activity != nil {
                if continuedTaskObject != nil {
                    diagnostic("[BG] App em primeiro plano • Continued Processing continua ativa")
                } else if continuedTaskRequested {
                    diagnostic("[BG] App em primeiro plano • engine continua na mesma sessão • Continued Processing ainda pendente")
                } else {
                    diagnostic("[BG] App em primeiro plano • engine continua na mesma sessão")
                }
            }
            endLegacyBackgroundTask()

        case .inactive:
            break

        @unknown default:
            break
        }
    }

    private func prepareContinuedProcessing(for mode: ActivityMode) {
        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = nil
        continuedTaskMode = mode
        continuedTaskRequested = false
        continuedTaskObject = nil
        continuedTaskIdentifier = nil
        continuedTaskSubmissionAttempt = 0
        continuedProgressSubunit = 0
        lastContinuedTitleSuccesses = -1
        lastContinuedPublicStatus = ""
        lastScenePhaseKey = nil

        guard #available(iOS 26.0, *) else {
            diagnostic("[BG] iOS anterior ao 26 • usando somente extensão curta de background")
            return
        }

        let appState: String
        switch UIApplication.shared.applicationState {
        case .active: appState = "active"
        case .inactive: appState = "inactive"
        case .background: appState = "background"
        @unknown default: appState = "unknown"
        }

        let refreshStatus: String
        switch UIApplication.shared.backgroundRefreshStatus {
        case .available: refreshStatus = "available"
        case .denied: refreshStatus = "denied"
        case .restricted: refreshStatus = "restricted"
        @unknown default: refreshStatus = "unknown"
        }

        let bundleID = Bundle.main.bundleIdentifier ?? "<desconhecido>"
        let expectedWildcard = "\(bundleID).continuedBot.*"
        let permitted = Bundle.main.object(forInfoDictionaryKey: "BGTaskSchedulerPermittedIdentifiers") as? [String] ?? []
        let wildcardOK = permitted.contains(expectedWildcard)
        diagnostic("[BG] Ambiente • app=\(appState) • Background App Refresh=\(refreshStatus) • Low Power=\(ProcessInfo.processInfo.isLowPowerModeEnabled ? "on" : "off") • wildcard=\(wildcardOK ? "ok" : "ausente")")
        if refreshStatus != "available" {
            diagnostic("[WARN] Background App Refresh não está disponível • Ajustes > Geral > Atualização em 2º Plano pode impedir BackgroundTasks")
        }
        if !wildcardOK {
            diagnostic("[ERROR] BGTaskSchedulerPermittedIdentifiers não contém \(expectedWildcard) • Continued Processing desativada")
            return
        }

        submitContinuedProcessingAttempt(for: mode, requestedGoal: min(100_000, max(1, sessionGoal)), attempt: 1)
    }

    @available(iOS 26.0, *)
    private func submitContinuedProcessingAttempt(for mode: ActivityMode, requestedGoal: Int, attempt: Int) {
        guard continuedTaskObject == nil else { return }

        let identifier = "\(continuedTaskIdentifierPrefix).\(UUID().uuidString.lowercased())"
        continuedTaskIdentifier = identifier
        continuedTaskSubmissionAttempt = attempt

        let registered = BGTaskScheduler.shared.register(
            forTaskWithIdentifier: identifier,
            using: nil
        ) { [weak self] task in
            guard let continued = task as? BGContinuedProcessingTask else {
                task.setTaskCompleted(success: false)
                return
            }

            Task { @MainActor [weak self] in
                guard let self else {
                    continued.setTaskCompleted(success: false)
                    return
                }
                self.attachContinuedProcessingTask(continued, identifier: identifier)
            }
        }

        guard registered else {
            continuedTaskRequested = false
            continuedTaskIdentifier = nil
            diagnostic("[WARN] Continued Processing não pôde ser registrada • tentativa \(attempt)/3 • fallback curto será usado")
            return
        }

        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier,
            title: "Kintarabot • \(mode.localizedTitle)",
            subtitle: "Meta \(requestedGoal) • preparando"
        )

        // Realtime precisa de proteção AGORA. A Apple usa .fail para tarefas que
        // só fazem sentido se puderem iniciar imediatamente. No SDK 26 submit(_:)
        // pode raramente ser aceito sem entregar o handler; o watchdog abaixo faz
        // no máximo duas novas tentativas, sempre com identificador único.
        request.strategy = .fail

        diagnostic("[BG] Solicitando Continued Processing • \(mode.localizedTitle) • meta \(requestedGoal) • tentativa \(attempt)/3")

        do {
            continuedTaskRequested = true
            try BGTaskScheduler.shared.submit(request)
            diagnostic("[BG] Solicitação aceita pelo submit • estratégia=fail • aguardando handler do scheduler")
            armContinuedProcessingActivationWatchdog(identifier: identifier)
        } catch {
            continuedTaskRequested = false
            continuedTaskIdentifier = nil
            diagnostic("[WARN] Continued Processing recusada imediatamente: \(error.localizedDescription) • fallback curto disponível")
        }
    }

    @available(iOS 26.0, *)
    private func attachContinuedProcessingTask(
        _ backgroundTask: BGContinuedProcessingTask,
        identifier: String
    ) {
        guard continuedTaskIdentifier == identifier,
              continuedTaskRequested,
              continuedTaskObject == nil
        else {
            backgroundTask.setTaskCompleted(success: false)
            return
        }

        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = nil
        continuedTaskObject = backgroundTask
        continuedTaskRequested = false

        backgroundTask.expirationHandler = { [weak self, weak backgroundTask] in
            guard let backgroundTask else { return }
            Task { @MainActor [weak self] in
                self?.handleContinuedProcessingExpiration(backgroundTask)
            }
        }

        updateContinuedProcessingProgress(forceTitleUpdate: true)
        let current = min(max(0, stats.successes), max(1, sessionGoal))
        diagnostic("[BG] ✅ Continued Processing INICIADA • \((activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade") • \(current)/\(max(1, sessionGoal)) • tentativa \(continuedTaskSubmissionAttempt)/3")
        endLegacyBackgroundTask()
    }

    private func armContinuedProcessingActivationWatchdog(identifier: String) {
        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = Task { [weak self] in
            do {
                try await Task.sleep(for: .milliseconds(1_500))
            } catch {
                return
            }

            guard !Task.isCancelled, let self else { return }
            self.handleContinuedProcessingActivationTimeout(identifier: identifier)
        }
    }

    private func handleContinuedProcessingActivationTimeout(identifier: String) {
        guard #available(iOS 26.0, *),
              continuedTaskIdentifier == identifier,
              continuedTaskRequested,
              continuedTaskObject == nil
        else { return }

        continuedTaskActivationWatchdog = nil
        let attempt = continuedTaskSubmissionAttempt
        diagnostic("[BG] Handler não chegou em 1.5s • verificando scheduler • tentativa \(attempt)/3")

        BGTaskScheduler.shared.getPendingTaskRequests { [weak self] requests in
            let pending = requests.contains { $0.identifier == identifier }
            Task { @MainActor [weak self] in
                guard let self,
                      self.continuedTaskIdentifier == identifier,
                      self.continuedTaskObject == nil,
                      self.continuedTaskRequested
                else { return }

                if pending {
                    self.diagnostic("[BG] Scheduler confirmou request pendente • ponte UIKit cobrirá a transição")
                    return
                }

                guard UIApplication.shared.applicationState == .active else {
                    self.diagnostic("[WARN] Continued Processing sem handler e sem request pendente • app já saiu do foreground; somente ponte UIKit está disponível")
                    self.continuedTaskRequested = false
                    self.continuedTaskIdentifier = nil
                    return
                }

                if attempt < 3, let mode = self.continuedTaskMode {
                    BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
                    self.continuedTaskRequested = false
                    self.diagnostic("[BG] Scheduler não reteve a request • repetindo com novo identificador")
                    self.submitContinuedProcessingAttempt(
                        for: mode,
                        requestedGoal: min(100_000, max(1, self.sessionGoal)),
                        attempt: attempt + 1
                    )
                } else {
                    BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier)
                    self.continuedTaskRequested = false
                    self.continuedTaskIdentifier = nil
                    self.diagnostic("[WARN] Continued Processing não foi concedida após 3 tentativas • foreground continua normal; em background haverá apenas a janela curta do UIKit")
                }
            }
        }
    }

    private func advanceContinuedProcessingSubprogress() {
        guard continuedTaskObject != nil else { return }
        continuedProgressSubunit = min(99, continuedProgressSubunit + 1)
    }

    private func updateContinuedProcessingProgress(forceTitleUpdate: Bool = false) {
        guard #available(iOS 26.0, *),
              let backgroundTask = continuedTaskObject as? BGContinuedProcessingTask
        else { return }

        // Progresso interno continua granular; o texto mostrado pelo sistema
        // usa a mesma fonte visível do card da atividade no app.
        let goalUnits = Int64(max(1, sessionGoal))
        let total = goalUnits * 100
        let successBase = Int64(min(max(0, stats.successes), max(1, sessionGoal))) * 100
        let completed = min(total, successBase + Int64(continuedProgressSubunit))
        backgroundTask.progress.totalUnitCount = total
        backgroundTask.progress.completedUnitCount = completed

        guard let mode = activity ?? continuedTaskMode else { return }
        let publicStatus = displayStatusMessage
        let successChanged = lastContinuedTitleSuccesses != stats.successes
        let statusChanged = lastContinuedPublicStatus != publicStatus

        // A superfície do sistema deve acompanhar o mesmo texto que o card do
        // app. Cada mudança visível relevante atualiza o título; não há mais
        // formatter genérico que substitua "Peixe #N • fisgada em ...".
        guard forceTitleUpdate || successChanged || statusChanged else { return }

        backgroundTask.updateTitle(
            "Kintarabot • \(mode.localizedTitle)",
            subtitle: "\(stats.successes)/\(max(1, sessionGoal)) • \(publicStatus)"
        )
        lastContinuedTitleSuccesses = stats.successes
        lastContinuedPublicStatus = publicStatus
    }

    private func finishContinuedProcessing(success: Bool, reason: String) {
        let pendingIdentifier = continuedTaskIdentifier
        let hadPendingRequest = continuedTaskRequested

        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = nil
        continuedTaskRequested = false

        if #available(iOS 26.0, *) {
            if let backgroundTask = continuedTaskObject as? BGContinuedProcessingTask {
                let total = Int64(max(1, sessionGoal)) * 100
                backgroundTask.progress.totalUnitCount = total
                if success {
                    backgroundTask.progress.completedUnitCount = total
                } else {
                    let base = Int64(min(max(0, stats.successes), max(1, sessionGoal))) * 100
                    backgroundTask.progress.completedUnitCount = min(total, base + Int64(continuedProgressSubunit))
                }
                backgroundTask.expirationHandler = nil
                backgroundTask.updateTitle(
                    "Kintarabot • \((activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade")",
                    subtitle: success ? "\(stats.successes)/\(max(1, sessionGoal)) • Meta concluída" : "Encerrada • \(reason)"
                )
                backgroundTask.setTaskCompleted(success: success)
                diagnostic("[BG] Continued Processing encerrada • sucesso=\(success ? "sim" : "não") • \(reason)")
            } else if hadPendingRequest, let pendingIdentifier {
                BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: pendingIdentifier)
                diagnostic("[BG] Solicitação Continued Processing pendente cancelada • \(reason)")
            }
        }

        continuedTaskObject = nil
        continuedTaskMode = nil
        continuedTaskIdentifier = nil
        continuedTaskSubmissionAttempt = 0
        continuedProgressSubunit = 0
        endLegacyBackgroundTask()
    }

    @available(iOS 26.0, *)
    private func handleContinuedProcessingExpiration(_ backgroundTask: BGContinuedProcessingTask) {
        guard continuedTaskObject === backgroundTask else {
            backgroundTask.setTaskCompleted(success: false)
            return
        }

        // Se a task expirar durante uma queda de rede no Wild, não destrua a
        // única tentativa de recuperação existente. Enquanto o callback ainda
        // receber runtime, mantenha a reconexão; se o iOS matar o processo depois
        // disso não existe comando offline capaz de garantir a saída.
        if activity?.isWildCombat == true, connectionRecoveryRequested {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            state = .recovering
            statusMessage = "Background expirando • aguardando rede para saída segura"
            stats.lastEvent = "expiração durante reconexão Wild"
            diagnostic("[BG] Expiração recebida durante queda de conexão no Wild • preservando reconexão de emergência enquanto houver runtime")
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            return
        }

        // Wild combat usa encerramento cooperativo enquanto o callback ainda tem
        // runtime: parar novos hits -> safe camp -> combat timer 0 -> World.
        if activity?.isWildCombat == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            activeEngine.requestSafeStop(reason: requestedStopReason ?? .backgroundExpiration)
            state = .recovering
            statusMessage = "Background expirando • saída imediata para o World"
            stats.lastEvent = "saída de emergência por expiração"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[BG] Expiração recebida no Wild • emergency-exit solicitado • recovery/XP/loot deixam de ter prioridade")
            return
        }

        requestedStopReason = .backgroundExpiration
        terminalFailureHandled = true
        let expiringRunID = activeRunID
        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = nil
        continuedTaskObject = nil
        continuedTaskRequested = false
        continuedTaskMode = nil
        continuedTaskIdentifier = nil
        backgroundTask.expirationHandler = nil
        backgroundTask.setTaskCompleted(success: false)

        // `engineRunTask` é uma Task independente da Task pai. Cancelar apenas
        // `task` deixava Fishing viva depois da expiração e mantinha activeRunID
        // ocupado (sessão fantasma / start ignorado). Encerre todos os donos da
        // sessão explicitamente e só libere single-flight depois do socket fechar.
        engineRunTask?.cancel()
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = "Execução em segundo plano encerrada pelo iOS"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Segundo plano encerrado pelo iOS"
        stats.sessionErrors += 1
        stats.lastEvent = "background expirado"
        diagnostic("[ERROR] BGContinuedProcessingTask expirou/cancelou • atividade não-Wild interrompida automaticamente")
        log("Falha: execução em segundo plano encerrada pelo iOS • bot interrompido automaticamente")
        Task { [weak self] in
            guard let self else { return }
            await self.socket.close()
            if let expiringRunID { self.completeRunCleanup(runID: expiringRunID) }
        }
        endLegacyBackgroundTask()
    }

    private func beginLegacyBackgroundTaskIfNeeded() {
        guard activity != nil, legacyBackgroundTask == .invalid else { return }

        let app = UIApplication.shared
        legacyBackgroundTask = app.beginBackgroundTask(withName: "KintarabotRealtime") { [weak self] in
            Task { @MainActor [weak self] in
                self?.handleLegacyBackgroundExpiration()
            }
        }

        if legacyBackgroundTask != .invalid {
            diagnostic("[BG] Extensão curta UIKit ativa • ponte temporária para preservar realtime")
        }
    }

    private func handleLegacyBackgroundExpiration() {
        if continuedTaskObject != nil {
            endLegacyBackgroundTask()
            return
        }

        endLegacyBackgroundTask()

        if continuedTaskRequested {
            diagnostic("[WARN] Ponte UIKit esgotada • Continued Processing segue pendente; engine preservada para o scheduler assumir")
            return
        }

        diagnostic("[WARN] Janela curta de background esgotada sem Continued Processing ativa")
        guard activity != nil else { return }

        if activity?.isWildCombat == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            activeEngine.requestSafeStop(reason: requestedStopReason ?? .backgroundExpiration)
            state = .recovering
            statusMessage = "Background expirando • saída imediata para o World"
            stats.lastEvent = "saída de emergência por background"
            diagnostic("[BG] Runtime curto esgotou no Wild • emergency-exit solicitado")
            return
        }

        requestedStopReason = .backgroundExpiration
        terminalFailureHandled = true
        let expiringRunID = activeRunID
        engineRunTask?.cancel()
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = "Execução contínua em segundo plano não foi concedida pelo iOS"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Segundo plano indisponível"
        stats.sessionErrors += 1
        stats.lastEvent = "background indisponível"
        log("Falha: Continued Processing não ficou ativa e a janela curta terminou • bot interrompido automaticamente")
        Task { [weak self] in
            guard let self else { return }
            await self.socket.close()
            if let expiringRunID { self.completeRunCleanup(runID: expiringRunID) }
        }
    }

    private func endLegacyBackgroundTask() {
        guard legacyBackgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(legacyBackgroundTask)
        legacyBackgroundTask = .invalid
    }

    private func importSocketTrace() async {
        let lines = await socket.drainTrace()
        for line in lines {
            let lower = line.lowercased()
            let expectedCleanup = requestedStopReason != nil || terminalFailureHandled || activity == nil
            if expectedCleanup && (
                lower.contains("software caused connection abort") ||
                lower.contains("operation cancelled") ||
                lower.contains("operation canceled") ||
                lower.contains("falhou: cancelled") ||
                lower.contains("falhou: canceled") ||
                (lower.contains("abortado em") && (lower.contains("cancelled") || lower.contains("canceled")))
            ) {
                continue
            }
            diagnostic(line)
        }
    }

    private func timestamped(_ value: String) -> String {
        "\(Date.now.formatted(date: .omitted, time: .standard))  \(value)"
    }

    private func trimLogs() {
        if logs.count > 300 {
            logs.removeFirst(logs.count - 300)
        }
        if diagnosticLogs.count > 10_000 {
            diagnosticLogs.removeFirst(diagnosticLogs.count - 10_000)
        }
    }
}

final class SessionManager {
    private let key = "kinttany.session.cookie"
    var cookie: String? { KeychainStore.get(key) }
    func save(cookie: String) { KeychainStore.set(key, cookie) }
    func clear() { KeychainStore.delete(key) }
}
