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
    @Published var connected = false
    private let session = SessionManager()
    private var task: Task<Void, Never>?
    private let socket = RealtimeSocket()

    func start(_ mode: ActivityMode) {
        task?.cancel(); task = Task { [weak self] in await self?.run(mode) }
    }
    func stop() { task?.cancel(); task = nil; Task { await socket.close() }; activity = nil; state = .cancelled; log("STOP confirmado — nenhuma nova ação será enviada") }
    func log(_ value: String) { logs.append("\(Date.now.formatted(date: .omitted, time: .standard))  \(value)"); if logs.count > 300 { logs.removeFirst(logs.count - 300) } }
    func saveCookie(_ cookie: String) { session.save(cookie: cookie); log("Sessão salva com segurança no Keychain") }

    private func run(_ mode: ActivityMode) async {
        activity = mode; state = .connecting; stats = ActivityStats(startedAt: .now); log("Iniciando \(mode.title)")
        do {
            try await socket.connect(session: session, shard: "s4")
            connected = true; state = .syncing; log("WebSocket pronto; aguardando snapshots autoritativos")
            state = .searching
            let stream = await socket.stream()
            for await data in stream {
                if Task.isCancelled { break }
                handle(data: data, mode: mode)
                if stats.successes >= goal { break }
            }
            if !Task.isCancelled { state = .completed; log("Meta concluída") }
        } catch is CancellationError { state = .cancelled }
        catch { state = .failed; log("Falha de sessão: \(error.localizedDescription)") }
    }

    private func handle(data: Data, mode: ActivityMode) {
        guard let event = RealtimeProtocol.decode(data) else { return }
        switch event {
        case .queueReady: log("queue_ready confirmado")
        case .regionAck(let region): player.region = region; log("region_ack: \(region)")
        case .snapshot(let packet):
            if let region = packet["region"] as? String { world.serverRegion = region }
            stats.lastEvent = "snap"; log("snapshot recebido")
        case .resourceEvent: stats.lastEvent = "res_evt"; state = .waitingResult
        case .actionProof: stats.lastEvent = "action_proof"; state = .waitingProof
        case .harvestHit: stats.lastEvent = "harv_hit"; stats.successes += 1; state = .cooldown
        case .mobEvent(let packet):
            stats.lastEvent = packet["t"] as? String ?? "mob_event"
            if packet["a"] as? String == "hit" { stats.confirmedHits += 1 }
            state = .waitingResult
        case .queuePosition: break
        case .unknown(let name): log("evento não utilizado: \(name)")
        }
        _ = mode
    }
}

final class SessionManager {
    private let key = "kinttany.session.cookie"
    var cookie: String? { KeychainStore.get(key) }
    func save(cookie: String) { KeychainStore.set(key, cookie) }
    func clear() { KeychainStore.delete(key) }
}
