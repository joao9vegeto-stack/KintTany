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
    static func status(
        mode: ActivityMode,
        state: ActivityState,
        currentTarget: String?,
        rawStatus: String
    ) -> String {
        if mode.isWildCombat,
           state == .recovering,
           rawStatus.localizedCaseInsensitiveContains("saindo") {
            return "Saindo do combate com segurança"
        }

        switch mode {
        case .tree:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando árvore"
            case .recovering, .syncing: return "Sincronizando árvore"
            case .completed, .cooldown: return "Madeira concluída"
            default: return "Cortando árvore"
            }
        case .stone:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando pedra"
            case .recovering, .syncing: return "Sincronizando pedra"
            case .completed, .cooldown: return "Pedra concluída"
            default: return "Minerando pedra"
            }
        case .coal:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando carvão"
            case .recovering, .syncing: return "Sincronizando carvão"
            case .completed, .cooldown: return "Carvão concluído"
            default: return "Minerando carvão"
            }
        case .fishing:
            switch state {
            case .searching, .selectingTarget, .moving, .syncing, .preparingAction:
                return "Preparando pesca"
            case .recovering: return "Ressincronizando pesca"
            case .completed, .cooldown: return "Peixe confirmado"
            default: return "Aguardando fisgada"
            }
        case .chicken:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando galinha"
            case .completed, .cooldown: return "Galinha derrotada"
            default: return "Combatendo galinha"
            }
        case .zombie:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando zumbi"
            case .recovering: return "Recuperando com segurança"
            case .completed, .cooldown: return "Zumbi derrotado"
            default: return "Em combate com zumbi"
            }
        case .dragon:
            switch state {
            case .searching, .selectingTarget, .moving: return "Procurando dragão"
            case .recovering: return "Recuperando com segurança"
            case .completed, .cooldown: return "Dragão derrotado"
            default: return "Em combate com dragão"
            }
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

struct ActivityStats: Codable {
    var attempts = 0
    var successes = 0
    var failures = 0
    var hits = 0
    var confirmedHits = 0
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
    @Published var logs: [String] = []
    @Published var diagnosticLogs: [String] = []
    @Published var connected = false
    @Published var currentTarget: String?
    @Published var statusMessage = "Pronto para iniciar"
    @Published var resourceCount = 0
    @Published var mobCount = 0

