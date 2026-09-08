import Foundation
import SwiftUI

enum ActivityMode: String, CaseIterable, Codable, Identifiable {
    case tree, coal, stone, fishing, chicken, zombie, dragon
    var id: String { rawValue }
    var title: String {
        switch self { case .tree: "Tree"; case .coal: "Coal"; case .stone: "Stone"; case .fishing: "Fishing"; case .chicken: "Chicken"; case .zombie: "Zombie"; case .dragon: "Dragon" }
    }
    var icon: String {
        switch self { case .tree: "tree.fill"; case .coal: "circle.fill"; case .stone: "mountain.2.fill"; case .fishing: "fish.fill"; case .chicken: "bird.fill"; case .zombie: "figure.walk"; case .dragon: "flame.fill" }
    }
}

enum ActivityState: String, Codable { case idle, connecting, syncing, searching, selectingTarget, moving, preparingAction, acting, waitingProof, waitingResult, cooldown, recovering, completed, cancelled, failed }

struct Position: Codable, Equatable { var x: Double; var y: Double = 0.25; var z: Double; var ry: Double = 0 }
struct ResourceNode: Codable, Identifiable, Equatable { var id: String; var kind: String; var keys: [String]; var available: Bool; var hasCoal: Bool = false; var proof: String? }
struct Mob: Codable, Identifiable, Equatable { var id: String; var index: Int; var type: String; var level: Int?; var position: Position; var hp: Int?; var alive: Bool }
struct PlayerState: Codable { var id: String?; var position = Position(x: 22.5, z: -3.5); var hp = 100; var shield = 0; var lifeEpoch = 1; var region = "world"; var resources: [String:Int] = [:] }
struct WorldState: Codable { var nodes: [ResourceNode] = []; var mobs: [Mob] = []; var region = "world"; var serverRegion: String? }
struct ActivityStats: Codable { var attempts = 0; var successes = 0; var failures = 0; var hits = 0; var confirmedHits = 0; var kills = 0; var startedAt: Date?; var lastEvent = "" }

@MainActor final class AppStore: ObservableObject {
    @Published var activity: ActivityMode?
    @Published var state: ActivityState = .idle
    @Published var player = PlayerState()
    @Published var world = WorldState()
    @Published var stats = ActivityStats()
    @Published var goal = 100
    @Published var logs: [String] = []
    @Published var diagnosticLogs: [String] = []
    @Published var connected = false

    private let session = SessionManager()
    private var task: Task<Void, Never>?
    private let socket = RealtimeSocket()

    func start(_ mode: ActivityMode) {
        task?.cancel()
        connected = false
        task = Task { [weak self] in
            await self?.run(mode)
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        connected = false
        Task { await socket.close() }
        activity = nil
        state = .cancelled
        log("STOP confirmado — nenhuma nova ação será enviada")
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
        log("Sessão autenticada e salva no Keychain; realtime será conectado ao iniciar uma atividade")
    }

    private func run(_ mode: ActivityMode) async {
        activity = mode
        state = .connecting
        stats = ActivityStats(startedAt: .now)
        connected = false
        log("Iniciando \(mode.title)")
        diagnostic("[UI] activity=\(mode.rawValue) state=connecting goal=\(goal)")

        defer {
            connected = false
            Task { await socket.close() }
        }

        do {
            let stream = try await socket.connect(session: session, shard: "s4")
            await importSocketTrace()

            connected = true
            state = .syncing
            log("Realtime conectado; aguardando snapshots autoritativos")
            diagnostic("[STATE] connected=true state=syncing")

            state = .searching
            diagnostic("[STATE] state=searching")

            for await data in stream {
                if Task.isCancelled { break }
                await importSocketTrace()
                handle(data: data, mode: mode)
                if stats.successes >= goal { break }
            }

            await importSocketTrace()

            if Task.isCancelled {
                state = .cancelled
                diagnostic("[STATE] atividade cancelada")
            } else if stats.successes >= goal {
                state = .completed
                log("Meta concluída")
            } else {
                state = .failed
                stats.failures += 1
                log("Conexão realtime encerrou antes da meta")
            }
        } catch is CancellationError {
            await importSocketTrace()
            state = .cancelled
            diagnostic("[STATE] CancellationError")
        } catch {
            await importSocketTrace()
            connected = false
            state = .failed
            stats.failures += 1
            diagnostic("[ERROR] \(String(reflecting: error))")
            log("Falha de sessão: \(error.localizedDescription)")
        }
    }

    private func importSocketTrace() async {
        let lines = await socket.drainTrace()
        for line in lines {
            diagnostic(line)
        }
    }

    private func handle(data: Data, mode: ActivityMode) {
        guard let event = RealtimeProtocol.decode(data) else {
            diagnostic("[PROTO] Payload recebido, mas RealtimeProtocol.decode não reconheceu JSON/tipo")
            return
        }

        switch event {
        case .queueReady:
            log("queue_ready confirmado")
        case .regionAck(let region):
            player.region = region
            log("region_ack: \(region)")
        case .snapshot(let packet):
            if let region = packet["region"] as? String { world.serverRegion = region }
            stats.lastEvent = "snap"
            log("snapshot recebido")
        case .resourceEvent:
            stats.lastEvent = "res_evt"
            state = .waitingResult
            diagnostic("[STATE] event=res_evt state=waitingResult")
        case .actionProof:
            stats.lastEvent = "action_proof"
            state = .waitingProof
            diagnostic("[STATE] event=action_proof state=waitingProof")
        case .harvestHit:
            stats.lastEvent = "harv_hit"
            stats.successes += 1
            state = .cooldown
            log("harv_hit confirmado • sucessos=\(stats.successes)")
        case .mobEvent(let packet):
            stats.lastEvent = packet["t"] as? String ?? "mob_event"
            if packet["a"] as? String == "hit" { stats.confirmedHits += 1 }
            state = .waitingResult
            diagnostic("[STATE] mob_event state=waitingResult confirmedHits=\(stats.confirmedHits)")
        case .queuePosition(let position):
            diagnostic("[PROTO] queue_pos=\(position)")
        case .unknown(let name):
            diagnostic("[PROTO] evento não utilizado: \(name)")
        }
        _ = mode
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
