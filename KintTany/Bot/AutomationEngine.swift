import Foundation

enum EngineEvent {
    case state(ActivityState, String)
    case log(String)
    case diagnostic(String)
    case target(String?)
    case attempt
    case success(String?)
    case failure(String)
    case fatal(String)
    case hitSent
    case confirmedHit
    case stateConfirmedHit
    case hitAckTimeout
    case gatherRecovery(proofMiss: Bool)
    case potionAckTimeout
    case kill
    case player(Position, hp: Int, shield: Int, region: String)
    case world(nodes: Int, mobs: Int, serverRegion: String?)
}

enum EngineStopReason: Equatable {
    case user
    case backgroundExpiration
    case connectionLoss
}

enum EmergencyWildExitResult: Equatable {
    case worldSafe
    case alreadyWorld
    case dead
}

struct FishingNumberingPolicy {
    static func publicFishNumber(successes: Int) -> Int {
        max(1, successes + 1)
    }
}

enum GatherToolPreflightDisposition: Equatable {
    case ready
    case needsWorld(tool: String)
    case missing(tool: String)
}

struct GatherToolPreflightPolicy {
    static func disposition(tool: String, carried: Int, bank: Int) -> GatherToolPreflightDisposition {
        if carried > 0 { return .ready }
        if bank > 0 { return .needsWorld(tool: tool) }
        return .missing(tool: tool)
    }
}

struct GatherTimingPolicy {
    /// Preserve the captured browser profile with relative spacing. If iOS
    /// wakes a frame late in background, the next delay starts from that real
    /// wake-up: no frame is abandoned and no backlog is sent as a burst.
    static let treeProfileWindowMS = 500
    static let minimumTreeFrameGapMS = 35
    static let mineFrameGapMS = 65
    static let delayedFrameDiagnosticThresholdMS = 220
    static let timingDiagnosticCooldownMS: Double = 5_000
    static let eventGraceMS = 420

    static func treeFrameGapMS(frameCount: Int) -> Int {
        let intervals = max(1, frameCount - 1)
        let browserGap = (treeProfileWindowMS + intervals - 1) / intervals
        return max(minimumTreeFrameGapMS, min(90, browserGap))
    }
}

/// Movement is emitted as the same 150 ms / 3.5 units-per-second frame stream
/// captured from the working Node client. A suspended iOS task must not consume
/// the movement budget while no frame can run: only frames actually emitted
/// advance the budget. This also prevents catch-up bursts after a background
/// wake because every frame still waits for its normal relative delay.
struct MovementProgressPolicy {
    static let frameSeconds = 0.15
    static let speed = 3.5

    static func frameBudget(maxSeconds: Double, frameSeconds: Double = frameSeconds) -> Int {
        max(1, Int(ceil(max(0, maxSeconds) / max(0.001, frameSeconds))))
    }

    static func exhausted(sentFrames: Int, maxSeconds: Double, frameSeconds: Double = frameSeconds) -> Bool {
        sentFrames >= frameBudget(maxSeconds: maxSeconds, frameSeconds: frameSeconds)
    }
}

struct CombatStateConfirmationPolicy {
    static func isStateCorrelatedHit(beforeHP: Int?, afterHP: Int?, snapshotAdvanced: Bool) -> Bool {
        guard snapshotAdvanced, let beforeHP, let afterHP else { return false }
        return afterHP < beforeHP
    }
}

private actor RealtimeEventGate {
    private struct Waiter {
        let afterSerial: Int
        let continuation: CheckedContinuation<Bool, Never>
    }

    private(set) var serial = 0
    private var waiters: [UUID: Waiter] = [:]

    func signal() {
        serial += 1
        let current = serial
        let ready = waiters.filter { $0.value.afterSerial < current }
        for (id, waiter) in ready {
            waiters.removeValue(forKey: id)
            waiter.continuation.resume(returning: true)
        }
    }

    func wait(after afterSerial: Int, timeoutMS: Int) async throws -> Bool {
        try Task.checkCancellation()
        if serial > afterSerial { return true }
        let id = UUID()
        let result = await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if self.serial > afterSerial {
                    continuation.resume(returning: true)
                    return
                }
                self.waiters[id] = Waiter(afterSerial: afterSerial, continuation: continuation)
                Task { [weak self] in
                    do {
                        try await Task.sleep(nanoseconds: UInt64(max(1, timeoutMS)) * 1_000_000)
                    } catch {
                        // Cancellation is handled by the outer cancellation handler.
                    }
                    await self?.resolve(id: id, value: false)
                }
            }
        }, onCancel: {
            Task { [weak self] in
                await self?.resolve(id: id, value: false)
            }
        })
        try Task.checkCancellation()
        return result
    }

    private func resolve(id: UUID, value: Bool) {
        guard let waiter = waiters.removeValue(forKey: id) else { return }
        waiter.continuation.resume(returning: value)
    }
}

struct ActivityToolPolicy {
    static func requiredTool(for mode: ActivityMode) -> String? {
        switch mode {
        case .tree: return "tool_axe"
        case .coal, .stone, .iron: return "tool_pickaxe"
        case .fishing: return "tool_fishing_rod"
        case .chicken, .zombie, .dragon: return nil
        }
    }

    static func displayName(_ type: String) -> String {
        switch type {
        case "tool_axe": return "Axe"
        case "tool_pickaxe": return "Pickaxe"
        case "tool_fishing_rod": return "Fishing Rod"
        default: return type
        }
    }
}

struct GatherResourcePolicy {
    static func matches(mode: ActivityMode, kind: String, hasCoal: Bool, hasMetal: Bool) -> Bool {
        switch mode {
        case .tree: return kind == "tree"
        case .coal: return kind == "rock" && hasCoal && !hasMetal
        case .stone: return kind == "rock" && !hasCoal && !hasMetal
        case .iron: return kind == "rock" && !hasCoal && hasMetal
        default: return false
        }
    }
}

struct GatherRegionPolicy {
    static func region(for mode: ActivityMode) -> String {
        mode == .iron ? "frostmere" : "eldergrove"
    }

    static func startPosition(for mode: ActivityMode) -> Position {
        switch mode {
        case .tree: return Position(x: -6.5, z: -18.5)
        case .iron: return Position(x: 5.5, z: -18.5)
        default: return Position(x: 22.5, z: -3.5)
        }
    }

    static func isGatherRegion(_ region: String) -> Bool {
        let normalized = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "eldergrove" || normalized == "frostmere"
    }

    static func gridOffset(for region: String) -> Double {
        region.lowercased() == "frostmere" ? 19.5 : 24.5
    }

    static func hasCoal(region: String, packetValue: Bool?) -> Bool? {
        region.lowercased() == "frostmere" ? (packetValue ?? false) : packetValue
    }

    static func hasMetal(region: String, packetValue: Bool?) -> Bool? {
        switch region.lowercased() {
        case "frostmere": return packetValue ?? true
        case "eldergrove": return packetValue ?? false
        default: return packetValue
        }
    }
}

struct CombatBankFirstPolicy {
    // RC3.2: o BANK-FIRST não é mais limitado à allowlist histórica de seis
    // recursos. Todo item core materializado em invSlots pode ser protegido,
    // exceto o que precisa permanecer carregado para o combate e categorias
    // conhecidamente especiais/soulbound. Arrays especiais nunca são tocados.
    static let maxStackCount = 10_000
    static let combatRequiredTypes: Set<String> = [
        "wild_sword", "potion_health", "potion_shield", "potion_strength"
    ]
    static let protectedPrefixes = ["mount_", "pet_", "cosmetic_", "furniture_"]
    static let protectedFragments = ["scroll", "soulbound"]

    static func shouldBankFirst(type: String, slot: [String: Any]) -> Bool {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalized.isEmpty else { return false }
        if combatRequiredTypes.contains(normalized) { return false }
        if protectedPrefixes.contains(where: { normalized.hasPrefix($0) }) { return false }
        if protectedFragments.contains(where: { normalized.contains($0) }) { return false }
        if RealtimeProtocol.bool(slot["soulbound"]) == true || RealtimeProtocol.bool(slot["bound"]) == true { return false }
        return true
    }

    static func slotQuantity(_ slot: [String: Any]) -> Int {
        max(1, RealtimeProtocol.int(slot["n"]) ?? 1)
    }

    // Só fazemos merge/split automático para stacks simples {t,n}. Itens com
    // durabilidade/id/metadados são movidos como o objeto inteiro para um slot
    // vazio, preservando seus campos.
    static func isSimpleStack(_ slot: [String: Any]) -> Bool {
        guard RealtimeProtocol.int(slot["n"]) != nil else { return false }
        return Set(slot.keys).isSubset(of: Set(["t", "n"]))
    }
}

struct BankSlotAllocator {
    static func place(slot source: [String: Any], quantity requested: Int, into bank: inout [Any]) -> Int {
        guard let type = source["t"] as? String, !type.isEmpty else { return 0 }
        let sourceQuantity = CombatBankFirstPolicy.slotQuantity(source)
        let wanted = min(max(0, requested), sourceQuantity)
        guard wanted > 0 else { return 0 }

        if !CombatBankFirstPolicy.isSimpleStack(source) {
            // Itens com metadados/durabilidade são indivisíveis aqui. Mova o
            // objeto completo, sem reconstruí-lo, somente para um slot vazio.
            guard wanted >= sourceQuantity, let empty = firstEmptyIndex(in: bank) else { return 0 }
            bank[empty] = source
            return sourceQuantity
        }

        var left = wanted
        while left > 0 {
            if let index = firstCompatiblePartialStack(type: type, in: bank) {
                var target = bank[index] as? [String: Any] ?? ["t": type, "n": 0]
                let current = max(0, RealtimeProtocol.int(target["n"]) ?? 0)
                let capacity = max(0, CombatBankFirstPolicy.maxStackCount - current)
                if capacity > 0 {
                    let moved = min(left, capacity)
                    target["n"] = current + moved
                    bank[index] = target
                    left -= moved
                    continue
                }
            }

            guard let empty = firstEmptyIndex(in: bank) else { break }
            let moved = min(left, CombatBankFirstPolicy.maxStackCount)
            bank[empty] = ["t": type, "n": moved]
            left -= moved
        }
        return wanted - left
    }

    private static func firstCompatiblePartialStack(type: String, in bank: [Any]) -> Int? {
        bank.indices.first { index in
            guard let slot = bank[index] as? [String: Any],
                  slot["t"] as? String == type,
                  CombatBankFirstPolicy.isSimpleStack(slot)
            else { return false }
            let count = max(0, RealtimeProtocol.int(slot["n"]) ?? 0)
            return count < CombatBankFirstPolicy.maxStackCount
        }
    }

    private static func firstEmptyIndex(in bank: [Any]) -> Int? {
        bank.indices.first { index in
            let raw = bank[index]
            return raw is NSNull || !(raw is [String: Any])
        }
    }
}

struct InventoryLoadoutAllocator {
    static func carriedCount(type: String, hotbar: [Any], inventory: [Any]) -> Int {
        func count(_ slots: [Any]) -> Int {
            slots.reduce(0) { partial, raw in
                guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
                return partial + CombatBankFirstPolicy.slotQuantity(slot)
            }
        }
        return count(hotbar) + count(inventory)
    }

    /// Move apenas do bankSlots para hotbar/invSlots usando estruturas já
    /// documentadas pelo save-backpack. Retorna a quantidade realmente retirada.
    /// Itens com metadata são indivisíveis; stacks simples podem ser parciais.
    static func withdraw(
        type: String,
        quantity targetRaw: Int,
        preferHotbar: Bool,
        hotbar: inout [Any],
        inventory: inout [Any],
        bank: inout [Any]
    ) -> Int {
        let target = max(1, targetRaw)
        let before = carriedCount(type: type, hotbar: hotbar, inventory: inventory)
        guard before < target else { return 0 }
        var need = target - before
        var movedTotal = 0

        func placeSimple(quantity: Int, in slots: inout [Any]) -> Int {
            var left = max(0, quantity)
            guard left > 0 else { return 0 }
            for index in slots.indices where left > 0 {
                guard var slot = slots[index] as? [String: Any],
                      slot["t"] as? String == type,
                      CombatBankFirstPolicy.isSimpleStack(slot)
                else { continue }
                let current = max(0, RealtimeProtocol.int(slot["n"]) ?? 0)
                let capacity = max(0, CombatBankFirstPolicy.maxStackCount - current)
                guard capacity > 0 else { continue }
                let moved = min(left, capacity)
                slot["n"] = current + moved
                slots[index] = slot
                left -= moved
            }
            while left > 0 {
                guard let empty = slots.firstIndex(where: { $0 is NSNull || !($0 is [String: Any]) }) else { break }
                let moved = min(left, CombatBankFirstPolicy.maxStackCount)
                slots[empty] = ["t": type, "n": moved]
                left -= moved
            }
            return quantity - left
        }

        func placeMetadata(_ source: [String: Any], in slots: inout [Any]) -> Bool {
            guard let empty = slots.firstIndex(where: { $0 is NSNull || !($0 is [String: Any]) }) else { return false }
            slots[empty] = source
            return true
        }

        for index in bank.indices where need > 0 {
            guard var slot = bank[index] as? [String: Any], slot["t"] as? String == type else { continue }
            let available = CombatBankFirstPolicy.slotQuantity(slot)
            guard available > 0 else { continue }

            if CombatBankFirstPolicy.isSimpleStack(slot) {
                let take = min(need, available)
                var placed = 0
                if preferHotbar { placed += placeSimple(quantity: take - placed, in: &hotbar) }
                if placed < take { placed += placeSimple(quantity: take - placed, in: &inventory) }
                if !preferHotbar, placed < take { placed += placeSimple(quantity: take - placed, in: &hotbar) }
                guard placed > 0 else { break }
                let left = available - placed
                if left > 0 {
                    slot["n"] = left
                    bank[index] = slot
                } else {
                    bank[index] = NSNull()
                }
                need -= placed
                movedTotal += placed
            } else {
                var placed = false
                if preferHotbar { placed = placeMetadata(slot, in: &hotbar) }
                if !placed { placed = placeMetadata(slot, in: &inventory) }
                if !preferHotbar && !placed { placed = placeMetadata(slot, in: &hotbar) }
                guard placed else { break }
                bank[index] = NSNull()
                let amount = available
                need = max(0, need - amount)
                movedTotal += amount
            }
        }

        return movedTotal
    }
}

struct WorldExitPolicy {
    /// Paridade com combat-bot.js v5.2: três ciclos antes de classificar a
    /// região como incerta e partir para verificação autoritativa por reconnect.
    static let probeCycles = 3
}

struct CombatAckCadence {
    static let circuitBreakerThreshold = 4
    static let baseWildMS: Double = 1_650
    static let maxWildMS: Double = 2_100
    static let missIncrementMS: Double = 125
    static let recoveryDecrementMS: Double = 50

    private(set) var cooldownMS: Double = baseWildMS
    private(set) var ackStreak = 0

    mutating func record(acknowledged: Bool) {
        if acknowledged {
            ackStreak += 1
            if ackStreak >= 3 {
                cooldownMS = max(Self.baseWildMS, cooldownMS - Self.recoveryDecrementMS)
            }
        } else {
            ackStreak = 0
            cooldownMS = min(Self.maxWildMS, cooldownMS + Self.missIncrementMS)
        }
    }
}

struct WildCombatSafetyPolicy {
    let emergencyEffectiveHP: Int
    let finisherEffectiveHP: Int
    let postKillSafeHP: Int
    let postKillSafeShield: Int
    let postKillDamageQuietMS: Double
    let quickPostEffective: Int

    /// A real Dragon burst was observed roughly four seconds after a kill.
    /// The old 1.1 s fast path and 3 s quiet-only gate could therefore release
    /// the combat loop before the authoritative damage arrived. Dragon always
    /// remains in the no-new-contact observation phase for at least six seconds.
    static let dragonMinimumPostKillObservationMS: Double = 6_000
    static let dragonRequiredDamageQuietMS: Double = 3_000

    static func policy(for mode: ActivityMode) -> WildCombatSafetyPolicy {
        if mode == .dragon {
            return WildCombatSafetyPolicy(
                emergencyEffectiveHP: 160,
                finisherEffectiveHP: 175,
                postKillSafeHP: 95,
                postKillSafeShield: 90,
                postKillDamageQuietMS: 1_400,
                quickPostEffective: 185
            )
        }
        return WildCombatSafetyPolicy(
            emergencyEffectiveHP: 95,
            finisherEffectiveHP: 135,
            postKillSafeHP: 90,
            postKillSafeShield: 65,
            postKillDamageQuietMS: 850,
            quickPostEffective: 145
        )
    }
}

struct EngineRunResult {
    let successes: Int
    let completedGoal: Bool
    let stoppedSafely: Bool
    let stopReason: EngineStopReason?
}

/// Paridade operacional com a `persistenceChain` do bot Node v5.2: gravações
/// HTTP de loot continuam serializadas, mas nunca bloqueiam movimento, proof ou
/// o próximo harvest da Presence.
struct GatherPersistencePolicy {
    static let hotPathPreviewMS = 75
    static let finalDrainMS = 5_000
}

struct GatherPersistenceReceipt: Sendable {
    let item: String
    let total: Int?
    let errorDescription: String?
}

actor GatherLootPersistenceQueue {
    private let http: KintaraHTTPClient
    private var tail: Task<GatherPersistenceReceipt, Never>?
    private var pending = 0

    init(cookie: String) {
        http = KintaraHTTPClient(cookie: cookie)
    }

    func enqueue(item: String, amount: Int) -> Task<GatherPersistenceReceipt, Never> {
        let previous = tail
        let client = http
        pending += 1

        let job = Task {
            if let previous { _ = await previous.value }
            do {
                let total = try await client.persistLoot(item, amount: amount)
                return GatherPersistenceReceipt(item: item, total: total, errorDescription: nil)
            } catch {
                return GatherPersistenceReceipt(item: item, total: nil, errorDescription: error.localizedDescription)
            }
        }
        tail = job

        Task { [weak self] in
            _ = await job.value
            await self?.markFinished()
        }
        return job
    }

    private func markFinished() {
        pending = max(0, pending - 1)
    }

    /// A v5.2 aguardava no máximo 75 ms apenas para enriquecer o texto do log.
    /// O job é não estruturado e continua na fila quando o preview expira.
    func preview(
        _ job: Task<GatherPersistenceReceipt, Never>,
        timeoutMS: Int = GatherPersistencePolicy.hotPathPreviewMS
    ) async -> GatherPersistenceReceipt? {
        enum Preview {
            case completed(GatherPersistenceReceipt)
            case queued
        }

        let stream = AsyncStream<Preview> { continuation in
            Task {
                continuation.yield(.completed(await job.value))
                continuation.finish()
            }
            Task {
                try? await Task.sleep(nanoseconds: UInt64(max(0, timeoutMS)) * 1_000_000)
                continuation.yield(.queued)
                continuation.finish()
            }
        }

        for await value in stream {
            switch value {
            case .completed(let receipt): return receipt
            case .queued: return nil
            }
        }
        return nil
    }

    func drain(timeoutMS: Int = GatherPersistencePolicy.finalDrainMS) async -> Bool {
        guard let current = tail, pending > 0 else { return true }

        let stream = AsyncStream<Bool> { continuation in
            Task {
                _ = await current.value
                continuation.yield(true)
                continuation.finish()
            }
            Task {
                try? await Task.sleep(nanoseconds: UInt64(max(0, timeoutMS)) * 1_000_000)
                continuation.yield(false)
                continuation.finish()
            }
        }
        for await drained in stream { return drained }
        return false
    }

    func pendingCount() -> Int { pending }
}