    private let session = SessionManager()
    private var task: Task<Void, Never>?
    private var receiverTask: Task<Void, Never>?
    private var traceTask: Task<Void, Never>?
    private var realtimeFailureMessage: String?
    private var terminalFailureHandled = false
    private let socket = RealtimeSocket()
    private var activeEngine: AutomationEngine?
    private var activeRunID: UUID?
    private var requestedStopReason: EngineStopReason?

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
    private var lastContinuedTitleUpdateAt: TimeInterval = 0
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
        min(1, Double(stats.successes) / Double(max(goal, 1)))
    }

    func start(_ mode: ActivityMode) {
        // Single-flight: um segundo toque nunca cancela e substitui uma sessão que
        // ainda está fechando. Isso elimina corrida entre socket/engine antiga e nova.
        guard task == nil, activeRunID == nil, activity == nil else {
            diagnostic("[STATE] start ignorado • já existe execução/encerramento em andamento")
            return
        }

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

        log("📊 RESUMO DA SESSÃO • \(mode.localizedTitle) • \(outcome)")
        log("Meta \(goal) • sucessos \(stats.successes) • tentativas \(stats.attempts) • falhas \(stats.failures) • tempo \(duration)")
        if mode == .chicken || mode.isWildCombat {
            log("Combate • hits enviados \(stats.hits) • hits confirmados \(stats.confirmedHits) • kills \(stats.kills)")
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
        let runGoal = goal
        realtimeFailureMessage = nil
        terminalFailureHandled = false

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

        let bootstrap = AutomationEngine.bootstrap(for: mode)

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
            await importSocketTrace()

            log("Servidor NA selecionado automaticamente: \(connection.serverName) (\(selectedShard)) • carga \(connection.populationLabel) • fila \(connection.queueLength)")

            let engine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: selectedShard,
                bootstrap: bootstrap,
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

            let result = try await engine.run(mode: mode, goal: runGoal)
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
                activity = nil
                log("✅ Meta concluída: \(result.successes)/\(runGoal) • atividade encerrada automaticamente")
                logSessionSummary(mode: mode, outcome: "META CONCLUÍDA")
                finishContinuedProcessing(success: true, reason: "meta concluída")
            } else {
                state = .failed
                statusMessage = "Engine encerrou antes da meta"
                stats.failures += 1
                currentTarget = nil
                activity = nil
                log("Atividade encerrou antes da meta • bot interrompido automaticamente")
                logSessionSummary(mode: mode, outcome: "ENCERRADA ANTES DA META")
                finishContinuedProcessing(success: false, reason: "engine encerrou antes da meta")
            }
        } catch is CancellationError {
            await importSocketTrace()
            guard activeRunID == runID else { return }
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
            if terminalFailureHandled { return }
            terminalFailureHandled = true
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = error.localizedDescription
            stats.failures += 1
            diagnostic("[ERROR] \(error.localizedDescription)")
            log("Falha: \(error.localizedDescription) • bot interrompido automaticamente")
            logSessionSummary(mode: mode, outcome: "FALHA")
            finishContinuedProcessing(success: false, reason: "falha da atividade")
        }
    }

    private func handleUnexpectedRealtimeEnd(for mode: ActivityMode, runID: UUID) async {
        guard activeRunID == runID, activity == mode, connected, !terminalFailureHandled else { return }
        terminalFailureHandled = true

        await importSocketTrace()
        let detail = await socket.disconnectReason()
        let reason: String
        if let detail, !detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            reason = "Conexão realtime perdida: \(detail)"
        } else {
            reason = "Conexão realtime encerrada inesperadamente"
        }

        realtimeFailureMessage = reason
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = reason
        stats.failures += 1
        diagnostic("[ERROR] \(reason)")
        log("Falha de conexão: \(reason) • bot interrompido automaticamente")
        finishContinuedProcessing(success: false, reason: "conexão realtime perdida")

        // Cancela imediatamente a engine; nenhuma nova ação deve sobreviver
        // à perda da Presence. O catch de CancellationError preserva .failed.
        task?.cancel()
        await socket.close()
    }

    private func handleEngineEvent(_ event: EngineEvent, runID: UUID) {
        guard activeRunID == runID else { return }
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
            if let detail { log("✅ \(detail) • \(stats.successes)/\(goal)") }
            updateContinuedProcessingProgress(forceTitleUpdate: true)

        case .failure(let reason):
            stats.failures += 1
            stats.lastEvent = reason
            log("⚠️ Falha: \(reason)")
            updateContinuedProcessingProgress()

        case .fatal(let reason):
            guard activity != nil, !terminalFailureHandled else { return }
            terminalFailureHandled = true
            realtimeFailureMessage = reason
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = reason
            stats.failures += 1
            stats.lastEvent = "erro fatal"
            diagnostic("[ERROR] \(reason)")
            log("Falha de conexão: \(reason) • bot interrompido automaticamente")
            finishContinuedProcessing(success: false, reason: "erro fatal")
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
        lastContinuedTitleUpdateAt = 0
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

        submitContinuedProcessingAttempt(for: mode, requestedGoal: min(100_000, max(1, goal)), attempt: 1)
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
        let current = min(max(0, stats.successes), max(1, goal))
        diagnostic("[BG] ✅ Continued Processing INICIADA • \((activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade") • \(current)/\(max(1, goal)) • tentativa \(continuedTaskSubmissionAttempt)/3")
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
                        requestedGoal: min(100_000, max(1, self.goal)),
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

        // Progresso interno continua granular; o texto público é desacoplado dos
        // detalhes de protocolo (proof/handshake/wear) e sofre throttling visual.
        let goalUnits = Int64(max(1, goal))
        let total = goalUnits * 100
        let successBase = Int64(min(max(0, stats.successes), max(1, goal))) * 100
        let completed = min(total, successBase + Int64(continuedProgressSubunit))
        backgroundTask.progress.totalUnitCount = total
        backgroundTask.progress.completedUnitCount = completed

        guard let mode = activity ?? continuedTaskMode else { return }
        let publicStatus = ContinuedActivityStatusFormatter.status(
            mode: mode,
            state: state,
            currentTarget: currentTarget,
            rawStatus: statusMessage
        )
        let now = Date().timeIntervalSince1970
        let successChanged = lastContinuedTitleSuccesses != stats.successes
        let statusChanged = lastContinuedPublicStatus != publicStatus
        let throttleElapsed = now - lastContinuedTitleUpdateAt >= 1.0
        guard forceTitleUpdate || successChanged || (statusChanged && throttleElapsed) || throttleElapsed else { return }

        backgroundTask.updateTitle(
            "Kintarabot • \(mode.localizedTitle)",
            subtitle: "\(stats.successes)/\(max(1, goal)) • \(publicStatus)"
        )
        lastContinuedTitleUpdateAt = now
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
                let total = Int64(max(1, goal)) * 100
                backgroundTask.progress.totalUnitCount = total
                if success {
                    backgroundTask.progress.completedUnitCount = total
                } else {
                    let base = Int64(min(max(0, stats.successes), max(1, goal))) * 100
                    backgroundTask.progress.completedUnitCount = min(total, base + Int64(continuedProgressSubunit))
                }
                backgroundTask.expirationHandler = nil
                backgroundTask.updateTitle(
                    "Kintarabot • \((activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade")",
                    subtitle: success ? "Meta concluída" : "Encerrada • \(reason)"
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

        // Wild combat usa encerramento cooperativo enquanto o callback ainda tem
        // runtime: parar novos hits -> safe camp -> combat timer 0 -> World.
        if activity?.isWildCombat == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            activeEngine.requestSafeStop(reason: requestedStopReason ?? .backgroundExpiration)
            state = .recovering
            statusMessage = "Saindo do combate com segurança"
            stats.lastEvent = "safe stop por expiração"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[BG] Expiração recebida no Wild • safe-stop solicitado antes de concluir a tarefa")
            return
        }

        requestedStopReason = .backgroundExpiration
        continuedTaskActivationWatchdog?.cancel()
        continuedTaskActivationWatchdog = nil
        continuedTaskObject = nil
        continuedTaskRequested = false
        continuedTaskMode = nil
        continuedTaskIdentifier = nil
        backgroundTask.expirationHandler = nil
        backgroundTask.setTaskCompleted(success: false)

        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = "Execução em segundo plano encerrada pelo iOS"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Segundo plano encerrado pelo iOS"
        stats.failures += 1
        stats.lastEvent = "background expirado"
        diagnostic("[ERROR] BGContinuedProcessingTask expirou/cancelou • atividade não-Wild interrompida automaticamente")
        log("Falha: execução em segundo plano encerrada pelo iOS • bot interrompido automaticamente")
        Task { await socket.close() }
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
            statusMessage = "Saindo do combate com segurança"
            stats.lastEvent = "safe stop por background"
            diagnostic("[BG] Runtime curto esgotou no Wild • safe-stop solicitado")
            return
        }

        requestedStopReason = .backgroundExpiration
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = "Execução contínua em segundo plano não foi concedida pelo iOS"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Segundo plano indisponível"
        stats.failures += 1
        stats.lastEvent = "background indisponível"
        log("Falha: Continued Processing não ficou ativa e a janela curta terminou • bot interrompido automaticamente")
        Task { await socket.close() }
    }

    private func endLegacyBackgroundTask() {
        guard legacyBackgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(legacyBackgroundTask)
        legacyBackgroundTask = .invalid
    }

    private func importSocketTrace() async {
        let lines = await socket.drainTrace()
        for line in lines {
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
