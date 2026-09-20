import Foundation
import SwiftUI
import UIKit
import BackgroundTasks

enum ActivityMode: String, CaseIterable, Codable, Identifiable {
    case tree, coal, stone, iron, silver, cacti, fishing, chicken, zombie, dragon

    var id: String { rawValue }

    var title: String {
        switch self {
        case .tree: "Tree"
        case .coal: "Coal"
        case .stone: "Stone"
        case .iron: "Iron Ore"
        case .silver: "Silver Ore"
        case .cacti: "Cacti"
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
        case .iron: "Iron Ore"
        case .silver: "Silver Ore"
        case .cacti: "Cacti"
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
        case .iron: "diamond.fill"
        case .silver: "sparkles"
        case .cacti: "leaf.fill"
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
        case .iron: .blue
        case .silver: .indigo
        case .cacti: .green
        case .fishing: .cyan
        case .chicken: .yellow
        case .zombie: .mint
        case .dragon: .red
        }
    }

    var isWildCombat: Bool {
        self == .zombie || self == .dragon
    }

    var isGathering: Bool {
        self == .tree || self == .stone || self == .coal || self == .iron || self == .silver || self == .cacti
    }

    var isDunesGathering: Bool {
        self == .silver || self == .cacti
    }

    var requiresSafeExit: Bool {
        isWildCombat || isDunesGathering
    }

