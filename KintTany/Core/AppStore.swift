import Foundation
import SwiftUI

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
    private let socket = RealtimeSocket()

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
        task = nil
        receiverTask = nil
        connected = false
        Task { await socket.close() }
        currentTarget = nil
        activity = nil
        state = .cancelled
        statusMessage = "Atividade interrompida"
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
        diagnosticLogs.append(timestamped(value))
        if diagnosticLogs.count > 2_000 {
            diagnosticLogs.removeFirst(diagnosticLogs.count - 2_000)
        }
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
            return
        }

        activity = mode
        state = .connecting
        stats = ActivityStats(startedAt: .now)
        connected = false
        currentTarget = nil
        resourceCount = 0
        mobCount = 0
        statusMessage = "Conectando ao Kintara"
        log("Iniciando \(mode.localizedTitle)")
        diagnostic("[UI] activity=\(mode.rawValue) state=connecting goal=\(goal)")

        let bootstrap = AutomationEngine.bootstrap(for: mode)

        defer {
            receiverTask?.cancel()
            receiverTask = nil
            connected = false
            Task { await socket.close() }
        }

        do {
            let stream = try await socket.connect(session: session, shard: "s4", bootstrap: bootstrap)
            await importSocketTrace()

            let engine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: "s4",
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
            }

            let result = try await engine.run(mode: mode, goal: goal)
            await importSocketTrace()

            if Task.isCancelled {
                state = .cancelled
                statusMessage = "Atividade cancelada"
                diagnostic("[STATE] atividade cancelada")
            } else if result.completedGoal {
                state = .completed
                statusMessage = "Meta concluída"
                log("Meta concluída: \(result.successes)/\(goal)")
            } else {
                state = .failed
                statusMessage = "Engine encerrou antes da meta"
                stats.failures += 1
                log("Atividade encerrou antes da meta")
            }
        } catch is CancellationError {
            await importSocketTrace()
            state = .cancelled
            statusMessage = "Atividade cancelada"
            diagnostic("[STATE] CancellationError")
        } catch {
            await importSocketTrace()
            connected = false
            state = .failed
            statusMessage = error.localizedDescription
            stats.failures += 1
            diagnostic("[ERROR] \(String(reflecting: error))")
            log("Falha: \(error.localizedDescription)")
        }
    }

    private func handleEngineEvent(_ event: EngineEvent) {
        switch event {
        case .state(let newState, let message):
            state = newState
            statusMessage = message
            stats.lastEvent = newState.rawValue

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

        case .failure(let reason):
            stats.failures += 1
            stats.lastEvent = reason
            diagnostic("[ENGINE] falha: \(reason)")

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
        if diagnosticLogs.count > 2_000 {
            diagnosticLogs.removeFirst(diagnosticLogs.count - 2_000)
        }
    }
}

final class SessionManager {
    private let key = "kinttany.session.cookie"
    var cookie: String? { KeychainStore.get(key) }
    func save(cookie: String) { KeychainStore.set(key, cookie) }
    func clear() { KeychainStore.delete(key) }
}
