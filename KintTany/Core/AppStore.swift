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
    private let socket = RealtimeSocket()

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
    private var continuedTaskRegistered = false
    private var continuedTaskRequested = false
    private var continuedTaskMode: ActivityMode?
    private var legacyBackgroundTask: UIBackgroundTaskIdentifier = .invalid

    private var continuedTaskIdentifier: String {
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
        if activity != nil {
            stop(silent: true)
        }

        // A solicitação precisa nascer do toque do usuário, antes de o app ser
        // colocado em segundo plano. No iOS 26 isso cria uma Continued Processing
        // Task real; em versões anteriores usamos somente a janela curta do UIKit.
        prepareContinuedProcessing(for: mode)

        task = Task { [weak self] in
            guard let self else { return }
            await self.run(mode)
        }
    }

    func stop() {
        stop(silent: false)
    }

    private func stop(silent: Bool) {
        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        task = nil
        receiverTask = nil
        traceTask = nil
        realtimeFailureMessage = nil
        connected = false
        Task { await socket.close() }
        currentTarget = nil
        activity = nil
        state = .cancelled
        statusMessage = "Atividade interrompida"
        finishContinuedProcessing(success: false, reason: "interrompida")
        endLegacyBackgroundTask()
        if !silent {
            log("STOP confirmado — nenhuma nova ação será enviada")
        }
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

    private func run(_ mode: ActivityMode) async {
        guard let cookie = session.cookie, !cookie.isEmpty else {
            activity = nil
            state = .failed
            statusMessage = "Faça login antes de iniciar"
            log("Sessão ausente. Abra Sessão e faça login.")
            finishContinuedProcessing(success: false, reason: "sessão ausente")
            return
        }

        goal = min(100_000, max(1, goal))
        let runGoal = goal
        realtimeFailureMessage = nil

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
        updateContinuedProcessingProgress()

        // O socket mantém um pequeno buffer interno. Antes, esse buffer só era
        // importado quando connect() terminava, então todos os eventos de conexão
        // pareciam acontecer dezenas de segundos depois do toque. Enquanto a
        // conexão está sendo negociada, drenamos o trace em tempo real.
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
            receiverTask = nil
            traceTask?.cancel()
            traceTask = nil
            connected = false
            Task { await socket.close() }
        }

        do {
            let connection = try await socket.connectBestNA(session: session, bootstrap: bootstrap)
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
                    self?.handleEngineEvent(event)
                }
            )

            connected = true
            state = .syncing
            statusMessage = "Sincronizando personagem e mundo"
            log("Realtime conectado; engine ativa iniciada")

            await engine.prepareIdentity()

            receiverTask = Task { [weak self] in
                guard let self else { return }
                for await data in stream {
                    if Task.isCancelled { break }
                    engine.ingest(data)
                    await self.importSocketTrace()
                }

                // AsyncStream termina quando o receive loop da Presence encerra.
                // Antes isso era silencioso: a engine continuava aparecendo ativa
                // até alguma ação seguinte tentar enviar no socket já morto.
                if !Task.isCancelled {
                    await self.handleUnexpectedRealtimeEnd(for: mode)
                }
            }

            let result = try await engine.run(mode: mode, goal: runGoal)
            await importSocketTrace()

            if let reason = realtimeFailureMessage {
                connected = false
                currentTarget = nil
                activity = nil
                state = .failed
                statusMessage = reason
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
                finishContinuedProcessing(success: true, reason: "meta concluída")
            } else {
                state = .failed
                statusMessage = "Engine encerrou antes da meta"
                stats.failures += 1
                currentTarget = nil
                activity = nil
                log("Atividade encerrou antes da meta • bot interrompido automaticamente")
                finishContinuedProcessing(success: false, reason: "engine encerrou antes da meta")
            }
        } catch is CancellationError {
            await importSocketTrace()
            if let reason = realtimeFailureMessage {
                connected = false
                currentTarget = nil
                activity = nil
                state = .failed
                statusMessage = reason
                diagnostic("[STATE] engine cancelada após perda da conexão realtime")
                finishContinuedProcessing(success: false, reason: "conexão realtime perdida")
            } else {
                state = .cancelled
                statusMessage = "Atividade cancelada"
                diagnostic("[STATE] CancellationError")
                finishContinuedProcessing(success: false, reason: "atividade cancelada")
            }
        } catch {
            await importSocketTrace()
            connected = false
            currentTarget = nil
            activity = nil
            state = .failed
            statusMessage = error.localizedDescription
            stats.failures += 1
            diagnostic("[ERROR] \(error.localizedDescription)")
            log("Falha: \(error.localizedDescription) • bot interrompido automaticamente")
            finishContinuedProcessing(success: false, reason: "falha da atividade")
        }
    }

    private func handleUnexpectedRealtimeEnd(for mode: ActivityMode) async {
        guard activity == mode, connected else { return }

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

    private func handleEngineEvent(_ event: EngineEvent) {
        switch event {
        case .state(let newState, let message):
            state = newState
            statusMessage = message
            stats.lastEvent = newState.rawValue
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

        case .success(let detail):
            stats.successes += 1
            stats.lastEvent = detail ?? "sucesso"
            if let detail { log("✅ \(detail) • \(stats.successes)/\(goal)") }
            updateContinuedProcessingProgress()

        case .failure(let reason):
            stats.failures += 1
            stats.lastEvent = reason
            log("⚠️ Falha: \(reason)")
            updateContinuedProcessingProgress()

        case .fatal(let reason):
            guard activity != nil else { return }
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
        switch phase {
        case .background:
            guard activity != nil else { return }
            if continuedTaskObject != nil {
                diagnostic("[BG] App em segundo plano • Continued Processing ativa • realtime preservado")
            } else if continuedTaskRequested {
                diagnostic("[BG] App em segundo plano • aguardando Continued Processing • ativando ponte curta")
                beginLegacyBackgroundTaskIfNeeded()
            } else {
                diagnostic("[BG] App em segundo plano • Continued Processing indisponível • ativando janela curta")
                beginLegacyBackgroundTaskIfNeeded()
            }

        case .active:
            if activity != nil {
                diagnostic("[BG] App em primeiro plano • engine continua na mesma sessão")
            }
            endLegacyBackgroundTask()

        case .inactive:
            break

        @unknown default:
            break
        }
    }

    private func prepareContinuedProcessing(for mode: ActivityMode) {
        continuedTaskMode = mode
        continuedTaskRequested = false

        guard #available(iOS 26.0, *) else {
            diagnostic("[BG] iOS anterior ao 26 • usando somente extensão curta de background")
            return
        }

        let identifier = continuedTaskIdentifier
        if !continuedTaskRegistered {
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
                    self.attachContinuedProcessingTask(continued)
                }
            }

            continuedTaskRegistered = registered
            if !registered {
                diagnostic("[WARN] BGContinuedProcessingTask não pôde ser registrada • fallback curto será usado")
                return
            }
        }

        let requestedGoal = min(100_000, max(1, goal))
        let request = BGContinuedProcessingTaskRequest(
            identifier: identifier,
            title: "Kintarabot • \(mode.localizedTitle)",
            subtitle: "Meta \(requestedGoal) • preparando"
        )

        // O bot só é útil se iniciar agora, em resposta direta ao toque. Se o
        // sistema não puder fornecer a tarefa contínua imediatamente, preferimos
        // saber disso e cair para a extensão curta em vez de deixar um job antigo
        // enfileirado para começar depois.
        request.strategy = .fail

        do {
            // Marque antes de submit para não perder um launch handler que seja
            // entregue imediatamente pelo scheduler.
            continuedTaskRequested = true
            try BGTaskScheduler.shared.submit(request)
            diagnostic("[BG] Continued Processing solicitada • \(mode.localizedTitle) • meta \(requestedGoal)")
        } catch {
            continuedTaskRequested = false
            diagnostic("[WARN] Continued Processing não iniciou: \(error.localizedDescription) • fallback curto disponível")
        }
    }

    @available(iOS 26.0, *)
    private func attachContinuedProcessingTask(_ backgroundTask: BGContinuedProcessingTask) {
        guard continuedTaskRequested else {
            backgroundTask.setTaskCompleted(success: false)
            return
        }

        continuedTaskObject = backgroundTask
        continuedTaskRequested = false

        backgroundTask.expirationHandler = { [weak self, weak backgroundTask] in
            guard let backgroundTask else { return }
            Task { @MainActor [weak self] in
                self?.handleContinuedProcessingExpiration(backgroundTask)
            }
        }

        updateContinuedProcessingProgress()
        diagnostic("[BG] Continued Processing ATIVA • pode trocar de aplicativo sem pausar o bot")
        endLegacyBackgroundTask()
    }

    private func updateContinuedProcessingProgress() {
        guard #available(iOS 26.0, *),
              let backgroundTask = continuedTaskObject as? BGContinuedProcessingTask
        else { return }

        let total = Int64(max(1, goal))
        let completed = Int64(min(max(0, stats.successes), max(1, goal)))
        backgroundTask.progress.totalUnitCount = total
        backgroundTask.progress.completedUnitCount = completed

        let modeName = (activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade"
        let shortStatus = statusMessage.count > 42 ? String(statusMessage.prefix(42)) + "…" : statusMessage
        backgroundTask.updateTitle(
            "Kintarabot • \(modeName)",
            subtitle: "\(completed)/\(total) • \(shortStatus)"
        )
    }

    private func finishContinuedProcessing(success: Bool, reason: String) {
        let hadPendingRequest = continuedTaskRequested
        continuedTaskRequested = false

        if #available(iOS 26.0, *) {
            if let backgroundTask = continuedTaskObject as? BGContinuedProcessingTask {
                let total = Int64(max(1, goal))
                backgroundTask.progress.totalUnitCount = total
                if success {
                    backgroundTask.progress.completedUnitCount = total
                } else {
                    backgroundTask.progress.completedUnitCount = Int64(min(max(0, stats.successes), max(1, goal)))
                }
                backgroundTask.expirationHandler = nil
                backgroundTask.updateTitle(
                    "Kintarabot • \((activity ?? continuedTaskMode)?.localizedTitle ?? "Atividade")",
                    subtitle: success ? "Meta concluída" : "Encerrada • \(reason)"
                )
                backgroundTask.setTaskCompleted(success: success)
                diagnostic("[BG] Continued Processing encerrada • sucesso=\(success ? "sim" : "não") • \(reason)")
            } else if hadPendingRequest {
                BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: continuedTaskIdentifier)
                diagnostic("[BG] Solicitação Continued Processing pendente cancelada • \(reason)")
            }
        }

        continuedTaskObject = nil
        continuedTaskMode = nil
        endLegacyBackgroundTask()
    }

    @available(iOS 26.0, *)
    private func handleContinuedProcessingExpiration(_ backgroundTask: BGContinuedProcessingTask) {
        guard continuedTaskObject === backgroundTask else {
            backgroundTask.setTaskCompleted(success: false)
            return
        }

        // Pode acontecer por pressão de recursos ou porque o usuário cancelou a
        // Live Activity do sistema. Erro/expiração deve parar o bot, conforme a
        // regra já adotada no v2.0.
        continuedTaskObject = nil
        continuedTaskRequested = false
        continuedTaskMode = nil
        backgroundTask.expirationHandler = nil
        backgroundTask.setTaskCompleted(success: false)

        task?.cancel()
        receiverTask?.cancel()
        traceTask?.cancel()
        task = nil
        receiverTask = nil
        traceTask = nil
        realtimeFailureMessage = "Execução em segundo plano encerrada pelo iOS"
        connected = false
        currentTarget = nil
        activity = nil
        state = .failed
        statusMessage = "Segundo plano encerrado pelo iOS"
        stats.failures += 1
        stats.lastEvent = "background expirado"
        diagnostic("[ERROR] BGContinuedProcessingTask expirou/cancelou • bot interrompido automaticamente")
        log("Falha: execução em segundo plano encerrada pelo iOS • bot interrompido automaticamente")
        Task { await socket.close() }
        endLegacyBackgroundTask()
    }

    private func beginLegacyBackgroundTaskIfNeeded() {
        guard activity != nil, legacyBackgroundTask == .invalid else { return }

        let app = UIApplication.shared
        legacyBackgroundTask = app.beginBackgroundTask(withName: "KintarabotRealtime") { [weak self] in
            guard let self else { return }
            self.diagnostic("[WARN] Janela curta de background esgotada • o iOS poderá suspender o processo")
            self.endLegacyBackgroundTask()
        }

        if legacyBackgroundTask != .invalid {
            diagnostic("[BG] Extensão curta UIKit ativa • ponte para preservar realtime")
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