    var isExperimental: Bool {
        isDunesGathering
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

    var isAutomationValidated: Bool { self == .feather || self == .trout }

    var supportLabel: String {
        self == .feather ? "The Pond • validado" : (self == .trout ? "Whisperwood • Trout • validado" : "protocolo da zona ainda não validado")
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
        case .iron: return "Minerando Iron Ore"
        case .silver: return "Minerando Silver Ore nas Dunes"
        case .cacti: return "Coletando Cacti nas Dunes"
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

/// Build 73: a Presence usada para o preflight transacional do banco não é
/// reaproveitada para entrar na região de coleta. A evidência de runtime mostra
/// que World→Eldergrove pode não receber region_ack após o ciclo do banco,
/// enquanto uma Presence nova já bootstrapada na região funciona normalmente.
struct GatherPresenceHandoffPolicy {
    static func requiresFreshActivityPresence(after disposition: GatherToolPreflightDisposition) -> Bool {
        if case .needsWorld = disposition { return true }
        return false
    }
}

/// Build 75: a Dunes run has a safe preflight phase (World/bank_shop) and a
/// full-loot phase. A transport loss during safe preflight must never be
/// reported as a Dunes/Shores recovery because the desert Presence has not
/// started yet. Once entry into `desert` is attempted, recovery becomes
/// conservative and assumes full-loot exposure until The Shores is proven.
enum DunesPresencePhase: Equatable {
    case inactive
    case preflightSafe
    case fullLootOrEntering
}

struct DunesPresenceSafetyPolicy {
    static func requiresShoresRecovery(mode: ActivityMode, phase: DunesPresencePhase) -> Bool {
        mode.isDunesGathering && phase == .fullLootOrEntering
    }
}

struct DunesCheckpointPolicy {
    /// Build 78: protect full-loot resources after at most 25 successful nodes,
    /// but never remain continuously exposed for more than three minutes.
    static let successInterval = 25
    static let maximumExposureMS: Double = 180_000

    static func phaseGoal(totalGoal: Int, completed: Int) -> Int {
        min(successInterval, max(0, totalGoal - completed))
    }

    static func exposureLimitReached(startedAtMS: Double, nowMS: Double) -> Bool {
        nowMS - startedAtMS >= maximumExposureMS
    }

    static func needsAnotherPhase(totalGoal: Int, completed: Int) -> Bool {
        completed < totalGoal
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
    var stateConfirmedHits = 0
    var hitAckTimeouts = 0
    var hitAckTimeoutsForeground = 0
    var hitAckTimeoutsBackground = 0
    var potionAckTimeouts = 0
    var potionAckTimeoutsForeground = 0
    var potionAckTimeoutsBackground = 0
    var gatherRecoveries = 0
    var gatherRecoveriesForeground = 0
    var gatherRecoveriesBackground = 0
    var gatherProofMisses = 0
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
    private var dunesPresencePhase: DunesPresencePhase = .inactive
    private var dunesExpectedTool: DunesToolInstanceIdentity?
    private var dunesExpectedLifeEpoch: Int?

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
    private var backgroundEnteredAt: Date?
    private var accumulatedBackgroundSeconds: TimeInterval = 0
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
        guard activeRunID != nil else {
            if !silent { log("STOP ignorado — nenhuma atividade está em execução") }
            return
        }
        let stoppedMode = activity
        guard requestedStopReason == nil else { return }
        requestedStopReason = .user

        // Se a Presence já caiu em uma região full-loot, o único caminho capaz
        // de tentar uma saída segura é manter a reconexão de emergência viva.
        // STOP apenas confirma a intenção; cancelar a Task impediria justamente
        // o retorno a World/The Shores quando a rede reaparecesse.
        if activity?.requiresSafeExit == true, connectionRecoveryRequested {
            state = .recovering
            statusMessage = "STOP • aguardando rede para saída segura"
            stats.lastEvent = "STOP aguardando reconexão"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                let destination = stoppedMode?.isDunesGathering == true ? "The Shores" : "World"
                log("STOP registrado durante queda de conexão • reconexão de emergência continuará apenas para voltar a \(destination)")
            }
            return
        }

        // Em regiões full-loot o STOP é cooperativo. A engine deixa de criar
        // novas ações e confirma World/The Shores antes de liberar a Presence.
        if activity?.requiresSafeExit == true, connected, let activeEngine {
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: .user)
            }
            state = .recovering
            statusMessage = stoppedMode?.isDunesGathering == true
                ? "Saindo das Dunes com segurança"
                : "Saindo do combate com segurança"
            stats.lastEvent = "safe stop solicitado"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                let region = stoppedMode?.isDunesGathering == true ? "Dunes" : "Wilderness"
                log("STOP solicitado — encerrando \(region) com segurança antes de fechar a conexão")
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
        closeTerminalNonWildPresenceNow(reason: "STOP")
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
        dunesPresencePhase = .inactive
        dunesExpectedTool = nil
        dunesExpectedLifeEpoch = nil
        activeRunID = nil
        requestedStopReason = nil
        task = nil
        connected = false
    }

    /// AutomationEngine is intentionally isolated from MainActor. UI delivery
    /// remains ordered by the engine but can be coalesced/delayed by iOS without
    /// delaying ACK ingestion, movement or action frames.
    private func engineReporter(runID: UUID) -> AutomationEngine.Reporter {
        { [weak self] event in
            Task { @MainActor [weak self] in
                self?.handleEngineEvent(event, runID: runID)
            }
        }
    }

    /// Consume the socket stream on the cooperative executor rather than on
    /// SwiftUI's MainActor. Socket trace is already imported by traceTask at a
    /// controlled cadence, so it is not mirrored once per realtime packet here.
    private func makeReceiverTask(
        stream: AsyncStream<Data>,
        engine: AutomationEngine,
        mode: ActivityMode,
        runID: UUID,
        notifyUnexpectedEnd: Bool = true
    ) -> Task<Void, Never> {
        Task.detached(priority: .userInitiated) { [weak self] in
            for await data in stream {
                if Task.isCancelled { break }
                await engine.ingest(data)
            }

            if notifyUnexpectedEnd, !Task.isCancelled {
                await self?.handleUnexpectedRealtimeEnd(for: mode, runID: runID)
            }
        }
    }

    /// Last line of defense for every terminal path reached while a Wild
    /// engine still exists. Returning from this method means the server either
    /// confirmed World/death or the emergency reconnect loop took ownership.
    private func containWildTerminalFailure(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        engine: AutomationEngine,
        failure: String
    ) async {
        diagnostic("[WILD][FAILSAFE] \(failure) • bloqueando encerramento dentro da Wilderness")
        state = .recovering
        statusMessage = "Falha detectada • saindo da Wilderness com segurança"
        stats.lastEvent = "failsafe Wild • retorno ao World"
        updateContinuedProcessingProgress(forceTitleUpdate: true)

        do {
            let outcome = try await engine.runEmergencyWildExit(
                mode: mode,
                reason: "falha operacional: \(failure)"
            )
            await importSocketTrace()
            terminalFailureHandled = true
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            stats.sessionErrors += 1

            switch outcome {
            case .worldSafe:
                statusMessage = "Falha encerrada com World seguro"
                stats.lastEvent = "falha operacional • World confirmado"
                log("🛡️ Falha operacional contida • World confirmado antes de liberar a conexão")
                log("Falha: \(failure) • combate interrompido com saída segura")
                logSessionSummary(mode: mode, outcome: "FALHA • WORLD SEGURO")
                finishContinuedProcessing(success: false, reason: "falha contida após World confirmado")
            case .alreadyWorld:
                statusMessage = "Falha encerrada fora da Wilderness"
                stats.lastEvent = "falha operacional • já estava no World"
                log("🛡️ Falha operacional contida • estado autoritativo confirmou personagem fora da Wilderness")
                log("Falha: \(failure) • conexão liberada fora do Wild")
                logSessionSummary(mode: mode, outcome: "FALHA • FORA DO WILD")
                finishContinuedProcessing(success: false, reason: "falha contida fora da Wilderness")
            case .dead:
                statusMessage = "Servidor confirmou morte"
                stats.lastEvent = "morte autoritativamente confirmada"
                log("💀 Falha: \(failure) • servidor confirmou morte antes da saída")
                logSessionSummary(mode: mode, outcome: "MORTE CONFIRMADA")
                finishContinuedProcessing(success: false, reason: "morte confirmada")
            }
        } catch {
            diagnostic("[WILD][FAILSAFE] saída na Presence atual não confirmou: \(error.localizedDescription) • iniciando reconexão de emergência")
            requestWildConnectionRecovery(
                reason: "Falha operacional no Wild; reconectando exclusivamente para confirmar World",
                runID: runID
            )
            await socket.close()
            _ = await recoverWildAfterUnexpectedDisconnect(
                mode: mode,
                runID: runID,
                shard: shard,
                cookie: cookie
            )
        }
    }

    /// Dunes East has heat, hostile players and full-loot death. A terminal
    /// path may not release its Presence until the engine has crossed the
    /// supported north portal and stabilized two authoritative beach snapshots.
    private func containDunesTerminalFailure(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        engine: AutomationEngine,
        failure: String
    ) async {
        diagnostic("[DUNES][FAILSAFE] \(failure) • bloqueando encerramento dentro das Dunes")
        state = .recovering
        statusMessage = "Falha detectada • saindo para The Shores"
        stats.lastEvent = "failsafe Dunes • retorno a The Shores"
        updateContinuedProcessingProgress(forceTitleUpdate: true)

        do {
            _ = try await engine.runEmergencyDunesExit(
                reason: "falha operacional: \(failure)",
                expectedTool: dunesExpectedTool,
                expectedLifeEpoch: dunesExpectedLifeEpoch
            )
            await closeDunesPresenceAfterConfirmedShores()
            terminalFailureHandled = true
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = "Falha encerrada com The Shores segura"
            stats.sessionErrors += 1
            stats.lastEvent = "falha operacional • The Shores confirmada"
            log("🛡️ Falha operacional contida • The Shores confirmada antes de liberar a conexão")
            log("Falha: \(failure) • coleta interrompida com saída segura")
            logSessionSummary(mode: mode, outcome: "FALHA • THE SHORES SEGURA")
            finishContinuedProcessing(success: false, reason: "falha contida após The Shores confirmada")
        } catch {
            if let engineError = error as? EngineError,
               case .dunesDeathDuringExit(let detail) = engineError {
                await handleConfirmedDunesDeath(mode: mode, detail: detail)
                return
            }
            diagnostic("[DUNES][FAILSAFE] saída na Presence atual não confirmou: \(error.localizedDescription) • iniciando reconexão exclusiva para saída")
            requestGatherConnectionRecovery(
                reason: "Falha operacional nas Dunes; reconectando exclusivamente para confirmar The Shores",
                runID: runID
            )
            await socket.close()
            _ = await recoverGatherAfterUnexpectedDisconnect(
                mode: mode,
                runID: runID,
                shard: shard,
                cookie: cookie,
                runGoal: sessionGoal
            )
        }
    }

    /// Called only after the engine has proved The Shores with two fresh
    /// snapshots. Awaiting close here prevents the manual client racing a late
    /// bot Presence after completion/STOP.
    private func closeDunesPresenceAfterConfirmedShores() async {
        receiverTask?.cancel()
        receiverTask = nil
        await socket.close()
        await importSocketTrace()
        connected = false
        diagnostic("[DUNES] Presence encerrada somente após The Shores + sobrevivência autoritativamente confirmadas")
    }

    private func handleConfirmedDunesDeath(mode: ActivityMode, detail: String) async {
        guard !terminalFailureHandled else { return }
        terminalFailureHandled = true
        receiverTask?.cancel()
        receiverTask = nil
        engineRunTask?.cancel()
        engineRunTask = nil
        await socket.close()
        await importSocketTrace()
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Morte detectada durante saída das Dunes"
        stats.sessionErrors += 1
        stats.lastEvent = "morte/full-loot detectado durante saída"
        log("💀 Dunes • morte/full-loot detectado • The Shores recebida por respawn, não por fuga segura")
        log("💀 Evidência: \(detail)")
        logSessionSummary(mode: mode, outcome: "MORTE/FULL-LOOT CONFIRMADO")
        finishContinuedProcessing(success: false, reason: "morte detectada durante saída das Dunes")
    }

    private func runDunesCheckpointed(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        initialEngine: AutomationEngine,
        runGoal: Int
    ) async throws -> EngineRunResult {
        var phaseEngine = initialEngine
        var completedBeforePhase = stats.successes

        while completedBeforePhase < runGoal {
            guard activeRunID == runID, activity == mode, !terminalFailureHandled else {
                throw CancellationError()
            }
            let phaseGoal = DunesCheckpointPolicy.phaseGoal(totalGoal: runGoal, completed: completedBeforePhase)
            guard phaseGoal > 0 else {
                return EngineRunResult(successes: completedBeforePhase, completedGoal: true, stoppedSafely: false, stopReason: nil)
            }

            if completedBeforePhase > 0 {
                log("🏦 Dunes CHECKPOINT concluído • progresso protegido=\(completedBeforePhase)/\(runGoal) • iniciando próximo lote de até \(phaseGoal)")
            }

            let phaseStart = completedBeforePhase
            let engineForPhase = phaseEngine
            let child = Task.detached(priority: .userInitiated) {
                try await engineForPhase.run(
                    mode: mode,
                    goal: phaseGoal,
                    successOffset: phaseStart,
                    displayGoal: runGoal
                )
            }
            engineRunTask = child
            let phaseResult = try await child.value
            engineRunTask = nil
            await importSocketTrace()
            await Task.yield()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let total = max(stats.successes, phaseStart + phaseResult.successes)
            stats.successes = total

            let timedCheckpoint = phaseResult.stopReason == .dunesCheckpoint
            if phaseResult.stoppedSafely && !timedCheckpoint {
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: phaseResult.stopReason
                )
            }
            guard phaseResult.completedGoal || timedCheckpoint else {
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: false,
                    stopReason: phaseResult.stopReason
                )
            }
            if total >= runGoal {
                return EngineRunResult(successes: total, completedGoal: true, stoppedSafely: false, stopReason: nil)
            }

            // A engine acabou de sair por The Shores e já confirmou que não foi
            // respawn por morte. Só agora liberamos a Presence e protegemos loot.
            let checkpointTrigger = timedCheckpoint ? "180s de exposição" : "\(DunesCheckpointPolicy.successInterval) sucessos"
            log("🏦 Dunes CHECKPOINT \(total)/\(runGoal) • gatilho=\(checkpointTrigger) • The Shores + sobrevivência confirmadas • protegendo recursos no banco")
            await closeDunesPresenceAfterConfirmedShores()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            dunesPresencePhase = .preflightSafe
            // A ferramenta e o lifeEpoch acabaram de sobreviver ao checkpoint.
            // Preserve-os durante a fase segura do banco para cobrir a janela da
            // próxima abertura `desert`; a nova engine atualizará a exposição.
            state = .connecting
            statusMessage = "Checkpoint Dunes • protegendo recursos"
            stats.lastEvent = "checkpoint Dunes • banco"
            updateContinuedProcessingProgress(forceTitleUpdate: true)

            let bankBootstrap = DunesWorldPreflightPolicy.bankBootstrap
            let bankStream = try await socket.connect(session: session, shard: shard, bootstrap: bankBootstrap)
            await importSocketTrace()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let bankEngine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: shard,
                bootstrap: bankBootstrap,
                fishingBait: selectedFishingBait,
                reporter: engineReporter(runID: runID)
            )
            activeEngine = bankEngine
            receiverTask = makeReceiverTask(stream: bankStream, engine: bankEngine, mode: mode, runID: runID)
            connected = true
            await bankEngine.prepareIdentity()
            let loadout = try await bankEngine.prepareDunesLoadoutFromWorld(for: mode)
            dunesExpectedTool = loadout.toolIdentity
            dunesExpectedLifeEpoch = loadout.lifeEpoch
            player.lifeEpoch = max(player.lifeEpoch, loadout.lifeEpoch)
            let toolName = ActivityToolPolicy.displayName(loadout.tool)
            log("🏦 Dunes CHECKPOINT • recursos protegidos no banco • \(toolName) única mantida ✅")
            if loadout.healthPotionPlus > 0 {
                log("❤️‍🔥 Checkpoint • Health Potion+ carregadas: \(loadout.healthPotionPlus)")
            } else {
                log("⚠️ Checkpoint • sem Health Potion+ • próximo lote usa piso de \(DunesHeatSafetyPolicy.minimumSafeHP) HP")
            }