/// The protocol engine owns one serial actor, independent from SwiftUI's main
/// actor. Socket ingestion, ACK gates, movement and action profiles therefore
/// continue to make progress while iOS deprioritizes UI work in background.
actor AutomationEngine {
    typealias Reporter = (EngineEvent) -> Void

    private let socket: RealtimeSocket
    private let cookie: String
    private let shard: String
    private let reporter: Reporter
    private let http: KintaraHTTPClient
    private let fishingBait: FishingBait
    private let gatherPersistenceQueue: GatherLootPersistenceQueue

    private var region: String
    private var serverRegion: String?
    private var lastRegionConfirmationSource: String?
    private var position: Position
    private var lifeEpoch = 1
    private var equipment: String?
    private var playerID: Int?
    private var playerHP = 100
    private var playerShield = 0

    /// Region of the latest authoritative snapshot that actually contained the
    /// `res` collection. A World snapshot must not unlock ElderGrove selection
    /// after a single-Presence World→ElderGrove preflight.
    private var resourceSnapshotRegion: String?
    private var cooldownUntil: [String: Double] = [:]
    private var gatherRetryPolicy = GatherRetryPolicy()
    private var gatherBusyUntil: [String: Double] = [:]
    private let gatherKnowledge: GatherKnowledgeStore
    private var gatherPositionMemory: [String: Position] = [:]
    private var gatherInternalRecoveries = 0
    private var gatherProofMisses = 0
    private var gatherLastTimingDiagnosticAt: Double = 0
    private var gatherResourceSerial = 0
    private let gatherEventGate = RealtimeEventGate()
    private let wildStateEventGate = RealtimeEventGate()

    private var currentGatherSignature: String?
    private var currentGatherKind: String?
    private var currentGatherKeys = Set<String>()
    private var harvestProof = ""
    private var harvestProofSerial = 0
    private var harvestWearSerial = 0
    private var harvestH = 0
    private var harvestHM = 99
    private var harvestLoot: String?
    private var harvestClearSeen = false

    private var fishSpots: [Int: FishSpot] = [:]
    private var fishSnapshotSerial = 0
    private var fishBiteSerial = 0
    private var lastFishBite: FishBite?
    private var activeFishingAction: [String: Any]?
    private var lastFishSpotSignature = ""
    private var fishingStats = FishingSessionStats()
    private var lastFishingInventory = FishingInventorySnapshot()
    /// RC3.4: saúde de alvo da pesca. Uma célula que repete no_bite/rotação
    /// não pode ser martelada indefinidamente. Após o limite ela é bloqueada
    /// pela geração atual; quando todas as células elegíveis de uma geração
    /// ficam ruins, a geração inteira aguarda um movimento REAL do servidor.
    private var fishCellFailureStreak: [String: Int] = [:]
    private var fishBlockedCells = Set<String>()
    private var fishQuarantinedGenerations = Set<String>()
    private var fishHealthWaitSerial = -1

    private var chickenCollectionPath: String?
    private var chickens: [Int: LiveMob] = [:]
    private var chickenSnapshotSerial = 0
    private var ambientHitSerial = 0
    private var lastAmbientHitIndex: Int?

    private var wildMobs: [Int: LiveMob] = [:]
    private var wildSnapshotSerial = 0
    private var wildHitSerial = 0
    private var lastWildHit: WildHitAck?
    private var wildSwordSeq = 0
    private var wildContactSeq = 0
    private var wildGrantSerial = 0
    private var recentWildGrants: [WildGrant] = []
    private var lastWildAvailabilitySignature = ""

    // MARK: Wilderness potions / defensive recovery (ported from Node v5.2.1)
    // HP/Shield remain server-authoritative. Potion ticks only PROPOSE php/wsh in
    // position frames; pvit/snap is what changes playerHP/playerShield.
    private var drinkSeq = 0
    private var lastDrinkAck: PotionDrinkAck?
    private var shieldPotionSeq = 0
    private var strengthBuffUntil: Double = 0
    private var lastPotionAt: Double = 0
    private var potionStock = PotionStock()
    private var potionPersistentCounts: [String: Int] = [:]
    private var potionStockLoaded = false
    private var persistentPotionTransport = false
    private var shieldConfirmFailureStreak = 0
    private var shieldMechanicUnavailable = false
    private var potionAckTimeoutStreak: [String: Int] = [:]

    // MARK: Wilderness combat safety / XP / resupply
    // O timer de combate do jogo é de 10 s. Não há campo autoritativo exposto
    // pela v5.2 para o countdown, então usamos a última confirmação de combate
    // (hit aceito ou dano recebido) como relógio conservador. Qualquer novo dano
    // reinicia a janela antes de sair do Wild/encerrar a Presence.
    private var lastCombatActivityAt: Double = 0
    private var lastCombatDamageAt: Double = 0
    private var emergencyVitalDrop = false
    private let combatLogoutWindowMS: Double = 10_000

    // skill_xp é autoritativo pelo Presence; player-stats é fallback/linha de base.
    private var combatXPTotal: Int?
    private var combatXPStart: Int?
    private var combatXPSerial = 0

    // Paridade com combat-bot v5.2.1: quando UMA categoria chega a zero,
    // a viagem de reposição completa as três para 6/6/6.
    private let targetHealthPotions = 6
    private let targetShieldPotions = 6
    private let targetStrengthPotions = 6

    private var successes = 0
    private var safeStopReason: EngineStopReason?
    private var safeStopCompleted = false

    private var emergencyBackgroundExitRequested: Bool {
        safeStopReason == .backgroundExpiration
    }

    init(
        socket: RealtimeSocket,
        cookie: String,
        shard: String,
        bootstrap: PresenceBootstrap,
        fishingBait: FishingBait = .feather,
        gatherPersistenceQueue: GatherLootPersistenceQueue? = nil,
        reporter: @escaping Reporter
    ) {
        self.socket = socket
        self.cookie = cookie
        self.shard = shard
        self.fishingBait = fishingBait
        self.reporter = reporter
        self.http = KintaraHTTPClient(cookie: cookie)
        self.gatherPersistenceQueue = gatherPersistenceQueue ?? GatherLootPersistenceQueue(cookie: cookie)
        self.gatherKnowledge = GatherKnowledgeStore()
        self.region = bootstrap.region
        self.position = bootstrap.position
        self.gatherPositionMemory = gatherKnowledge.positionSnapshot(region: bootstrap.region)
    }

    static func bootstrap(for mode: ActivityMode) -> PresenceBootstrap {
        switch mode {
        case .tree:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: -6.5, z: -18.5))
        case .iron:
            return PresenceBootstrap(region: "frostmere", position: Position(x: 5.5, z: -18.5))
        case .coal, .stone, .chicken:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: 22.5, z: -3.5))
        case .fishing, .zombie, .dragon:
            return PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
        }
    }

    /// Compatibilidade com chamadas antigas que ainda pedem o bootstrap sem
    /// fornecer a decisão autoritativa do preflight.
    static func bootstrapForRun(for mode: ActivityMode, cookie: String) async -> PresenceBootstrap {
        bootstrap(for: mode)
    }

    /// RC3.6: o local da ferramenta decide onde a única Presence da sessão
    /// nasce. Ferramenta carregada conecta direto em ElderGrove; ferramenta no
    /// banco conecta em World e a própria engine faz World→ElderGrove depois do
    /// saque, sem fechar/reabrir o transporte.
    static func bootstrapForRun(
        for mode: ActivityMode,
        gatherDisposition: GatherToolPreflightDisposition
    ) -> PresenceBootstrap {
        guard mode.isGathering else {
            return bootstrap(for: mode)
        }
        if case .needsWorld = gatherDisposition {
            return PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
        }
        return bootstrap(for: mode)
    }

    static func gatherToolPreflightDisposition(for mode: ActivityMode, cookie: String) async -> GatherToolPreflightDisposition {
        guard mode.isGathering,
              let tool = ActivityToolPolicy.requiredTool(for: mode)
        else { return .ready }

        do {
            let counts = try await KintaraHTTPClient(cookie: cookie).itemLocationCounts(type: tool)
            return GatherToolPreflightPolicy.disposition(tool: tool, carried: counts.carried, bank: counts.bank)
        } catch {
            // Falha de leitura não autoriza ElderGrove às cegas. O chamador fará
            // o preflight World e uma nova leitura autoritativa sem cache.
            return .needsWorld(tool: tool)
        }
    }

    @discardableResult
    static func ensureGatherToolCarried(for mode: ActivityMode, cookie: String) async throws -> Int {
        guard mode.isGathering,
              let tool = ActivityToolPolicy.requiredTool(for: mode)
        else { return 0 }
        let client = KintaraHTTPClient(cookie: cookie)
        let before = try await client.itemLocationCounts(type: tool)
        if before.carried >= 1 { return before.carried }
        guard before.bank >= 1 else {
            throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(tool))
        }
        let carried = try await client.ensureCarriedItem(type: tool, quantity: 1, preferHotbar: true)
        let confirmed = try await client.itemLocationCounts(type: tool)
        guard carried >= 1 || confirmed.carried >= 1 else {
            throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(tool))
        }
        return max(carried, confirmed.carried)
    }

    func prepareIdentity() async {
        do {
            let me = try await http.get("/api/auth/me")
            if let player = me["player"] as? [String: Any], let id = RealtimeProtocol.int(player["id"]) {
                playerID = id
                reporter(.diagnostic("[PLAYER] /api/auth/me confirmou playerId=\(id)"))
            } else {
                reporter(.diagnostic("[PLAYER] /api/auth/me não trouxe player.id; confirmações by=self ficarão conservadoras"))
            }
        } catch {
            reporter(.diagnostic("[PLAYER] /api/auth/me falhou: \(error.localizedDescription)"))
        }
    }

    func ingest(_ data: Data) async {
        guard let packet = RealtimeProtocol.packet(data), let type = packet["t"] as? String else { return }

        if let le = RealtimeProtocol.int(packet["le"]), le > lifeEpoch {
            lifeEpoch = le
        }

        switch type {
        case "region_ack":
            if let value = packet["region"] as? String, !value.isEmpty {
                serverRegion = value
                lastRegionConfirmationSource = "region_ack"
                region = value
                reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
                reporter(.diagnostic("[REGION] ACK \(value)"))
            }

        case "snap":
            await ingestSnapshot(packet)

        case "res_evt", "res_snap":
            await ingestResourceEvent(packet)

        case "action_proof":
            await ingestActionProof(packet)

        case "fish_spots":
            ingestFishSpots(packet)

        case "fish_spot_moved":
            ingestFishSpotMoved(packet)

        case "fish_bite":
            guard let fc = RealtimeProtocol.int(packet["fc"]), let fr = RealtimeProtocol.int(packet["fr"]) else { return }
            fishBiteSerial += 1
            lastFishBite = FishBite(serial: fishBiteSerial, fc: fc, fr: fr, ms: max(0, RealtimeProtocol.int(packet["ms"]) ?? 0), at: nowMS)
            reporter(.diagnostic("[FISH] fish_bite fc=\(fc) fr=\(fr) ms=\(RealtimeProtocol.int(packet["ms"]) ?? 0)"))

        case "am_ev":
            if packet["a"] as? String == "hit", isSelf(packet["by"]), let index = RealtimeProtocol.int(packet["i"]) {
                ambientHitSerial += 1
                lastAmbientHitIndex = index
                reporter(.diagnostic("[COMBAT] am_ev hit confirmado i=\(index)"))
            }

        case "wm_ev":
            if packet["a"] as? String == "hit", isSelf(packet["by"]), let index = RealtimeProtocol.int(packet["i"]) {
                wildHitSerial += 1
                lastCombatActivityAt = nowMS
                let killedType: String? = RealtimeProtocol.int(packet["dr"]) == 1 ? "dragon" : (RealtimeProtocol.int(packet["zm"]) == 1 ? "zombie" : nil)
                lastWildHit = WildHitAck(serial: wildHitSerial, index: index, killedType: killedType)
                reporter(.diagnostic("[COMBAT] wm_ev hit confirmado i=\(index)\(killedType.map { " kill=\($0)" } ?? "")"))
            }

        case "inv_grant":
            if let grant = wildGrantHint(packet) {
                wildGrantSerial += 1
                recentWildGrants.append(WildGrant(serial: wildGrantSerial, type: grant.type, quantity: grant.quantity, at: nowMS))
                if recentWildGrants.count > 40 { recentWildGrants.removeFirst(recentWildGrants.count - 40) }
                reporter(.diagnostic("[LOOT] inv_grant #\(wildGrantSerial) • \(grant.quantity)x \(grant.type)"))
            }

        case "drink_ack":
            if let seq = RealtimeProtocol.int(packet["seq"]) {
                let potion = (packet["pt"] as? String) ?? ""
                let ok = RealtimeProtocol.bool(packet["ok"]) ?? ((packet["error"] as? String) == nil)
                let error = packet["error"] as? String
                lastDrinkAck = PotionDrinkAck(seq: seq, potion: potion, ok: ok, error: error)
                reporter(.diagnostic("[POTION] drink_ack seq=\(seq) pt=\(potion.isEmpty ? "?" : potion) ok=\(ok ? "sim" : "não")\(error.map { " error=\($0)" } ?? "")"))
            }

        case "skill_xp":
            if let xp = packet["xp"] as? [String: Any], let combat = RealtimeProtocol.int(xp["combat"]) {
                combatXPTotal = max(0, combat)
                combatXPSerial += 1
                reporter(.diagnostic("[XP] Combat XP autoritativo=\(combatXPTotal ?? 0)"))
            }

        case "pvit", "wild_mb_ack":
            ingestVitals(packet)

        default:
            break
        }
    }

    func requestSafeStop(reason: EngineStopReason) {
        guard safeStopReason == nil else { return }
        safeStopReason = reason
        let label: String
        switch reason {
        case .user: label = "usuário"
        case .backgroundExpiration: label = "encerramento externo de Continued Processing"
        case .connectionLoss: label = "queda de conexão"
        }
        reporter(.diagnostic("[STATE] safe-stop solicitado • motivo=\(label)"))
    }

    func run(mode: ActivityMode, goal: Int) async throws -> EngineRunResult {
        successes = 0
        safeStopCompleted = false
        try Task.checkCancellation()

        switch mode {
        case .tree, .coal, .stone, .iron:
            try await runGather(mode: mode, goal: goal)
        case .fishing:
            try await runFishing(goal: goal)
        case .chicken:
            try await runChicken(goal: goal)
        case .zombie, .dragon:
            try await runWild(mode: mode, goal: goal)
        }

        return EngineRunResult(
            successes: successes,
            completedGoal: successes >= goal,
            stoppedSafely: safeStopCompleted,
            stopReason: safeStopReason
        )
    }

    /// RC3 emergency path used only after an unexpected Presence loss in Wild.
    /// It never resumes combat: after authoritative state arrives, its sole goal
    /// is to confirm death/World or leave Wilderness through the normal safe path.
    func runEmergencyWildExit(
        mode: ActivityMode,
        reason: String = "reconexão de emergência"
    ) async throws -> EmergencyWildExitResult {
        guard mode.isWildCombat else { return .alreadyWorld }
        reporter(.state(.recovering, "Sincronizando estado para saída segura"))

        let syncDeadline = nowMS + 8_000
        while nowMS < syncDeadline {
            try Task.checkCancellation()
            if playerHP <= 0 { return .dead }
            if let authoritative = serverRegion?.lowercased(), !authoritative.isEmpty {
                if !authoritative.hasPrefix("wild") {
                    reporter(.log("✅ Estado autoritativo • região=\(authoritative) • personagem fora da Wilderness"))
                    return .alreadyWorld
                }
                region = authoritative
                break
            }
            try await sleep(80)
        }

        guard let authoritative = serverRegion?.lowercased(), authoritative.hasPrefix("wild") else {
            throw EngineError.regionNotConfirmed("estado autoritativo após reconexão")
        }
        guard playerHP > 0 else { return .dead }

        // A janela anterior ficou parcialmente offline e não pode ser conhecida com
        // precisão. Reinicie conservadoramente os 10 s a partir da reconexão.
        let recoveredAt = nowMS
        lastCombatActivityAt = recoveredAt
        lastCombatDamageAt = recoveredAt
        safeStopReason = .connectionLoss
        reporter(.log("🛡️ Wilderness confirmada após \(reason) • nenhum ataque será retomado • iniciando saída segura"))

        try await moveToWildSafeCamp(reason: reason)
        guard playerHP > 0 else { return .dead }
        try await waitForCombatSafetyWindow(reason: reason)
        guard playerHP > 0 else { return .dead }
        try await exitWildToWorld(reason: reason)
        return .worldSafe
    }

    // MARK: - Common state

    private func ingestSnapshot(_ packet: [String: Any]) async {
        let previousHP = playerHP
        let previousShield = playerShield

        if let packetRegion = packet["region"] as? String, !packetRegion.isEmpty {
            serverRegion = packetRegion
            lastRegionConfirmationSource = "snapshot"
        }

        if let res = packet["res"] as? [[String: Any]] {
            let snapshotRegion = serverRegion?
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
            resourceSnapshotRegion = snapshotRegion

            // World can also publish `res`. During the single-Presence tool
            // preflight those rows must never contaminate a gathering region's
            // cooldowns or unlock its persisted catalog.
            if let snapshotRegion, GatherRegionPolicy.isGatherRegion(snapshotRegion) {
                let now = nowMS
                for group in res {
                    let kind = ((group["kind"] ?? group["k"]) as? String) ?? ""
                    guard !kind.isEmpty else { continue }
                    let keys = stringArray(group["keys"] ?? group["key"])
                    guard !keys.isEmpty else { continue }
                    rememberGatherMetadata(
                        region: snapshotRegion ?? "",
                        kind: kind,
                        keys: keys,
                        hasCoal: RealtimeProtocol.bool(group["hasCoal"]),
                        hasMetal: RealtimeProtocol.bool(group["hasMetal"]),
                        source: "snap_cooldown"
                    )
                    let until = RealtimeProtocol.double(group["until"]) ?? (now + 2_500)
                    for key in keys {
                        cooldownUntil["\(kind):\(key)"] = until
                    }
                }
            }
        }

        // A posição usada pela engine é o estado de comando local, assim como em
        // presenceWs.js v5.2. Snapshots podem chegar atrasados (por exemplo ainda
        // mostrando o portal 30.5,0.5 depois de já termos enviado o stand -1.5,-1.5).
        // Se esses snapshots sobrescreverem `position`, o próximo heartbeat desfaz
        // nosso próprio movimento e a pesca fica longe de todos os fish_spots.
        //
        // Ainda preservamos a posição recebida do servidor para a telemetria da UI;
        // apenas não deixamos um snapshot antigo alterar a posição operacional.
        var authoritativePosition = position
        if let players = packet["players"] as? [[String: Any]], let id = playerID,
           let me = players.first(where: { RealtimeProtocol.int($0["id"]) == id }) {
            if let x = RealtimeProtocol.double(me["x"]), let z = RealtimeProtocol.double(me["z"]) {
                authoritativePosition.x = x
                authoritativePosition.z = z
                if let y = RealtimeProtocol.double(me["y"]) { authoritativePosition.y = y }
                if let ry = RealtimeProtocol.double(me["ry"]) { authoritativePosition.ry = ry }
            }
            if let hp = RealtimeProtocol.int(me["php"]) { playerHP = hp }
            if let shield = RealtimeProtocol.int(me["wsh"]) { playerShield = shield }
            if let le = RealtimeProtocol.int(me["le"]), le > lifeEpoch { lifeEpoch = le }
        }

        if let vitals = packet["playersVital"] as? [[String: Any]], let id = playerID,
           let me = vitals.first(where: { RealtimeProtocol.int($0["id"] ?? $0["pid"]) == id }) {
            if let hp = RealtimeProtocol.int(me["php"]) { playerHP = hp }
            if let shield = RealtimeProtocol.int(me["wsh"]) { playerShield = shield }
            if let le = RealtimeProtocol.int(me["le"]), le > lifeEpoch { lifeEpoch = le }
        }

        if let wear = packet["wear"] as? [[String: Any]] {
            for item in wear {
                let kind = ((item["kind"] ?? item["k"]) as? String) ?? ""
                let keys = stringArray(item["keys"] ?? item["key"])
                rememberGatherMetadata(
                    region: (packet["region"] as? String) ?? serverRegion ?? region,
                    kind: kind,
                    keys: keys,
                    hasCoal: RealtimeProtocol.bool(item["hasCoal"]),
                    hasMetal: RealtimeProtocol.bool(item["hasMetal"]),
                    source: "snap_wear"
                )
                guard matchesCurrentGather(kind: kind, keys: keys) else { continue }
                if let h = RealtimeProtocol.int(item["h"]), h >= harvestH {
                    if h > harvestH {
                        harvestWearSerial += 1
                        gatherResourceSerial += 1
                    }
                    harvestH = h
                }
                if let hm = RealtimeProtocol.int(item["hm"]), hm > 0 { harvestHM = hm }
                let proof = proofString(item)
                if !proof.isEmpty, proof != harvestProof {
                    harvestProof = proof
                    harvestProofSerial += 1
                    gatherResourceSerial += 1
                }
                await gatherEventGate.signal()
            }
        }

        if let npcs = packet["npcs"] as? [String: Any] {
            ingestChickenCollections(npcs)
            if let wild = npcs["wildMobs"] as? [[String: Any]] {
                await ingestWildMobs(wild)
            }
        }
        if let wild = packet["wildMobs"] as? [[String: Any]] {
            await ingestWildMobs(wild)
        }

        if (serverRegion ?? region).hasPrefix("wild"), (playerHP < previousHP || playerShield < previousShield) {
            let timestamp = nowMS
            lastCombatActivityAt = timestamp
            lastCombatDamageAt = timestamp
            let previousEffective = max(0, previousHP) + max(0, previousShield)
            let currentEffective = max(0, playerHP) + max(0, playerShield)
            if previousEffective - currentEffective >= 30 { emergencyVitalDrop = true }
        }

        reporter(.player(authoritativePosition, hp: playerHP, shield: playerShield, region: serverRegion ?? region))
        reporter(.world(nodes: availableSeedCount(), mobs: max(chickens.count, wildMobs.count), serverRegion: serverRegion))
    }

    private func ingestVitals(_ packet: [String: Any]) {
        if let pid = RealtimeProtocol.int(packet["pid"] ?? packet["id"]), let playerID, pid != playerID { return }
        let previousHP = playerHP
        let previousShield = playerShield
        if let hp = RealtimeProtocol.int(packet["php"]) { playerHP = hp }
        if let shield = RealtimeProtocol.int(packet["wsh"]) { playerShield = shield }
        if let le = RealtimeProtocol.int(packet["le"]), le > lifeEpoch { lifeEpoch = le }
        if region.hasPrefix("wild"), (playerHP < previousHP || playerShield < previousShield) {
            let timestamp = nowMS
            lastCombatActivityAt = timestamp
            lastCombatDamageAt = timestamp
            let previousEffective = max(0, previousHP) + max(0, previousShield)
            let currentEffective = max(0, playerHP) + max(0, playerShield)
            if previousEffective - currentEffective >= 30 { emergencyVitalDrop = true }
        }
        reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
    }

    private func sendPosition(moving: Bool, full: Bool = false, action: [String: Any] = [:]) async throws {
        var extra = action
        if let equipment, extra["eq"] == nil { extra["eq"] = equipment }
        if region.hasPrefix("wild") {
            // Important: a potion tick may intentionally pass php/wsh/sps/stb.
            // Do not overwrite those one-shot proposals with stale local vitals.
            if extra["php"] == nil { extra["php"] = playerHP }
            if extra["wsh"] == nil { extra["wsh"] = playerShield }
            if extra["wsp"] == nil { extra["wsp"] = 0 }
            if extra["stb"] == nil {
                let strengthSeconds = strengthBuffSeconds()
                if strengthSeconds > 0 { extra["stb"] = strengthSeconds }
            }
        }
        let data = try RealtimeProtocol.position(region: region, position: position, lifeEpoch: lifeEpoch, moving: moving, full: full, action: extra)
        try await socket.send(data)
    }

    private func setRegion(_ value: String, at pos: Position, extras: [String: Any] = [:]) async throws {
        let previousRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let nextRegion = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if GatherRegionPolicy.isGatherRegion(nextRegion), previousRegion != nextRegion {
            resourceSnapshotRegion = nil
            cooldownUntil.removeAll(keepingCapacity: true)
            gatherBusyUntil.removeAll(keepingCapacity: true)
        }
        region = value
        position = pos
        serverRegion = nil
        lastRegionConfirmationSource = nil
        reporter(.state(.syncing, "Entrando em \(prettyRegion(value))"))
        reporter(.log("🌍 Entrando em \(prettyRegion(value))…"))
        try await sendPosition(moving: false, full: true, action: extras)
    }

    private func waitForRegion(_ expected: String, timeoutMS: Int) async throws -> Bool {
        let expectedLower = expected.lowercased()
        let deadline = nowMS + Double(timeoutMS)
        while nowMS < deadline {
            try Task.checkCancellation()
            if serverRegion?.lowercased() == expectedLower { return true }
            if expectedLower == "pond", !fishSpots.isEmpty { return true }
            try await sleep(50)
        }

        // Background scheduling may resume this task just after the nominal
        // deadline even though the receive loop already ingested the ACK.
        // Always perform one authoritative final read before declaring timeout.
        try Task.checkCancellation()
        if serverRegion?.lowercased() == expectedLower { return true }
        if expectedLower == "pond", !fishSpots.isEmpty { return true }
        return false
    }

    private func equip(_ item: String) async throws {
        equipment = item
        try await sendPosition(moving: false)
        reporter(.diagnostic("[EQUIP] \(item)"))
        try await sleep(120)
    }

    private func clearAction() async throws {
        activeFishingAction = nil
        position.y = 0.25
        try await sendPosition(moving: false)
    }

    private func sendFishingPhase(_ target: FishTarget, phase: Int) async throws {
        let action: [String: Any] = [
            "act": "fish",
            "eq": "tool_fishing_rod",
            "fc": target.fc,
            "fr": target.fr,
            "fph": phase
        ]
        activeFishingAction = action
        try await sendPosition(moving: false, action: action)
    }

    private func walk(to target: Position, maxSeconds: Double = 35, status: String? = nil) async throws {
        if let status, !status.isEmpty {
            reporter(.state(.moving, status))
        }
        let speed = MovementProgressPolicy.speed
        let dt = MovementProgressPolicy.frameSeconds
        var sentFrames = 0

        while true {
            try Task.checkCancellation()
            let dx = target.x - position.x
            let dz = target.z - position.z
            let distance = hypot(dx, dz)
            if distance < 0.4 { break }
            if MovementProgressPolicy.exhausted(sentFrames: sentFrames, maxSeconds: maxSeconds, frameSeconds: dt) {
                throw EngineError.movementTimeout
            }

            let amount = min(distance, speed * dt)
            position.x += (dx / distance) * amount
            position.z += (dz / distance) * amount
            position.y = 0.2978266400228179
            position.ry = atan2(dx, dz)
            try await sendPosition(moving: true)
            sentFrames += 1
            reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
            try await sleep(150)
        }

        position = Position(x: target.x, y: 0.25, z: target.z, ry: target.ry)
        try await sendPosition(moving: false)
        reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
    }

    private func heartbeat() async {
        while !Task.isCancelled {
            do {
                try await sleep(3_000)
                if Task.isCancelled { return }

                // Paridade com Presence._sendPos() da v5.2: durante um cast,
                // o heartbeat precisa continuar enviando act=fish + fc/fr/fph.
                // Um pos sem act equivale ao clearAct() usado pelo cliente Node
                // e podia cancelar silenciosamente a pesca antes do fish_bite.
                if region == "pond", let action = activeFishingAction {
                    try await sendPosition(moving: false, action: action)
                } else {
                    try await sendPosition(moving: false)
                }
            } catch is CancellationError {
                // Fim normal da atividade/meta/STOP. Cancelar o heartbeat não é
                // perda de conexão e não pode transformar 5/5 em erro fatal.
                return
            } catch {
                if Task.isCancelled { return }
                reporter(.fatal("Conexão realtime perdida: \(error.localizedDescription)"))
                return
            }
        }
    }

    // MARK: - Gathering

    private func recordGatherRecovery(proofMiss: Bool = false) {
        gatherInternalRecoveries += 1
        if proofMiss { gatherProofMisses += 1 }
        reporter(.gatherRecovery(proofMiss: proofMiss))
    }

    private func runGather(mode: ActivityMode, goal: Int) async throws {
        // RC3.6: se a ferramenta estava no banco, a mesma engine/Presence já a
        // materializou em World. Daqui em diante a ferramenta precisa estar
        // carregada e Gathering nunca volta ao World no hot path.
        try await ensureActivityToolLoadout(for: mode)

        let targetRegion = GatherRegionPolicy.region(for: mode)
        let start = GatherRegionPolicy.startPosition(for: mode)
        reporter(.state(.syncing, "Sincronizando \(prettyRegion(targetRegion))"))
        if serverRegion?.lowercased() != targetRegion {
            try await setRegion(targetRegion, at: start)
        }
        guard try await waitForRegion(targetRegion, timeoutMS: 6_000) else {
            throw EngineError.regionNotConfirmed(targetRegion)
        }
        gatherPositionMemory = gatherKnowledge.positionSnapshot(region: targetRegion)

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer {
            hb.cancel()
            gatherKnowledge.flush()
        }

        gatherInternalRecoveries = 0
        gatherProofMisses = 0
        gatherLastTimingDiagnosticAt = 0
        gatherRetryPolicy.resetExpired(nowMS: nowMS)

        reporter(.state(.searching, "Sincronizando recursos"))
        let resourceDeadline = nowMS + 7_000
        while resourceSnapshotRegion != targetRegion && nowMS < resourceDeadline {
            try Task.checkCancellation()
            try await sleep(80)
        }
        if resourceSnapshotRegion != targetRegion {
            reporter(.diagnostic("[GATHER] snap.res ainda não chegou; usando somente bootstrap conhecido, sem assumir disponibilidade do catálogo persistido"))
        } else {
            let persisted = persistedSeedCount(for: mode)
            reporter(.log("🗺️ Catálogo persistente v5.2 • \(availableSeedCount(for: mode)) alvos disponíveis • aprendidos=\(persisted) • posições lembradas=\(gatherPositionMemory.count)"))
        }

        while successes < goal {
            try Task.checkCancellation()
            reporter(.state(.searching, "Procurando \(mode.displayName.lowercased())"))

            guard let seed = selectGatherSeed(for: mode) else {
                reporter(.target(nil))
                reporter(.diagnostic("[GATHER] Nenhum alvo disponível agora; aguardando cooldown/defer"))
                try await sleep(1_500)
                continue
            }

            reporter(.target("\(mode.displayName) • \(seed.keys.joined(separator: ","))"))
            reporter(.state(.selectingTarget, "Alvo \(seed.targetKey)"))
            reporter(.log("🎯 \(mode.displayName) \(seed.targetKey) selecionado"))

            let interactionPosition = gatherPositionMemory[seed.signature] ?? seed.position
            try await walk(to: interactionPosition, status: "Indo até \(mode.displayName) \(seed.targetKey)")
            position.ry = interactionPosition.ry
            try await sendPosition(moving: false)
            reporter(.diagnostic("[MOVE] arrived \(seed.targetKey) pos=\(format(position.x)),\(format(position.z)) ry=\(format(position.ry))"))

            let result = try await harvestWithRecovery(seed: seed, mode: mode)
            if result.felled {
                reporter(.attempt)
                let signature = seed.signature
                let localCooldown = nowMS + 12_000
                for key in seed.keys { cooldownUntil["\(seed.kind):\(key)"] = localCooldown }
                gatherRetryPolicy.markSuccess(signature: signature)
                let successfulPosition = Position(x: position.x, y: 0.25, z: position.z, ry: position.ry)
                gatherPositionMemory[signature] = successfulPosition
                _ = gatherKnowledge.rememberPosition(
                    region: targetRegion,
                    kind: seed.kind,
                    keys: seed.keys,
                    position: successfulPosition,
                    at: nowMS
                )
                let resolvedCoal: Bool? = seed.kind == "rock" ? seed.hasCoal : nil
                let resolvedMetal: Bool? = seed.kind == "rock" ? seed.hasMetal : nil
                let catalogChange = gatherKnowledge.rememberResource(
                    region: targetRegion,
                    kind: seed.kind,
                    keys: seed.keys,
                    hasCoal: resolvedCoal,
                    hasMetal: resolvedMetal,
                    source: "self_felled",
                    confirmedAt: nowMS
                )
                if catalogChange == .added || catalogChange == .updated {
                    reporter(.diagnostic("[GATHER] catálogo persistente confirmado por sucesso • \(seed.signature)"))
                }

                var persistenceLabel = "sem loot confirmado"
                if let loot = result.loot, !loot.isEmpty {
                    let job = await gatherPersistenceQueue.enqueue(item: loot, amount: 1)
                    let reporter = self.reporter
                    Task {
                        let receipt = await job.value
                        if let error = receipt.errorDescription {
                            reporter(.diagnostic("[INVENTORY][ERROR] \(receipt.item) • \(error)"))
                        }
                    }

                    if let receipt = await gatherPersistenceQueue.preview(job) {
                        if let error = receipt.errorDescription {
                            persistenceLabel = "persistência enfileirada; última gravação falhou: \(error)"
                        } else {
                            persistenceLabel = receipt.total.map { "\(loot)=\($0)" } ?? "\(loot) persistido"
                        }
                    } else {
                        persistenceLabel = "\(loot) • persistência enfileirada"
                    }
                }

                successes += 1
                reporter(.success(result.loot))
                reporter(.state(.cooldown, "Concluído \(successes)/\(goal)"))
                reporter(.log("✅ \(mode.displayName) concluído • h=\(result.h)/\(result.hm) • \(persistenceLabel) • \(successes)/\(goal)"))
                try await sleep(280)
                continue
            }

            if result.recoverable {
                recordGatherRecovery(proofMiss: result.pureProofMiss)
                if result.pureProofMiss {
                    gatherRetryPolicy.deferProofMiss(signature: seed.signature, nowMS: nowMS)
                    reporter(.state(.recovering, "Sincronizando recurso"))
                    reporter(.log("🟡 \(mode.displayName) \(seed.targetKey) • proof ainda não aceito após recovery • alvo adiado • nenhuma falha contabilizada"))
                } else {
                    gatherRetryPolicy.deferAcceptedPartial(signature: seed.signature, nowMS: nowMS)
                    reporter(.state(.recovering, "Continuando ação aceita"))
                    reporter(.log("🔄 \(mode.displayName) \(seed.targetKey) • progresso aceito h=\(result.h)/\(result.hm) • continuará em novo ciclo • nenhuma falha contabilizada"))
                }
                try await sleep(350)
                continue
            }

            reporter(.attempt)
            let deferred = gatherRetryPolicy.markRealFailure(signature: seed.signature, nowMS: nowMS)
            reporter(.failure(result.reason))
            reporter(.state(.recovering, "Reavaliando alvo"))
            if deferred {
                reporter(.log("⚠️ \(mode.displayName) \(seed.targetKey): \(result.reason) • alvo adiado por 10s após falhas reais repetidas"))
            } else {
                reporter(.log("⚠️ \(mode.displayName) \(seed.targetKey): \(result.reason); outro alvo será tentado"))
            }
            try await sleep(650)
        }

        let pendingBeforeDrain = await gatherPersistenceQueue.pendingCount()
        if pendingBeforeDrain > 0 {
            reporter(.diagnostic("[INVENTORY] aguardando fila serial • pendentes=\(pendingBeforeDrain) • limite=\(GatherPersistencePolicy.finalDrainMS)ms"))
        }
        let persistenceDrained = await gatherPersistenceQueue.drain()
        if !persistenceDrained {
            reporter(.diagnostic("[INVENTORY][WARN] fila ainda pendente após \(GatherPersistencePolicy.finalDrainMS)ms; atividade realtime já pode encerrar"))
        }
        reporter(.log("📊 Coleta encerrada • \(mode.displayName) • sucessos=\(successes)/\(goal) • recoveries internos=\(gatherInternalRecoveries) • proof misses=\(gatherProofMisses)"))
    }

    private func harvestWithRecovery(seed: GatherSeed, mode: ActivityMode) async throws -> HarvestResult {
        var merged = try await harvest(seed: seed, mode: mode, handshakeTries: 4)

        // v7.7: um proof miss puro é primeiro tratado como problema de sincronização,
        // não como falha do usuário. Reenvia a mesma posição, espera refresh e tenta
        // novamente antes de abandonar a geometria que acabou de ser usada.
        if merged.pureProofMiss {
            recordGatherRecovery(proofMiss: true)
            reporter(.diagnostic("[GATHER] proof miss • same-position event resync 900ms • \(seed.targetKey)"))
            let eventBefore = await gatherEventGate.serial
            position.y = 0.25
            try await sendPosition(moving: false, full: true)
            _ = try await gatherEventGate.wait(after: eventBefore, timeoutMS: 900)
            try await equip(seed.kind == "tree" ? "tool_axe" : "tool_pickaxe")
            let retry = try await harvest(seed: seed, mode: mode, handshakeTries: 2)
            merged = merged.merging(retry)
        }

        // v7.7: se a mesma posição ainda não obtiver proof, percorre somente células
        // cardinais canônicas adjacentes ao footprint real do recurso. Nenhum ponto
        // arbitrário é inventado.
        if merged.pureProofMiss {
            let candidates = canonicalGatherRecoveryPositions(for: seed)
            for (index, candidate) in candidates.enumerated() {
                try Task.checkCancellation()
                if hypot(position.x - candidate.x, position.z - candidate.z) < 0.25 { continue }
                recordGatherRecovery(proofMiss: true)
                reporter(.diagnostic("[GATHER] recovery adjacent \(index + 1)/\(candidates.count) • \(seed.targetKey) • x=\(format(candidate.x)) z=\(format(candidate.z))"))
                try await walk(to: candidate, maxSeconds: 18, status: "Reposicionando para \(mode.displayName) \(seed.targetKey)")
                position.ry = candidate.ry
                try await sendPosition(moving: false)
                let probe = try await harvest(seed: seed, mode: mode, handshakeTries: 2)
                merged = merged.merging(probe)
                if !probe.pureProofMiss { break }
            }
        }

        // v7.7 accepted-continuation: se o servidor já aceitou proof/wear parcial,
        // uma ausência transitória do próximo ACK não transforma a ação em falha.
        var continuation = 0
        while !merged.felled, merged.accepted, continuation < 3 {
            try Task.checkCancellation()
            continuation += 1
            recordGatherRecovery()
            reporter(.diagnostic("[GATHER] recovery accepted • \(seed.targetKey) • continuidade \(continuation)/3 • h=\(merged.h)/\(merged.hm)"))
            try await sleep(90)
            let next = try await harvest(seed: seed, mode: mode, handshakeTries: 2)
            merged = merged.merging(next)
            if merged.felled { break }
            if !next.accepted && !next.pureProofMiss { break }
        }

        return merged
    }

    private func harvest(seed: GatherSeed, mode: ActivityMode, handshakeTries: Int) async throws -> HarvestResult {
        let kind = seed.kind
        currentGatherSignature = seed.signature
        currentGatherKind = kind
        currentGatherKeys = Set(seed.keys)
        harvestProof = ""
        harvestProofSerial = 0
        harvestWearSerial = 0
        harvestH = 0
        harvestHM = 99
        harvestLoot = nil
        harvestClearSeen = false

        let tool = kind == "tree" ? "tool_axe" : "tool_pickaxe"
        try await equip(tool)

        position.ry = position.ry.isFinite ? position.ry : seed.position.ry
        position.y = 0.25
        try await sendPosition(moving: false)
        try await sleep(55)

        reporter(.state(.preparingAction, kind == "tree" ? "Preparando corte" : "Preparando mineração"))

        var totalHits = 0
        var damageHits = 0
        var mineProgress = 0.0
        var lastHitAt = 0.0

        func targetTile() -> (Int, Int) {
            let parts = seed.targetKey.split(separator: ",")
            return (Int(parts.first ?? "0") ?? 0, Int(parts.dropFirst().first ?? "0") ?? 0)
        }

        func sendProfile(_ second: Bool, progressive: Bool) async throws {
            var maxSchedulerDelayMS = 0

            func waitRelative(_ intendedMS: Int) async throws {
                let before = nowMS
                try await sleep(intendedMS)
                let actualMS = max(0, Int((nowMS - before).rounded()))
                maxSchedulerDelayMS = max(maxSchedulerDelayMS, max(0, actualMS - intendedMS))
            }

            if kind == "tree" {
                let profile = second ? Self.treeY2 : Self.treeY1
                let gap = GatherTimingPolicy.treeFrameGapMS(frameCount: profile.count)
                for (index, delta) in profile.enumerated() {
                    if index > 0 { try await waitRelative(gap) }
                    position.y = 0.25 + delta
                    try await sendPosition(moving: false, action: ["act": "chop", "eq": tool])
                }
            } else {
                let tile = targetTile()
                let yProfile = second ? Self.mineY2 : Self.mineY1
                let mpProfile = second ? Self.mineMP2 : Self.mineMP1
                let estimatedHM = harvestHM < 99 ? harvestHM : (seed.keys.count <= 1 ? 6 : (seed.keys.count == 2 ? 7 : 10))
                if progressive {
                    mineProgress = max(mineProgress, min(1, Double(harvestH) / Double(max(1, estimatedHM))))
                    let next = min(1, Double(harvestH + 1) / Double(max(1, estimatedHM)) + min(0.010, 0.06 / Double(max(1, estimatedHM))))
                    let shapeMax = Self.mineMP1.last ?? 1
                    for index in Self.mineMP1.indices {
                        if index > 0 { try await waitRelative(GatherTimingPolicy.mineFrameGapMS) }
                        let shape = Self.mineMP1[index] / shapeMax
                        let value = min(1, mineProgress + max(0, next - mineProgress) * shape)
                        position.y = 0.25 + Self.mineY1[index]
                        try await sendPosition(moving: false, action: ["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": value])
                        mineProgress = max(mineProgress, value)
                    }
                } else {
                    for index in mpProfile.indices {
                        if index > 0 { try await waitRelative(GatherTimingPolicy.mineFrameGapMS) }
                        mineProgress = max(mineProgress, mpProfile[index])
                        position.y = 0.25 + yProfile[index % yProfile.count]
                        try await sendPosition(moving: false, action: ["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": mineProgress])
                    }
                }
            }

            if maxSchedulerDelayMS >= GatherTimingPolicy.delayedFrameDiagnosticThresholdMS,
               gatherLastTimingDiagnosticAt == 0 || nowMS - gatherLastTimingDiagnosticAt >= GatherTimingPolicy.timingDiagnosticCooldownMS {
                gatherLastTimingDiagnosticAt = nowMS
                reporter(.diagnostic("[GATHER][TIMING] scheduler atrasou até \(maxSchedulerDelayMS)ms • perfil preservado com espaçamento relativo • nenhuma rajada enviada"))
            }
        }

        func sendHit(proof: String?) async throws {
            let data = try RealtimeProtocol.harvestHit(
                region: region,
                kind: kind,
                keys: seed.keys,
                hasCoal: seed.hasCoal,
                hasMetal: seed.hasMetal,
                proof: proof
            )
            try await socket.send(data)
            totalHits += 1
            reporter(.hitSent)
            lastHitAt = nowMS
        }

        func waitForAck(proofBefore: Int, wearBefore: Int, hBefore: Int, timeoutMS: Int) async throws -> HarvestAck {
            func inspect() -> HarvestAck? {
                if harvestHM < 99, harvestH >= harvestHM { return .felled }
                let sawFreshProof = harvestProofSerial > proofBefore && !harvestProof.isEmpty
                let sawProgress = harvestWearSerial > wearBefore || harvestH > hBefore
                if sawFreshProof && sawProgress { return .accepted }
                return nil
            }

            if let immediate = inspect() { return immediate }
            let deadline = nowMS + Double(timeoutMS)
            var eventSerial = await gatherEventGate.serial
            while nowMS < deadline {
                try Task.checkCancellation()
                let remaining = max(1, Int(deadline - nowMS))
                let signaled = try await gatherEventGate.wait(after: eventSerial, timeoutMS: remaining)
                eventSerial = await gatherEventGate.serial
                if let state = inspect() { return state }
                if !signaled { break }
            }

            if let final = inspect() { return final }

            // Proof e wear podem chegar em mensagens separadas. Em vez de polling
            // de 20 ms (sensível ao scheduler em background), aguarde diretamente
            // o próximo evento autoritativo por uma pequena janela.
            let hasHalfAck = (harvestProofSerial > proofBefore && !harvestProof.isEmpty) ||
                (harvestWearSerial > wearBefore || harvestH > hBefore)
            if hasHalfAck {
                let beforeGrace = await gatherEventGate.serial
                _ = try await gatherEventGate.wait(
                    after: beforeGrace,
                    timeoutMS: GatherTimingPolicy.eventGraceMS
                )
                if let graceState = inspect() { return graceState }
            }
            return .timeout
        }

        var handshake: HarvestAck = harvestProof.isEmpty ? .timeout : .accepted
        if harvestProof.isEmpty {
            let tries = min(4, max(1, handshakeTries))
            for attempt in 1...tries {
                let proofBefore = harvestProofSerial
                let wearBefore = harvestWearSerial
                let hBefore = harvestH

                if kind == "rock" {
                    try await sendHit(proof: nil)
                    try await sendProfile(attempt == 2, progressive: false)
                } else {
                    try await sendProfile(attempt == 2, progressive: false)
                    try await sendHit(proof: nil)
                }

                reporter(.state(.waitingProof, "Handshake \(attempt)/\(tries)"))
                reporter(.diagnostic("[GATHER] handshake #\(attempt) \(kind) keys=\(seed.keys) proof=none"))
                handshake = try await waitForAck(
                    proofBefore: proofBefore,
                    wearBefore: wearBefore,
                    hBefore: hBefore,
                    timeoutMS: attempt == 1 ? 900 : 1_200
                )
                if handshake != .timeout { break }

                if attempt == 2 {
                    position.y = 0.25
                    try await sendPosition(moving: false)
                    try await sleep(90)
                    try await equip(tool)
                }
            }
        }

        if handshake == .felled {
            try? await clearAction()
            return HarvestResult(felled: true, h: harvestH, hm: harvestHM, loot: harvestLoot, reason: "felled_during_handshake", accepted: true, proofMiss: false)
        }
        guard handshake == .accepted, !harvestProof.isEmpty else {
            try? await clearAction()
            let accepted = harvestH > 0 || !harvestProof.isEmpty
            return HarvestResult(
                felled: false,
                h: harvestH,
                hm: harvestHM,
                loot: harvestLoot,
                reason: "sem action_proof próprio após handshake",
                accepted: accepted,
                proofMiss: !accepted
            )
        }

        reporter(.state(.acting, kind == "tree" ? "Cortando" : "Minerando"))
        while damageHits < 12, !(harvestHM < 99 && harvestH >= harvestHM) {
            try Task.checkCancellation()
            guard !harvestProof.isEmpty else { break }
            let proof = harvestProof
            let proofBefore = harvestProofSerial
            let wearBefore = harvestWearSerial
            let hBefore = harvestH

            if kind == "rock" {
                let gapLeft = 490.0 - (nowMS - lastHitAt)
                if gapLeft > 0 { try await sleep(Int(gapLeft)) }
                try await sendHit(proof: proof)
                damageHits += 1
                try await sendProfile(false, progressive: true)
            } else {
                try await sendProfile(damageHits % 2 == 1, progressive: false)
                try await sendHit(proof: proof)
                damageHits += 1
            }

            reporter(.state(.waitingResult, "Progresso \(harvestH)/\(harvestHM < 99 ? String(harvestHM) : "?")"))
            let ack = try await waitForAck(proofBefore: proofBefore, wearBefore: wearBefore, hBefore: hBefore, timeoutMS: 1_400)
            if ack == .felled { break }
            if ack != .accepted {
                reporter(.diagnostic("[GATHER] hit sem proof+wear fresco h=\(harvestH) hm=\(harvestHM)"))
                break
            }
            reporter(.confirmedHit)
            if kind == "rock", harvestHM < 99 {
                mineProgress = max(mineProgress, min(1, Double(harvestH) / Double(max(1, harvestHM))))
            }
        }

        let settleDeadline = nowMS + 1_200
        var settleSerial = await gatherEventGate.serial
        while nowMS < settleDeadline, !(harvestHM < 99 && harvestH >= harvestHM) {
            try Task.checkCancellation()
            let remaining = max(1, Int(settleDeadline - nowMS))
            let signaled = try await gatherEventGate.wait(after: settleSerial, timeoutMS: remaining)
            settleSerial = await gatherEventGate.serial
            if !signaled { break }
        }
        try? await clearAction()

        let felled = harvestHM < 99 && harvestH >= harvestHM
        let accepted = felled || damageHits > 0 || harvestH > 0 || !harvestProof.isEmpty
        return HarvestResult(
            felled: felled,
            h: harvestH,
            hm: harvestHM,
            loot: harvestLoot,
            reason: felled ? "FELLED" : (harvestClearSeen ? "clear sem h/hm conclusivo" : "ação não concluiu o wear"),
            accepted: accepted,
            proofMiss: !accepted && !harvestClearSeen
        )
    }

    private func canonicalGatherRecoveryPositions(for seed: GatherSeed) -> [Position] {
        canonicalGatherPositions(keys: seed.keys, region: seed.region)
    }

    private func canonicalGatherPositions(keys: [String], region: String) -> [Position] {
        let tiles: [(Int, Int)] = keys.compactMap { key in
            let parts = key.split(separator: ",")
            guard parts.count == 2, let c = Int(parts[0]), let r = Int(parts[1]) else { return nil }
            return (c, r)
        }
        guard !tiles.isEmpty else { return [] }

        let occupied = Set(tiles.map { "\($0.0),\($0.1)" })
        var seen = Set<String>()
        var candidates: [Position] = []
        for (c, r) in tiles {
            for (dc, dr) in [(0, -1), (1, 0), (0, 1), (-1, 0)] {
                let pc = c + dc
                let pr = r + dr
                let key = "\(pc),\(pr)"
                guard !occupied.contains(key), seen.insert(key).inserted else { continue }

                let gridOffset = GatherRegionPolicy.gridOffset(for: region)
                let px = Double(pc) - gridOffset
                let pz = Double(pr) - gridOffset
                let nearest = tiles.min { a, b in
                    hypot(Double(a.0) - Double(pc), Double(a.1) - Double(pr)) < hypot(Double(b.0) - Double(pc), Double(b.1) - Double(pr))
                } ?? (c, r)
                let tx = Double(nearest.0) - gridOffset
                let tz = Double(nearest.1) - gridOffset
                let ry = atan2(tx - px, tz - pz)
                candidates.append(Position(x: px, z: pz, ry: ry))
            }
        }

        return candidates.sorted {
            let da = hypot($0.x - position.x, $0.z - position.z)
            let db = hypot($1.x - position.x, $1.z - position.z)
            return da < db
        }
    }

    private func ingestActionProof(_ packet: [String: Any]) async {
        guard currentGatherSignature != nil else { return }
        if let by = RealtimeProtocol.int(packet["by"]), let playerID, by != playerID { return }
        let keys = stringArray(packet["keys"] ?? packet["key"])
        if !keys.isEmpty && currentGatherKeys.isDisjoint(with: keys) { return }
        let proof = proofString(packet)
        guard !proof.isEmpty, proof != harvestProof else { return }
        harvestProof = proof
        harvestProofSerial += 1
        gatherResourceSerial += 1
        await gatherEventGate.signal()
        reporter(.diagnostic("[GATHER] action_proof #\(harvestProofSerial)"))
    }

    private func ingestResourceEvent(_ packet: [String: Any]) async {
        let kind = ((packet["kind"] ?? packet["k"]) as? String) ?? ""
        let keys = stringArray(packet["keys"] ?? packet["key"])
        let by = RealtimeProtocol.int(packet["by"])

        // res_evt/res_snap são evidência autoritativa de metadados estáticos do
        // footprint, inclusive quando o evento pertence a outro player. Nunca
        // persistimos proof/wear/cooldown; somente região/tipo/keys/subtipo rock.
        rememberGatherMetadata(
            region: (packet["region"] as? String) ?? serverRegion ?? region,
            kind: kind,
            keys: keys,
            hasCoal: RealtimeProtocol.bool(packet["hasCoal"]),
            hasMetal: RealtimeProtocol.bool(packet["hasMetal"]),
            source: packet["evt"] as? String == "clear" ? "res_evt_clear" : "res_evt"
        )

        // v7.7 remote-activity guard: progresso de outro player torna somente
        // aquele footprint temporariamente ocupado. Nunca aceite proof/wear alheio
        // como confirmação da nossa ação.
        if let by, let playerID, by != playerID {
            let remoteProgress = packet["evt"] as? String == "wear" ||
                (RealtimeProtocol.int(packet["h"]) ?? 0) > 0 ||
                !proofString(packet).isEmpty
            if remoteProgress {
                let keySet = Set(keys)
                for seed in gatherSeedPool() where seed.kind == kind && !Set(seed.keys).isDisjoint(with: keySet) {
                    gatherBusyUntil[seed.signature] = nowMS + 10_000
                }
                reporter(.diagnostic("[GATHER] recurso ocupado por outro player • kind=\(kind) keys=\(keys) • defer 10s"))
            }
            return
        }

        guard matchesCurrentGather(kind: kind, keys: keys) else { return }
        gatherResourceSerial += 1

        if packet["evt"] as? String == "clear" {
            harvestClearSeen = true
            let until = nowMS + 3_000
            for key in keys { cooldownUntil["\(kind):\(key)"] = until }
        }

        var changed = false
        if let h = RealtimeProtocol.int(packet["h"]), h >= harvestH {
            if h > harvestH { changed = true }
            harvestH = h
        }
        if let hm = RealtimeProtocol.int(packet["hm"]), hm > 0 { harvestHM = hm }
        if let loot = packet["loot"] as? String, !loot.isEmpty { harvestLoot = loot }
        let proof = proofString(packet)
        if !proof.isEmpty, proof != harvestProof {
            harvestProof = proof
            harvestProofSerial += 1
        }
        if changed { harvestWearSerial += 1 }
        await gatherEventGate.signal()
        reporter(.diagnostic("[GATHER] res_evt h=\(harvestH) hm=\(harvestHM) proof=\(!harvestProof.isEmpty) loot=\(harvestLoot ?? "-")"))
    }

    private func matchesCurrentGather(kind: String, keys: [String]) -> Bool {
        guard let currentGatherKind, currentGatherSignature != nil else { return false }
        if !kind.isEmpty && kind != currentGatherKind { return false }
        if keys.isEmpty { return true }
        return !currentGatherKeys.isDisjoint(with: keys)
    }

    private func rememberGatherMetadata(
        region incomingRegion: String,
        kind: String,
        keys: [String],
        hasCoal: Bool?,
        hasMetal: Bool?,
        source: String
    ) {
        let normalizedRegion = incomingRegion.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard GatherRegionPolicy.isGatherRegion(normalizedRegion) else { return }
        let resolvedCoal = GatherRegionPolicy.hasCoal(region: normalizedRegion, packetValue: hasCoal)
        let resolvedMetal = GatherRegionPolicy.hasMetal(region: normalizedRegion, packetValue: hasMetal)
        let change = gatherKnowledge.rememberResource(
            region: normalizedRegion,
            kind: kind,
            keys: keys,
            hasCoal: resolvedCoal,
            hasMetal: resolvedMetal,
            source: source,
            confirmedAt: nowMS
        )
        guard change == .added || change == .updated else { return }
        if normalizedRegion == resourceSnapshotRegion {
            gatherPositionMemory = gatherKnowledge.positionSnapshot(region: normalizedRegion)
        }

        let normalizedKind = kind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let subtype: String
        if normalizedKind == "tree" {
            subtype = "tree"
        } else if resolvedMetal == true {
            subtype = "iron"
        } else if resolvedCoal == true {
            subtype = "coal"
        } else if resolvedCoal == false && resolvedMetal == false {
            subtype = "stone"
        } else {
            subtype = "rock (subtipo ainda não confirmado)"
        }
        reporter(.diagnostic("[GATHER] novo conhecimento persistido • \(subtype) • keys=\(GatherKnowledgeStore.normalizeKeys(keys)) • fonte=\(source)"))
    }

    /// Bootstrap compilado + recursos aprendidos. O catálogo restaurado só entra
    /// na seleção depois do primeiro snap.res atual, pois snap.res é a verdade de
    /// cooldown da geração atual. Isso replica a disciplina da v5.2: metadados
    /// persistem, disponibilidade/proof/progresso NÃO.
    private func gatherSeedPool(region requestedRegion: String? = nil) -> [GatherSeed] {
        let activeRegion = requestedRegion ?? resourceSnapshotRegion ?? serverRegion ?? region
        let normalizedRegion = activeRegion.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        var result = Self.gatherSeeds.filter { $0.region == normalizedRegion }
        guard resourceSnapshotRegion == normalizedRegion else { return result }

        var known = Set(result.map(\.signature))
        for entry in gatherKnowledge.catalogEntries(region: normalizedRegion) {
            let kind = entry.kind.lowercased()
            guard kind == "tree" || kind == "rock" else { continue }
            let entryKeys = Set(entry.resourceKeys)
            if result.contains(where: { $0.kind == kind && !Set($0.keys).isDisjoint(with: entryKeys) }) {
                // O mesmo recurso pode ter sido observado primeiro como footprint
                // parcial. O bootstrap comprovado continua sendo a geometria segura
                // até um FELLED confirmar o footprint completo no catálogo.
                continue
            }
            let resolvedCoal = GatherRegionPolicy.hasCoal(region: normalizedRegion, packetValue: entry.hasCoal)
            let resolvedMetal = GatherRegionPolicy.hasMetal(region: normalizedRegion, packetValue: entry.hasMetal)
            if kind == "rock", resolvedCoal == nil || resolvedMetal == nil {
                // Um rock sem subtipo comprovado é lembrado, mas não é usado como
                // Stone por omissão. Um res_evt/snap com os flags ou um FELLED
                // resolverá a classificação futuramente.
                continue
            }
            let signature = GatherKnowledgeStore.signature(kind: kind, keys: entry.resourceKeys)
            guard !signature.isEmpty, known.insert(signature).inserted else { continue }
            guard let fallback = gatherPositionMemory[signature] ?? canonicalGatherPositions(keys: entry.resourceKeys, region: normalizedRegion).first else { continue }
            result.append(GatherSeed(
                region: normalizedRegion,
                kind: kind,
                keys: entry.resourceKeys,
                position: fallback,
                targetKey: entry.resourceKeys.first ?? "?",
                hasCoal: resolvedCoal ?? false,
                hasMetal: resolvedMetal ?? false
            ))
        }
        return result
    }

    private func persistedSeedCount(for mode: ActivityMode? = nil) -> Int {
        let targetRegion = mode.map { GatherRegionPolicy.region(for: $0) } ?? resourceSnapshotRegion ?? region.lowercased()
        guard resourceSnapshotRegion == targetRegion else { return 0 }
        let bootstrapSeeds = Self.gatherSeeds.filter { $0.region == targetRegion }
        return gatherKnowledge.catalogEntries(region: targetRegion).filter { entry in
            let entryKeys = Set(entry.resourceKeys)
            if bootstrapSeeds.contains(where: { $0.kind == entry.kind && !Set($0.keys).isDisjoint(with: entryKeys) }) { return false }
            let resolvedCoal = GatherRegionPolicy.hasCoal(region: targetRegion, packetValue: entry.hasCoal)
            let resolvedMetal = GatherRegionPolicy.hasMetal(region: targetRegion, packetValue: entry.hasMetal)
            if entry.kind == "rock", resolvedCoal == nil || resolvedMetal == nil { return false }
            guard let mode else { return true }
            return GatherResourcePolicy.matches(
                mode: mode,
                kind: entry.kind,
                hasCoal: resolvedCoal ?? false,
                hasMetal: resolvedMetal ?? false
            )
        }.count
    }

    private func selectGatherSeed(for mode: ActivityMode) -> GatherSeed? {
        let now = nowMS
        return gatherSeedPool(region: GatherRegionPolicy.region(for: mode))
            .filter { seed in
                GatherResourcePolicy.matches(mode: mode, kind: seed.kind, hasCoal: seed.hasCoal, hasMetal: seed.hasMetal)
            }
            .filter { seed in
                gatherRetryPolicy.isEligible(signature: seed.signature, nowMS: now) &&
                (gatherBusyUntil[seed.signature] ?? 0) <= now &&
                seed.keys.allSatisfy { (cooldownUntil["\(seed.kind):\($0)"] ?? 0) <= now }
            }
            .min { a, b in
                let retryA = gatherRetryPolicy.hasRetryPriority(signature: a.signature) ? 0 : 1
                let retryB = gatherRetryPolicy.hasRetryPriority(signature: b.signature) ? 0 : 1
                if retryA != retryB { return retryA < retryB }
                let pa = gatherPositionMemory[a.signature] ?? a.position
                let pb = gatherPositionMemory[b.signature] ?? b.position
                return distance(from: position, to: pa) < distance(from: position, to: pb)
            }
    }

    private func availableSeedCount(for mode: ActivityMode? = nil) -> Int {
        let now = nowMS
        let targetRegion = mode.map { GatherRegionPolicy.region(for: $0) }
        return gatherSeedPool(region: targetRegion).filter { seed in
            let modeOK: Bool
            if let mode {
                modeOK = GatherResourcePolicy.matches(mode: mode, kind: seed.kind, hasCoal: seed.hasCoal, hasMetal: seed.hasMetal)
            } else {
                modeOK = true
            }
            return modeOK &&
                gatherRetryPolicy.isEligible(signature: seed.signature, nowMS: now) &&
                (gatherBusyUntil[seed.signature] ?? 0) <= now &&
                seed.keys.allSatisfy { (cooldownUntil["\(seed.kind):\($0)"] ?? 0) <= now }
        }.count
    }

    // MARK: - Activity loadout preflight

    private func ensureWorldBankAccess(reason: String) async throws {
        if serverRegion?.lowercased() != "world" || region.lowercased() != "world" {
            reporter(.state(.syncing, "🌍 Indo ao World • \(reason)"))
            try await setRegion("world", at: Position(x: 22.5, z: -3.5))
            guard try await waitForRegion("world", timeoutMS: 5_000) else {
                throw EngineError.regionNotConfirmed("world")
            }
        }
        let bankPosition = Position(x: -24.0, z: -17.5)
        if hypot(position.x - bankPosition.x, position.z - bankPosition.z) > 0.8 {
            try await walk(to: bankPosition, maxSeconds: 35, status: "🏦 Indo ao banco • \(reason)")
        }
        try await sleep(450)
    }

    private func returnToGatherRegionIfNeeded(for mode: ActivityMode) async throws {
        guard mode.isGathering else { return }
        let targetRegion = GatherRegionPolicy.region(for: mode)
        let start = GatherRegionPolicy.startPosition(for: mode)
        reporter(.state(.syncing, "Retornando a \(prettyRegion(targetRegion))"))
        try await setRegion(targetRegion, at: start)
        guard try await waitForRegion(targetRegion, timeoutMS: 6_000) else {
            throw EngineError.regionNotConfirmed(targetRegion)
        }
    }

    /// Executed by the definitive session engine when its single Presence was
    /// bootstrapped in World. It reuses the proven movement + backpack path,
    /// confirms the tool, and leaves World→gather region to runGather on this same
    /// transport.
    @discardableResult
    func prepareGatherToolFromWorld(for mode: ActivityMode) async throws -> Int {
        guard mode.isGathering,
              let tool = ActivityToolPolicy.requiredTool(for: mode)
        else { return 0 }
        let name = ActivityToolPolicy.displayName(tool)

        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }

        let counts = try await http.itemLocationCounts(type: tool)
        if counts.carried >= 1 {
            reporter(.log("🧰 Preflight transacional • \(name) já está carregada ✅"))
            return counts.carried
        }
        guard counts.bank >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }

        try await ensureWorldBankAccess(reason: "buscar \(name)")
        let carried = try await http.ensureCarriedItem(type: tool, quantity: 1, preferHotbar: true)
        let confirmed = try await http.itemLocationCounts(type: tool)
        let finalCount = max(carried, confirmed.carried)
        guard finalCount >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }
        reporter(.log("🧰 Preflight transacional • \(name) retirada do banco e carregada ✅"))
        return finalCount
    }

    private func ensureActivityToolLoadout(for mode: ActivityMode) async throws {
        guard let tool = ActivityToolPolicy.requiredTool(for: mode) else { return }
        let name = ActivityToolPolicy.displayName(tool)
        let counts = try await http.itemLocationCounts(type: tool)

        if counts.carried >= 1 {
            reporter(.log("🧰 Preflight • \(name) carregada ✅"))
            return
        }

        // RC3.6: Gathering nunca volta da região de coleta ao World para buscar ferramenta.
        // Quando a ferramenta estava no banco, esta mesma engine já a trouxe em
        // World antes de iniciar o hot path de Gathering.
        if mode.isGathering {
            throw EngineError.gatherLoadoutNotReady(name)
        }

        guard counts.bank >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }

        reporter(.state(.syncing, "🧰 Buscando \(name) no banco"))
        try await ensureWorldBankAccess(reason: "buscar \(name)")
        let result = try await http.ensureCarriedItem(
            type: tool,
            quantity: 1,
            preferHotbar: true
        )
        guard result >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }
        reporter(.log("🧰 Preflight • \(name) retirada do banco e carregada ✅"))
    }

    private func ensureFishingBaitLoadout(type: String, goal: Int) async throws {
        let wanted = max(1, goal)
        var counts = try await http.itemLocationCounts(type: type)
        let totalAvailable = counts.carried + counts.bank
        guard totalAvailable >= wanted else {
            throw EngineError.insufficientFishingBait(fishingBait.displayName, have: totalAvailable, need: wanted)
        }

        if counts.carried < wanted {
            reporter(.state(.syncing, "🪱 Buscando \(fishingBait.displayName) no banco"))
            try await ensureWorldBankAccess(reason: "buscar \(fishingBait.displayName)")
            let carried = try await http.ensureCarriedItem(
                type: type,
                quantity: wanted,
                preferHotbar: false
            )
            counts = try await http.itemLocationCounts(type: type)
            guard carried >= wanted || counts.carried >= wanted else {
                throw EngineError.insufficientFishingBait(fishingBait.displayName, have: counts.carried, need: wanted)
            }
            reporter(.log("🪱 Preflight • \(fishingBait.displayName) retirada do banco • \(counts.carried)/\(wanted) carregada ✅"))
        } else {
            reporter(.log("🪱 Preflight • \(fishingBait.displayName) \(counts.carried)/\(wanted) carregada ✅"))
        }
    }

    // MARK: - Fishing

    private func runFishing(goal: Int) async throws {
        // Defense in depth: AppStore already blocks unvalidated bait paths before
        // connecting. The engine repeats the guard so a future caller cannot
        // silently fish The Pond with the wrong selected bait.
        guard fishingBait.isAutomationValidated,
              fishingBait.confirmedInventoryKey != nil
        else {
            throw EngineError.unsupportedFishingBait(fishingBait.displayName)
        }

        activeFishingAction = nil
        fishingStats = FishingSessionStats()
        lastFishingInventory = FishingInventorySnapshot()
        fishCellFailureStreak.removeAll()
        fishBlockedCells.removeAll()
        fishQuarantinedGenerations.removeAll()
        fishHealthWaitSerial = -1

        if serverRegion?.lowercased() != "world" {
            try await setRegion("world", at: Position(x: 22.5, z: -3.5))
            _ = try await waitForRegion("world", timeoutMS: 4_000)
        }

        try await ensureActivityToolLoadout(for: .fishing)
        if let baitType = fishingBait.confirmedInventoryKey {
            try await ensureFishingBaitLoadout(type: baitType, goal: goal)
        }

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        let pondPortal = Position(x: 30.5, z: 0.5)
        let pondEntry = Position(x: -18.5, z: 0)
        let pondStand = Position(x: -1.5, z: -1.5)

        reporter(.state(.moving, "Indo ao portal de The Pond"))
        try await walk(to: pondPortal, maxSeconds: 20)

        var enteredViaPortal = try await waitForRegion("pond", timeoutMS: 5_000)
        var pondConfirmed = enteredViaPortal
        if !pondConfirmed {
            let probes = [pondPortal, pondEntry, pondStand]
            for probe in probes {
                try await setRegion("pond", at: probe)
                if try await waitForRegion("pond", timeoutMS: 2_500) {
                    pondConfirmed = true
                    enteredViaPortal = false
                    break
                }
            }
        }
        guard pondConfirmed else { throw EngineError.regionNotConfirmed("pond") }

        region = "pond"
        reporter(.log("✅ The Pond confirmado"))

        if enteredViaPortal {
            position = pondEntry
            try await sendPosition(moving: false)
            try await sleep(300)
            try await walk(to: pondStand, maxSeconds: 15, status: "Indo para o ponto de pesca")
        } else {
            position = pondStand
            try await sendPosition(moving: false)
        }

        try await sleep(450)
        try await equip("tool_fishing_rod")
        try await sleep(450)
        reporter(.log("🎣 Posição de pesca pronta • x=\(format(position.x)) z=\(format(position.z))"))
        lastFishingInventory = await fetchFishingInventorySnapshot() ?? FishingInventorySnapshot()
        reporter(.log("🪱 Isca selecionada • \(fishingBait.displayName) • estoque \(lastFishingInventory.bait)"))
        guard lastFishingInventory.bait > 0 else {
            throw EngineError.missingFishingBait(fishingBait.displayName)
        }

        if fishSpots.isEmpty {
            reporter(.log("📡 Aguardando fish_spots do servidor…"))
            let spotDeadline = nowMS + 15_000
            while fishSpots.isEmpty && nowMS < spotDeadline {
                try Task.checkCancellation()
                reporter(.state(.syncing, "Aguardando spots de pesca"))
                try await sleep(100)
            }
            if fishSpots.isEmpty {
                reporter(.log("📡 fish_spots ainda não chegou; aguardando o próximo snapshot sem usar coordenadas antigas"))
            }
        } else {
            reporter(.log("🎣 fish_spots já disponível • iniciando seleção do melhor tile"))
        }

        var fishAttemptNumber = 0

        while successes < goal {
            try Task.checkCancellation()
            reporter(.state(.searching, "Procurando spot de pesca"))
            guard let target = selectFishTarget() else {
                reporter(.target(nil))
                // Sem alvo saudável, não contabilize novas tentativas. Apenas
                // ressincronize STAND/vara e aguarde geração realmente nova.
                if !fishBlockedCells.isEmpty || !fishQuarantinedGenerations.isEmpty {
                    if fishHealthWaitSerial != fishSnapshotSerial {
                        fishHealthWaitSerial = fishSnapshotSerial
                        reporter(.log("🎣 Spots atuais temporariamente descartados • aguardando nova geração autoritativa"))
                    }
                    reporter(.state(.recovering, "Pesca • aguardando novo spot válido"))
                }
                position = pondStand
                try? await clearAction()
                try? await sendPosition(moving: false)
                try? await equip("tool_fishing_rod")
                try await sleep(2_500)
                continue
            }

            fishAttemptNumber += 1
            fishingStats.attempts += 1
            let attemptNumber = fishAttemptNumber
            let fishNumber = FishingNumberingPolicy.publicFishNumber(successes: successes)
            let targetLabel = "Spot #\(target.slot) (\(target.fc),\(target.fr))"

            reporter(.target("Spot #\(target.slot) • \(target.fc),\(target.fr)"))
            reporter(.attempt)
            reporter(.state(.acting, "Lançando linha • Peixe #\(fishNumber)"))

            let snapshotBefore = fishSnapshotSerial
            let biteBefore = fishBiteSerial
            let generation = target.generation
            try await sendFishingPhase(target, phase: 0)

            let biteDeadline = nowMS + FishingRecoveryPolicy.biteScheduleTimeoutMS
            var bite: FishBite?
            while nowMS < biteDeadline {
                try Task.checkCancellation()
                if !fishTargetStillValid(target, generation: generation) { break }
                if fishBiteSerial > biteBefore, let candidate = lastFishBite, candidate.fc == target.fc, candidate.fr == target.fr {
                    bite = candidate
                    break
                }
                try await sleep(50)
            }

            guard let bite else {
                try? await clearAction()
                let stillSameGeneration = fishTargetStillValid(target, generation: generation)
                let changed = !stillSameGeneration && fishSnapshotSerial != snapshotBefore
                let reason = changed ? "spot mudou antes da fisgada" : "sem fisgada (fish_bite não recebido)"
                if changed { fishingStats.spotChanged += 1 } else { fishingStats.noBite += 1 }
                reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • \(reason)"))
                recordFishTargetFailure(target, reason: reason)
                try await sleep(650)
                continue
            }

            // fish_bite autoritativo prova que esta célula está saudável agora.
            recordFishTargetSuccess(target)

            let biteSeconds = String(format: "%.1f", Double(bite.ms) / 1000)
            reporter(.log("🪝 Peixe #\(fishNumber) • fisgada em \(biteSeconds)s • \(targetLabel)"))

            let ttl = remainingMS(for: fishSpots[target.slot])
            guard ttl >= Double(bite.ms + FishingRecoveryPolicy.biteExpiryMarginMS) else {
                try? await clearAction()
                fishingStats.staleAvoided += 1
                reporter(.log("↪️ Peixe #\(fishNumber) • tentativa descartada: spot expirando • TTL=\(Int(ttl))ms"))
                reporter(.diagnostic("[FISH] cast #\(attemptNumber) descartado: TTL \(Int(ttl))ms < bite+margin"))
                try await sleep(650)
                continue
            }

            reporter(.state(.waitingResult, "Peixe #\(fishNumber) • fisgada em \(biteSeconds)s"))
            let waitUntil = nowMS + Double(bite.ms + 70)
            var spotRotatedDuringWait = false
            while nowMS < waitUntil {
                try Task.checkCancellation()
                guard fishTargetStillValid(target, generation: generation) else {
                    try? await clearAction()
                    fishingStats.spotChanged += 1
                    reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • spot rotacionou durante a espera"))
                    recordFishTargetFailure(target, reason: "spot rotacionou durante a espera")
                    spotRotatedDuringWait = true
                    break
                }
                try await sleep(100)
            }
            if spotRotatedDuringWait {
                try await sleep(650)
                continue
            }
            guard fishTargetStillValid(target, generation: generation) else { continue }

            try await sendFishingPhase(target, phase: 1)
            try await sleep(180)
            try await sendFishingPhase(target, phase: 2)
            try await sleep(220)

            guard fishTargetStillValid(target, generation: generation) else {
                try? await clearAction()
                fishingStats.spotChanged += 1
                reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • spot mudou antes da confirmação"))
                recordFishTargetFailure(target, reason: "spot mudou antes da confirmação")
                try await sleep(650)
                continue
            }

            do {
                let shardID = Int(shard.replacingOccurrences(of: "s", with: "")) ?? 4
                let response = try await http.post("/api/auth/grant-fish-xp", body: ["mountCatch": true, "fleet": "us", "shardId": shardID])
                try? await clearAction()

                guard RealtimeProtocol.bool(response["ok"]) != false else {
                    let reason = (response["error"] as? String) ?? (response["message"] as? String) ?? "grant-fish-xp recusado"
                    if isMissingFishingBait(reason) {
                        if let fresh = await fetchFishingInventorySnapshot() {
                            lastFishingInventory = fresh
                        }
                        reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • \(fishingBait.displayName) indisponível"))
                        reporter(.log("🛑 \(fishingBait.displayName) não foi aceita/está sem estoque • pesca encerrada sem repetir grants"))
                        throw EngineError.missingFishingBait(fishingBait.displayName)
                    } else if isFishActionStale(reason) {
                        fishingStats.staleRejects += 1
                        quarantineFishTarget(target)
                        reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • fish_action_stale"))
                        reporter(.log("⚠️ fish_action_stale #\(fishingStats.staleRejects) • conferindo inventário e ressincronizando Pond"))
                        await verifyFishingInventoryAfterStale()
                        try await recoverFishingAfterStale(stand: pondStand)
                    } else {
                        reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • \(reason)"))
                        try await sleep(FishingRecoveryPolicy.staleRecoveryMS)
                    }
                    continue
                }

                successes += 1
                fishingStats.catches += 1
                recordFishTargetSuccess(target)
                updateFishingInventory(fromGrant: response)
                reporter(.success(nil))
                reporter(.log("✅ Peixe #\(fishNumber) confirmado • \(successes)/\(goal) • \(targetLabel)"))

                if successes < goal {
                    // Node v5.2 usa 4.8 s entre capturas para aguardar o próximo
                    // estado autoritativo e reduzir stale na ação seguinte.
                    try await sleep(FishingRecoveryPolicy.betweenCatchMS)
                }
            } catch {
                try? await clearAction()
                let reason = error.localizedDescription
                if isMissingFishingBait(reason) {
                    if let fresh = await fetchFishingInventorySnapshot() {
                        lastFishingInventory = fresh
                    }
                    reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • \(fishingBait.displayName) indisponível"))
                    reporter(.log("🛑 \(fishingBait.displayName) não foi aceita/está sem estoque • pesca encerrada sem repetir grants"))
                    throw EngineError.missingFishingBait(fishingBait.displayName)
                } else if isFishActionStale(reason) {
                    fishingStats.staleRejects += 1
                    quarantineFishTarget(target)
                    reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • confirmação falhou: fish_action_stale"))
                    reporter(.log("⚠️ fish_action_stale #\(fishingStats.staleRejects) • conferindo inventário e aguardando novo estado do spot"))
                    await verifyFishingInventoryAfterStale()
                    try await recoverFishingAfterStale(stand: pondStand)
                } else {
                    reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • confirmação falhou: \(reason)"))
                    try await sleep(FishingRecoveryPolicy.staleRecoveryMS)
                }
            }
        }

        reporter(.log(
            "📊 Pesca encerrada • peixes=\(fishingStats.catches)/\(goal) • tentativas=\(fishingStats.attempts) • stale=\(fishingStats.staleRejects) • stale evitado=\(fishingStats.staleAvoided) • no_bite=\(fishingStats.noBite) • rotações=\(fishingStats.spotChanged) • quarentenas=\(fishingStats.targetQuarantines)"
        ))
    }

    private func isFishActionStale(_ value: String) -> Bool {
        FishingRecoveryPolicy.isStale(value)
    }

    private func isMissingFishingBait(_ value: String) -> Bool {
        let normalized = value.lowercased().replacingOccurrences(of: " ", with: "_")
        return normalized.contains("missing_bait") || normalized.contains("no_bait")
    }

    private func recoverFishingAfterStale(stand: Position) async throws {
        try? await clearAction()
        position = stand
        position.y = 0.25
        try await sendPosition(moving: false)
        try await equip("tool_fishing_rod")
        reporter(.state(.recovering, "Ressincronizando pesca"))
        try await sleep(FishingRecoveryPolicy.staleRecoveryMS)
    }

    private func fetchFishingInventorySnapshot() async -> FishingInventorySnapshot? {
        do {
            let me = try await http.get("/api/auth/me")
            let backpack = (me["backpack"] as? [String: Any]) ?? ((me["player"] as? [String: Any])?["backpack"] as? [String: Any]) ?? [:]
            return FishingInventorySnapshot(
                fish: fishingResourceCount(backpack, key: "fish"),
                bait: fishingResourceCount(backpack, key: fishingBait.confirmedInventoryKey ?? ""),
                xp: fishingXP(from: me)
            )
        } catch {
            reporter(.diagnostic("[FISH] inventário pós-stale indisponível: \(error.localizedDescription)"))
            return nil
        }
    }

    private func verifyFishingInventoryAfterStale() async {
        guard let fresh = await fetchFishingInventorySnapshot() else { return }
        if fresh != lastFishingInventory {
            let xpText: String
            if let old = lastFishingInventory.xp, let new = fresh.xp {
                xpText = " • XP \(old)→\(new)"
            } else {
                xpText = ""
            }
            reporter(.log("🔎 Estado após stale • fish \(lastFishingInventory.fish)→\(fresh.fish) • bait \(lastFishingInventory.bait)→\(fresh.bait)\(xpText)"))
        }
        lastFishingInventory = fresh
    }

    private func updateFishingInventory(fromGrant response: [String: Any]) {
        if let backpack = response["backpack"] as? [String: Any] {
            lastFishingInventory.fish = fishingResourceCount(backpack, key: "fish")
            lastFishingInventory.bait = fishingResourceCount(backpack, key: fishingBait.confirmedInventoryKey ?? "")
        }
        if let xp = fishingXP(from: response) { lastFishingInventory.xp = xp }
    }

    private func fishingResourceCount(_ backpack: [String: Any], key: String) -> Int {
        let flat = max(0, RealtimeProtocol.int(backpack[key]) ?? 0)
        let inv = max(0, slotCounts(backpack["invSlots"])[key] ?? 0)
        let hotbar = max(0, slotCounts(backpack["hotbar"])[key] ?? 0)
        // Baits não fazem parte dos 13 counters enviados em `resources` pela
        // baseline v5.2. Portanto um flat 0 não pode esconder bait recém-retirada
        // do banco e já confirmada nos slots.
        return max(flat, inv + hotbar)
    }

    private func fishingXP(from object: [String: Any]) -> Int? {
        if let xp = object["xp"] as? [String: Any], let value = RealtimeProtocol.int(xp["fishing"]) { return value }
        if let player = object["player"] as? [String: Any], let xp = player["xp"] as? [String: Any], let value = RealtimeProtocol.int(xp["fishing"]) { return value }
        return nil
    }

    private func ingestFishSpots(_ packet: [String: Any]) {
        if let packetRegion = packet["region"] as? String, !packetRegion.isEmpty, packetRegion.lowercased() != "pond" { return }
        guard let spots = packet["spots"] as? [[String: Any]] else { return }
        let now = nowMS
        var next: [Int: FishSpot] = [:]
        for item in spots {
            guard let slot = RealtimeProtocol.int(item["s"]), let c = RealtimeProtocol.int(item["c"]), let r = RealtimeProtocol.int(item["r"]), let ms = RealtimeProtocol.int(item["ms"]) else { continue }
            let previous = fishSpots[slot]
            let moved = previous == nil || previous?.c != c || previous?.r != r
            let generation = moved ? (previous?.generation ?? 0) + 1 : (previous?.generation ?? 0)
            if moved { clearOldFishHealth(slot: slot, keeping: generation) }
            next[slot] = FishSpot(slot: slot, c: c, r: r, expiresAt: now + Double(max(0, ms)), generation: generation)
        }
        fishSpots = next
        fishSnapshotSerial += 1

        let signature = next.values
            .sorted { $0.slot < $1.slot }
            .map { "#\($0.slot):\($0.c),\($0.r)" }
            .joined(separator: " • ")
        if !signature.isEmpty, signature != lastFishSpotSignature {
            lastFishSpotSignature = signature
            reporter(.log("🎣 Spots do servidor: \(signature)"))
        }

        reporter(.world(nodes: availableSeedCount(), mobs: max(chickens.count, wildMobs.count), serverRegion: "pond"))
    }

    private func ingestFishSpotMoved(_ packet: [String: Any]) {
        let source = (packet["spot"] as? [String: Any]) ?? (packet["to"] as? [String: Any]) ?? (packet["newSpot"] as? [String: Any]) ?? packet
        guard let slot = RealtimeProtocol.int(source["s"] ?? packet["s"]),
              let c = RealtimeProtocol.int(source["c"] ?? packet["c"]),
              let r = RealtimeProtocol.int(source["r"] ?? packet["r"]),
              let ms = RealtimeProtocol.int(source["ms"] ?? packet["ms"]) else { return }
        let previous = fishSpots[slot]
        let generation = (previous?.generation ?? 0) + 1
        clearOldFishHealth(slot: slot, keeping: generation)
        fishSpots[slot] = FishSpot(slot: slot, c: c, r: r, expiresAt: nowMS + Double(max(0, ms)), generation: generation)
        fishSnapshotSerial += 1
        if previous?.c != c || previous?.r != r {
            reporter(.log("🌀 Spot #\(slot) mudou para \(c),\(r)"))
        }
    }

    private func fishGenerationKey(slot: Int, generation: Int) -> String {
        "\(slot):\(generation)"
    }

    private func fishCellKey(_ target: FishTarget) -> String {
        "\(target.slot):\(target.generation):\(target.fc),\(target.fr)"
    }

    private func quarantineFishTarget(_ target: FishTarget) {
        let key = fishGenerationKey(slot: target.slot, generation: target.generation)
        if fishQuarantinedGenerations.insert(key).inserted {
            fishingStats.targetQuarantines += 1
        }
        reporter(.diagnostic("[FISH] geração em quarentena • slot=#\(target.slot) gen=\(target.generation) • aguardando MOVIMENTO real do servidor"))
    }

    private func recordFishTargetSuccess(_ target: FishTarget) {
        let key = fishCellKey(target)
        fishCellFailureStreak.removeValue(forKey: key)
        fishBlockedCells.remove(key)
    }

    private func recordFishTargetFailure(_ target: FishTarget, reason: String) {
        let key = fishCellKey(target)
        let next = (fishCellFailureStreak[key] ?? 0) + 1
        fishCellFailureStreak[key] = next
        guard next >= FishingRecoveryPolicy.maxFailuresPerCell else { return }

        if fishBlockedCells.insert(key).inserted {
            reporter(.diagnostic("[FISH] célula bloqueada nesta geração • #\(target.slot) gen=\(target.generation) cell=\(target.fc),\(target.fr) • motivo=\(reason)"))
        }

        let playerCol = Int(round(position.x + 19.5))
        let playerRow = Int(round(position.z + 19.5))
        let generationCells = [(target.c, target.r), (target.c + 1, target.r), (target.c, target.r + 1), (target.c + 1, target.r + 1)]
            .filter { fc, fr in hypot(Double(fc - playerCol), Double(fr - playerRow)) <= 6.5 }
            .map { fc, fr in "\(target.slot):\(target.generation):\(fc),\(fr)" }

        if !generationCells.isEmpty && generationCells.allSatisfy({ fishBlockedCells.contains($0) }) {
            quarantineFishTarget(target)
        }
    }

    private func clearOldFishHealth(slot: Int, keeping generation: Int) {
        // Um movimento autoritativo torna TODO conhecimento de saúde anterior
        // daquele slot obsoleto. Remova tudo do slot, inclusive se o servidor
        // omitiu o slot por um snapshot e a geração local voltou a um número já
        // usado; nunca carregue uma quarentena antiga para um spot realmente novo.
        let prefix = "\(slot):"
        fishQuarantinedGenerations = Set(fishQuarantinedGenerations.filter { !$0.hasPrefix(prefix) })
        fishCellFailureStreak = fishCellFailureStreak.filter { key, _ in !key.hasPrefix(prefix) }
        fishBlockedCells = Set(fishBlockedCells.filter { key in !key.hasPrefix(prefix) })
        _ = generation // mantém a assinatura explícita do evento que causou a limpeza
    }

    private func selectFishTarget() -> FishTarget? {
        let playerCol = Int(round(position.x + 19.5))
        let playerRow = Int(round(position.z + 19.5))
        let minTTL = FishingRecoveryPolicy.minStartTTLMS
        var candidates: [FishTarget] = []
        for spot in fishSpots.values where remainingMS(for: spot) >= minTTL {
            let generationKey = fishGenerationKey(slot: spot.slot, generation: spot.generation)
            if fishQuarantinedGenerations.contains(generationKey) { continue }
            for (fc, fr) in [(spot.c, spot.r), (spot.c + 1, spot.r), (spot.c, spot.r + 1), (spot.c + 1, spot.r + 1)] {
                let dist = hypot(Double(fc - playerCol), Double(fr - playerRow))
                guard dist <= 6.5 else { continue }
                let cellKey = "\(spot.slot):\(spot.generation):\(fc),\(fr)"
                guard !fishBlockedCells.contains(cellKey) else { continue }
                candidates.append(FishTarget(slot: spot.slot, c: spot.c, r: spot.r, fc: fc, fr: fr, generation: spot.generation, distance: dist, ttl: remainingMS(for: spot)))
            }
        }
        return candidates.sorted { a, b in
            if abs(a.ttl - b.ttl) > FishingRecoveryPolicy.ttlPriorityDifferenceMS { return a.ttl > b.ttl }
            return a.distance < b.distance
        }.first
    }

    private func fishTargetStillValid(_ target: FishTarget, generation: Int) -> Bool {
        guard let spot = fishSpots[target.slot] else { return false }
        return spot.generation == generation && spot.c == target.c && spot.r == target.r && remainingMS(for: spot) > 0
    }

    private func remainingMS(for spot: FishSpot?) -> Double {
        guard let spot else { return 0 }
        return max(0, spot.expiresAt - nowMS)
    }

    // MARK: - Chicken

    private func runChicken(goal: Int) async throws {
        if serverRegion?.lowercased() != "eldergrove" {
            try await setRegion("eldergrove", at: Position(x: 22.5, z: -3.5))
            _ = try await waitForRegion("eldergrove", timeoutMS: 6_000)
        }
        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }
        try await equip("wild_sword")

        let initialDeadline = nowMS + 15_000
        while chickens.isEmpty && nowMS < initialDeadline {
            reporter(.state(.searching, "Procurando galinhas"))
            try await sleep(250)
        }
        if chickens.isEmpty {
            reporter(.log("🔎 Nenhuma galinha próxima; indo ao centro de Whisperwood"))
            try await walk(to: Position(x: 0, z: 0), maxSeconds: 20, status: "Indo procurar galinhas no centro")
        }

        while successes < goal {
            try Task.checkCancellation()
            reporter(.state(.searching, "Procurando galinha"))
            guard var target = nearestMob(in: chickens.values) else {
                reporter(.target(nil))
                try await sleep(800)
                continue
            }

            reporter(.target("Chicken #\(target.index) • HP \(target.hp.map { String($0) } ?? "?")"))
            reporter(.attempt)
            try await moveAdjacent(to: target, gap: 0.65)
            try await equip("wild_sword")
            reporter(.state(.preparingAction, "Preparando ataque"))

            var acceptedHits = 0
            var confirmedKill = false
            var noAck = 0

            for swing in 1...12 {
                try Task.checkCancellation()
                guard let live = chickens[target.index], live.alive else {
                    confirmedKill = acceptedHits > 0
                    break
                }
                target = live
                reporter(.target("Chicken #\(live.index) • HP \(live.hp.map { String($0) } ?? "?")"))

                if distance(from: position, to: live.position) > 1.10 {
                    try await moveAdjacent(to: live, gap: 0.65)
                    try await equip("wild_sword")
                } else {
                    position.ry = atan2(live.position.x - position.x, live.position.z - position.z)
                    try await sendPosition(moving: false)
                }

                // v2.0: o card da Galinha não fica mais preso em “Movendo até o alvo”.
                // Cada golpe enviado recebe numeração local do alvo (Hit 1, Hit 2, ...),
                // sem alterar a confirmação autoritativa nem a métrica global de hits.
                reporter(.state(.acting, "Hit \(swing)"))

                let before = ambientHitSerial
                let sentAt = nowMS
                let data = try RealtimeProtocol.ambientHit(region: "eldergrove", index: live.index, lifeEpoch: lifeEpoch, position: position)
                try await socket.send(data)
                reporter(.hitSent)
                reporter(.state(.waitingResult, "Hit \(swing) • aguardando confirmação"))

                let ackDeadline = nowMS + 1_250
                var accepted = false
                while nowMS < ackDeadline {
                    try Task.checkCancellation()
                    if ambientHitSerial > before, lastAmbientHitIndex == live.index {
                        accepted = true
                        break
                    }
                    if chickens[live.index] == nil { break }
                    try await sleep(25)
                }

                // Em background o iOS pode coalescer o sleep de 25 ms e devolver
                // a Task já depois do deadline. Faça uma última leitura do estado
                // autoritativo antes de declarar timeout para não perder um ACK que
                // já chegou ao receive-loop enquanto esta Task estava suspensa.
                if !accepted, ambientHitSerial > before, lastAmbientHitIndex == live.index {
                    accepted = true
                }

                if accepted {
                    acceptedHits += 1
                    noAck = 0
                    reporter(.confirmedHit)
                    reporter(.state(.acting, "Hit \(swing) confirmado"))
                } else {
                    noAck += 1
                    reporter(.hitAckTimeout)
                    reporter(.state(.recovering, "Hit \(swing) sem confirmação"))
                }

                let nextSwing = sentAt + 2_050
                if nowMS < nextSwing { try await sleep(Int(nextSwing - nowMS)) }
                if let refreshed = chickens[live.index] {
                    reporter(.target("Chicken #\(refreshed.index) • HP \(refreshed.hp.map { String($0) } ?? "?")"))
                    if !refreshed.alive {
                        confirmedKill = acceptedHits > 0
                        break
                    }
                } else if acceptedHits > 0 {
                    confirmedKill = true
                    break
                }

                if noAck >= 3 { break }
            }

            if confirmedKill {
                successes += 1
                reporter(.kill)
                reporter(.success(nil))
                reporter(.state(.cooldown, "Galinha \(successes)/\(goal) concluída"))
                reporter(.log("✅ Galinha derrotada • \(successes)/\(goal) • hits confirmados=\(acceptedHits)"))
                try await sleep(450)
            } else {
                reporter(.failure("galinha não teve morte confirmada"))
                reporter(.state(.recovering, "Buscando próxima galinha"))
                try await sleep(900)
            }
        }
    }

    private func ingestChickenCollections(_ npcs: [String: Any]) {
        let collections = collectArrays(root: npcs, prefix: "npcs", depth: 0)
        let ranked = collections.map { collection -> (String, [[String: Any]], Int) in
            let path = collection.0
            let array = collection.1
            let p = path.lowercased()
            if p.range(of: "chick|hen|galinha|poultry", options: .regularExpression) != nil {
                return (path, array, 100)
            }
            let named = array.prefix(12).filter { mob in
                mobText(path: path, mob: mob).range(of: "chick|hen|galinha|poultry", options: .regularExpression) != nil
            }.count
            if named > 0 { return (path, array, 90 + min(named, 9)) }
            if p.hasSuffix(".wildmobs"), region == "eldergrove" { return (path, array, 20) }
            return (path, array, 0)
        }.filter { $0.2 > 0 }.sorted { a, b in
            if a.2 != b.2 { return a.2 > b.2 }
            return a.1.count > b.1.count
        }

        guard let best = ranked.first else { return }
        var next: [Int: LiveMob] = [:]
        for (index, mob) in best.1.enumerated() {
            guard mobAlive(mob), let pos = mobPosition(mob, offset: -30.5) else { continue }
            next[index] = LiveMob(index: index, type: "chicken", hp: mobLife(mob), position: pos, alive: true)
        }
        chickenCollectionPath = best.0
        chickens = next
        chickenSnapshotSerial += 1
    }

    // MARK: - Wilderness combat

    private func runWild(mode: ActivityMode, goal: Int) async throws {
        let targetType = mode == .dragon ? "dragon" : "zombie"

        // XP precisa de baseline antes da primeira kill para que o ganho por mob e
        // o acumulado da sessão sejam calculados sem adivinhação.
        await loadCombatXPBaseline()

        if safeStopReason != nil {
            safeStopCompleted = true
            reporter(.state(.cancelled, "STOP concluído em World seguro"))
            return
        }

        // RC3 / Node v5.2.1: toda sessão Wild passa pelo banco ANTES de entrar,
        // mesmo quando 6/6/6 já está carregado. Isso reduz o valor exposto se a
        // rede desaparecer completamente, situação em que nenhum comando pode ser
        // enviado até a conexão voltar. Depois, reponha somente se necessário.
        try await refreshPotionStock(logSummary: true)
        let initialResupplyReason = localPotionZeroReason(includeStrengthWhileBuffed: true)
        if let reason = initialResupplyReason {
            reporter(.log("🧪 Reposição necessária antes do combate • \(reason)"))
        }
        try await prepareWorldCombatSession(resupplyReason: initialResupplyReason)
        if safeStopReason != nil {
            safeStopCompleted = true
            reporter(.state(.cancelled, "Encerrado em World seguro"))
            return
        }

        try await enterWildernessFromWorld()
        try await refreshPotionStock(logSummary: true)

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        while successes < goal {
            try Task.checkCancellation()
            if safeStopReason != nil { break }
            guard playerHP > 0 else { throw EngineError.playerDead }

            // Se uma categoria chegou a zero entre encontros, faça UMA viagem ao
            // World, complete 6/6/6 e retorne pela mesma Presence.
            if let reason = try await confirmedPotionResupplyReason(includeStrengthWhileBuffed: true) {
                try await combatWorldServiceTrip(
                    drops: [:],
                    resupplyReason: reason,
                    returnToWild: true,
                    reasonLabel: "reposição entre combates"
                )
            }

            // v5.2.1: não iniciar um novo encontro já ferido. Isso é separado da
            // regra de "vitais baixos" durante o alvo, que na v2.4 é estritamente
            // HP<=50 E shield==0.
            try await prepareWildVitalsBeforeNewTarget(mode: mode)
            if let reason = try await confirmedPotionResupplyReason(includeStrengthWhileBuffed: true) {
                try await combatWorldServiceTrip(
                    drops: [:],
                    resupplyReason: reason,
                    returnToWild: true,
                    reasonLabel: "reposição após pré-combate"
                )
                continue
            }

            let zombieCount = wildMobs.values.filter { $0.alive && $0.type == "zombie" }.count
            let dragonCount = wildMobs.values.filter { $0.alive && $0.type == "dragon" }.count
            if zombieCount + dragonCount > 0 {
                let signature = "z\(zombieCount)-d\(dragonCount)"
                if signature != lastWildAvailabilitySignature {
                    lastWildAvailabilitySignature = signature
                    reporter(.log("👹 Wilderness • Zumbis disponíveis=\(zombieCount) • Dragões disponíveis=\(dragonCount)"))
                }
            }

            reporter(.state(.searching, "Procurando \(mode.displayName.lowercased())"))
            let candidates = wildMobs.values.filter { $0.alive && $0.type == targetType }
            guard var target = nearestMob(in: candidates) else {
                reporter(.target(nil))
                try await sleep(900)
                continue
            }

            let targetName = "\(mode.displayName) #\(target.index)"
            reporter(.target("\(targetName) • HP \(target.hp.map { String($0) } ?? "?")"))
            reporter(.log("🎯 \(targetName) selecionado • HP \(target.hp.map { String($0) } ?? "?") • disponíveis=\(candidates.count)"))

            if safeStopReason != nil { break }
            reporter(.state(.moving, "Movendo até \(targetName)"))
            try await moveWildAdjacent(to: target)
            if safeStopReason != nil { break }

            // v3.0: snapshots podem mudar enquanto caminhamos. Não gaste Strength
            // nem conte tentativa se outro jogador matou/despawnou o mob antes de
            // chegarmos em alcance.
            guard let approachedTarget = wildMobs[target.index],
                  approachedTarget.alive,
                  approachedTarget.type == targetType
            else {
                reporter(.target(nil))
                reporter(.state(.searching, "Alvo mudou durante a aproximação"))
                reporter(.log("ℹ️ \(targetName) ficou indisponível durante a aproximação • nenhuma poção/hit consumido • buscando outro alvo"))
                try await sleep(350)
                continue
            }
            target = approachedTarget
            reporter(.target("\(targetName) • HP \(target.hp.map { String($0) } ?? "?")"))
            reporter(.attempt)

            let targetXPStart = combatXPTotal

            // Baselines autoritativos usados somente para associar recompensa à kill atual.
            let backpackBefore = try? await http.backpackState()
            let groundBagBaseline = try? await http.groundBagIDs(shardID: shardNumber)
            let grantBaseline = wildGrantSerial

            try await ensureStrengthReady(targetName: targetName)

            // A ativação do buff também leva tempo. Se o mob desaparecer antes do
            // primeiro hit, registre churn de alvo, nunca uma falsa falha de kill.
            guard let preparedTarget = wildMobs[target.index],
                  preparedTarget.alive,
                  preparedTarget.type == targetType
            else {
                reporter(.target(nil))
                reporter(.state(.searching, "Alvo indisponível antes do primeiro hit"))
                reporter(.log("ℹ️ \(targetName) deixou de estar válido antes do primeiro hit • tentativa descartada sem falha"))
                try await sleep(350)
                continue
            }
            target = preparedTarget
            try await equip("wild_sword")
            reporter(.state(.acting, "Preparando ataque • \(targetName)"))

            var killed = false
            var acceptedHits = 0
            var lastTargetPosition = target.position
            var swing = 1
            var targetLostDuringRecovery = false
            var targetBecameUnavailable = false
            var safeStopInterruptedTarget = false
            var ackCadence = CombatAckCadence()
            var consecutiveAckTimeouts = 0

            while swing <= 30 {
                try Task.checkCancellation()
                if safeStopReason != nil {
                    safeStopInterruptedTarget = true
                    break
                }
                guard let live = wildMobs[target.index], live.alive, live.type == targetType else {
                    targetBecameUnavailable = true
                    break
                }
                target = live
                lastTargetPosition = live.position

                // Estoque zerou no meio do encontro: preserve o índice do mob,
                // espere o combat timer ficar seguro, reabasteça 6/6/6 no World e
                // tente reassumir EXATAMENTE o mesmo target ao voltar.
                if let reason = localPotionZeroReason(includeStrengthWhileBuffed: false) {
                    let resumed = try await resupplyLockedWildTarget(
                        mode: mode,
                        targetIndex: target.index,
                        targetName: targetName,
                        reason: reason
                    )
                    if !resumed {
                        targetLostDuringRecovery = true
                        break
                    }
                    continue
                }

                // v5.2.1 defensive layer: separate from the user's general
                // HP<=50 && shield==0 rule. Dragon (and the conservative Zombie
                // floor from the baseline) uses effective HP before a new swing,
                // especially when the next hit can finish the mob.
                if shouldUsePreventiveWildRecovery(mode: mode, targetHP: target.hp) {
                    let policy = WildCombatSafetyPolicy.policy(for: mode)
                    let effective = effectiveVitals
                    let finishing = (target.hp ?? Int.max) <= 25
                    let trigger = emergencyVitalDrop
                        ? "queda brusca de vitais"
                        : (finishing && effective < policy.finisherEffectiveHP ? "proteção antes do golpe final" : "reserva efetiva baixa")
                    reporter(.log("🛡️ Defesa preventiva • \(targetName) • \(trigger) • efetivo \(effective) • HP \(playerHP) + shield \(playerShield)"))
                    let resumed = try await recoverLockedWildTarget(
                        mode: mode,
                        targetIndex: target.index,
                        targetName: targetName,
                        preFightRecovery: true,
                        reasonLabel: trigger
                    )
                    emergencyVitalDrop = false
                    if !resumed {
                        targetLostDuringRecovery = true
                        break
                    }
                    continue
                }

                // v2.4: "vitais baixos" = HP <= 50 E shield == 0. Não recua por
                // shield 72/50 etc. Isso elimina o ciclo visto no Dragon da v2.3.
                if shouldRecoverVitals(mode: mode) {
                    let resumed = try await recoverLockedWildTarget(
                        mode: mode,
                        targetIndex: target.index,
                        targetName: targetName
                    )
                    if !resumed {
                        targetLostDuringRecovery = true
                        break
                    }
                    continue
                }

                // Strength v5.2: renova antes do próximo swing. Se já acabou e o
                // estoque também zerou, a próxima iteração aciona resupply mantendo target.
                if strengthBuffSeconds() <= 2, potionStock.strength > 0 {
                    _ = try await ensureStrengthReady(targetName: targetName, force: true)
                }

                guard let current = wildMobs[target.index], current.alive, current.type == targetType else {
                    targetBecameUnavailable = true
                    break
                }
                target = current
                lastTargetPosition = current.position

                if chebyshevDistance(to: current.position) > 1 {
                    reporter(.state(.moving, "Reposicionando • \(targetName)"))
                    try await moveWildAdjacent(to: current)
                }

                reporter(.target("\(targetName) • HP \(current.hp.map { String($0) } ?? "?")"))
                reporter(.state(.acting, "Hit \(swing) • \(targetName)"))
                position.ry = atan2(current.position.x - position.x, current.position.z - position.z)
                wildSwordSeq += 1
                try await sendPosition(moving: false, action: ["wss": wildSwordSeq, "eq": "wild_sword"])

                let ackBefore = wildHitSerial
                let wildSnapshotBefore = wildSnapshotSerial
                let hpBeforeSwing = current.hp
                let sentAt = nowMS
                let hit = try RealtimeProtocol.wildHit(region: "wild", index: current.index, lifeEpoch: lifeEpoch, position: position)
                try await socket.send(hit)
                reporter(.hitSent)
                reporter(.state(.waitingResult, "Hit \(swing) • aguardando confirmação"))

                let dx = position.x - current.position.x
                let dz = position.z - current.position.z
                let len = max(0.001, hypot(dx, dz))
                wildContactSeq += 1
                try await sendPosition(moving: false, action: ["wmb": wildContactSeq, "wmx": dx / len, "wmz": dz / len, "eq": "wild_sword"])

                let ackDeadline = nowMS + 1_450
                var ack: WildHitAck?
                while nowMS < ackDeadline {
                    try Task.checkCancellation()
                    if wildHitSerial > ackBefore, let candidate = lastWildHit, candidate.index == current.index {
                        ack = candidate
                        break
                    }
                    try await sleep(25)
                }

                // Mesma proteção aplicada à Galinha: timers do iOS podem voltar
                // depois do deadline em background. O receive-loop pode já ter
                // gravado o ACK; faça a leitura final antes de marcar miss.
                if ack == nil, wildHitSerial > ackBefore, let candidate = lastWildHit, candidate.index == current.index {
                    ack = candidate
                }

                // RC3.5: `wm_ev` pode sumir/atrasar em background enquanto snapshots
                // autoritativos continuam chegando. Antes de alimentar o circuit
                // breaker, correlacione uma atualização fresca do mesmo mob com
                // redução de HP. Mantemos métrica separada; não fingimos ACK.
                var stateCorrelatedHP: Int?
                if ack == nil {
                    let existingHP = wildMobs[current.index]?.hp
                    if CombatStateConfirmationPolicy.isStateCorrelatedHit(
                        beforeHP: hpBeforeSwing,
                        afterHP: existingHP,
                        snapshotAdvanced: wildSnapshotSerial > wildSnapshotBefore
                    ) {
                        stateCorrelatedHP = existingHP
                    } else {
                        let stateSerialBeforeWait = await wildStateEventGate.serial
                        _ = try await wildStateEventGate.wait(after: stateSerialBeforeWait, timeoutMS: 550)
                        let refreshedHP = wildMobs[current.index]?.hp
                        if CombatStateConfirmationPolicy.isStateCorrelatedHit(
                            beforeHP: hpBeforeSwing,
                            afterHP: refreshedHP,
                            snapshotAdvanced: wildSnapshotSerial > wildSnapshotBefore
                        ) {
                            stateCorrelatedHP = refreshedHP
                        }
                    }
                }

                let acknowledgedByServerState = stateCorrelatedHP != nil
                ackCadence.record(acknowledged: ack != nil || acknowledgedByServerState)

                if let ack {
                    consecutiveAckTimeouts = 0
                    acceptedHits += 1
                    reporter(.confirmedHit)
                    try await sleep(280)
                    let refreshedHP = wildMobs[current.index]?.hp
                    let hpLabel = ack.killedType == targetType ? "0" : (refreshedHP.map { String($0) } ?? "?")
                    reporter(.target("\(targetName) • HP \(hpLabel)"))
                    reporter(.state(.acting, "Hit \(swing) confirmado • \(targetName)"))
                    reporter(.log("⚔️ \(targetName) • Hit \(swing) confirmado • alvo HP \(hpLabel) • você HP \(playerHP) + shield \(playerShield) • força \(strengthBuffSeconds())s"))
                    if ack.killedType == targetType {
                        killed = true
                        break
                    }
                } else if let stateHP = stateCorrelatedHP {
                    consecutiveAckTimeouts = 0
                    acceptedHits += 1
                    reporter(.stateConfirmedHit)
                    let beforeLabel = hpBeforeSwing.map(String.init) ?? "?"
                    let hpLabel = String(stateHP)
                    reporter(.target("\(targetName) • HP \(hpLabel)"))
                    reporter(.state(.acting, "Hit \(swing) confirmado por estado • \(targetName)"))
                    reporter(.log("🛰️ \(targetName) • Hit \(swing) correlacionado por snapshot • HP \(beforeLabel) → \(hpLabel) • ACK específico ausente"))
                    if stateHP <= 0 {
                        // Snapshot HP=0 proves the target died, but without the
                        // bot-specific wm_ev/kill credit another player may have
                        // delivered the final blow. Keep the transport healthy,
                        // but never fabricate a bot kill from correlation alone.
                        targetBecameUnavailable = true
                        reporter(.diagnostic("[COMBAT] alvo chegou a HP 0 por estado sem kill ACK • kill não atribuída ao bot"))
                        break
                    }
                } else {
                    consecutiveAckTimeouts += 1
                    reporter(.hitAckTimeout)
                    reporter(.state(.recovering, "Hit \(swing) sem confirmação • \(targetName)"))
                    reporter(.log("⚠️ \(targetName) • Hit \(swing) sem ACK nem queda autoritativa de HP • próximo intervalo \(Int(ackCadence.cooldownMS))ms"))

                    // Quatro misses REAIS consecutivos (sem ACK e sem mudança
                    // correlacionável de HP) indicam Presence degradada.
                    if consecutiveAckTimeouts >= CombatAckCadence.circuitBreakerThreshold {
                        reporter(.diagnostic("[WARN] Presence degradada • \(consecutiveAckTimeouts) misses reais consecutivos em \(targetName)"))
                        reporter(.fatal("Presence degradada: \(consecutiveAckTimeouts) hits consecutivos sem ACK/estado"))
                        throw CancellationError()
                    }
                    try await sleep(280)
                }

                if playerHP <= 0 { throw EngineError.playerDead }

                if shouldRecoverVitals(mode: mode) {
                    let resumed = try await recoverLockedWildTarget(
                        mode: mode,
                        targetIndex: target.index,
                        targetName: targetName
                    )
                    if !resumed {
                        targetLostDuringRecovery = true
                        break
                    }
                }

                if safeStopReason != nil {
                    safeStopInterruptedTarget = true
                    break
                }

                let cadenceLeft = ackCadence.cooldownMS - (nowMS - sentAt)
                if cadenceLeft > 0 { try await sleep(Int(cadenceLeft)) }
                swing += 1
            }

            if killed {
                successes += 1
                reporter(.kill)
                reporter(.success(nil))

                // Expiração do iOS tem prioridade maior que XP/loot/recovery. A
                // kill já foi confirmada; não gaste a janela restante com trabalho
                // secundário. Vá direto ao caminho de saída de emergência.
                if emergencyBackgroundExitRequested {
                    reporter(.diagnostic("[BG] Kill confirmada durante expiração • XP/loot pós-kill adiados • priorizando World"))
                    break
                }

                // Node v5.2.1: sobreviver aos pacotes/danos atrasados vem ANTES
                // de XP, loot ou seleção do próximo mob. O teste real de Dragon
                // morreu ~5 s após a kill com HP81/shield0, exatamente esta janela.
                try await postKillSafety(mode: mode, defeatedMob: target, killPosition: lastTargetPosition)
                if emergencyBackgroundExitRequested {
                    reporter(.diagnostic("[BG] Expiração detectada durante pós-kill • pulando XP/loot e saindo imediatamente"))
                    break
                }
                reporter(.state(.cooldown, "\(mode.displayName) \(successes)/\(goal) concluído"))

                let xp = await resolveCombatXPAfterKill(mode: mode, before: targetXPStart)
                if emergencyBackgroundExitRequested {
                    reporter(.diagnostic("[BG] Expiração detectada após XP • loot ignorado para priorizar saída"))
                    break
                }
                let xpText: String
                if let xp {
                    xpText = " • XP +\(xp.gain) • XP sessão +\(xp.sessionGain) • Combat XP \(xp.total)"
                } else {
                    xpText = " • XP aguardando confirmação do servidor"
                }
                reporter(.log("✅ \(targetName) derrotado • \(successes)/\(goal) • hits aceitos=\(acceptedHits)\(xpText)"))

                let drops = try await collectWildDrops(
                    mode: mode,
                    targetNumber: target.index,
                    killPosition: lastTargetPosition,
                    backpackBefore: backpackBefore?.backpack,
                    groundBagBaseline: groundBagBaseline,
                    grantBaseline: grantBaseline
                )

                if safeStopReason != nil {
                    if emergencyBackgroundExitRequested {
                        reporter(.diagnostic("[BG] Expiração durante coleta de loot • depósito adiado • priorizando World"))
                        break
                    }
                    if !drops.bankable.isEmpty {
                        try await combatWorldServiceTrip(
                            drops: drops.bankable,
                            resupplyReason: nil,
                            returnToWild: false,
                            reasonLabel: "STOP seguro"
                        )
                    }
                    break
                }

                // Meta final: primeiro proteja drops bancáveis, respeitando o
                // combat timer de 10 s, e permaneça no World. Não reentra no Wild.
                if successes >= goal {
                    if !drops.bankable.isEmpty {
                        try await combatWorldServiceTrip(
                            drops: drops.bankable,
                            resupplyReason: nil,
                            returnToWild: false,
                            reasonLabel: "meta concluída"
                        )
                    }
                    break
                }

                let resupplyReason = try await confirmedPotionResupplyReason(includeStrengthWhileBuffed: true)
                if !drops.bankable.isEmpty || resupplyReason != nil {
                    try await combatWorldServiceTrip(
                        drops: drops.bankable,
                        resupplyReason: resupplyReason,
                        returnToWild: true,
                        reasonLabel: resupplyReason == nil ? "proteção de drop" : "reposição de poções"
                    )
                }

                try await sleep(mode == .dragon ? 1_200 : 900)
            } else if safeStopInterruptedTarget || safeStopReason != nil {
                reporter(.state(.recovering, "Saindo do combate com segurança"))
                reporter(.log("🛑 STOP recebido • nenhum novo ataque será iniciado • iniciando saída segura"))
                break
            } else if targetLostDuringRecovery {
                reporter(.state(.searching, "Alvo original não está mais disponível"))
                reporter(.log("ℹ️ \(targetName) desapareceu/morreu durante recovery/reposição; será buscado um novo alvo"))
                try await sleep(500)
            } else if targetBecameUnavailable {
                reporter(.target(nil))
                reporter(.state(.searching, "Alvo ficou indisponível durante o combate"))
                reporter(.log("ℹ️ \(targetName) desapareceu/morreu sem kill atribuível ao bot • não contabilizado como falha • buscando outro alvo"))
                try await sleep(500)
            } else {
                reporter(.failure("\(mode.displayName) sem kill autoritativa"))
                reporter(.state(.recovering, "Buscando outro \(mode.displayName.lowercased())"))
                try await sleep(1_000)
            }
        }

        // Nunca entregue a Presence para o AppStore fechar enquanto ainda existe
        // combat tag. Meta e STOP cooperativo passam pela mesma saída segura.
        if safeStopReason != nil {
            let reason = emergencyBackgroundExitRequested ? "expiração de background" : "STOP seguro"
            try await finalizeCombatSessionSafely(mode: mode, reason: reason)
            safeStopCompleted = true
        } else if successes >= goal {
            try await finalizeCombatSessionSafely(mode: mode, reason: "meta concluída")
        }
    }

    private func prepareWildVitalsBeforeNewTarget(mode: ActivityMode) async throws {
        let limits = wildCombatLimits(mode)
        guard playerHP > 0 else { throw EngineError.playerDead }
        guard playerHP < limits.preFightHP || playerShield < limits.preFightShield else { return }

        reporter(.state(.recovering, "Preparando vitais antes do próximo alvo"))
        reporter(.log("🛡️ Pré-combate • HP \(playerHP)/\(limits.preFightHP) • shield \(playerShield)/\(limits.preFightShield)"))
        try await moveToWildSafeCamp(reason: "pré-combate")
        try await recoverVitals(mode: mode, preFight: true)
    }

    private func shouldRecoverVitals(mode: ActivityMode) -> Bool {
        // Requisito v2.4: considerar vitais realmente baixos SOMENTE quando as
        // duas condições coexistirem. O parâmetro mode é mantido para a API do
        // combate, mas o gatilho é único para Zumbi/Dragão.
        _ = mode
        return playerHP <= 50 && playerShield <= 0
    }

    private var effectiveVitals: Int {
        max(0, playerHP) + max(0, playerShield)
    }

    private func shouldUsePreventiveWildRecovery(mode: ActivityMode, targetHP: Int?) -> Bool {
        let policy = WildCombatSafetyPolicy.policy(for: mode)
        let finishing = (targetHP ?? Int.max) <= 25
        return emergencyVitalDrop
            || effectiveVitals <= policy.emergencyEffectiveHP
            || (finishing && effectiveVitals < policy.finisherEffectiveHP)
    }

    /// Port direto da disciplina pós-kill da baseline combat-bot v5.2.1.
    /// Nada de XP/loot é processado antes deste método terminar: primeiro o
    /// personagem se afasta, observa dano atrasado e recupera em SAFE_CAMP se
    /// necessário. Não cria novos contatos/ataques.
    private func postKillSafety(mode: ActivityMode, defeatedMob: LiveMob, killPosition: Position) async throws {
        if emergencyBackgroundExitRequested { return }
        let policy = WildCombatSafetyPolicy.policy(for: mode)
        let killedAt = nowMS
        reporter(.state(.recovering, "Pós-kill • estabilizando combate"))

        // Disengage de um tile, escolhendo a célula cardinal válida que aumenta
        // a distância do mob morto. É a mesma geometria usada pelo Node.
        var disengageCompleted = true
        if let step = safeWildStepAway(from: killPosition) {
            reporter(.diagnostic("[COMBAT] pós-kill disengage → \(format(step.x)),\(format(step.z))"))
            do {
                try await walk(to: step, maxSeconds: mode == .dragon ? 2.4 : 3.5, status: "Pós-kill • afastando do alvo")
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                disengageCompleted = false
                reporter(.diagnostic("[COMBAT] disengage pós-kill não concluiu: \(error.localizedDescription)"))
            }
        }

        guard playerHP > 0 else { throw EngineError.playerDead }
        if emergencyBackgroundExitRequested { return }

        if mode == .dragon {
            // O histórico real contém burst autoritativo aproximadamente quatro
            // segundos depois da kill. Portanto não existe fast path de 1.1 s:
            // todo Dragão recua e permanece sem criar contato novo durante a
            // janela que cobre esse dano tardio.
            if emergencyBackgroundExitRequested { return }
            let suffix = disengageCompleted ? "" : " • disengage curto falhou"
            reporter(.log("🛡️ Pós-Dragão defensivo • recuando ao SAFE_CAMP antes de XP/loot\(suffix)"))
            try await moveToWildSafeCamp(reason: "pós-Dragão")
            if emergencyBackgroundExitRequested { return }
        }

        // Janela mínima/máxima da v5.2.1. Sem um campo de `pending contact` no
        // Swift atual, usamos exclusivamente o dano autoritativo recebido; não
        // inventamos ACK de contato.
        let settleStarted = nowMS
        let mustWaitUntil = mode == .dragon
            ? max(settleStarted, killedAt + WildCombatSafetyPolicy.dragonMinimumPostKillObservationMS)
            : settleStarted + 900
        let settleDeadline = mode == .dragon
            ? max(mustWaitUntil + WildCombatSafetyPolicy.dragonRequiredDamageQuietMS, killedAt + 12_000)
            : settleStarted + 3_200
        while nowMS < settleDeadline {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested { return }
            guard playerHP > 0 else { throw EngineError.playerDead }
            let quietFor = nowMS - lastCombatDamageAt
            let requiredQuiet = mode == .dragon
                ? WildCombatSafetyPolicy.dragonRequiredDamageQuietMS
                : policy.postKillDamageQuietMS
            if nowMS >= mustWaitUntil && quietFor >= requiredQuiet { break }
            try await sleep(100)
        }

        let recoveryFloor = mode == .dragon ? 180 : 145
        let needsRecovery = playerHP < policy.postKillSafeHP
            || playerShield < policy.postKillSafeShield
            || effectiveVitals < recoveryFloor

        if needsRecovery {
            if emergencyBackgroundExitRequested { return }
            reporter(.log("🧪 Pós-kill • estabilizando vitais • HP \(playerHP) • shield \(playerShield)"))
            let attempts = mode == .dragon ? 3 : 2
            for index in 0..<attempts {
                try Task.checkCancellation()
                if emergencyBackgroundExitRequested { return }
                guard playerHP > 0 else { throw EngineError.playerDead }
                do {
                    try await recoverVitals(mode: mode, preFight: true)
                    break
                } catch {
                    if index == attempts - 1 { throw error }
                    try await sleep(600)
                }
            }
        }

        if mode == .dragon {
            // v5.2.1 aumentou esta quiet window porque um burst real apareceu
            // cerca de 4 s após uma kill. Só avançamos para XP/loot quando os
            // vitais altos e 3 s sem dano autoritativo coexistirem.
            let quietDeadline = nowMS + 8_500
            while nowMS < quietDeadline {
                try Task.checkCancellation()
                if emergencyBackgroundExitRequested { return }
                guard playerHP > 0 else { throw EngineError.playerDead }
                let readyVitals = playerHP >= policy.postKillSafeHP && playerShield >= policy.postKillSafeShield
                let quietFor = nowMS - lastCombatDamageAt
                if readyVitals && quietFor >= 3_000 { break }
                try await sleep(120)
            }
            if emergencyBackgroundExitRequested { return }
            guard playerHP > 0 else { throw EngineError.playerDead }
            guard playerHP >= policy.postKillSafeHP && playerShield >= policy.postKillSafeShield else {
                throw EngineError.potionRecoveryFailed("pós-Dragão permaneceu inseguro • HP \(playerHP)/\(policy.postKillSafeHP) • shield \(playerShield)/\(policy.postKillSafeShield)")
            }
        }

        emergencyVitalDrop = false
        reporter(.log("✅ Pós-kill seguro • \(mode.displayName) • HP \(playerHP) + shield \(playerShield)"))
        _ = defeatedMob // mantém assinatura explícita do alvo validado para futuras métricas
    }

    private func safeWildStepAway(from mobPosition: Position) -> Position? {
        let currentCol = Int(round(position.x + 24.5))
        let currentRow = Int(round(position.z + 24.5))
        let mobCol = Int(round(mobPosition.x + 24.5))
        let mobRow = Int(round(mobPosition.z + 24.5))
        let blocked = Set(Self.wildBlockedTiles)

        let candidates = [
            (currentCol + 1, currentRow),
            (currentCol - 1, currentRow),
            (currentCol, currentRow + 1),
            (currentCol, currentRow - 1)
        ].filter { col, row in
            col >= 0 && col <= 49 && row >= 0 && row <= 49 && !blocked.contains("\(col),\(row)")
        }

        guard let best = candidates.max(by: { lhs, rhs in
            hypot(Double(lhs.0 - mobCol), Double(lhs.1 - mobRow))
                < hypot(Double(rhs.0 - mobCol), Double(rhs.1 - mobRow))
        }) else { return nil }

        return Position(x: Double(best.0) - 24.5, y: 0.25, z: Double(best.1) - 24.5)
    }

    /// Retorna true somente se o MESMO mob continua vivo e foi reassumido.
    /// `preFightRecovery` é usado pela camada defensiva v5.2.1 para recuperar
    /// até os thresholds altos sem alterar o gatilho geral HP<=50 && shield==0.
    private func recoverLockedWildTarget(
        mode: ActivityMode,
        targetIndex: Int,
        targetName: String,
        preFightRecovery: Bool = false,
        reasonLabel: String? = nil
    ) async throws -> Bool {
        guard playerHP > 0 else { throw EngineError.playerDead }

        reporter(.state(.recovering, "Recuando • mantendo \(targetName)"))
        let reasonText = reasonLabel ?? "vitais baixos"
        reporter(.log("🏃 \(reasonText) • mantendo \(targetName) travado • HP \(playerHP) + shield \(playerShield)"))
        try await moveToWildSafeCamp(reason: "\(targetName) • \(reasonText)")
        if safeStopReason != nil { return false }

        // Se alguma poção já está em zero, não entre num ciclo de recovery sem
        // suprimento. Saia de forma segura, reponha e tente o mesmo mob.
        if let reason = try await confirmedPotionResupplyReason(includeStrengthWhileBuffed: true) {
            return try await resupplyLockedWildTarget(
                mode: mode,
                targetIndex: targetIndex,
                targetName: targetName,
                reason: reason
            )
        }

        try await recoverVitals(mode: mode, preFight: preFightRecovery)
        if safeStopReason != nil { return false }

        // Uma das doses usadas no recovery pode ter zerado a categoria. Nesse
        // caso reabasteça antes de voltar a atacar o alvo travado.
        if let reason = try await confirmedPotionResupplyReason(includeStrengthWhileBuffed: true) {
            return try await resupplyLockedWildTarget(
                mode: mode,
                targetIndex: targetIndex,
                targetName: targetName,
                reason: reason
            )
        }

        guard let sameTarget = wildMobs[targetIndex], sameTarget.alive,
              sameTarget.type == (mode == .dragon ? "dragon" : "zombie")
        else {
            reporter(.target(nil))
            return false
        }

        reporter(.log("↩️ Retornando ao mesmo \(targetName) • HP alvo \(sameTarget.hp.map { String($0) } ?? "?") • você HP \(playerHP) + shield \(playerShield)"))
        reporter(.state(.moving, "Retornando ao mesmo \(targetName)"))
        try await moveWildAdjacent(to: sameTarget)
        try await equip("wild_sword")
        reporter(.target("\(targetName) • HP \(sameTarget.hp.map { String($0) } ?? "?")"))
        reporter(.state(.acting, "Combate retomado • \(targetName)"))
        return true
    }

    private func localPotionZeroReason(includeStrengthWhileBuffed: Bool) -> String? {
        var reasons: [String] = []
        if potionStock.health <= 0 { reasons.append("❤️ Vida") }
        if potionStock.shield <= 0 { reasons.append("🛡️ Escudo") }
        if potionStock.strength <= 0 && (includeStrengthWhileBuffed || strengthBuffSeconds() <= 2) {
            reasons.append("💪 Força")
        }
        return reasons.isEmpty ? nil : reasons.joined(separator: " + ")
    }

    /// Confirma o zero com /me antes de gastar uma viagem ao World. Isso evita
    /// sair do Wild por contador local desatualizado após ACK de poção.
    private func confirmedPotionResupplyReason(includeStrengthWhileBuffed: Bool) async throws -> String? {
        guard localPotionZeroReason(includeStrengthWhileBuffed: includeStrengthWhileBuffed) != nil else { return nil }
        try await refreshPotionStock(logSummary: false)
        return localPotionZeroReason(includeStrengthWhileBuffed: includeStrengthWhileBuffed)
    }

    /// Preparação BANK-FIRST da v5.2.1. Toda entrada inicial no Wild passa aqui:
    /// primeiro protege recursos comuns materializados em invSlots e só depois
    /// completa poções, quando necessário. Itens especiais nunca entram na allowlist.
    private func prepareWorldCombatSession(resupplyReason: String?) async throws {
        if serverRegion?.lowercased().hasPrefix("wild") == true || region.hasPrefix("wild") {
            throw EngineError.combatSupplyFailed("preparação de combate solicitada fora do World")
        }
        let bankPosition = Position(x: -24.0, z: -17.5)
        reporter(.state(.moving, "Protegendo inventário no banco"))
        try await walk(to: bankPosition, maxSeconds: 35, status: "🏦 Indo ao banco • BANK-FIRST")
        try await sleep(600)
        try await performCombatBankFirstSafety()
        if resupplyReason != nil {
            try await ensureCombatSupplies()
        } else {
            reporter(.log("🛡️ BANK-FIRST concluído • poções já suficientes • entrada no Wild liberada"))
        }
    }

    private func performCombatBankFirstSafety() async throws {
        reporter(.state(.syncing, "BANK-FIRST • protegendo recursos"))
        let result = try await http.depositAllBankFirstInventory()
        if result.confirmed.isEmpty && result.unresolved.isEmpty {
            reporter(.log("🏦 BANK-FIRST • itens bancáveis carregados já estão protegidos"))
            return
        }
        for (type, quantity) in result.confirmed.sorted(by: { $0.key < $1.key }) {
            reporter(.log("🏦 BANK-FIRST • \(quantity)x \(prettyItem(type)) → banco ✅"))
        }
        for detail in result.diagnostics {
            reporter(.diagnostic("[BANK] \(detail)"))
        }
        guard result.unresolved.isEmpty else {
            let detail = result.unresolved.sorted().map(prettyItem).joined(separator: ", ")
            reporter(.log("🛑 BANK-FIRST não confirmado • \(detail) • entrada na Wilderness bloqueada"))
            throw EngineError.bankDepositFailed(detail)
        }
    }

    /// Regra v5.2: um único zero dispara reposição completa 6/6/6. Primeiro
    /// reaproveita poções do banco; o restante é comprado no Alquimista usando os
    /// custos confirmados: vida=60 wood, shield=50 stone, força=40 coal.
    private func ensureCombatSupplies() async throws {
        reporter(.state(.syncing, "Reabastecendo poções 6/6/6"))

        // Materialize contador flat + retire poções prontas do banco antes de comprar.
        _ = try await http.ensurePotionLoadout(
            targets: [
                "potion_health": targetHealthPotions,
                "potion_shield": targetShieldPotions,
                "potion_strength": targetStrengthPotions
            ]
        )
        try await refreshPotionStock(logSummary: false)

        let snapshot = try await http.backpackState()
        let bp = snapshot.backpack
        let totalWood = http.totalResource(bp, type: "wood")
        let totalStone = http.totalResource(bp, type: "stone")
        let totalCoal = http.totalResource(bp, type: "coal")

        let needHealth = max(0, targetHealthPotions - potionStock.health)
        let needShield = max(0, targetShieldPotions - potionStock.shield)
        let needStrength = max(0, targetStrengthPotions - potionStock.strength)
        let requiredWood = needHealth * 60
        let requiredStone = needShield * 50
        let requiredCoal = needStrength * 40

        var shortages: [String] = []
        if totalWood < requiredWood { shortages.append("Vida: precisa \(requiredWood) wood, disponível \(totalWood)") }
        if totalStone < requiredStone { shortages.append("Escudo: precisa \(requiredStone) stone, disponível \(totalStone)") }
        if totalCoal < requiredCoal { shortages.append("Força: precisa \(requiredCoal) coal, disponível \(totalCoal)") }
        if !shortages.isEmpty {
            reporter(.log("🛑 Recursos insuficientes para repor 6/6/6 • \(shortages.joined(separator: " | "))"))
            throw EngineError.combatSupplyFailed(shortages.joined(separator: " | "))
        }

        let plans: [(String, Int)] = [
            ("potion_health", targetHealthPotions),
            ("potion_shield", targetShieldPotions),
            ("potion_strength", targetStrengthPotions)
        ]

        for (type, target) in plans {
            var guardCount = 0
            while currentPotionStock(type) < target && guardCount < target + 4 {
                try Task.checkCancellation()
                guardCount += 1
                let before = currentPotionStock(type)
                let response = try await http.alchemistPotionBuy(type: type, quantity: 1)
                guard RealtimeProtocol.bool(response["ok"]) != false, response["error"] == nil else {
                    throw EngineError.combatSupplyFailed("\(prettyItem(type)) recusada pelo Alquimista: \((response["error"] as? String) ?? "rejected")")
                }

                _ = try await http.ensurePotionLoadout(
                    targets: [
                        "potion_health": targetHealthPotions,
                        "potion_shield": targetShieldPotions,
                        "potion_strength": targetStrengthPotions
                    ]
                )
                try await refreshPotionStock(logSummary: false)
                let after = currentPotionStock(type)
                reporter(.log("🧪 Compra • \(prettyItem(type)) • \(before) → \(after)/\(target)"))
                if after <= before {
                    throw EngineError.combatSupplyFailed("\(prettyItem(type)) comprada, mas não ficou carregada; parada para evitar gasto em loop")
                }
            }
        }

        try await refreshPotionStock(logSummary: false)
        guard potionStock.health >= targetHealthPotions,
              potionStock.shield >= targetShieldPotions,
              potionStock.strength >= targetStrengthPotions
        else {
            throw EngineError.combatSupplyFailed("loadout incompleto • ❤️\(potionStock.health)/\(targetHealthPotions) 🛡️\(potionStock.shield)/\(targetShieldPotions) 💪\(potionStock.strength)/\(targetStrengthPotions)")
        }

        shieldMechanicUnavailable = false
        shieldConfirmFailureStreak = 0
        reporter(.log("🎒 Reposição concluída • ❤️ \(potionStock.health) • 🛡️ \(potionStock.shield) • 💪 \(potionStock.strength)"))

        // Não deduzimos custos por fórmula para exibir saldo: o valor mostrado
        // vem de um /me NOVO após todas as compras/materializações.
        let finalState = try await http.backpackState()
        let finalBP = finalState.backpack
        let remainingWood = http.totalResource(finalBP, type: "wood")
        let remainingStone = http.totalResource(finalBP, type: "stone")
        let remainingCoal = http.totalResource(finalBP, type: "coal")
        reporter(.log("📦 Recursos restantes • 🪵 Madeira \(remainingWood) • 🪨 Pedra \(remainingStone) • ⚫ Carvão \(remainingCoal)"))
    }

    /// Viagem única para banco/reposição. Antes de sair do Wild, sempre respeita
    /// o combat timer. Em meta final pode permanecer no World; durante a sessão
    /// retorna ao Wild usando a mesma Presence.
    private func combatWorldServiceTrip(
        drops: [String: Int],
        resupplyReason: String?,
        returnToWild: Bool,
        reasonLabel: String
    ) async throws {
        if region.hasPrefix("wild") || serverRegion?.hasPrefix("wild") == true {
            try await moveToWildSafeCamp(reason: reasonLabel)
            try await waitForCombatSafetyWindow(reason: reasonLabel)
            try await exitWildToWorld(reason: reasonLabel)
        }

        let bankPosition = Position(x: -24.0, z: -17.5)
        reporter(.state(.moving, "Indo ao banco"))
        try await walk(to: bankPosition, maxSeconds: 35, status: "🏦 Indo ao banco • protegendo itens")
        try await sleep(650)

        if !drops.isEmpty {
            reporter(.state(.syncing, "Depositando drops no banco"))
            let result = try await http.depositIntoBank(drops)
            for item in result.confirmed.sorted(by: { $0.key < $1.key }) {
                reporter(.log("🏦 \(item.value)x \(prettyItem(item.key)) → banco ✅"))
            }
            guard result.unresolved.isEmpty else {
                let detail = result.unresolved.sorted().map(prettyItem).joined(separator: ", ")
                throw EngineError.bankDepositFailed(detail)
            }
        }

        // Toda visita ao banco antes de uma possível reentrada no Wild volta a
        // aplicar a allowlist BANK-FIRST. Assim recursos comuns adquiridos durante
        // a sessão não permanecem expostos por acidente.
        try await performCombatBankFirstSafety()

        if let resupplyReason, safeStopReason == nil {
            reporter(.log("🧪 Reabastecendo no World • motivo=\(resupplyReason)"))
            try await ensureCombatSupplies()
        } else if safeStopReason != nil, resupplyReason != nil {
            reporter(.diagnostic("[STATE] safe-stop ativo • reposição cancelada no World"))
        }

        if safeStopReason != nil {
            reporter(.state(.cooldown, "World seguro • STOP em andamento"))
            reporter(.log("🏠 World confirmado durante STOP • retorno à Wilderness cancelado"))
            return
        }

        guard returnToWild else {
            reporter(.state(.cooldown, "World seguro • encerrando combate"))
            reporter(.log("🏠 World seguro confirmado • conexão poderá ser encerrada sem combat tag"))
            return
        }

        reporter(.log("↩️ Banco/reposição concluídos • retornando à Wilderness na mesma sessão"))
        try await enterWildernessFromWorld()
        try await refreshPotionStock(logSummary: true)
    }

    /// Reposição mid-fight com target lock. Ao voltar, procura o mesmo índice por
    /// alguns segundos; somente se ele tiver morrido/despawnado o seletor é liberado.
    private func resupplyLockedWildTarget(
        mode: ActivityMode,
        targetIndex: Int,
        targetName: String,
        reason: String
    ) async throws -> Bool {
        reporter(.state(.recovering, "Reabastecendo • mantendo \(targetName)"))
        reporter(.log("🧪 Estoque zerado • \(reason) • mantendo \(targetName) #\(targetIndex) travado"))
        try await moveToWildSafeCamp(reason: "reposição \(targetName)")
        if safeStopReason != nil { return false }
        try await combatWorldServiceTrip(
            drops: [:],
            resupplyReason: reason,
            returnToWild: true,
            reasonLabel: "reposição mantendo \(targetName)"
        )
        if safeStopReason != nil { return false }

        let expectedType = mode == .dragon ? "dragon" : "zombie"
        let deadline = nowMS + 5_000
        while nowMS < deadline {
            try Task.checkCancellation()
            if let same = wildMobs[targetIndex], same.alive, same.type == expectedType {
                reporter(.log("↩️ Mesmo \(targetName) ainda válido após reposição • HP \(same.hp.map { String($0) } ?? "?")"))
                reporter(.state(.moving, "Retornando ao mesmo \(targetName)"))
                try await moveWildAdjacent(to: same)
                try await equip("wild_sword")
                reporter(.target("\(targetName) • HP \(same.hp.map { String($0) } ?? "?")"))
                reporter(.state(.acting, "Combate retomado • \(targetName)"))
                return true
            }
            try await sleep(100)
        }

        reporter(.target(nil))
        reporter(.log("ℹ️ \(targetName) não está mais válido após reposição; liberando seleção de novo alvo"))
        return false
    }

    /// Aguarda 10 s desde o último hit confirmado/dano. Novo dano reinicia o
    /// countdown. Isso protege itens antes de Wild→World e antes do socket fechar.
    private func waitForCombatSafetyWindow(reason: String) async throws {
        reporter(.state(.cooldown, "Aguardando combat timer • \(reason)"))
        var lastShown = Int.max

        while true {
            try Task.checkCancellation()
            let elapsed = max(0, nowMS - lastCombatActivityAt)
            let remainingMS = max(0, combatLogoutWindowMS - elapsed)
            let remaining = Int(ceil(remainingMS / 1_000))

            if remaining != lastShown {
                lastShown = remaining
                if remaining > 0 {
                    reporter(.log("⏳ Combat timer • \(remaining)s • \(reason)"))
                } else {
                    reporter(.log("🟢 Combat timer • 0s • saída/desconexão segura liberada"))
                }
            }

            if remainingMS <= 0 { break }
            try await sleep(min(250, max(50, Int(remainingMS))))
        }
    }

    private func finalizeCombatSessionSafely(mode: ActivityMode, reason: String) async throws {
        if emergencyBackgroundExitRequested {
            try await finalizeEmergencyBackgroundExit(mode: mode)
            return
        }

        if region.hasPrefix("wild") || serverRegion?.hasPrefix("wild") == true {
            reporter(.state(.recovering, reason == "meta concluída" ? "Meta concluída • ficando em segurança" : "Saindo do combate com segurança"))
            let elapsed = max(0, nowMS - lastCombatActivityAt)
            let remaining = Int(ceil(max(0, combatLogoutWindowMS - elapsed) / 1_000))
            reporter(.log("🛡️ \(mode.displayName) • saída segura iniciada • motivo=\(reason) • combat timer \(remaining)s"))
            reporter(.log("⏳ Deslocamento até a área segura conta dentro da janela de combate de 10s"))
            try await moveToWildSafeCamp(reason: reason)
            try await waitForCombatSafetyWindow(reason: reason)
            try await exitWildToWorld(reason: reason)
        }
        reporter(.state(.cooldown, "World seguro • pronto para encerrar"))
        reporter(.log("🏠 World confirmado • combate encerrado em área segura • motivo=\(reason)"))
    }

    /// BGContinuedProcessingTask expiration has a much smaller grace window than
    /// a user STOP. Do not spend it on shield recovery, XP, loot or bank work.
    /// Move directly toward the Wild exit while the combat timer elapses, then
    /// request World with short repeated probes and require server confirmation.
    private func finalizeEmergencyBackgroundExit(mode: ActivityMode) async throws {
        if !(region.hasPrefix("wild") || serverRegion?.hasPrefix("wild") == true) {
            reporter(.state(.cooldown, "World seguro • expiração concluída"))
            reporter(.log("🏠 Expiração de background • personagem já estava fora da Wilderness"))
            return
        }

        reporter(.state(.recovering, "Background expirando • saída imediata para o World"))
        let elapsed = max(0, nowMS - lastCombatActivityAt)
        let remaining = Int(ceil(max(0, combatLogoutWindowMS - elapsed) / 1_000))
        reporter(.log("🚨 Expiração do iOS • \(mode.displayName) • prioridade absoluta=World • combat timer \(remaining)s"))
        reporter(.diagnostic("[BG] emergency-exit • recovery/XP/loot/reposição ignorados"))

        // Ir direto à borda, sem parada separada no SAFE_CAMP. A caminhada conta
        // dentro da janela de combate e termina praticamente no mesmo corredor.
        let exitEdge = Position(x: 0.5, z: 24.5)
        if hypot(position.x - exitEdge.x, position.z - exitEdge.z) > 0.8 {
            do {
                try await walk(to: exitEdge, maxSeconds: 18, status: "🚨 Saída de emergência para o World")
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                reporter(.diagnostic("[BG] emergency-exit • caminhada à borda não concluiu: \(error.localizedDescription)"))
            }
        }

        try await waitForCombatSafetyWindow(reason: "expiração de background")
        try await exitWildToWorld(reason: "expiração de background", emergency: true)
        reporter(.state(.cooldown, "World seguro • expiração concluída"))
        reporter(.log("🏠 World confirmado • expiração do iOS encerrada com saída de emergência"))
    }

    private func loadCombatXPBaseline() async {
        guard let playerID else {
            reporter(.diagnostic("[XP] playerId ausente; Combat XP usará apenas skill_xp se chegar"))
            return
        }
        do {
            if let xp = try await http.combatXP(playerID: playerID) {
                combatXPTotal = xp
                combatXPStart = xp
                reporter(.log("📈 Combat XP inicial • \(xp)"))
            }
        } catch {
            reporter(.diagnostic("[XP] player-stats inicial falhou: \(error.localizedDescription)"))
        }
    }

    private func resolveCombatXPAfterKill(mode: ActivityMode, before: Int?) async -> CombatXPResult? {
        let start = combatXPStart
        let expectedNormal = mode == .dragon ? 75 : 50
        let deadline = nowMS + 1_500

        if let before {
            while nowMS < deadline {
                try? Task.checkCancellation()
                if let current = combatXPTotal, current > before { break }
                try? await sleep(50)
            }
        } else {
            try? await sleep(250)
        }

        // Presence é preferido. Se o push atrasou/perdeu-se, player-stats confirma.
        if let playerID {
            if before == nil || combatXPTotal == nil || (combatXPTotal ?? 0) <= (before ?? -1) {
                if let fresh = try? await http.combatXP(playerID: playerID) {
                    combatXPTotal = fresh
                }
            }
        }

        guard let total = combatXPTotal else { return nil }
        let gain: Int
        if let before {
            gain = max(0, total - before)
        } else {
            gain = 0
        }
        let sessionGain = start.map { max(0, total - $0) } ?? gain

        if gain == 0 {
            reporter(.diagnostic("[XP] Kill confirmada, mas delta Combat XP ainda 0; esperado normal ~\(expectedNormal)"))
        }
        return CombatXPResult(gain: gain, sessionGain: sessionGain, total: total)
    }

    private func moveToWildSafeCamp(reason: String) async throws {
        // SAFE_CAMP da v5.2.1: col 25,row 47 -> world (0.5,22.5), faixa sem
        // spawn de mobs usada para recuperação defensiva.
        let safeCamp = Position(x: 0.5, z: 22.5)
        if hypot(position.x - safeCamp.x, position.z - safeCamp.z) > 0.8 {
            reporter(.state(.moving, "Recuando para área segura"))
            reporter(.log("🏕️ Área segura • motivo=\(reason) • destino 25,47"))
            try await walk(to: safeCamp, maxSeconds: 35, status: "🛡️ Recuando para área segura • \(reason)")
        }
        try await sendPosition(moving: false)
        try await sleep(450)
    }

    private func recoverVitals(mode: ActivityMode, preFight: Bool) async throws {
        let limits = wildCombatLimits(mode)
        let hpGoal = preFight ? limits.preFightHP : max(80, limits.potionHP)
        let shieldGoal = preFight ? limits.preFightShield : max(50, limits.shieldHP)
        let deadline = nowMS + Double(preFight ? (mode == .dragon ? 26_000 : 18_000) : 16_000)

        try await refreshPotionStock(logSummary: false)
        reporter(.log("🧪 Recuperação iniciada • meta HP \(hpGoal) • shield \(shieldGoal) • estoque ❤️\(potionStock.health) 🛡️\(potionStock.shield) 💪\(potionStock.strength)"))

        var usedAny = false
        while nowMS < deadline {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested {
                reporter(.diagnostic("[BG] Recovery de vitais interrompido • saída de emergência tem prioridade"))
                return
            }
            guard playerHP > 0 else { throw EngineError.playerDead }

            if playerHP >= hpGoal && playerShield >= shieldGoal {
                reporter(.log("✅ Recuperação confirmada • HP \(playerHP) • shield \(playerShield)"))
                try await equip("wild_sword")
                return
            }

            if playerHP < hpGoal {
                if potionStock.health > 0 {
                    let before = playerHP
                    if try await consumePotion("potion_health") {
                        usedAny = true
                        reporter(.log("❤️ Poção de vida aceita • HP antes \(before) • aguardando pvit/snapshot"))
                        try await driveHealthPotionTicks(goal: hpGoal)
                        continue
                    }
                } else if playerHP <= limits.retreatHP {
                    throw EngineError.potionRecoveryFailed("sem poção de vida com HP crítico \(playerHP)")
                }
            }

            if !shieldMechanicUnavailable, playerShield < shieldGoal {
                if potionStock.shield > 0 {
                    let before = playerShield
                    if try await consumePotion("potion_shield") {
                        usedAny = true
                        reporter(.log("🛡️ Poção de escudo aceita • shield antes \(before) • aguardando SPS + pvit"))
                        try await driveShieldPotionTicks(goal: shieldGoal, before: before)
                        if playerShield <= before {
                            shieldConfirmFailureStreak += 1
                            if shieldConfirmFailureStreak >= 2 {
                                shieldMechanicUnavailable = true
                                reporter(.log("⚠️ Shield sem confirmação em 2 doses; uso automático pausado para não desperdiçar poções"))
                            }
                        } else {
                            shieldConfirmFailureStreak = 0
                        }
                        continue
                    }
                }
            }

            // Sem uma ação de poção possível neste instante. Revalida /me uma vez
            // porque hotbar/Presence pode estar atrasado em relação ao estado persistido.
            if !usedAny {
                try await refreshPotionStock(logSummary: false)
            }

            if playerHP >= hpGoal && (playerShield >= shieldGoal || (shieldMechanicUnavailable && mode != .dragon)) {
                reporter(.log("✅ Recuperação suficiente • HP \(playerHP) • shield \(playerShield)"))
                try await equip("wild_sword")
                return
            }

            if potionStock.health <= 0 && (potionStock.shield <= 0 || shieldMechanicUnavailable) {
                let detail = "estoque insuficiente • HP \(playerHP)/\(hpGoal) • shield \(playerShield)/\(shieldGoal)"
                throw EngineError.potionRecoveryFailed(detail)
            }

            try await sleep(250)
        }

        if playerHP >= hpGoal && (playerShield >= shieldGoal || (shieldMechanicUnavailable && mode != .dragon)) {
            reporter(.log("✅ Recuperação concluída no limite • HP \(playerHP) • shield \(playerShield)"))
            try await equip("wild_sword")
            return
        }
        throw EngineError.potionRecoveryFailed("timeout • HP \(playerHP)/\(hpGoal) • shield \(playerShield)/\(shieldGoal)")
    }

    @discardableResult
    private func ensureStrengthReady(targetName: String, force: Bool = false) async throws -> Bool {
        let seconds = strengthBuffSeconds()
        if !force, seconds > 2 { return true }
        if force, seconds > 2 { return true }

        if !potionStockLoaded { try await refreshPotionStock(logSummary: false) }
        guard potionStock.strength > 0 else {
            if seconds <= 0 {
                reporter(.log("ℹ️ \(targetName) • sem poção de força carregada; combate segue sem buff"))
            }
            return false
        }

        if try await consumePotion("potion_strength") {
            strengthBuffUntil = nowMS + 30_000
            try await sendPosition(moving: false, action: ["stb": 30])
            reporter(.log("💪 Poção de força ativa • 30s • \(targetName) • restantes \(potionStock.strength)"))
            try await equip("wild_sword")
            return true
        }
        return false
    }

    private func strengthBuffSeconds() -> Int {
        guard strengthBuffUntil > nowMS else {
            strengthBuffUntil = 0
            return 0
        }
        return max(0, Int(ceil((strengthBuffUntil - nowMS) / 1_000)))
    }

    private func refreshPotionStock(logSummary: Bool) async throws {
        let state = try await http.backpackState()
        let bp = state.backpack
        potionPersistentCounts = [
            "potion_health": max(0, RealtimeProtocol.int(bp["potion_health"]) ?? 0),
            "potion_shield": max(0, RealtimeProtocol.int(bp["potion_shield"]) ?? 0),
            "potion_strength": max(0, RealtimeProtocol.int(bp["potion_strength"]) ?? 0)
        ]
        potionStock.health = carriedPotionCount(bp, type: "potion_health")
        potionStock.shield = carriedPotionCount(bp, type: "potion_shield")
        potionStock.strength = carriedPotionCount(bp, type: "potion_strength")
        potionStockLoaded = true
        if logSummary {
            reporter(.log("🎒 Poções carregadas • ❤️ \(potionStock.health) • 🛡️ \(potionStock.shield) • 💪 \(potionStock.strength)"))
        }
    }

    private func carriedPotionCount(_ backpack: [String: Any], type: String) -> Int {
        let flat = max(0, RealtimeProtocol.int(backpack[type]) ?? 0)
        guard flat > 0 else { return 0 }
        let slotted = potionSlotCount(backpack["hotbar"], type: type) + potionSlotCount(backpack["invSlots"], type: type)
        return slotted > 0 ? flat : 0
    }

    private func potionSlotCount(_ value: Any?, type: String) -> Int {
        guard let slots = value as? [Any] else { return 0 }
        return slots.reduce(0) { partial, raw in
            guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
            return partial + max(0, RealtimeProtocol.int(slot["n"]) ?? 0)
        }
    }

    private func decrementPotionStock(_ type: String) {
        switch type {
        case "potion_health": potionStock.health = max(0, potionStock.health - 1)
        case "potion_shield": potionStock.shield = max(0, potionStock.shield - 1)
        case "potion_strength": potionStock.strength = max(0, potionStock.strength - 1)
        default: break
        }
        if let current = potionPersistentCounts[type] {
            potionPersistentCounts[type] = max(0, current - 1)
        }
    }

    private func currentPotionStock(_ type: String) -> Int {
        switch type {
        case "potion_health": potionStock.health
        case "potion_shield": potionStock.shield
        case "potion_strength": potionStock.strength
        default: 0
        }
    }

    /// Presence primeiro: pos act=eat/eq=potion -> drink(seq,pt) -> drink_ack.
    /// Se a Presence disser not_carried mas /me provar estoque persistido, usa o
    /// mesmo fallback oficial da v5.2: POST /api/auth/consume-potion.
    private func consumePotion(_ type: String) async throws -> Bool {
        if !potionStockLoaded { try await refreshPotionStock(logSummary: false) }
        guard currentPotionStock(type) > 0 || (potionPersistentCounts[type] ?? 0) > 0 else { return false }

        let rateWait = max(0, 2_550.0 - (nowMS - lastPotionAt))
        if rateWait > 0 { try await sleep(Int(rateWait)) }
        lastPotionAt = nowMS

        if persistentPotionTransport {
            return try await consumePotionHTTP(type)
        }

        let previousEquipment = equipment
        drinkSeq += 1
        let seq = drinkSeq
        lastDrinkAck = nil

        do {
            equipment = type
            try await sendPosition(moving: false, action: ["act": "eat", "eq": type])
            let packet: [String: Any] = ["t": "drink", "seq": seq, "pt": type]
            let data = try JSONSerialization.data(withJSONObject: packet)
            try await socket.send(data)
        } catch {
            equipment = previousEquipment
            try? await sendPosition(moving: false)
            reporter(.diagnostic("[POTION] Presence send falhou para \(type): \(error.localizedDescription); tentando endpoint persistente"))
            return try await consumePotionHTTP(type)
        }

        let deadline = nowMS + 3_200
        var ack: PotionDrinkAck?
        while nowMS < deadline {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested { break }
            if let candidate = lastDrinkAck, candidate.seq == seq {
                ack = candidate
                break
            }
            try await sleep(25)
        }

        // Mesmo princípio dos hits: se o scheduler devolveu a Task depois do
        // deadline, o receive-loop pode já ter armazenado o drink_ack.
        if ack == nil, let candidate = lastDrinkAck, candidate.seq == seq {
            ack = candidate
        }

        equipment = previousEquipment
        try? await sendPosition(moving: false)

        if emergencyBackgroundExitRequested {
            reporter(.diagnostic("[BG] Consumo de poção interrompido por expiração • nenhuma tentativa HTTP adicional será feita"))
            return false
        }

        if let ack, ack.ok {
            potionAckTimeoutStreak[type] = 0
            decrementPotionStock(type)
            return true
        }

        if let ack, ack.error == "not_carried" {
            potionAckTimeoutStreak[type] = 0
            try await refreshPotionStock(logSummary: false)
            if (potionPersistentCounts[type] ?? 0) > 0 {
                persistentPotionTransport = true
                reporter(.diagnostic("[POTION] Presence hotbar dessincronizada; transporte persistente ativado"))
                return try await consumePotionHTTP(type)
            }
            return false
        }

        // ACK pode se perder depois de o servidor já aceitar a dose. Compare /me
        // antes de arriscar um fallback que consumiria duas poções.
        let before = currentPotionStock(type)
        if ack == nil {
            reporter(.potionAckTimeout)
            potionAckTimeoutStreak[type, default: 0] += 1
        } else {
            potionAckTimeoutStreak[type] = 0
        }

        try? await refreshPotionStock(logSummary: false)
        if currentPotionStock(type) < before || (potionPersistentCounts[type] ?? before) < before {
            potionAckTimeoutStreak[type] = 0
            reporter(.diagnostic("[POTION] ACK ausente, mas /me confirmou consumo de \(type)"))
            return true
        }

        // Duas janelas Presence consecutivas sem ACK e /me confirmando que nada
        // foi consumido são evidência suficiente de transporte instável. Como o
        // estado persistente acabou de confirmar ausência de consumo, o fallback
        // HTTP não duplica a dose. Mantém-se neste modo durante a conexão atual.
        if ack == nil, (potionAckTimeoutStreak[type] ?? 0) >= 2, (potionPersistentCounts[type] ?? 0) > 0 {
            persistentPotionTransport = true
            reporter(.diagnostic("[POTION] 2 timeouts de drink_ack para \(type) com /me inalterado • transporte persistente ativado"))
            reporter(.log("🔁 \(prettyItem(type)) • Presence instável; usando consumo persistente confirmado pelo servidor"))
            let consumed = try await consumePotionHTTP(type)
            if consumed { potionAckTimeoutStreak[type] = 0 }
            return consumed
        }

        reporter(.log("⚠️ \(prettyItem(type)) não teve consumo confirmado\(ack?.error.map { " • \($0)" } ?? "")"))
        return false
    }

    private func consumePotionHTTP(_ type: String) async throws -> Bool {
        do {
            let response = try await http.consumePotion(type)
            guard RealtimeProtocol.bool(response["ok"]) != false, response["error"] == nil else {
                reporter(.log("⚠️ \(prettyItem(type)) recusada pelo endpoint persistente"))
                return false
            }
            potionAckTimeoutStreak[type] = 0
            decrementPotionStock(type)
            if let bp = response["backpack"] as? [String: Any] {
                potionPersistentCounts[type] = max(0, RealtimeProtocol.int(bp[type]) ?? (potionPersistentCounts[type] ?? 0))
            }
            return true
        } catch {
            reporter(.log("⚠️ \(prettyItem(type)) falhou: \(error.localizedDescription)"))
            return false
        }
    }

    private func driveHealthPotionTicks(goal: Int) async throws {
        try await sleep(1_250)
        if emergencyBackgroundExitRequested { return }
        for _ in 0..<10 {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested { return }
            guard playerHP > 0 else { throw EngineError.playerDead }
            if playerHP >= goal || playerHP >= 100 { break }
            let before = playerHP
            let proposed = min(100, before + 10)
            try await sendPosition(moving: false, action: ["php": proposed])
            try await sleep(35)
            try await sendPosition(moving: false, action: ["php": proposed])

            let deadline = nowMS + 1_100
            while nowMS < deadline, playerHP <= before {
                try Task.checkCancellation()
                if emergencyBackgroundExitRequested { return }
                try await sleep(60)
            }
            reporter(.log("❤️ Tick de vida • \(before) → \(playerHP)\(playerHP <= before ? " (sem confirmação)" : "")"))
            if playerHP >= goal { break }
        }
    }

    private func driveShieldPotionTicks(goal: Int, before initialShield: Int) async throws {
        try await sleep(1_800)
        if emergencyBackgroundExitRequested { return }
        shieldPotionSeq += 1
        try await sendPosition(moving: false, action: ["sps": shieldPotionSeq])
        reporter(.diagnostic("[POTION] Shield SPS=\(shieldPotionSeq) enviado"))
        try await sleep(1_000)
        if emergencyBackgroundExitRequested { return }

        for _ in 0..<5 {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested { return }
            if playerShield >= goal || playerShield >= 100 { break }
            let before = playerShield
            let proposed = min(100, before + 10)
            try await sendPosition(moving: false, action: ["wsh": proposed])
            try await sleep(35)
            try await sendPosition(moving: false, action: ["wsh": proposed])

            let deadline = nowMS + 1_100
            while nowMS < deadline, playerShield <= before {
                try Task.checkCancellation()
                if emergencyBackgroundExitRequested { return }
                try await sleep(60)
            }
            reporter(.log("🛡️ Tick de escudo • \(before) → \(playerShield)\(playerShield <= before ? " (sem confirmação)" : "")"))
            if playerShield >= goal { break }
        }

        if playerShield <= initialShield {
            reporter(.diagnostic("[POTION] Shield não aumentou após SPS/ticks"))
        }
    }

    private func wildCombatLimits(_ mode: ActivityMode) -> WildCombatLimits {
        if mode == .dragon {
            return WildCombatLimits(potionHP: 88, shieldHP: 72, retreatHP: 68, preFightHP: 95, preFightShield: 90)
        }
        return WildCombatLimits(potionHP: 75, shieldHP: 45, retreatHP: 45, preFightHP: 90, preFightShield: 60)
    }

    private func enterWildernessFromWorld() async throws {
        // Paridade com combat-bot v5.2.1: a Wild Sword precisa estar equipada
        // no pacote World → Wilderness.
        try await equip("wild_sword")
        reporter(.log("⚔️ Wild Sword equipada"))

        if serverRegion?.lowercased() != "world" {
            try await setRegion("world", at: Position(x: 0.5, z: -29.5))
            guard try await waitForRegion("world", timeoutMS: 5_000) else {
                throw EngineError.regionNotConfirmed("world")
            }
        }

        reporter(.state(.moving, "Indo ao portal da Wilderness"))
        try await walk(to: Position(x: 0.5, z: -30.5), maxSeconds: 25, status: "🌍 Indo ao portal da Wilderness")
        try await sleep(200)

        reporter(.state(.syncing, "Entrando na Wilderness"))
        try await setRegion("wild", at: Position(x: 0.5, z: 23.5), extras: ["wblk": Self.wildBlockedTiles])
        guard try await waitForRegion("wild", timeoutMS: 14_000) else {
            throw EngineError.regionNotConfirmed("wild")
        }
        reporter(.log("✅ Wilderness confirmada via \(lastRegionConfirmationSource ?? "servidor")"))
    }

    private func exitWildToWorld(reason: String, emergency: Bool = false) async throws {
        reporter(.state(.moving, emergency ? "Saída de emergência para o World" : "Saindo da Wilderness para o World"))
        reporter(.log("🌍 Saída segura da Wilderness • motivo=\(reason)"))

        // v5.2: primeiro alcança a borda norte do Wild (tile 25,49 = 0.5,24.5).
        // Na expiração a função chamadora já iniciou esse deslocamento; não gaste
        // novamente toda a janela se a posição operacional já está na borda.
        let exitEdge = Position(x: 0.5, z: 24.5)
        if hypot(position.x - exitEdge.x, position.z - exitEdge.z) > 0.8 {
            try await walk(to: exitEdge, maxSeconds: emergency ? 18 : 35, status: emergency ? "🚨 Saída de emergência para o World" : "🌍 Saindo da Wilderness para o World")
        }

        let probes = [Position(x: 0.5, z: -29.5), Position(x: 0.5, z: -30.5)]
        // Paridade com a v5.2: saída normal também recebe três ciclos de probes.
        // Persistindo incerteza, AppStore reconecta no mesmo shard e usa snapshot
        // autoritativo em vez de declarar falha cega.
        let attempts = WorldExitPolicy.probeCycles
        let probeTimeout = emergency ? 2_500 : 5_000
        var confirmed = false

        for attempt in 1...attempts where !confirmed {
            for probe in probes {
                try Task.checkCancellation()
                try await setRegion("world", at: probe)
                if try await waitForRegion("world", timeoutMS: probeTimeout) {
                    confirmed = true
                    break
                }
                region = "wild"
            }
            if !confirmed, attempt < attempts {
                reporter(.diagnostic("[BG] World ainda não confirmou • probe de emergência \(attempt)/\(attempts)"))
                try await sleep(250)
            }
        }

        guard confirmed else { throw EngineError.worldExitUnconfirmed }
        wildMobs.removeAll()
        lastWildAvailabilitySignature = ""
        reporter(.log("✅ World confirmado • área segura"))
    }

    private func collectWildDrops(
        mode: ActivityMode,
        targetNumber: Int,
        killPosition: Position,
        backpackBefore: [String: Any]?,
        groundBagBaseline: Set<String>?,
        grantBaseline: Int
    ) async throws -> WildDropCollection {
        let mobName = "\(mode.displayName) #\(targetNumber)"

        // Primeiro procura bags novas, próximas da kill e pertencentes ao próprio jogador.
        // Nunca toca em bolsa preexistente de outro jogador.
        if let groundBagBaseline {
            do {
                let bags = try await http.groundBags(shardID: shardNumber)
                for bag in bags {
                    guard let id = groundBagID(bag), !groundBagBaseline.contains(id) else { continue }
                    guard groundBagOwnerMatches(bag), groundBagNear(bag, killPosition) else { continue }
                    let response = try await http.lootBag(id)
                    if RealtimeProtocol.bool(response["ok"]) == false {
                        reporter(.log("⚠️ \(mobName) • drop bag \(id) recusado pelo servidor"))
                    } else {
                        reporter(.log("🎁 \(mobName) • drop bag coletado"))
                    }
                }
            } catch {
                reporter(.diagnostic("[LOOT] ground-bags indisponível: \(error.localizedDescription)"))
            }
        } else {
            reporter(.diagnostic("[LOOT] baseline de ground-bags indisponível; nenhuma bolsa será coletada por segurança"))
        }

        // Dê tempo para /me refletir inv_grant/loot-bag. A diferença é calculada
        // somente contra o snapshot feito imediatamente antes deste combate.
        var latestBackpack: [String: Any]? = nil
        var diff = InventoryDiff.empty
        if let before = backpackBefore {
            for probe in 0..<6 {
                if probe > 0 { try await sleep(350) }
                if let state = try? await http.backpackState() {
                    latestBackpack = state.backpack
                    diff = inventoryDiff(before: before, after: state.backpack)
                    if !diff.all.isEmpty { break }
                }
            }
        } else if let state = try? await http.backpackState() {
            latestBackpack = state.backpack
        }

        // inv_grant é a segunda evidência autoritativa. Complementa tipos que
        // ainda não apareceram no snapshot HTTP, sem duplicar um drop já visto.
        let grants = recentWildGrants.filter { $0.serial > grantBaseline }
        for grant in grants where diff.all[grant.type] == nil {
            diff.add(type: grant.type, quantity: grant.quantity, location: .unknown)
        }

        guard !diff.all.isEmpty else {
            reporter(.diagnostic("[LOOT] \(mobName) sem drop confirmado"))
            return WildDropCollection(bankable: [:])
        }

        var bankable: [String: Int] = [:]
        for (type, quantity) in diff.all.sorted(by: { $0.key < $1.key }) {
            let location = classifyDrop(type: type, backpack: latestBackpack, diff: diff)
            switch location {
            case .mountProtected:
                reporter(.log("🎁 \(mobName) • \(quantity)x \(prettyItem(type)) • mount protegida; permanece no inventário ✅"))
            case .bankableInventory:
                bankable[type, default: 0] += quantity
                reporter(.log("🎁 \(mobName) • \(quantity)x \(prettyItem(type)) • drop bancável confirmado"))
            case .specialNonBankable:
                reporter(.log("🎁 \(mobName) • \(quantity)x \(prettyItem(type)) • slot especial não bancável; mantido"))
            case .unknown:
                reporter(.log("🎁 \(mobName) • \(quantity)x \(prettyItem(type)) • não confirmado como bancável; mantido"))
            }
        }

        return WildDropCollection(bankable: bankable)
    }

    private var shardNumber: Int {
        Int(shard.replacingOccurrences(of: "s", with: "")) ?? 4
    }

    private func wildGrantHint(_ packet: [String: Any]) -> (type: String, quantity: Int)? {
        if let grant = packet["grant"] as? String, !grant.isEmpty {
            return (grant, max(1, RealtimeProtocol.int(packet["n"] ?? packet["qty"] ?? packet["quantity"]) ?? 1))
        }
        if let grant = packet["grant"] as? [String: Any] {
            let type = (grant["t"] ?? grant["type"] ?? grant["itemType"] ?? grant["item"]) as? String
            if let type, !type.isEmpty {
                return (type, max(1, RealtimeProtocol.int(grant["n"] ?? grant["qty"] ?? grant["quantity"]) ?? 1))
            }
        }
        if let type = (packet["itemType"] ?? (packet["item"] as? [String: Any])?["t"] ?? (packet["item"] as? [String: Any])?["type"]) as? String, !type.isEmpty {
            return (type, max(1, RealtimeProtocol.int(packet["n"] ?? packet["qty"] ?? packet["quantity"] ?? (packet["item"] as? [String: Any])?["n"]) ?? 1))
        }
        return nil
    }

    private func groundBagID(_ bag: [String: Any]) -> String? {
        for key in ["id", "bagId", "bag_id", "_id"] {
            if let value = bag[key] as? String, !value.isEmpty { return value }
            if let value = RealtimeProtocol.int(bag[key]) { return String(value) }
        }
        return nil
    }

    private func groundBagOwnerMatches(_ bag: [String: Any]) -> Bool {
        let raw = bag["ownerId"] ?? bag["playerId"] ?? bag["pid"] ?? bag["by"] ?? (bag["owner"] as? [String: Any])?["id"]
        guard let owner = RealtimeProtocol.int(raw), let playerID else { return true }
        return owner == playerID
    }

    private func groundBagNear(_ bag: [String: Any], _ position: Position, radius: Double = 3.25) -> Bool {
        let nested = bag["position"] as? [String: Any]
        let x = RealtimeProtocol.double(bag["x"] ?? bag["px"] ?? nested?["x"])
        let z = RealtimeProtocol.double(bag["z"] ?? bag["pz"] ?? nested?["z"])
        guard let x, let z else { return false }
        return hypot(x - position.x, z - position.z) <= radius
    }

    private func inventoryDiff(before: [String: Any], after: [String: Any]) -> InventoryDiff {
        var result = InventoryDiff.empty
        for key in ["invSlots", "hotbar", "mountSlots", "petSlots", "cosmeticSlots", "furnitureSlots"] {
            let a = slotCounts(before[key])
            let b = slotCounts(after[key])
            let allTypes = Set(a.keys).union(b.keys)
            for type in allTypes {
                let gain = (b[type] ?? 0) - (a[type] ?? 0)
                guard gain > 0 else { continue }
                let location: DropLocation
                switch key {
                case "invSlots": location = .bankableInventory
                case "mountSlots": location = .mountProtected
                case "petSlots", "cosmeticSlots", "furnitureSlots": location = .specialNonBankable
                default: location = .unknown
                }
                result.add(type: type, quantity: gain, location: location)
            }
        }
        return result
    }

    private func slotCounts(_ value: Any?) -> [String: Int] {
        guard let slots = value as? [Any] else { return [:] }
        var out: [String: Int] = [:]
        for raw in slots {
            guard let slot = raw as? [String: Any], let type = slot["t"] as? String, !type.isEmpty else { continue }
            out[type, default: 0] += max(1, RealtimeProtocol.int(slot["n"]) ?? 1)
        }
        return out
    }

    private func classifyDrop(type: String, backpack: [String: Any]?, diff: InventoryDiff) -> DropLocation {
        if type.lowercased().hasPrefix("mount_") { return .mountProtected }
        if let known = diff.locationByType[type], known != .unknown { return known }
        guard let backpack else { return .unknown }
        if (slotCounts(backpack["mountSlots"])[type] ?? 0) > 0 { return .mountProtected }
        if (slotCounts(backpack["invSlots"])[type] ?? 0) > 0 { return .bankableInventory }
        for key in ["petSlots", "cosmeticSlots", "furnitureSlots"] {
            if (slotCounts(backpack[key])[type] ?? 0) > 0 { return .specialNonBankable }
        }
        return .unknown
    }

    private func prettyItem(_ type: String) -> String {
        type.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func ingestWildMobs(_ array: [[String: Any]]) async {
        guard region.hasPrefix("wild") || serverRegion?.hasPrefix("wild") == true else { return }
        var next: [Int: LiveMob] = [:]
        for (arrayIndex, mob) in array.enumerated() {
            let index = RealtimeProtocol.int(mob["i"]) ?? arrayIndex
            let type: String
            if let d = RealtimeProtocol.int(mob["d"]) {
                type = d == 1 ? "dragon" : "zombie"
            } else if let previous = wildMobs[index] {
                type = previous.type
            } else {
                continue
            }
            let hp = RealtimeProtocol.int(mob["lv"])
            guard let pos = mobPosition(mob, offset: -24.5) else { continue }
            next[index] = LiveMob(index: index, type: type, hp: hp, position: pos, alive: (hp ?? 1) > 0)
        }
        wildMobs = next
        wildSnapshotSerial += 1
        await wildStateEventGate.signal()
    }

    private func moveAdjacent(to mob: LiveMob, gap: Double) async throws {
        let dx = position.x - mob.position.x
        let dz = position.z - mob.position.z
        let len = hypot(dx, dz)
        let ux = len > 0.001 ? dx / len : 1
        let uz = len > 0.001 ? dz / len : 0
        let target = Position(x: mob.position.x + ux * gap, z: mob.position.z + uz * gap)
        try await walk(to: target, status: "Aproximando da Galinha #\(mob.index)")
        position.ry = atan2(mob.position.x - position.x, mob.position.z - position.z)
        try await sendPosition(moving: false)
        try await sleep(450)
    }

    private func moveWildAdjacent(to mob: LiveMob) async throws {
        if chebyshevDistance(to: mob.position) <= 1 { return }
        let dx = position.x - mob.position.x
        let dz = position.z - mob.position.z
        let len = max(0.001, hypot(dx, dz))
        let target = Position(x: mob.position.x + dx / len * 0.75, z: mob.position.z + dz / len * 0.75)
        let label = mob.type == "dragon" ? "Dragão" : (mob.type == "zombie" ? "Zumbi" : mob.type.capitalized)
        try await walk(to: target, maxSeconds: 30, status: "Aproximando do \(label) #\(mob.index)")
        position.ry = atan2(mob.position.x - position.x, mob.position.z - position.z)
        try await sendPosition(moving: false)
    }

    // MARK: - Parsing / helpers

    private func nearestMob<S: Sequence>(in sequence: S) -> LiveMob? where S.Element == LiveMob {
        sequence.filter(\.alive).min { a, b in
            distance(from: position, to: a.position) < distance(from: position, to: b.position)
        }
    }

    private func chebyshevDistance(to target: Position) -> Int {
        let colA = Int(round(position.x + 24.5))
        let rowA = Int(round(position.z + 24.5))
        let colB = Int(round(target.x + 24.5))
        let rowB = Int(round(target.z + 24.5))
        return max(abs(colA - colB), abs(rowA - rowB))
    }

    private func collectArrays(root: [String: Any], prefix: String, depth: Int) -> [(String, [[String: Any]])] {
        guard depth <= 3 else { return [] }
        var output: [(String, [[String: Any]])] = []
        for (key, value) in root {
            let path = "\(prefix).\(key)"
            if let array = value as? [[String: Any]] {
                output.append((path, array))
            } else if let dictionary = value as? [String: Any] {
                output.append(contentsOf: collectArrays(root: dictionary, prefix: path, depth: depth + 1))
            }
        }
        return output
    }

    private func mobText(path: String, mob: [String: Any]) -> String {
        var values = [path]
        for key in ["kind", "type", "name", "species", "mob", "model", "label", "t"] {
            if let value = mob[key] as? String { values.append(value) }
        }
        return values.joined(separator: " ").lowercased()
    }

    private func mobAlive(_ mob: [String: Any]) -> Bool {
        if RealtimeProtocol.bool(mob["dead"]) == true || RealtimeProtocol.bool(mob["alive"]) == false { return false }
        if let life = mobLife(mob) { return life > 0 }
        return true
    }

    private func mobLife(_ mob: [String: Any]) -> Int? {
        for key in ["lv", "hp", "life", "lives", "health"] {
            if let value = RealtimeProtocol.int(mob[key]) { return value }
        }
        return nil
    }

    private func mobPosition(_ mob: [String: Any], offset: Double) -> Position? {
        if let x = RealtimeProtocol.double(mob["x"]), let z = RealtimeProtocol.double(mob["z"]) {
            return Position(x: x, z: z, ry: RealtimeProtocol.double(mob["ry"]) ?? 0)
        }
        let col = RealtimeProtocol.double(mob["col"] ?? mob["c"])
        let row = RealtimeProtocol.double(mob["row"] ?? mob["r"])
        guard let col, let row else { return nil }
        return Position(x: col + offset, z: row + offset)
    }

    private func stringArray(_ value: Any?) -> [String] {
        if let values = value as? [String] {
            var seen = Set<String>()
            return values.filter { seen.insert($0).inserted }
        }
        if let values = value as? [Any] { return values.map { String(describing: $0) }.filter { !$0.isEmpty } }
        if let value { return [String(describing: value)] }
        return []
    }

    private func proofString(_ packet: [String: Any]) -> String {
        for key in ["actionProof", "action_proof", "proof", "ap"] {
            if let value = packet[key] as? String, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return value.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return ""
    }

    private func isSelf(_ value: Any?) -> Bool {
        guard let by = RealtimeProtocol.int(value) else { return false }
        guard let playerID else { return false }
        return by == playerID
    }

    private var nowMS: Double { Date().timeIntervalSince1970 * 1_000 }

    private func distance(from a: Position, to b: Position) -> Double {
        hypot(a.x - b.x, a.z - b.z)
    }

    private func format(_ value: Double) -> String { String(format: "%.2f", value) }

    private func prettyRegion(_ value: String) -> String {
        switch value.lowercased() {
        case "eldergrove": return "Whisperwood"
        case "frostmere": return "Frostmere"
        case "pond": return "The Pond"
        case "wild": return "Wilderness"
        default: return value.capitalized
        }
    }

    private func sleep(_ milliseconds: Int) async throws {
        try Task.checkCancellation()
        try await Task.sleep(nanoseconds: UInt64(max(0, milliseconds)) * 1_000_000)
        try Task.checkCancellation()
    }

    private static let mineY1 = [0.00629560793392864, 0.02224276186607366, 0.03662646321599944, 0.03771608875383880, 0.03069865652012693, 0.01618712234202430, 0.00735788692206685, 0.00081763842931276]
    private static let mineY2 = [0.00766947679797140, 0.03015640266727820, 0.03882025634389390, 0.03647150992470300, 0.02445169554520240, 0.01522137744508880, 0.00196209347010380]
    private static let treeY1 = [0.00450896712899457, 0.01539204827607130, 0.02708118998628260, 0.04000636653457300, 0.04956577042048940, 0.04831809999893905, 0.03927627531081584, 0.02781287636392693, 0.01623708421983360, 0.00684757460640900, 0.00129550473512485, 0.00064396844236564]
    private static let treeY2 = [0.00663976698948520, 0.01859204306440910, 0.04408819025393710, 0.04611773644183903, 0.03339753631590325, 0.01585228047343873, 0.00639929747344103]
    private static let mineMP1 = [0.01771428570151329, 0.03792857142431395, 0.05796428569725582, 0.08728571427719933, 0.10660714285714286, 0.13549999999148504, 0.15417857142431393, 0.17592857141579898]
    private static let mineMP2 = [0.20549999999148505, 0.23346428571002825, 0.2490357142686844, 0.27735714284437046, 0.30524999999574254, 0.32310714285288544, 0.35599999998297016]

    private static let gatherSeeds: [GatherSeed] = [
        GatherSeed(kind: "rock", keys: ["0,30", "1,30"], position: Position(x: -22.5, z: 5.5, ry: -1.570796326795), targetKey: "1,30", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["0,31"], position: Position(x: -23.5, z: 6.5, ry: -1.570796326795), targetKey: "0,31", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["1,29"], position: Position(x: -22.5, z: 4.5, ry: -1.570796326795), targetKey: "1,29", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["1,34"], position: Position(x: -23.5, z: 10.5, ry: 3.14159265359), targetKey: "1,34", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["10,49"], position: Position(x: -15.5, z: 24.5, ry: 1.570796326795), targetKey: "10,49", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["12,46", "12,47"], position: Position(x: -12.5, z: 20.5, ry: 0), targetKey: "12,46", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["13,46", "13,47", "14,46", "14,47"], position: Position(x: -12.5, z: 21.5, ry: 1.570796326795), targetKey: "13,46", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["13,48"], position: Position(x: -11.5, z: 22.5, ry: 0), targetKey: "13,48", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["15,45", "15,46"], position: Position(x: -9.5, z: 19.5, ry: 0), targetKey: "15,45", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["16,36", "17,36"], position: Position(x: -6.5, z: 11.5, ry: -1.570796326795), targetKey: "17,36", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["19,37"], position: Position(x: -4.5, z: 12.5, ry: -1.570796326795), targetKey: "19,37", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["2,0", "3,0"], position: Position(x: -21.5, z: -25.5, ry: 0), targetKey: "3,0", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["21,43"], position: Position(x: -4.5, z: 18.5, ry: 1.570796326795), targetKey: "21,43", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["29,45", "30,45"], position: Position(x: 5.5, z: 19.5, ry: 0), targetKey: "30,45", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["31,44", "31,45", "32,44", "32,45"], position: Position(x: 7.5, z: 18.5, ry: 0), targetKey: "32,44", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["4,29"], position: Position(x: -20.5, z: 5.5, ry: 3.14159265359), targetKey: "4,29", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["4,30", "4,31", "5,30", "5,31"], position: Position(x: -21.5, z: 6.5, ry: 1.570796326795), targetKey: "4,31", hasCoal: false),
        GatherSeed(kind: "rock", keys: ["4,36", "5,36"], position: Position(x: -20.5, z: 10.5, ry: 0), targetKey: "4,36", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["4,48", "4,49", "5,48", "5,49"], position: Position(x: -20.5, z: 22.5, ry: 0), targetKey: "4,48", hasCoal: true),
        GatherSeed(kind: "rock", keys: ["8,5", "8,6"], position: Position(x: -16.5, z: -17.5, ry: 3.14159265359), targetKey: "8,6", hasCoal: true),
        GatherSeed(kind: "tree", keys: ["10,31"], position: Position(x: -14.5, z: 5.5, ry: 0), targetKey: "10,31", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["2,28"], position: Position(x: -21.5, z: 3.5, ry: -1.570796326795), targetKey: "2,28", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["20,40"], position: Position(x: -3.5, z: 15.5, ry: -1.570796326795), targetKey: "20,40", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["21,41"], position: Position(x: -2.5, z: 16.5, ry: -1.570796326795), targetKey: "21,41", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["24,41"], position: Position(x: 0.5, z: 16.5, ry: -1.570796326795), targetKey: "24,41", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["25,40"], position: Position(x: 0.5, z: 14.5, ry: 0), targetKey: "25,40", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["25,42"], position: Position(x: 0.5, z: 16.5, ry: 0), targetKey: "25,42", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["27,38"], position: Position(x: 1.5, z: 13.5, ry: 1.570796326795), targetKey: "27,38", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["28,41"], position: Position(x: 2.5, z: 16.5, ry: 1.570796326795), targetKey: "28,41", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["29,42"], position: Position(x: 3.5, z: 17.5, ry: 1.570796326795), targetKey: "29,42", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["3,26"], position: Position(x: -20.5, z: 1.5, ry: -1.570796326795), targetKey: "3,26", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["3,30"], position: Position(x: -20.5, z: 5.5, ry: -1.570796326795), targetKey: "3,30", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["30,43"], position: Position(x: 4.5, z: 18.5, ry: 1.570796326795), targetKey: "30,43", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["30,48"], position: Position(x: 5.5, z: 22.5, ry: 0), targetKey: "30,48", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["5,25"], position: Position(x: -18.5, z: 0.5, ry: -1.570796326795), targetKey: "5,25", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["5,26"], position: Position(x: -18.5, z: 1.5, ry: -1.570796326795), targetKey: "5,26", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["6,33"], position: Position(x: -18.5, z: 7.5, ry: 0), targetKey: "6,33", hasCoal: false),
        GatherSeed(kind: "tree", keys: ["9,28"], position: Position(x: -15.5, z: 2.5, ry: 0), targetKey: "9,28", hasCoal: false),
        // Frostmere: 32 iron-rock footprints from the deterministic map layout.
        // Iron remains wire kind `rock`; hasMetal is the authoritative subtype.
        GatherSeed(region: "frostmere", kind: "rock", keys: ["38,34"], position: Position(x: 17.5, z: 14.5, ry: 1.570796326795), targetKey: "38,34", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["2,30", "3,30"], position: Position(x: -17.5, z: 9.5, ry: 0.463647609001), targetKey: "2,30", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["11,15"], position: Position(x: -8.5, z: -5.5, ry: 0), targetKey: "11,15", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["11,23"], position: Position(x: -8.5, z: 2.5, ry: 0), targetKey: "11,23", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["34,28"], position: Position(x: 14.5, z: 7.5, ry: 0), targetKey: "34,28", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["9,14", "9,15", "10,14", "10,15"], position: Position(x: -10.5, z: -6.5, ry: 0.321750554397), targetKey: "9,14", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["34,26"], position: Position(x: 14.5, z: 5.5, ry: 0), targetKey: "34,26", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["4,9", "5,9"], position: Position(x: -15.5, z: -11.5, ry: 0.463647609001), targetKey: "4,9", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["7,4"], position: Position(x: -13.5, z: -15.5, ry: 1.570796326795), targetKey: "7,4", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["8,35"], position: Position(x: -11.5, z: 14.5, ry: 0), targetKey: "8,35", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["1,21"], position: Position(x: -18.5, z: 0.5, ry: 0), targetKey: "1,21", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["38,36"], position: Position(x: 18.5, z: 15.5, ry: 0), targetKey: "38,36", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["37,15"], position: Position(x: 17.5, z: -5.5, ry: 0), targetKey: "37,15", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["9,18"], position: Position(x: -10.5, z: -2.5, ry: 0), targetKey: "9,18", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["39,22"], position: Position(x: 18.5, z: 2.5, ry: 1.570796326795), targetKey: "39,22", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["33,9", "34,9"], position: Position(x: 13.5, z: -11.5, ry: 0.463647609001), targetKey: "33,9", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["31,36"], position: Position(x: 11.5, z: 15.5, ry: 0), targetKey: "31,36", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["33,29"], position: Position(x: 13.5, z: 8.5, ry: 0), targetKey: "33,29", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["12,2", "13,2"], position: Position(x: -7.5, z: -18.5, ry: 0.463647609001), targetKey: "12,2", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["5,5"], position: Position(x: -14.5, z: -15.5, ry: 0), targetKey: "5,5", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["2,36", "3,36"], position: Position(x: -16.5, z: 15.5, ry: -0.463647609001), targetKey: "2,36", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["1,0"], position: Position(x: -19.5, z: -19.5, ry: 1.570796326795), targetKey: "1,0", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["39,9"], position: Position(x: 19.5, z: -11.5, ry: 0), targetKey: "39,9", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["34,17"], position: Position(x: 14.5, z: -3.5, ry: 0), targetKey: "34,17", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["26,8"], position: Position(x: 6.5, z: -12.5, ry: 0), targetKey: "26,8", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["25,30", "25,31"], position: Position(x: 4.5, z: 10.5, ry: 1.107148717794), targetKey: "25,30", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["23,33"], position: Position(x: 3.5, z: 12.5, ry: 0), targetKey: "23,33", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["39,21"], position: Position(x: 19.5, z: 0.5, ry: 0), targetKey: "39,21", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["7,25"], position: Position(x: -13.5, z: 5.5, ry: 1.570796326795), targetKey: "7,25", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["30,30"], position: Position(x: 10.5, z: 9.5, ry: 0), targetKey: "30,30", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["4,18"], position: Position(x: -15.5, z: -2.5, ry: 0), targetKey: "4,18", hasCoal: false, hasMetal: true),
        GatherSeed(region: "frostmere", kind: "rock", keys: ["10,0"], position: Position(x: -10.5, z: -19.5, ry: 1.570796326795), targetKey: "10,0", hasCoal: false, hasMetal: true),
    ]

    private static let wildBlockedTiles: [String] = [
        "0,45", "49,45", "0,46", "49,46", "0,47", "49,47", "0,48", "49,48", "0,49", "49,49", "1,45", "2,45",
        "3,45", "4,45", "44,45", "45,45", "46,45", "47,45", "48,45", "42,4", "49,30", "8,39", "22,40", "30,25",
        "40,33", "5,25", "26,8", "2,23", "34,3", "37,21", "3,17", "16,14", "10,29", "25,38", "8,25", "46,31",
        "42,7", "30,38", "4,19", "20,19", "35,3", "17,6", "48,33", "40,5", "21,33", "19,42", "46,13", "35,18",
        "14,44", "33,36", "36,20", "35,12", "13,42", "1,27", "41,4", "40,30", "31,39", "7,37", "36,23", "38,1",
        "44,33", "7,2", "21,36", "16,24", "13,4", "1,2", "23,16", "17,30", "46,16", "49,15", "19,13", "14,37",
        "4,21", "7,4", "48,37", "2,14", "35,10", "16,29", "12,6", "15,32", "2,33", "6,0", "5,29", "10,34",
        "13,0", "9,9", "7,13", "32,40", "33,37", "15,26", "12,11", "14,6", "40,34", "7,11", "43,11", "33,21",
        "21,29", "18,38", "5,37", "17,18", "22,11", "2,24", "16,6", "32,27", "6,20", "20,1", "20,16", "29,8",
        "44,30", "45,32", "41,33", "38,43", "21,14", "35,16", "30,3", "41,14", "27,42", "41,7", "25,39", "7,12",
        "14,9", "5,41", "49,16", "8,36", "38,44", "41,11", "48,20", "41,13", "5,40", "8,42", "4,6", "15,17",
        "0,30", "17,26", "1,18", "49,35", "4,27", "9,1", "10,2", "30,33", "30,10", "45,5", "44,43", "23,22",
        "14,11", "22,43", "27,38", "5,19", "20,23", "44,15", "9,8", "26,15", "9,7", "2,21", "25,9", "48,6",
        "42,17", "4,10", "40,2", "2,30", "42,25", "20,5", "32,6", "13,37", "27,43", "44,21", "4,40", "19,20",
        "10,41", "44,8", "0,13", "22,39", "32,18", "18,1", "8,24", "45,34", "4,28", "20,33", "6,39", "13,26",
        "36,28", "6,13", "33,3", "12,13", "3,34", "13,28", "13,29", "14,28", "14,29", "13,21", "37,30", "15,39",
        "15,40", "16,39", "16,40", "44,2", "30,12", "30,13", "15,33", "46,44", "1,15", "19,24", "5,44", "21,12",
        "21,13", "38,21", "38,22", "37,11", "39,43", "30,18", "40,40", "41,40", "48,32", "42,9", "44,34", "46,34",
        "41,31", "4,30", "44,31", "9,3", "15,2", "15,3", "16,2", "16,3", "15,35", "6,42", "6,43", "24,13",
        "7,23", "47,15", "13,13", "13,14", "42,27", "42,28", "47,18", "47,19", "48,18", "48,19", "43,38", "44,38",
        "27,14", "27,15", "28,11", "28,12", "29,11", "29,12", "27,10", "11,37", "20,28", "36,14", "37,14", "12,9",
        "6,6", "6,7", "21,22", "21,23", "28,43", "31,19", "3,6", "14,3", "40,21", "28,9", "28,10", "29,9",
        "29,10", "27,34", "34,29", "34,30", "35,29", "35,30", "20,37", "24,9", "24,10", "16,4", "22,23", "22,24",
        "20,36", "43,17", "44,17", "13,35", "2,8", "32,39", "33,39", "37,42", "33,5", "31,38", "16,19", "4,11",
        "4,12", "5,11", "5,12", "45,19", "46,19", "34,17", "4,35", "49,37", "8,7", "32,33", "33,33", "7,30",
        "23,12", "40,7", "12,43", "39,8", "39,29",
    ]
}

private struct GatherSeed {
    let region: String
    let kind: String
    let keys: [String]
    let position: Position
    let targetKey: String
    let hasCoal: Bool
    let hasMetal: Bool

    init(
        region: String = "eldergrove",
        kind: String,
        keys: [String],
        position: Position,
        targetKey: String,
        hasCoal: Bool,
        hasMetal: Bool = false
    ) {
        self.region = region
        self.kind = kind
        self.keys = keys
        self.position = position
        self.targetKey = targetKey
        self.hasCoal = hasCoal
        self.hasMetal = hasMetal
    }

    var signature: String { "\(kind):\(keys.sorted().joined(separator: "|"))" }
}

private struct HarvestResult {
    let felled: Bool
    let h: Int
    let hm: Int
    let loot: String?
    let reason: String
    let accepted: Bool
    let proofMiss: Bool

    var pureProofMiss: Bool { !felled && !accepted && proofMiss }
    var recoverable: Bool { pureProofMiss || (!felled && accepted) }

    func merging(_ next: HarvestResult) -> HarvestResult {
        let mergedAccepted = accepted || next.accepted
        return HarvestResult(
            felled: felled || next.felled,
            h: max(h, next.h),
            hm: next.hm < 99 ? next.hm : hm,
            loot: next.loot ?? loot,
            reason: next.reason,
            accepted: mergedAccepted,
            proofMiss: !mergedAccepted && (proofMiss || next.proofMiss)
        )
    }
}

struct GatherRetryPolicy {
    private(set) var retryStreaks: [String: Int] = [:]
    private(set) var deferredUntil: [String: Double] = [:]

    let maxSameTargetRetries = 3
    let proofMissDeferMS: Double = 10_000
    let acceptedPartialDeferMS: Double = 1_200
    let realFailureCooldownMS: Double = 8_000
    let repeatedFailureDeferMS: Double = 10_000

    mutating func resetExpired(nowMS: Double) {
        deferredUntil = deferredUntil.filter { $0.value > nowMS }
    }

    func isEligible(signature: String, nowMS: Double) -> Bool {
        (deferredUntil[signature] ?? 0) <= nowMS
    }

    func hasRetryPriority(signature: String) -> Bool {
        (retryStreaks[signature] ?? 0) > 0
    }

    mutating func markSuccess(signature: String) {
        retryStreaks.removeValue(forKey: signature)
        deferredUntil.removeValue(forKey: signature)
    }

    mutating func deferProofMiss(signature: String, nowMS: Double) {
        retryStreaks.removeValue(forKey: signature)
        deferredUntil[signature] = nowMS + proofMissDeferMS
    }

    mutating func deferAcceptedPartial(signature: String, nowMS: Double) {
        retryStreaks[signature] = 1
        deferredUntil[signature] = nowMS + acceptedPartialDeferMS
    }

    @discardableResult
    mutating func markRealFailure(signature: String, nowMS: Double) -> Bool {
        let next = (retryStreaks[signature] ?? 0) + 1
        if next >= maxSameTargetRetries {
            retryStreaks.removeValue(forKey: signature)
            deferredUntil[signature] = nowMS + repeatedFailureDeferMS
            return true
        }
        retryStreaks[signature] = next
        deferredUntil[signature] = nowMS + realFailureCooldownMS
        return false
    }
}

private enum HarvestAck { case accepted, felled, timeout }

private struct FishSpot {
    let slot: Int
    let c: Int
    let r: Int
    let expiresAt: Double
    let generation: Int
}

private struct FishTarget {
    let slot: Int
    let c: Int
    let r: Int
    let fc: Int
    let fr: Int
    let generation: Int
    let distance: Double
    let ttl: Double
}

private struct FishBite {
    let serial: Int
    let fc: Int
    let fr: Int
    let ms: Int
    let at: Double
}

struct FishingRecoveryPolicy {
    static let minStartTTLMS: Double = 38_000
    static let maxFailuresPerCell = 2
    static let biteExpiryMarginMS = 4_500
    static let biteScheduleTimeoutMS: Double = 3_500
    static let betweenCatchMS = 4_800
    static let staleRecoveryMS = 4_500
    /// Paridade direta com fishing-bot.js v5.2: diferenças >5 s priorizam o
    /// spot com maior TTL antes da distância.
    static let ttlPriorityDifferenceMS: Double = 5_000

    static func isStale(_ text: String) -> Bool {
        text.range(of: "fish_action_stale", options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
}

private struct FishingSessionStats {
    var attempts = 0
    var catches = 0
    var staleRejects = 0
    var staleAvoided = 0
    var noBite = 0
    var spotChanged = 0
    var targetQuarantines = 0
}

private struct FishingInventorySnapshot: Equatable {
    var fish = 0
    var bait = 0
    var xp: Int?
}

private struct LiveMob {
    let index: Int
    let type: String
    let hp: Int?
    let position: Position
    let alive: Bool
}

private struct WildHitAck {
    let serial: Int
    let index: Int
    let killedType: String?
}

private struct PotionDrinkAck {
    let seq: Int
    let potion: String
    let ok: Bool
    let error: String?
}

private struct PotionStock {
    var health = 0
    var shield = 0
    var strength = 0
}

private struct CombatXPResult {
    let gain: Int
    let sessionGain: Int
    let total: Int
}

private struct WildCombatLimits {
    let potionHP: Int
    let shieldHP: Int
    let retreatHP: Int
    let preFightHP: Int
    let preFightShield: Int
}

private struct WildGrant {
    let serial: Int
    let type: String
    let quantity: Int
    let at: Double
}

private enum DropLocation: Equatable {
    case bankableInventory
    case mountProtected
    case specialNonBankable
    case unknown
}

private struct InventoryDiff {
    var all: [String: Int]
    var locationByType: [String: DropLocation]

    static let empty = InventoryDiff(all: [:], locationByType: [:])

    mutating func add(type: String, quantity: Int, location: DropLocation) {
        guard !type.isEmpty, quantity > 0 else { return }
        all[type, default: 0] += quantity
        if locationByType[type] == nil || locationByType[type] == .unknown {
            locationByType[type] = location
        }
    }
}

private struct WildDropCollection {
    let bankable: [String: Int]
}

private struct BackpackState {
    let stateSeq: Int
    let backpack: [String: Any]
}

private struct ItemLocationCounts {
    let carried: Int
    let bank: Int
}

private struct BankDepositResult {
    let confirmed: [String: Int]
    let unresolved: [String]
    let diagnostics: [String]
}

enum EngineError: LocalizedError {
    case movementTimeout
    case regionNotConfirmed(String)
    case worldExitUnconfirmed
    case playerDead
    case unsafeVitals
    case potionRecoveryFailed(String)
    case combatSupplyFailed(String)
    case bankDepositFailed(String)
    case missingRequiredItem(String)
    case gatherLoadoutNotReady(String)
    case gatherEndedBeforeGoal
    case missingFishingBait(String)
    case insufficientFishingBait(String, have: Int, need: Int)
    case unsupportedFishingBait(String)

    var errorDescription: String? {
        switch self {
        case .movementTimeout: return "Movimento excedeu o tempo limite"
        case .regionNotConfirmed(let region): return "O servidor não confirmou a região \(region)"
        case .worldExitUnconfirmed: return "Saída para World enviada, mas a confirmação autoritativa ficou incerta"
        case .playerDead: return "O personagem morreu"
        case .unsafeVitals: return "Combate interrompido por HP/Shield baixos"
        case .potionRecoveryFailed(let detail): return "Recuperação com poções falhou: \(detail)"
        case .combatSupplyFailed(let detail): return "Reposição de combate falhou: \(detail)"
        case .bankDepositFailed(let item): return "Recurso/item não pôde ser confirmado no banco: \(item)"
        case .missingRequiredItem(let item): return "Item obrigatório não encontrado no inventário/banco: \(item)"
        case .gatherLoadoutNotReady(let item): return "Preflight de ferramenta não materializou \(item) antes de entrar na região de coleta"
        case .gatherEndedBeforeGoal: return "Engine de coleta encerrou antes da meta após reconexão"
        case .missingFishingBait(let bait): return "Isca selecionada sem estoque: \(bait)"
        case .insufficientFishingBait(let bait, let have, let need): return "Isca insuficiente: \(bait) \(have)/\(need)"
        case .unsupportedFishingBait(let bait): return "Automação ainda não validada para \(bait)"
        }
    }
}

private struct KintaraHTTPClient {
    let cookie: String
    private let base = URL(string: "https://kintara.com")!

    func get(_ path: String) async throws -> [String: Any] {
        try await request(method: "GET", path: path, body: nil)
    }

    func post(_ path: String, body: [String: Any]) async throws -> [String: Any] {
        try await request(method: "POST", path: path, body: body)
    }

    func consumePotion(_ type: String) async throws -> [String: Any] {
        try await post("/api/auth/consume-potion", body: ["type": type])
    }

    func alchemistPotionBuy(type: String, quantity: Int = 1) async throws -> [String: Any] {
        try await post("/api/auth/alchemist-potion-buy", body: ["potionType": type, "qty": max(1, quantity)])
    }

    func combatXP(playerID: Int) async throws -> Int? {
        let response = try await get("/api/auth/player-stats?playerId=\(playerID)")
        if let xp = response["skillXp"] as? [String: Any], let value = RealtimeProtocol.int(xp["combat"]) {
            return max(0, value)
        }
        if let data = response["data"] as? [String: Any],
           let xp = data["skillXp"] as? [String: Any],
           let value = RealtimeProtocol.int(xp["combat"]) {
            return max(0, value)
        }
        return nil
    }

    func totalResource(_ backpack: [String: Any], type: String) -> Int {
        let carried = max(0, RealtimeProtocol.int(backpack[type]) ?? 0)
        return carried + slotCount(backpack["bankSlots"], type: type)
    }

    /// Replica ensurePotionLoadout da v5.2: materializa contadores flat sem slot
    /// e retira poções prontas do banco até a meta. Preserva todos os outros slots.
    @discardableResult
    func ensurePotionLoadout(targets: [String: Int]) async throws -> BackpackState {
        let state = try await backpackState()
        var backpack = state.backpack
        var hotbar = backpack["hotbar"] as? [Any] ?? Array(repeating: NSNull(), count: 6)
        var inv = backpack["invSlots"] as? [Any] ?? Array(repeating: NSNull(), count: 24)
        var bank = backpack["bankSlots"] as? [Any] ?? []
        var dirty = false

        func slotsCount(_ type: String) -> Int {
            func count(_ slots: [Any]) -> Int {
                slots.reduce(0) { partial, raw in
                    guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
                    return partial + max(0, RealtimeProtocol.int(slot["n"]) ?? 0)
                }
            }
            return count(hotbar) + count(inv)
        }

        func place(_ type: String, quantity: Int) -> Int {
            var left = max(0, quantity)
            guard left > 0 else { return 0 }

            func add(to slots: inout [Any]) {
                guard left > 0 else { return }
                if let existing = slots.firstIndex(where: { raw in
                    guard let slot = raw as? [String: Any] else { return false }
                    return slot["t"] as? String == type
                }) {
                    var slot = slots[existing] as? [String: Any] ?? ["t": type, "n": 0]
                    slot["n"] = max(0, RealtimeProtocol.int(slot["n"]) ?? 0) + left
                    slots[existing] = slot
                    left = 0
                    return
                }
                if let empty = slots.firstIndex(where: { raw in raw is NSNull || !(raw is [String: Any]) }) {
                    slots[empty] = ["t": type, "n": left]
                    left = 0
                }
            }

            add(to: &hotbar)
            add(to: &inv)
            return max(0, quantity - left)
        }

        for (type, targetRaw) in targets.sorted(by: { $0.key < $1.key }) {
            let target = max(0, targetRaw)
            var flat = max(0, RealtimeProtocol.int(backpack[type]) ?? 0)
            var slotted = slotsCount(type)
            var carried = flat > 0 && slotted > 0 ? flat : 0

            // Compra pode deixar apenas o contador flat. Materialize a parte ainda
            // sem slot, até a meta, antes de tocar no banco.
            let loose = max(0, flat - slotted)
            if loose > 0 && carried < target {
                let wanted = min(loose, target - carried)
                let placed = place(type, quantity: wanted)
                if placed > 0 {
                    dirty = true
                    slotted += placed
                    carried = min(flat, slotted)
                }
            }

            if carried >= target { continue }
            var need = target - carried

            for index in bank.indices where need > 0 {
                guard var slot = bank[index] as? [String: Any], slot["t"] as? String == type else { continue }
                let available = max(0, RealtimeProtocol.int(slot["n"]) ?? 0)
                guard available > 0 else { continue }

                let take = min(need, available)
                let placed = place(type, quantity: take)
                if placed <= 0 { break }

                let left = available - placed
                if left > 0 {
                    slot["n"] = left
                    bank[index] = slot
                } else {
                    bank[index] = NSNull()
                }
                flat += placed
                backpack[type] = flat
                carried += placed
                need -= placed
                dirty = true
            }
        }

        if dirty {
            backpack["hotbar"] = hotbar
            backpack["invSlots"] = inv
            backpack["bankSlots"] = bank
            _ = try await saveBackpack(backpack, baseSeq: state.stateSeq)
            return try await backpackState()
        }
        return state
    }

    func itemLocationCounts(type: String) async throws -> ItemLocationCounts {
        let state = try await backpackState()
        let hotbar = state.backpack["hotbar"] as? [Any] ?? []
        let inv = state.backpack["invSlots"] as? [Any] ?? []
        let bank = state.backpack["bankSlots"] as? [Any] ?? []
        return ItemLocationCounts(
            carried: InventoryLoadoutAllocator.carriedCount(type: type, hotbar: hotbar, inventory: inv),
            bank: slotCount(bank, type: type)
        )
    }

    /// Garante que um item necessário à próxima atividade esteja carregado.
    /// Usa o mesmo save-backpack já comprovado para poções/BANK-FIRST; não cria
    /// item e não altera bags especiais. Ferramentas com metadados são movidas
    /// como objeto inteiro. Stacks simples (ex.: bait) podem ser retirados
    /// parcialmente do banco até a quantidade solicitada.
    @discardableResult
    func ensureCarriedItem(type: String, quantity targetRaw: Int, preferHotbar: Bool) async throws -> Int {
        let target = max(1, targetRaw)
        let state = try await backpackState()
        var backpack = state.backpack
        var hotbar = backpack["hotbar"] as? [Any] ?? Array(repeating: NSNull(), count: 6)
        var inv = backpack["invSlots"] as? [Any] ?? Array(repeating: NSNull(), count: 24)
        var bank = backpack["bankSlots"] as? [Any] ?? []

        let before = InventoryLoadoutAllocator.carriedCount(type: type, hotbar: hotbar, inventory: inv)
        if before >= target { return before }

        let moved = InventoryLoadoutAllocator.withdraw(
            type: type,
            quantity: target,
            preferHotbar: preferHotbar,
            hotbar: &hotbar,
            inventory: &inv,
            bank: &bank
        )
        guard moved > 0 else { return before }

        backpack["hotbar"] = hotbar
        backpack["invSlots"] = inv
        backpack["bankSlots"] = bank
        if backpack[type] != nil {
            backpack[type] = max(0, RealtimeProtocol.int(backpack[type]) ?? 0) + moved
        }
        _ = try await saveBackpack(backpack, baseSeq: state.stateSeq)

        let fresh = try await backpackState()
        let freshHotbar = fresh.backpack["hotbar"] as? [Any] ?? []
        let freshInv = fresh.backpack["invSlots"] as? [Any] ?? []
        return InventoryLoadoutAllocator.carriedCount(type: type, hotbar: freshHotbar, inventory: freshInv)
    }

    func backpackState() async throws -> BackpackState {
        let state = try await get("/api/auth/me")
        guard let stateSeq = RealtimeProtocol.int(state["stateSeq"]), let backpack = state["backpack"] as? [String: Any] else {
            throw HTTPError.invalidState
        }
        return BackpackState(stateSeq: stateSeq, backpack: backpack)
    }

    func groundBags(shardID: Int) async throws -> [[String: Any]] {
        let any = try await requestAny(method: "GET", path: "/api/wild/ground-bags?shard=\(shardID)", body: nil)
        return normalizeGroundBags(any)
    }

    func groundBagIDs(shardID: Int) async throws -> Set<String> {
        let bags = try await groundBags(shardID: shardID)
        var ids = Set<String>()
        for bag in bags {
            for key in ["id", "bagId", "bag_id", "_id"] {
                if let value = bag[key] as? String, !value.isEmpty { ids.insert(value); break }
                if let value = RealtimeProtocol.int(bag[key]) { ids.insert(String(value)); break }
            }
        }
        return ids
    }

    func lootBag(_ bagID: String) async throws -> [String: Any] {
        try await post("/api/wild/loot-bag", body: ["bagId": bagID])
    }

    /// RC3.2 BANK-FIRST: protege todo item core materializado em invSlots/hotbar
    /// que não pertence às categorias especiais e não é necessário durante o
    /// combate. Mount/pet/cosmetic/furniture vivem em arrays separados e nunca
    /// são tocados. Potions/wild_sword permanecem carregados.
    func depositAllBankFirstInventory() async throws -> BankDepositResult {
        let state = try await backpackState()
        var wanted: [String: Int] = [:]

        for key in ["invSlots", "hotbar"] {
            guard let slots = state.backpack[key] as? [Any] else { continue }
            for raw in slots {
                guard let slot = raw as? [String: Any],
                      let type = slot["t"] as? String,
                      CombatBankFirstPolicy.shouldBankFirst(type: type, slot: slot)
                else { continue }
                wanted[type, default: 0] += CombatBankFirstPolicy.slotQuantity(slot)
            }
        }

        guard !wanted.isEmpty else {
            return BankDepositResult(confirmed: [:], unresolved: [], diagnostics: [])
        }

        // Um tipo por transação: se um item futuro realmente não for aceito pelo
        // banco, ele não impede que os demais recursos sejam protegidos e o log
        // identifica exatamente qual tipo falhou. A Wilderness continua fail-closed
        // enquanto qualquer item core candidato permanecer sem confirmação.
        var confirmed: [String: Int] = [:]
        var unresolved = Set<String>()
        var diagnostics: [String] = []
        for (type, quantity) in wanted.sorted(by: { $0.key < $1.key }) {
            do {
                let result = try await depositIntoBank([type: quantity], sourceKeys: ["invSlots", "hotbar"])
                for (key, value) in result.confirmed { confirmed[key, default: 0] += value }
                unresolved.formUnion(result.unresolved)
                diagnostics.append(contentsOf: result.diagnostics)
            } catch {
                unresolved.insert(type)
                diagnostics.append("\(type) • transação recusada/indisponível: \(error.localizedDescription)")
            }
        }
        return BankDepositResult(confirmed: confirmed, unresolved: Array(unresolved).sorted(), diagnostics: diagnostics)
    }

    func depositIntoBank(_ wanted: [String: Int]) async throws -> BankDepositResult {
        try await depositIntoBank(wanted, sourceKeys: ["invSlots"])
    }

    private func depositIntoBank(_ wanted: [String: Int], sourceKeys: [String]) async throws -> BankDepositResult {
        let state = try await backpackState()
        var backpack = state.backpack
        var sourceArrays: [String: [Any]] = [:]
        for key in sourceKeys { sourceArrays[key] = backpack[key] as? [Any] ?? [] }
        var bank = backpack["bankSlots"] as? [Any] ?? []

        var moved: [String: Int] = [:]
        var unresolved = Set<String>()
        var diagnostics: [String] = []
        var beforeCarried: [String: Int] = [:]
        var beforeBank: [String: Int] = [:]

        func countInSources(type: String, arrays: [String: [Any]]) -> Int {
            arrays.values.reduce(0) { partial, slots in
                partial + slots.reduce(0) { subtotal, raw in
                    guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return subtotal }
                    return subtotal + CombatBankFirstPolicy.slotQuantity(slot)
                }
            }
        }

        for (type, requestedRaw) in wanted.sorted(by: { $0.key < $1.key }) {
            let requested = max(0, requestedRaw)
            guard requested > 0 else { continue }
            beforeCarried[type] = countInSources(type: type, arrays: sourceArrays)
            beforeBank[type] = slotCount(bank, type: type)
            var remaining = requested

            for sourceKey in sourceKeys where remaining > 0 {
                guard var slots = sourceArrays[sourceKey] else { continue }

                for index in slots.indices where remaining > 0 {
                    guard var slot = slots[index] as? [String: Any],
                          slot["t"] as? String == type
                    else { continue }

                    let available = CombatBankFirstPolicy.slotQuantity(slot)
                    guard available > 0 else { continue }
                    let requestedFromSlot = min(available, remaining)
                    let placed = BankSlotAllocator.place(slot: slot, quantity: requestedFromSlot, into: &bank)
                    guard placed > 0 else { continue }

                    let left = available - placed
                    if left <= 0 {
                        slots[index] = NSNull()
                    } else if CombatBankFirstPolicy.isSimpleStack(slot) {
                        slot["n"] = left
                        slots[index] = slot
                    } else {
                        // Metadados não são fracionados. Este caminho só deve ocorrer
                        // para stack simples; se não, mantenha o objeto intacto.
                        slots[index] = slot
                        diagnostics.append("\(type): item com metadados não pôde ser fracionado")
                        continue
                    }

                    remaining -= placed
                    moved[type, default: 0] += placed
                }
                sourceArrays[sourceKey] = slots
            }

            if remaining > 0 { unresolved.insert(type) }
            let movedQty = moved[type] ?? 0
            if movedQty > 0, backpack[type] != nil {
                backpack[type] = max(0, (RealtimeProtocol.int(backpack[type]) ?? 0) - movedQty)
            }
        }

        for (key, slots) in sourceArrays { backpack[key] = slots }
        backpack["bankSlots"] = bank

        // Se o item atualmente selecionado no hotbar foi protegido, aponte o
        // índice para um slot ainda existente. Não inventa equipamento nem move
        // potions/wild_sword; apenas evita índice apontando para null.
        if sourceKeys.contains("hotbar"), let hotbar = sourceArrays["hotbar"] {
            let equipped = max(0, RealtimeProtocol.int(backpack["equippedHotbar"]) ?? 0)
            if equipped >= hotbar.count || hotbar[equipped] is NSNull || !(hotbar[equipped] is [String: Any]) {
                backpack["equippedHotbar"] = hotbar.indices.first(where: { hotbar[$0] is [String: Any] }) ?? 0
            }
        }

        if moved.values.reduce(0, +) > 0 {
            _ = try await saveBackpack(backpack, baseSeq: state.stateSeq)
        }

        let fresh = try await backpackState()
        let freshArrays: [String: [Any]] = Dictionary(uniqueKeysWithValues: sourceKeys.map {
            ($0, fresh.backpack[$0] as? [Any] ?? [])
        })
        var confirmed: [String: Int] = [:]

        for (type, expected) in moved.sorted(by: { $0.key < $1.key }) {
            let b0 = beforeBank[type] ?? 0
            let b1 = slotCount(fresh.backpack["bankSlots"], type: type)
            let c0 = beforeCarried[type] ?? 0
            let c1 = countInSources(type: type, arrays: freshArrays)
            let bankIncrease = max(0, b1 - b0)
            let carriedDecrease = max(0, c0 - c1)
            diagnostics.append("\(type) • solicitado=\(wanted[type] ?? expected) movido=\(expected) • banco \(b0)→\(b1) • carregado \(c0)→\(c1)")

            if bankIncrease >= expected && carriedDecrease >= expected {
                confirmed[type] = expected
            } else {
                unresolved.insert(type)
            }
        }

        return BankDepositResult(
            confirmed: confirmed,
            unresolved: Array(unresolved).sorted(),
            diagnostics: diagnostics
        )
    }

    private func saveBackpack(_ backpack: [String: Any], baseSeq: Int) async throws -> [String: Any] {
        let resourceKeys = ["wood", "stone", "coal", "metal", "gold", "fish", "cooked_fish_meat", "raw_chicken", "cooked_chicken", "potion_health", "potion_shield", "potion_strength", "potion_poison"]
        var resources: [String: Any] = [:]
        for key in resourceKeys { resources[key] = RealtimeProtocol.int(backpack[key]) ?? 0 }

        var body: [String: Any] = [
            "resources": resources,
            "baseSeq": baseSeq,
            "intentionalRemovals": []
        ]
        for key in ["invSlots", "hotbar", "mountSlots", "cosmeticSlots", "petSlots", "furnitureSlots", "bankSlots"] {
            body[key] = backpack[key] ?? []
        }
        body["equippedHotbar"] = backpack["equippedHotbar"] ?? 0
        for flag in ["mountDragonRiding", "mountWhaleRiding", "mountSpiderRiding", "mountWolfRiding", "mountTigerRiding", "mountUnicornRiding", "mountCrocodileRiding", "mountGiraffeRiding", "mountWoolyMammothRiding", "mountHarambeRiding", "mountTralaleroRiding"] {
            body[flag] = backpack[flag] ?? false
        }

        let response = try await post("/api/auth/save-backpack", body: body)
        guard RealtimeProtocol.bool(response["ok"]) != false else {
            throw HTTPError.server((response["error"] as? String) ?? "save-backpack recusado")
        }
        return response
    }

    private func slotCount(_ value: Any?, type: String) -> Int {
        guard let slots = value as? [Any] else { return 0 }
        return slots.reduce(0) { partial, raw in
            guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
            return partial + max(1, RealtimeProtocol.int(slot["n"]) ?? 1)
        }
    }

    private func normalizeGroundBags(_ any: Any) -> [[String: Any]] {
        if let bags = any as? [[String: Any]] { return bags }
        guard let object = any as? [String: Any] else { return [] }
        for key in ["bags", "groundBags", "items"] {
            if let bags = object[key] as? [[String: Any]] { return bags }
        }
        if let data = object["data"] as? [String: Any], let bags = data["bags"] as? [[String: Any]] { return bags }
        return []
    }

    func persistLoot(_ item: String, amount: Int) async throws -> Int? {
        let state = try await get("/api/auth/me")
        guard let stateSeq = RealtimeProtocol.int(state["stateSeq"]), var backpack = state["backpack"] as? [String: Any] else {
            throw HTTPError.invalidState
        }

        let current = RealtimeProtocol.int(backpack[item]) ?? 0
        backpack[item] = current + amount

        var slots = backpack["invSlots"] as? [Any] ?? []
        var updatedSlot = false
        for index in slots.indices {
            if var slot = slots[index] as? [String: Any], slot["t"] as? String == item {
                slot["n"] = (RealtimeProtocol.int(slot["n"]) ?? 0) + amount
                slots[index] = slot
                updatedSlot = true
                break
            }
        }
        if !updatedSlot, let empty = slots.firstIndex(where: { $0 is NSNull }) {
            slots[empty] = ["t": item, "n": amount]
        }
        backpack["invSlots"] = slots

        let resourceKeys = ["wood", "stone", "coal", "metal", "gold", "fish", "cooked_fish_meat", "raw_chicken", "cooked_chicken", "potion_health", "potion_shield", "potion_strength", "potion_poison"]
        var resources: [String: Any] = [:]
        for key in resourceKeys { resources[key] = RealtimeProtocol.int(backpack[key]) ?? 0 }

        var body: [String: Any] = [
            "resources": resources,
            "baseSeq": stateSeq,
            "intentionalRemovals": []
        ]
        for key in ["invSlots", "hotbar", "mountSlots", "cosmeticSlots", "petSlots", "furnitureSlots", "bankSlots"] {
            body[key] = backpack[key] ?? []
        }
        body["equippedHotbar"] = backpack["equippedHotbar"] ?? 0
        for flag in ["mountDragonRiding", "mountWhaleRiding", "mountSpiderRiding", "mountWolfRiding", "mountTigerRiding", "mountUnicornRiding", "mountCrocodileRiding", "mountGiraffeRiding", "mountWoolyMammothRiding", "mountHarambeRiding", "mountTralaleroRiding"] {
            body[flag] = backpack[flag] ?? false
        }

        let response = try await post("/api/auth/save-backpack", body: body)
        guard RealtimeProtocol.bool(response["ok"]) != false else {
            throw HTTPError.server((response["error"] as? String) ?? "save-backpack recusado")
        }
        if let confirmed = response["backpack"] as? [String: Any] {
            return RealtimeProtocol.int(confirmed[item])
        }
        let fresh = try await get("/api/auth/me")
        return (fresh["backpack"] as? [String: Any]).flatMap { RealtimeProtocol.int($0[item]) }
    }

    private func request(method: String, path: String, body: [String: Any]?) async throws -> [String: Any] {
        let any = try await requestAny(method: method, path: path, body: body)
        guard let object = any as? [String: Any] else { throw HTTPError.nonJSON(200) }
        return object
    }

    private func requestAny(method: String, path: String, body: [String: Any]?) async throws -> Any {
        guard let url = URL(string: path, relativeTo: base) else { throw HTTPError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 15
        if method == "GET", path.hasPrefix("/api/auth/me") {
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
            request.setValue("no-cache", forHTTPHeaderField: "Pragma")
        }
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw HTTPError.invalidResponse }
        let any = try JSONSerialization.jsonObject(with: data)
        if !(200...299).contains(http.statusCode) {
            if let object = any as? [String: Any] {
                throw HTTPError.server((object["error"] as? String) ?? (object["message"] as? String) ?? "HTTP \(http.statusCode)")
            }
            throw HTTPError.server("HTTP \(http.statusCode)")
        }
        return any
    }
}

private enum HTTPError: LocalizedError {
    case invalidURL
    case invalidResponse
    case nonJSON(Int)
    case invalidState
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "URL HTTP inválida"
        case .invalidResponse: return "Resposta HTTP inválida"
        case .nonJSON(let status): return "Resposta não JSON (HTTP \(status))"
        case .invalidState: return "Estado de inventário incompleto"
        case .server(let message): return message
        }
    }
}

private extension ActivityMode {
    var displayName: String {
        switch self {
        case .tree: return "Madeira"
        case .coal: return "Carvão"
        case .stone: return "Pedra"
        case .iron: return "Iron Ore"
        case .fishing: return "Pesca"
        case .chicken: return "Galinha"
        case .zombie: return "Zumbi"
        case .dragon: return "Dragão"
        }
    }
}