            receiverTask?.cancel()
            receiverTask = nil
            activeEngine = nil
            connected = false
            await socket.close()
            await importSocketTrace()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let activityBootstrap = AutomationEngine.bootstrap(for: mode)
            dunesPresencePhase = .fullLootOrEntering
            state = .connecting
            statusMessage = "Checkpoint concluído • reentrando nas Dunes"
            stats.lastEvent = "checkpoint protegido • nova Presence desert"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[DUNES][CHECKPOINT] banco concluído em \(total)/\(runGoal) • nova Presence full-loot no mesmo shard \(shard)")

            let activityStream = try await socket.connect(
                session: session,
                shard: shard,
                bootstrap: activityBootstrap
            )
            await importSocketTrace()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let activityEngine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: shard,
                bootstrap: activityBootstrap,
                fishingBait: selectedFishingBait,
                reporter: engineReporter(runID: runID)
            )
            phaseEngine = activityEngine
            activeEngine = activityEngine
            receiverTask = makeReceiverTask(
                stream: activityStream,
                engine: activityEngine,
                mode: mode,
                runID: runID
            )
            connected = true
            state = .syncing
            statusMessage = "Sincronizando novo lote das Dunes"
            await activityEngine.prepareIdentity()
            completedBeforePhase = total
        }

        return EngineRunResult(successes: completedBeforePhase, completedGoal: completedBeforePhase >= runGoal, stoppedSafely: false, stopReason: nil)
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
        if mode.isGathering {
            log("Gather • recoveries internos \(stats.gatherRecoveries) (FG \(stats.gatherRecoveriesForeground) / BG \(stats.gatherRecoveriesBackground)) • proof misses \(stats.gatherProofMisses)")
        }
        if mode == .chicken || mode.isWildCombat {
            let statePart = stats.stateConfirmedHits > 0 ? " • por estado \(stats.stateConfirmedHits)" : ""
            log("Combate • hits enviados \(stats.hits) • hits ACK \(stats.confirmedHits)\(statePart) • ACK timeout \(stats.hitAckTimeouts) (FG \(stats.hitAckTimeoutsForeground) / BG \(stats.hitAckTimeoutsBackground)) • kills \(stats.kills)")
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
            value.hasPrefix("[BANK]") ||
            value.hasPrefix("[GATHER][TIMING]") ||
            value.hasPrefix("[GATHER][TRACE]") ||
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
        dunesPresencePhase = mode.isDunesGathering ? .preflightSafe : .inactive
        dunesExpectedTool = nil
        dunesExpectedLifeEpoch = nil

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

        // Cada atividade nasce como uma execução independente: nenhuma queue,
        // Presence, receive loop ou linha de trace da meta anterior atravessa
        // esta barreira.
        await socket.resetForNewRun()
        guard activeRunID == runID else { return }

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

        defer {
            receiverTask?.cancel()
            traceTask?.cancel()
            connected = false
            let closingRunID = runID
            let socket = self.socket
            Task.detached(priority: .userInitiated) { [weak self] in
                // A engine já terminou neste ponto. Ceda uma vez para as tasks
                // auxiliares observarem o cancelamento antes de fechar a Presence.
                await Task.yield()
                await socket.close()
                // O fechamento pertence à execução que acabou; não deixe essas
                // linhas reaparecerem quando o logger da próxima meta iniciar.
                _ = await socket.drainTrace()
                await self?.completeRunCleanup(runID: closingRunID)
            }
        }

        do {
            var gatherPreflight: GatherToolPreflightDisposition = .ready
            if mode.isDunesGathering {
                guard let fallback = ActivityToolPolicy.requiredTool(for: mode) else {
                    throw EngineError.missingRequiredItem("ferramenta das Dunes")
                }
                state = .syncing
                statusMessage = "🛡️ Preparando banco para as Dunes"
                stats.lastEvent = "preflight Dunes • World/bank_shop"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                // Build 74: Dunes SEMPRE passam por World/bank_shop, mesmo se a
                // ferramenta já estiver carregada. Precisamos BANK-FIRST +
                // Health Potion+ antes de abrir a Presence full-loot.
                gatherPreflight = .needsWorld(tool: fallback)
                log("🛡️ Preflight Dunes • World/bank_shop obrigatório • ferramenta + Health Potion+ + BANK-FIRST antes da região full-loot")
            } else if mode.isGathering {
                gatherPreflight = await AutomationEngine.gatherToolPreflightDisposition(for: mode, cookie: cookie)
                switch gatherPreflight {
                case .ready:
                    diagnostic("[LOADOUT] \(mode.localizedTitle) • ferramenta já carregada antes da Presence")
                case .missing(let tool):
                    throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(tool))
                case .needsWorld(let tool):
                    let name = ActivityToolPolicy.displayName(tool)
                    state = .syncing
                    statusMessage = "🧰 Buscando \(name) no banco"
                    stats.lastEvent = "preflight World • \(name)"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    log("🧰 Preflight transacional • \(name) está no banco • Presence World/bank_shop será encerrada antes da região de coleta")
                }
            }

            // A decisão autoritativa de inventário acontece antes da conexão.
            // Se a ferramenta está no banco, a primeira Presence nasce em World,
            // executa o ciclo World→bank_shop→World e termina. A atividade começa
            // em uma segunda Presence nova, no mesmo shard, já bootstrapada na região
            // correta. Esse é o ciclo que funcionou nas builds estáveis e evita tentar
            // World→Eldergrove na Presence recém-usada pelo banco.
            let bootstrap: PresenceBootstrap
            if mode == .fishing {
                // Fishing always starts with a safe World Presence for the
                // transactional rod+bait bank preflight. A fresh activity
                // Presence is opened only after World/bank_shop/World completes.
                bootstrap = PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
            } else {
                bootstrap = AutomationEngine.bootstrapForRun(
                    for: mode,
                    gatherDisposition: gatherPreflight
                )
            }
            guard activeRunID == runID else { return }
            state = .connecting
            statusMessage = "Conectando à região da atividade"
            updateContinuedProcessingProgress()

            let connection = try await socket.connectBestNA(session: session, bootstrap: bootstrap)
            guard activeRunID == runID else { return }
            let stream = connection.stream
            let selectedShard = connection.shard
            activeShard = selectedShard
            await importSocketTrace()

            log("Servidor NA selecionado automaticamente: \(connection.serverName) (\(selectedShard)) • carga \(connection.populationLabel) • fila \(connection.queueLength)")

            var engine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: selectedShard,
                bootstrap: bootstrap,
                fishingBait: selectedFishingBait,
                reporter: engineReporter(runID: runID)
            )
            activeEngine = engine

            connected = true
            state = .syncing
            statusMessage = "Sincronizando personagem e mundo"
            log("Realtime conectado; engine ativa iniciada")

            // O receiver precisa estar ativo antes do preflight World porque a
            // confirmação de bank_shop/World e os snapshots chegam pela stream
            // da fase bancária. Se houver saque, essa stream termina antes da
            // Presence definitiva da atividade.
            receiverTask = makeReceiverTask(stream: stream, engine: engine, mode: mode, runID: runID)

            await engine.prepareIdentity()
            guard activeRunID == runID else { return }

            if mode == .fishing {
                state = .syncing
                statusMessage = "🎣 Preparando vara e isca no banco"
                stats.lastEvent = "preflight Pesca • World/bank_shop"
                updateContinuedProcessingProgress(forceTitleUpdate: true)

                try await engine.prepareFishingLoadoutFromWorld(goal: runGoal)
                guard activeRunID == runID, !terminalFailureHandled else { return }

                diagnostic("[FISH] preflight World concluído • encerrando Presence bancária antes da região de pesca")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityBootstrap = AutomationEngine.bootstrap(for: mode, fishingBait: selectedFishingBait)
                state = .connecting
                statusMessage = "Conectando à região de pesca"
                stats.lastEvent = "handoff Pesca • \(activityBootstrap.region)"
                updateContinuedProcessingProgress()

                let activityStream = try await socket.connect(
                    session: session,
                    shard: selectedShard,
                    bootstrap: activityBootstrap
                )
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityEngine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: selectedShard,
                    bootstrap: activityBootstrap,
                    fishingBait: selectedFishingBait,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = makeReceiverTask(
                    stream: activityStream,
                    engine: activityEngine,
                    mode: mode,
                    runID: runID
                )
                connected = true
                state = .syncing
                statusMessage = "Sincronizando região de pesca"
                log("🎣 Presence World encerrada • nova Presence \(activityBootstrap.region) aberta no mesmo shard \(selectedShard)")
                await activityEngine.prepareIdentity()
                guard activeRunID == runID else { return }
            }

            if GatherPresenceHandoffPolicy.requiresFreshActivityPresence(after: gatherPreflight),
               case .needsWorld(let tool) = gatherPreflight {
                var name = ActivityToolPolicy.displayName(tool)
                if mode.isDunesGathering {
                    let dunesLoadout = try await engine.prepareDunesLoadoutFromWorld(for: mode)
                    dunesExpectedTool = dunesLoadout.toolIdentity
                    dunesExpectedLifeEpoch = dunesLoadout.lifeEpoch
                    player.lifeEpoch = max(player.lifeEpoch, dunesLoadout.lifeEpoch)
                    name = ActivityToolPolicy.displayName(dunesLoadout.tool)
                    log("🛡️ Preflight Dunes • itens bancáveis protegidos • \(name) mantida ✅")
                    if dunesLoadout.healthPotionPlus > 0 {
                        log("❤️‍🔥 Proteção térmica • Health Potion+ carregadas: \(dunesLoadout.healthPotionPlus) • cura automática autoritativa habilitada")
                    } else {
                        log("⚠️ Proteção Dunes • sem Health Potion+ • coleta será interrompida em HP \(DunesHeatSafetyPolicy.minimumSafeHP) e sairá para The Shores")
                    }
                    log("⚠️ Dunes East é open-PvP/full-loot e sofre calor • Presence do banco será encerrada antes de entrar")
                } else {
                    let carried = try await engine.prepareGatherToolFromWorld(for: mode)
                    guard carried >= 1 else { throw EngineError.missingRequiredItem(name) }
                }

                guard activeRunID == runID, !terminalFailureHandled else { return }
                diagnostic("[LOADOUT] \(name) confirmado • encerrando Presence World após banco antes da região de coleta")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityBootstrap = AutomationEngine.bootstrap(for: mode)
                state = .connecting
                statusMessage = "Conectando à região da atividade"
                stats.lastEvent = "handoff de Presence • \(activityBootstrap.region)"
                updateContinuedProcessingProgress()

                if mode.isDunesGathering {
                    // From this point the server may create a desert Presence even
                    // if the client loses transport during the handshake. Recovery
                    // therefore becomes conservative and must prove The Shores.
                    dunesPresencePhase = .fullLootOrEntering
                    diagnostic("[DUNES] preflight seguro concluído • iniciando Presence full-loot em \(activityBootstrap.region)")
                }
                let activityStream = try await socket.connect(
                    session: session,
                    shard: selectedShard,
                    bootstrap: activityBootstrap
                )
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityEngine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: selectedShard,
                    bootstrap: activityBootstrap,
                    fishingBait: selectedFishingBait,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = makeReceiverTask(
                    stream: activityStream,
                    engine: activityEngine,
                    mode: mode,
                    runID: runID
                )
                connected = true
                state = .syncing
                statusMessage = "Sincronizando personagem e mundo"
                log("Realtime da atividade conectado em \(activityBootstrap.region); nova Presence ativa no \(selectedShard)")

                await activityEngine.prepareIdentity()
                guard activeRunID == runID else { return }
                diagnostic("[LOADOUT] \(name) confirmado • Presence World encerrada • nova Presence \(activityBootstrap.region) aberta no mesmo shard \(selectedShard)")
            }

            let runEngine = engine
            let result: EngineRunResult
            if mode.isDunesGathering {
                result = try await runDunesCheckpointed(
                    mode: mode,
                    runID: runID,
                    shard: selectedShard,
                    cookie: cookie,
                    initialEngine: runEngine,
                    runGoal: runGoal
                )
            } else {
                let child = Task.detached(priority: .userInitiated) {
                    try await runEngine.run(mode: mode, goal: runGoal)
                }
                engineRunTask = child
                result = try await child.value
                engineRunTask = nil
                await importSocketTrace()
            }
            guard activeRunID == runID else { return }
            // UI events are intentionally decoupled from the realtime actor.
            // Reconcile the authoritative engine total before rendering the
            // terminal state in case MainActor still has telemetry queued.
            stats.successes = max(stats.successes, result.successes)

            if let reason = realtimeFailureMessage {
                connected = false
                currentTarget = nil
                activity = nil
                state = .failed
                statusMessage = reason
            } else if result.stoppedSafely {
                if mode.isDunesGathering {
                    await closeDunesPresenceAfterConfirmedShores()
                }
                connected = false
                currentTarget = nil
                activity = nil
                state = .cancelled
                let stopReason = result.stopReason ?? requestedStopReason
                switch stopReason {
                case .backgroundExpiration:
                    statusMessage = "Continued Processing encerrada externamente"
                    stats.lastEvent = "encerramento externo com saída segura"
                    let destination = mode.isDunesGathering ? "The Shores" : "World"
                    log("Continued Processing encerrada/cancelada externamente — \(destination) confirmado e conexão liberada com segurança")
                    logSessionSummary(mode: mode, outcome: "ENCERRAMENTO EXTERNO SEGURO")
                    finishContinuedProcessing(success: false, reason: "encerramento externo após saída segura")
                case .connectionLoss:
                    let destination = mode.isDunesGathering ? "The Shores" : "World"
                    statusMessage = "Conexão recuperada • \(destination) seguro"
                    stats.lastEvent = "saída segura após perda de conexão"
                    log("Conexão recuperada — \(destination) seguro e nenhuma nova ação será enviada")
                    logSessionSummary(mode: mode, outcome: "RECONEXÃO SEGURA")
                    finishContinuedProcessing(success: false, reason: "conexão recuperada com saída segura")
                case .dunesCheckpoint:
                    statusMessage = "Checkpoint Dunes encerrou antes da retomada"
                    stats.lastEvent = "checkpoint adaptativo interrompido"
                    log("⚠️ Checkpoint adaptativo chegou ao encerramento da sessão sem retomar a coleta")
                    logSessionSummary(mode: mode, outcome: "CHECKPOINT INTERROMPIDO")
                    finishContinuedProcessing(success: false, reason: "checkpoint adaptativo interrompido")
                case .dunesHeatSafety:
                    statusMessage = "Proteção térmica • The Shores + sobrevivência confirmadas"
                    stats.lastEvent = "saída térmica sobrevivida"
                    log("Proteção térmica concluída — The Shores e sobrevivência confirmadas antes de liberar a conexão")
                    logSessionSummary(mode: mode, outcome: "PROTEÇÃO TÉRMICA")
                    finishContinuedProcessing(success: false, reason: "proteção térmica das Dunes")
                case .dunesDangerSafety:
                    statusMessage = "Dano externo detectado • The Shores + sobrevivência confirmadas"
                    stats.lastEvent = "saída por dano não-térmico sobrevivida"
                    log("🚨 Proteção Dunes concluída — dano não-térmico interrompeu a coleta e a sobrevivência foi confirmada")
                    logSessionSummary(mode: mode, outcome: "RISCO EXTERNO • SAÍDA SEGURA")
                    finishContinuedProcessing(success: false, reason: "dano não-térmico detectado nas Dunes")
                case .user, .none:
                    statusMessage = "Atividade encerrada com segurança"
                    stats.lastEvent = "atividade cancelada pelo usuário"
                    let destination = mode.isDunesGathering ? "The Shores" : "World"
                    log("STOP confirmado — \(destination) seguro e nenhuma nova ação será enviada")
                    logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                    finishContinuedProcessing(success: false, reason: "interrompida com saída segura")
                }
            } else if Task.isCancelled {
                state = .cancelled
                statusMessage = "Atividade cancelada"
                diagnostic("[STATE] atividade cancelada")
            } else if result.completedGoal {
                if mode.isDunesGathering {
                    await closeDunesPresenceAfterConfirmedShores()
                }
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
            if mode.isGathering,
               connectionRecoveryRequested,
               let shard = activeShard {
                _ = await recoverGatherAfterUnexpectedDisconnect(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie,
                    runGoal: runGoal
                )
                return
            }
            if mode.isWildCombat, let activeEngine, let shard = activeShard {
                await containWildTerminalFailure(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie,
                    engine: activeEngine,
                    failure: "Execução do combate cancelada inesperadamente"
                )
                return
            }
            if DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: mode, phase: dunesPresencePhase),
               let activeEngine, let shard = activeShard {
                await containDunesTerminalFailure(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie,
                    engine: activeEngine,
                    failure: "Execução da coleta cancelada inesperadamente"
                )
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
                let byUser = requestedStopReason == .user
                let externallyEnded = requestedStopReason == .backgroundExpiration
                statusMessage = externallyEnded ? "Continued Processing encerrada externamente" : "Atividade cancelada"
                if byUser {
                    diagnostic("[STATE] atividade cancelada pelo usuário")
                } else if externallyEnded {
                    diagnostic("[STATE] atividade cancelada após encerramento externo de Continued Processing")
                } else {
                    diagnostic("[STATE] atividade cancelada")
                }
                if continuedTaskObject != nil || continuedTaskRequested {
                    let reason = byUser ? "atividade cancelada pelo usuário" : (externallyEnded ? "Continued Processing encerrada externamente" : "atividade cancelada")
                    finishContinuedProcessing(success: false, reason: reason)
                }
            }
        } catch {
            await importSocketTrace()
            guard activeRunID == runID else { return }
            if let engineError = error as? EngineError,
               case .dunesDeathDuringExit(let detail) = engineError,
               mode.isDunesGathering {
                await handleConfirmedDunesDeath(mode: mode, detail: detail)
                return
            }
            if mode.isWildCombat, connectionRecoveryRequested, let shard = activeShard {
                _ = await recoverWildAfterUnexpectedDisconnect(mode: mode, runID: runID, shard: shard, cookie: cookie)
                return
            }

            if mode.isGathering, let shard = activeShard {
                let disconnectDetail = await socket.disconnectReason()
                let socketAlreadyClosed: Bool
                if let socketError = error as? SocketError, case .notConnected = socketError {
                    socketAlreadyClosed = true
                } else {
                    socketAlreadyClosed = false
                }

                // Pode haver uma pequena corrida entre o send que percebeu a
                // queda e o receive loop que solicita recovery. Um motivo real
                // registrado pelo socket ou `.notConnected` fecha essa janela.
                if connectionRecoveryRequested || disconnectDetail != nil || socketAlreadyClosed {
                    let detail = disconnectDetail ?? error.localizedDescription
                    if mode.isDunesGathering,
                       !DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: mode, phase: dunesPresencePhase) {
                        await failDunesPreflightTransport(
                            reason: "Conexão realtime perdida: \(detail)",
                            runID: runID
                        )
                        return
                    }
                    if !connectionRecoveryRequested {
                        requestGatherConnectionRecovery(
                            reason: "Conexão realtime perdida: \(detail)",
                            runID: runID
                        )
                    }
                    await socket.close()
                    _ = await recoverGatherAfterUnexpectedDisconnect(
                        mode: mode,
                        runID: runID,
                        shard: shard,
                        cookie: cookie,
                        runGoal: runGoal
                    )
                    return
                }
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

            // Wild safety firewall: an operational engine error (including a
            // real movement failure) is never allowed to fall through to the
            // generic defer and close a live Presence in Wilderness. Freeze all
            // combat, confirm authoritative state and leave through World. If
            // that cannot be completed on this socket, the existing emergency
            // reconnect becomes the only owner of teardown/recovery.
            if mode.isWildCombat, let activeEngine, let shard = activeShard {
                await containWildTerminalFailure(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie,
                    engine: activeEngine,
                    failure: error.localizedDescription
                )
                return
            }

            // Dunes safety firewall: no operational error may fall through to
            // generic teardown while the authoritative region can still be
            // desert. Exit to The Shores on the current Presence or reconnect
            // exclusively to finish that exit.
            if DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: mode, phase: dunesPresencePhase),
               let activeEngine, let shard = activeShard {
                await containDunesTerminalFailure(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie,
                    engine: activeEngine,
                    failure: error.localizedDescription
                )
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

        // Gathering acontece em região segura. Uma stream realmente encerrada
        // pausa a engine e transfere a conexão ao loop de retomada, preservando
        // meta, sucessos e a mesma Continued Processing.
        if mode.isGathering {
            if mode.isDunesGathering,
               !DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: mode, phase: dunesPresencePhase) {
                await failDunesPreflightTransport(reason: reason, runID: runID)
                return
            }
            requestGatherConnectionRecovery(reason: reason, runID: runID)
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

    /// A queda aconteceu enquanto a sessão ainda estava em World/bank_shop.
    /// Essa fase não é full-loot: encerre sem abrir `desert` e, principalmente,
    /// sem declarar The Shores como confirmada.
    private func failDunesPreflightTransport(reason: String, runID: UUID) async {
        guard activeRunID == runID,
              activity?.isDunesGathering == true,
              dunesPresencePhase == .preflightSafe,
              !terminalFailureHandled else { return }

        terminalFailureHandled = true
        realtimeFailureMessage = reason
        connected = false
        currentTarget = nil
        state = .failed
        statusMessage = "Conexão perdida durante preflight seguro"
        stats.sessionErrors += 1
        stats.lastEvent = "preflight Dunes interrompido fora do full-loot"
        diagnostic("[DUNES][PREFLIGHT] \(reason) • fase segura World/bank_shop • Presence desert NÃO iniciada • The Shores não será declarada")
        log("⚠️ Preflight Dunes interrompido por perda de conexão • personagem ainda fora da fase full-loot • nenhuma coleta será iniciada")
        logSessionSummary(mode: activity ?? .silver, outcome: "FALHA DE CONEXÃO • PREFLIGHT SEGURO")
        finishContinuedProcessing(success: false, reason: "conexão perdida durante preflight seguro das Dunes")

        engineRunTask?.cancel()
        task?.cancel()
        await socket.close()
    }

    /// Somente perdas reais do transporte chegam aqui. Recoveries de harvest,
    /// partial e proof miss pertencem exclusivamente à engine e nunca derrubam
    /// uma Presence saudável.
    private func requestGatherConnectionRecovery(reason: String, runID: UUID) {
        guard activeRunID == runID, activity?.isGathering == true, !terminalFailureHandled else { return }
        let dunesExitOnly = activity?.isDunesGathering == true &&
            DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: activity ?? .stone, phase: dunesPresencePhase)

        if !connectionRecoveryRequested {
            connectionRecoveryDetail = reason
            if dunesExitOnly {
                diagnostic("[WARN] \(reason) • Dunes: reconexão exclusiva para saída solicitada")
                log("⚠️ Conexão perdida nas Dunes • nenhuma coleta será retomada • reconectando apenas para sair em The Shores")
            } else {
                diagnostic("[WARN] \(reason) • Gathering: retomada no mesmo shard solicitada")
                log("⚠️ Conexão perdida durante a coleta • progresso preservado • reconectando para continuar a meta")
            }
        }
        connectionRecoveryRequested = true
        connected = false
        state = .recovering
        statusMessage = dunesExitOnly
            ? "Conexão perdida • recuperando saída das Dunes"
            : "Conexão perdida • retomando coleta"
        stats.lastEvent = dunesExitOnly ? "reconexão Dunes para saída" : "reconexão de Gathering"
        updateContinuedProcessingProgress(forceTitleUpdate: true)
        engineRunTask?.cancel()
        receiverTask?.cancel()
    }

    @discardableResult
    private func recoverGatherAfterUnexpectedDisconnect(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        runGoal: Int
    ) async -> Bool {
        guard activeRunID == runID, mode.isGathering else { return false }
        guard !connectionRecoveryInProgress else { return false }
        connectionRecoveryInProgress = true
        defer { connectionRecoveryInProgress = false }

        engineRunTask = nil
        receiverTask?.cancel()
        receiverTask = nil
        await socket.close()

        let started = Date()
        let recoveryDeadline: TimeInterval = mode.isDunesGathering ? 900 : 300
        var attempt = 0

        while Date().timeIntervalSince(started) < recoveryDeadline {
            guard activeRunID == runID,
                  activity == mode,
                  !terminalFailureHandled,
                  (requestedStopReason == nil || mode.isDunesGathering),
                  !Task.isCancelled
            else { return false }

            // Eventos de sucesso são entregues ao MainActor separadamente da
            // realtime actor. Ceder evita calcular a meta restante antes deles.
            await Task.yield()
            let remaining = max(0, runGoal - stats.successes)
            if remaining == 0, !mode.isDunesGathering {
                connectionRecoveryRequested = false
                connectionRecoveryDetail = nil
                connected = false
                currentTarget = nil
                state = .completed
                statusMessage = "Meta concluída"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                activity = nil
                log("✅ Meta concluída: \(stats.successes)/\(runGoal) • confirmada durante retomada da conexão")
                logSessionSummary(mode: mode, outcome: "META CONCLUÍDA")
                finishContinuedProcessing(success: true, reason: "meta concluída")
                return true
            }

            attempt += 1
            state = .recovering
            statusMessage = "Reconectando coleta • tentativa \(attempt)"
            stats.lastEvent = "reconexão de coleta \(attempt)"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[NET] Reconexão Gathering • \(shard) • \(mode.rawValue) • tentativa \(attempt) • restantes=\(remaining)")

            var phaseConnected = false
            do {
                let bootstrap: PresenceBootstrap
                if mode.isDunesGathering {
                    let recoveryRegion = player.region.lowercased().contains("desert") ? player.region : "desert"
                    bootstrap = PresenceBootstrap(
                        region: recoveryRegion,
                        position: player.position,
                        lifeEpoch: max(1, dunesExpectedLifeEpoch ?? player.lifeEpoch)
                    )
                } else {
                    bootstrap = AutomationEngine.bootstrap(for: mode)
                }
                let stream = try await socket.connect(session: session, shard: shard, bootstrap: bootstrap)
                phaseConnected = true
                await importSocketTrace()
                guard activeRunID == runID, activity == mode else { return false }

                let engine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: shard,
                    bootstrap: bootstrap,
                    fishingBait: selectedFishingBait,
                    reporter: engineReporter(runID: runID)
                )
                activeEngine = engine
                receiverTask = makeReceiverTask(
                    stream: stream,
                    engine: engine,
                    mode: mode,
                    runID: runID
                )
                await engine.prepareIdentity()

                // A Presence anterior caiu em região full-loot. Nesta sessão de
                // recovery é proibido voltar a minerar/cortar: a única operação
                // aceita é descobrir o estado autoritativo e confirmar Shores.
                if mode.isDunesGathering {
                    connected = true
                    state = .recovering
                    statusMessage = "Reconectado • saindo das Dunes"
                    stats.lastEvent = "saída de emergência das Dunes"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    log("🔁 Conexão restaurada no \(shard) • prioridade absoluta: confirmar The Shores")

                    _ = try await engine.runEmergencyDunesExit(
                        reason: "perda de conexão",
                        expectedTool: dunesExpectedTool,
                        expectedLifeEpoch: dunesExpectedLifeEpoch
                    )
                    await closeDunesPresenceAfterConfirmedShores()
                    terminalFailureHandled = true
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    currentTarget = nil
                    activity = nil

                    if stats.successes >= runGoal, requestedStopReason == nil {
                        state = .completed
                        statusMessage = "Meta concluída • The Shores segura"
                        stats.lastEvent = "meta concluída e Shores confirmada"
                        log("✅ Reconexão confirmou The Shores após a meta • sessão encerrada com segurança")
                        logSessionSummary(mode: mode, outcome: "META CONCLUÍDA • THE SHORES")
                        finishContinuedProcessing(success: true, reason: "meta concluída com The Shores confirmada")
                    } else {
                        let requested = requestedStopReason
                        state = requested == nil ? .failed : .cancelled
                        statusMessage = "The Shores segura • coleta encerrada"
                        stats.lastEvent = "The Shores confirmada após reconexão"
                        if requested == nil { stats.sessionErrors += 1 }
                        log("✅ Reconexão de emergência concluída • The Shores confirmada • nenhuma coleta foi retomada")
                        logSessionSummary(mode: mode, outcome: requested == nil ? "CONEXÃO PERDIDA • SHORES SEGURA" : "STOP • SHORES SEGURA")
                        finishContinuedProcessing(success: false, reason: "The Shores confirmada após reconexão")
                    }
                    return true
                }

                connected = true
                connectionRecoveryRequested = false
                connectionRecoveryDetail = nil
                state = .syncing
                statusMessage = "Conexão restaurada • retomando coleta"
                stats.lastEvent = "coleta reconectada"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                log("🔁 Conexão restaurada no \(shard) • retomando \(mode.localizedTitle) em \(stats.successes)/\(runGoal)")

                await Task.yield()
                let completedBeforePhase = stats.successes
                let phaseGoal = max(1, runGoal - completedBeforePhase)
                let child = Task.detached(priority: .userInitiated) {
                    try await engine.run(mode: mode, goal: phaseGoal)
                }
                engineRunTask = child
                let result = try await child.value
                engineRunTask = nil
                await importSocketTrace()
                await Task.yield()

                guard activeRunID == runID, activity == mode else { return false }
                stats.successes = max(stats.successes, completedBeforePhase + result.successes)

                if result.completedGoal || stats.successes >= runGoal {
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    connected = false
                    currentTarget = nil
                    state = .completed
                    statusMessage = "Meta concluída"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    activity = nil
                    log("✅ Meta concluída: \(stats.successes)/\(runGoal) • atividade retomada e encerrada automaticamente")
                    logSessionSummary(mode: mode, outcome: "META CONCLUÍDA")
                    finishContinuedProcessing(success: true, reason: "meta concluída após reconexão")
                    return true
                }

                throw EngineError.gatherEndedBeforeGoal
            } catch is CancellationError {
                await importSocketTrace()
                if connectionRecoveryRequested, activeRunID == runID, activity == mode {
                    receiverTask?.cancel()
                    receiverTask = nil
                    connected = false
                    await socket.close()
                    continue
                }
                return false
            } catch {
                await importSocketTrace()
                receiverTask?.cancel()
                receiverTask = nil
                connected = false

                if let engineError = error as? EngineError,
                   case .dunesDeathDuringExit(let detail) = engineError,
                   mode.isDunesGathering {
                    await handleConfirmedDunesDeath(mode: mode, detail: detail)
                    return false
                }

                let disconnectDetail = await socket.disconnectReason()
                let isClosedSocket: Bool
                if let socketError = error as? SocketError, case .notConnected = socketError {
                    isClosedSocket = true
                } else {
                    isClosedSocket = false
                }
                let transportFailure = !phaseConnected || connectionRecoveryRequested || disconnectDetail != nil || isClosedSocket

                if !transportFailure, !mode.isDunesGathering {
                    terminalFailureHandled = true
                    realtimeFailureMessage = error.localizedDescription
                    currentTarget = nil
                    activity = nil
                    state = .failed
                    statusMessage = error.localizedDescription
                    stats.sessionErrors += 1
                    diagnostic("[ERROR] Retomada Gathering encontrou falha estrutural: \(error.localizedDescription)")
                    log("Falha: \(error.localizedDescription) • coleta interrompida após reconexão")
                    logSessionSummary(mode: mode, outcome: "FALHA")
                    finishContinuedProcessing(success: false, reason: "falha estrutural após reconexão")
                    return false
                }

                // Em Dunes até uma falha estrutural da tentativa de saída deve
                // conservar o firewall: feche esta Presence e tente novamente,
                // sem jamais cair no teardown genérico ainda dentro do deserto.
                connectionRecoveryRequested = true
                if connectionRecoveryDetail == nil {
                    connectionRecoveryDetail = disconnectDetail ?? error.localizedDescription
                }
                await socket.close()
                let elapsed = Int(Date().timeIntervalSince(started))
                diagnostic("[WARN] Reconexão Gathering tentativa \(attempt) falhou após \(elapsed)s: \(error.localizedDescription)")
                let wait = min(6.0, 1.0 + Double(attempt) * 0.5)
                try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
            }
        }

        terminalFailureHandled = true
        realtimeFailureMessage = connectionRecoveryDetail ?? "Conexão realtime perdida durante a coleta"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Não foi possível retomar a conexão da coleta"
        stats.sessionErrors += 1
        if mode.isDunesGathering {
            statusMessage = "Não foi possível confirmar The Shores"
            log("🛑 Reconexão de segurança expirou após 15 minutos • The Shores não pôde ser confirmada")
            logSessionSummary(mode: mode, outcome: "FALHA DE SAÍDA DAS DUNES")
            finishContinuedProcessing(success: false, reason: "saída das Dunes não confirmada")
        } else {
            log("🛑 Reconexão da coleta expirou após 5 minutos • progresso preservado em \(stats.successes)/\(runGoal)")
            logSessionSummary(mode: mode, outcome: "FALHA DE RECONEXÃO")
            finishContinuedProcessing(success: false, reason: "reconexão da coleta expirou")
        }
        return false
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
                    reporter: engineReporter(runID: runID)
                )
                activeEngine = recoveryEngine
                await recoveryEngine.prepareIdentity()

                receiverTask?.cancel()
                receiverTask = makeReceiverTask(
                    stream: stream,
                    engine: recoveryEngine,
                    mode: mode,
                    runID: runID,
                    notifyUnexpectedEnd: false
                )

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

        case .gatherSuccess(let detail, let absolute):
            // Build 78 checkpoint phases use independent engines. Absolute gather
            // progress makes delayed MainActor delivery idempotent: a success from
            // the previous 10-node phase can never increment the global total twice.
            stats.successes = max(stats.successes, absolute)
            continuedProgressSubunit = 0
            stats.lastEvent = detail ?? "sucesso de coleta"
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

            if currentMode.isGathering {
                requestGatherConnectionRecovery(reason: reason, runID: runID)
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
            stats.lastEvent = "hit confirmado por ACK"
            advanceContinuedProcessingSubprogress()
            updateContinuedProcessingProgress()

        case .stateConfirmedHit:
            stats.stateConfirmedHits += 1
            stats.lastEvent = "hit correlacionado por estado"
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

        case .gatherRecovery(let proofMiss):
            stats.gatherRecoveries += 1
            if proofMiss { stats.gatherProofMisses += 1 }
            if lastScenePhaseKey == "background" {
                stats.gatherRecoveriesBackground += 1
            } else {
                stats.gatherRecoveriesForeground += 1
            }
            stats.lastEvent = proofMiss ? "gather proof miss/recovery" : "gather recovery"

        case .kill:
            stats.kills += 1
            stats.lastEvent = "kill confirmado"

        case .player(let position, let hp, let shield, let region):
            player.position = position
            player.hp = hp
            player.shield = shield
            player.region = region
            world.region = region

        case .dunesExposure(let tool, let lifeEpoch):
            dunesExpectedTool = tool
            dunesExpectedLifeEpoch = lifeEpoch
            player.lifeEpoch = max(player.lifeEpoch, lifeEpoch)
            stats.lastEvent = "Dunes • exposição registrada"
            diagnostic("[DUNES][EXPOSURE] ferramenta física registrada • type=\(tool.type) • iid=\(tool.iid == nil ? "não" : "sim") • lifeEpoch=\(lifeEpoch)")

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
            if backgroundEnteredAt == nil { backgroundEnteredAt = .now }
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
            if let enteredAt = backgroundEnteredAt {
                accumulatedBackgroundSeconds += max(0, Date.now.timeIntervalSince(enteredAt))
                backgroundEnteredAt = nil
            }
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
        backgroundEnteredAt = UIApplication.shared.applicationState == .background ? .now : nil
        accumulatedBackgroundSeconds = 0

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
        if activity?.requiresSafeExit == true, connectionRecoveryRequested {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            state = .recovering
            statusMessage = "Continued Processing encerrada • aguardando rede para saída segura"
            stats.lastEvent = activity?.isDunesGathering == true
                ? "encerramento externo durante reconexão Dunes"
                : "encerramento externo durante reconexão Wild"
            diagnostic("[BG] Encerramento externo recebido durante queda de conexão em região de risco • preservando reconexão de emergência enquanto houver runtime")
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            return
        }

        // Wild combat usa encerramento cooperativo enquanto o callback ainda tem
        // runtime: parar novos hits -> safe camp -> combat timer 0 -> World.
        if activity?.requiresSafeExit == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            let reason = requestedStopReason ?? .backgroundExpiration
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: reason)
            }
            state = .recovering
            statusMessage = activity?.isDunesGathering == true
                ? "Continued Processing encerrada • saída para The Shores"
                : "Continued Processing encerrada • saída imediata para o World"
            stats.lastEvent = "saída de emergência por encerramento externo"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[BG] Encerramento externo recebido em região de risco • saída segura cooperativa solicitada")
            return
        }

        // O mesmo callback é usado pelo sistema para expiração real e para um
        // encerramento solicitado pela superfície de Continued Processing.
        // A API não informa qual dos dois ocorreu; trate-o como cancelamento
        // externo neutro, preservando exatamente o cleanup seguro existente.
        requestedStopReason = .backgroundExpiration
        terminalFailureHandled = true
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
        // ocupado (sessão fantasma / start ignorado). O `defer` da Task pai
        // fecha a Presence somente depois que esta engine cancelar de fato.
        engineRunTask?.cancel()
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        realtimeFailureMessage = nil
        connected = false
        currentTarget = nil
        activity = nil
        state = .cancelled
        statusMessage = "Continued Processing encerrada externamente"
        stats.lastEvent = "encerramento externo"
        diagnostic("[BG] Continued Processing encerrada/cancelada externamente • \(continuedProcessingTerminationContext())")
        diagnostic("[BG] Atividade não-Wild interrompida • fechamento imediato da Presence solicitado")
        log("Continued Processing encerrada/cancelada pelo sistema ou pelo controle da Dynamic Island • atividade interrompida com segurança")
        endLegacyBackgroundTask()
        closeTerminalNonWildPresenceNow(reason: "encerramento externo")
    }

    private func closeTerminalNonWildPresenceNow(reason: String) {
        diagnostic("[NET] Encerramento terminal não-Wild • motivo=\(reason) • cancelando Presence sem aguardar a ação pendente")
        let socket = self.socket
        Task.detached(priority: .userInitiated) {
            await socket.close()
            // O cancelamento da engine e o fechamento do socket podem se cruzar
            // por alguns milissegundos. Essas linhas pertencem ao teardown já
            // confirmado, não a uma nova falha estrutural da atividade.
            _ = await socket.drainTrace()
        }
    }

    private func continuedProcessingTerminationContext(now: Date = .now) -> String {
        let totalSeconds = max(0, now.timeIntervalSince(stats.startedAt ?? now))
        let currentBackground = backgroundEnteredAt.map { max(0, now.timeIntervalSince($0)) } ?? 0
        let backgroundSeconds = accumulatedBackgroundSeconds + currentBackground
        let thermal: String
        switch ProcessInfo.processInfo.thermalState {
        case .nominal: thermal = "nominal"
        case .fair: thermal = "fair"
        case .serious: thermal = "serious"
        case .critical: thermal = "critical"
        @unknown default: thermal = "unknown"
        }
        return "runtime=\(Int(totalSeconds))s • BG acumulado=\(Int(backgroundSeconds))s • progresso=\(stats.successes)/\(max(1, sessionGoal)) • Low Power=\(ProcessInfo.processInfo.isLowPowerModeEnabled ? "on" : "off") • thermal=\(thermal)"
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

        if activity?.requiresSafeExit == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            let reason = requestedStopReason ?? .backgroundExpiration
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: reason)
            }
            state = .recovering
            statusMessage = activity?.isDunesGathering == true
                ? "Background expirando • saída para The Shores"
                : "Background expirando • saída imediata para o World"
            stats.lastEvent = "saída de emergência por background"
            let region = activity?.isDunesGathering == true ? "Dunes" : "Wild"
            diagnostic("[BG] Runtime curto esgotou em \(region) • emergency-exit solicitado")
            return
        }

        requestedStopReason = .backgroundExpiration
        terminalFailureHandled = true
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
        closeTerminalNonWildPresenceNow(reason: "janela curta de background encerrada")
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
