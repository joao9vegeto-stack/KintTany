import Foundation
import AVFoundation
import SwiftUI
import UIKit
import BackgroundTasks

enum ActivityMode: String, CaseIterable, Codable, Identifiable {
    case tree, coal, stone, iron, silver, cacti, fishing, roastPit, blacksmith, chicken, zombie, dragon

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
        case .roastPit: "Roast Pit"
        case .blacksmith: "Frostmere Smith"
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
        case .roastPit: "Roast Pit"
        case .blacksmith: "Frostmere Smith"
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
        case .roastPit: "flame.fill"
        case .blacksmith: "hammer.fill"
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
        case .roastPit: .orange
        case .blacksmith: .gray
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
        false
    }

    /// v4.0: safe activities reuse the same proven same-shard Presence recovery
    /// instead of terminating when the realtime transport blips.
    var resumesAfterSafeRealtimeLoss: Bool {
        switch self {
        case .fishing, .roastPit, .blacksmith, .chicken:
            return true
        default:
            return false
        }
    }

    /// UI can be fully headless in background whenever the activity does not
    /// require live full-loot safety presentation.
    var supportsBackgroundHeadless: Bool {
        !requiresSafeExit
    }

    /// STOP waits for the in-flight server transaction to settle before teardown.
    var supportsAtomicStop: Bool {
        self == .fishing || self == .roastPit || self == .blacksmith
    }
}

enum ActivitySessionPolicy {
    static func freshStats(at date: Date = .now) -> ActivityStats {
        ActivityStats(startedAt: date)
    }
}

enum BackgroundRuntimePolicy {
    /// Build 127: once genuine audio runtime is alive, expiry of a system
    /// background lease is no longer a reason to terminate any KintTany mode.
    /// Full-loot protection remains owned by the activity engine itself.
    static func preservesExecution(mode _: ActivityMode, audioAlive: Bool) -> Bool {
        audioAlive
    }

    static func shouldRearmContinuedProcessing(
        hasActivity: Bool,
        hasContinuedTask: Bool,
        continuedTaskRequested: Bool,
        appIsActive: Bool,
        audioAlive: Bool
    ) -> Bool {
        hasActivity &&
        !hasContinuedTask &&
        !continuedTaskRequested &&
        appIsActive &&
        audioAlive
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
        case .roastPit: return "Assando no Roast Pit"
        case .blacksmith: return "Trabalhando no Frostmere Smith"
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

enum CharacterSkill: String, CaseIterable, Identifiable {
    case combat
    case woodcutting
    case mining
    case fishing
    case cooking
    case smithing

    var id: String { rawValue }

    var localizedName: String {
        switch self {
        case .combat: "Combate"
        case .woodcutting: "Madeira"
        case .mining: "Mineração"
        case .fishing: "Pesca"
        case .cooking: "Culinária"
        case .smithing: "Ferraria"
        }
    }

    var icon: String {
        switch self {
        case .combat: "figure.martial.arts"
        case .woodcutting: "tree.fill"
        case .mining: "hammer.fill"
        case .fishing: "fish.fill"
        case .cooking: "flame.fill"
        case .smithing: "wrench.and.screwdriver.fill"
        }
    }
}

struct CharacterSkillStats: Equatable {
    static let maxLevel = 40
    static let empty = CharacterSkillStats()

    private static let totalLevelSkills: [CharacterSkill] = [
        .combat, .woodcutting, .mining, .fishing, .cooking
    ]

    var xp: [CharacterSkill: Int] = [:]
    var loaded = false

    init(xp: [CharacterSkill: Int] = [:], loaded: Bool = false) {
        self.xp = xp.mapValues { max(0, min(Self.maximumXP, $0)) }
        self.loaded = loaded
    }

    func totalXP(for skill: CharacterSkill) -> Int {
        max(0, xp[skill] ?? 0)
    }

    func level(for skill: CharacterSkill) -> Int {
        Self.level(fromTotalXP: totalXP(for: skill))
    }

    func progress(for skill: CharacterSkill) -> Double {
        Self.progressWithinLevel(fromTotalXP: totalXP(for: skill))
    }

    /// XP conquistado desde o início do nível atual.
    func currentLevelXP(for skill: CharacterSkill) -> Int {
        let total = totalXP(for: skill)
        let level = level(for: skill)
        guard level < Self.maxLevel else { return 0 }
        let lower = Self.xpThreshold(forLevelIndex: level - 1)
        return max(0, Int(floor(Double(total) - lower)))
    }

    /// Quantidade de XP necessária para atravessar o nível atual.
    func currentLevelXPGoal(for skill: CharacterSkill) -> Int {
        let level = level(for: skill)
        guard level < Self.maxLevel else { return 0 }
        let lower = Self.xpThreshold(forLevelIndex: level - 1)
        let upper = Self.xpThreshold(forLevelIndex: level)
        return max(1, Int(ceil(upper - lower)))
    }

    var totalLevel: Int {
        let precise = Self.totalLevelSkills.reduce(0.0) { partial, skill in
            partial + Self.preciseLevel(fromTotalXP: totalXP(for: skill))
        } / Double(Self.totalLevelSkills.count)
        return max(1, min(Self.maxLevel, Int(floor(precise))))
    }

    static func level(fromTotalXP value: Int) -> Int {
        let value = max(0, value)
        var level = 1
        for index in 1..<maxLevel where Double(value) >= xpThreshold(forLevelIndex: index) {
            level = index + 1
        }
        return min(maxLevel, level)
    }

    static func progressWithinLevel(fromTotalXP value: Int) -> Double {
        let value = max(0, value)
        let level = level(fromTotalXP: value)
        guard level < maxLevel else { return 1 }
        let lower = xpThreshold(forLevelIndex: level - 1)
        let upper = xpThreshold(forLevelIndex: level)
        return max(0, min(1, (Double(value) - lower) / max(1, upper - lower)))
    }

    private static func preciseLevel(fromTotalXP value: Int) -> Double {
        let level = level(fromTotalXP: value)
        return level >= maxLevel ? Double(maxLevel) : Double(level) + progressWithinLevel(fromTotalXP: value)
    }

    private static func xpThreshold(forLevelIndex index: Int) -> Double {
        guard index > 0 else { return 0 }
        return 480 * (pow(1.2, Double(index)) - 1) / 0.2
    }

    private static var maximumXP: Int {
        let level40 = xpThreshold(forLevelIndex: maxLevel - 1)
        let level39 = xpThreshold(forLevelIndex: maxLevel - 2)
        return Int(floor(level40 + (level40 - level39)))
    }
}

struct DailyQuest: Identifiable, Equatable {
    let id: String
    let kind: String
    let label: String
    let target: Int
    let progress: Int
    let claimed: Bool
    let rewardXpSkill: String?
    let rewardXpAmount: Int
    let rewardXpSpreadTotal: Int
    let rewardXpAll: Bool
    let rewards: [String]
    let rewardBadges: [String]

    var isComplete: Bool { progress >= target }
    var progressFraction: Double { min(1, Double(progress) / Double(max(1, target))) }

    var rewardSummary: String {
        var parts: [String] = []
        if let skill = rewardXpSkill, rewardXpAmount > 0 {
            let names = ["combat":"Combate","woodcutting":"Madeira","mining":"Mineração","fishing":"Pesca","cooking":"Culinária","smithing":"Ferraria"]
            parts.append("+\(rewardXpAmount) \(names[skill] ?? skill) XP")
        } else if rewardXpAll {
            parts.append("Quarter XP (todas as skills)")
        }
        if rewardXpSpreadTotal > 0 { parts.append("+\(rewardXpSpreadTotal) XP") }
        parts.append(contentsOf: rewards)
        parts.append(contentsOf: rewardBadges)
        return parts.isEmpty ? "Sem recompensa configurada" : parts.joined(separator: " · ")
    }
}

struct CharacterAppearance: Equatable {
    var outfitSchema = 15
    var hat = 0
    var top = 0
    var pants = 0
    var shoe = 0
    var skinTone = 1
    var hatFX: String?
    var torsoDecal: String?
    var pantsPattern: String?
    var shoeFX: String?
    var topFX: String?
    var pantsFX: String?
    var aura: String?
    var cape: String?
    var glasses: String?
    var shoeCosmetic: String?
    var faceMask: String?
    var wings: String?
    var handProp: String?
    var eyeFX: String?
    var hatColor: Int?
    var topColor: Int?
    var pantsColor: Int?
    var strapColor: Int?
    var shoeColor: Int?
}

struct CharacterProfile: Equatable {
    var playerID: Int?
    var displayName = "KintTany"
    var serverAverageLevel: Int?
    var appearance = CharacterAppearance()
    var skills = CharacterSkillStats.empty
    var loaded = false

    var totalLevel: Int {
        serverAverageLevel ?? skills.totalLevel
    }
}

enum CharacterProfilePayloadParser {
    static func profile(me: [String: Any], playerStats: [String: Any]?) -> CharacterProfile {
        let player = me["player"] as? [String: Any] ?? [:]
        let meta = me["meta"] as? [String: Any] ?? [:]
        let statsRoot = ((playerStats?["data"] as? [String: Any]) ?? playerStats) ?? [:]

        let playerID = int(player["id"] ?? me["playerId"])
        let rawName = string(player["display_name"])
            ?? string(player["displayName"])
            ?? string(player["name"])
            ?? string(me["displayName"])
            ?? "KintTany"
        let displayName = rawName.trimmingCharacters(in: .whitespacesAndNewlines)

        let outfit = (me["outfit"] as? [String: Any])
            ?? (player["outfit"] as? [String: Any])
            ?? [:]
        let skillXP = (statsRoot["skillXp"] as? [String: Any])
            ?? (meta["skillXp"] as? [String: Any])
            ?? (me["skillXp"] as? [String: Any])
            ?? [:]

        var parsedXP: [CharacterSkill: Int] = [:]
        for skill in CharacterSkill.allCases {
            if let value = int(skillXP[skill.rawValue]) {
                parsedXP[skill] = max(0, value)
            }
        }

        let average = int(player["avg"] ?? meta["avg"] ?? me["avg"])
        return CharacterProfile(
            playerID: playerID,
            displayName: displayName.isEmpty ? "KintTany" : displayName,
            serverAverageLevel: average.map { max(1, min(CharacterSkillStats.maxLevel, $0)) },
            appearance: appearance(outfit),
            skills: CharacterSkillStats(xp: parsedXP, loaded: !parsedXP.isEmpty),
            loaded: playerID != nil || !outfit.isEmpty || !parsedXP.isEmpty
        )
    }

    private static func appearance(_ object: [String: Any]) -> CharacterAppearance {
        CharacterAppearance(
            outfitSchema: int(object["outfitSchema"]) ?? 15,
            hat: int(object["hat"]) ?? 0,
            top: int(object["top"]) ?? 0,
            pants: int(object["pants"]) ?? 0,
            shoe: int(object["shoe"]) ?? 0,
            skinTone: int(object["skinTone"]) ?? 1,
            hatFX: string(object["hatFx"]),
            torsoDecal: string(object["torsoDecal"]),
            pantsPattern: string(object["pantsPattern"]),
            shoeFX: string(object["shoeFx"]),
            topFX: string(object["topFx"]),
            pantsFX: string(object["pantsFx"]),
            aura: string(object["aura"]),
            cape: string(object["cape"]),
            glasses: string(object["glasses"]),
            shoeCosmetic: string(object["shoeCosmetic"]),
            faceMask: string(object["faceMask"]),
            wings: string(object["wings"]),
            handProp: string(object["handProp"]),
            eyeFX: string(object["eyeFx"]),
            hatColor: int(object["hatC"]),
            topColor: int(object["topC"]),
            pantsColor: int(object["pantsC"]),
            strapColor: int(object["strapC"]),
            shoeColor: int(object["shoeC"])
        )
    }

    private static func int(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String { return Int(value) }
        return nil
    }

    private static func string(_ value: Any?) -> String? {
        guard let value = value as? String, !value.isEmpty else { return nil }
        return value
    }
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

struct DunesStopPolicy {
    static func requiresCooperativeShoresExit(
        mode: ActivityMode,
        phase: DunesPresencePhase,
        connected: Bool
    ) -> Bool {
        mode.isDunesGathering && connected && phase == .fullLootOrEntering
    }

    static func canFinishWithoutDunesReentry(mode: ActivityMode, phase: DunesPresencePhase) -> Bool {
        mode.isDunesGathering && phase != .fullLootOrEntering
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
    var roastCycleRemaining = 0
    var roastCooked = 0
    var roastBurned = 0
    var roastLastXPGained = 0
    var roastSessionXPGained = 0
    var roastCookingXPTotal = 0
    var smithCycleRemaining = 0
    var smithProduced = 0
    var smithLastXPGained = 0
    var smithSessionXPGained = 0
    var smithingXPTotal = 0
    var smithRepairs = 0
    var smithBatchSize = 1
    var smithRecipeLabel = ""
    var smithRequiredSummary = ""
    var smithBankRemainingSummary = ""
    var smithLastInventoryTotal = 0
    var startedAt: Date?
    var lastEvent = ""
}

private final class BackgroundAudioRuntime: @unchecked Sendable {
    struct Snapshot {
        let runningFlag: Bool
        let engineRunning: Bool
        let playerPlaying: Bool
        let route: String

        var active: Bool {
            runningFlag && engineRunning && playerPlaying
        }

        var summary: String {
            "active=\(active ? "sim" : "não") • engine=\(engineRunning ? "sim" : "não") • player=\(playerPlaying ? "sim" : "não") • route=\(route)"
        }
    }

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let format: AVAudioFormat
    private let loopBuffer: AVAudioPCMBuffer
    private var prepared = false
    private var running = false
    private var observerTokens: [NSObjectProtocol] = []
    private var eventSink: ((String) -> Void)?

    init() {
        let sampleRate = 44_100.0
        let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        self.format = format

        let frames = AVAudioFrameCount(sampleRate)
        let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames)!
        buffer.frameLength = frames

        // Real non-zero PCM. Kept extremely quiet so the background-runtime
        // experiment remains unobtrusive while still being genuine playback.
        if let channel = buffer.floatChannelData?[0] {
            let amplitude: Float = 0.0005
            let frequency = 220.0
            for index in 0..<Int(frames) {
                let phase = 2.0 * Double.pi * frequency * Double(index) / sampleRate
                channel[index] = amplitude * Float(sin(phase))
            }
        }
        self.loopBuffer = buffer
    }

    deinit {
        removeObservers()
    }

    func start(onEvent: @escaping (String) -> Void) throws {
        eventSink = onEvent
        installObserversIfNeeded()

        if running, engine.isRunning, player.isPlaying {
            emit("start ignorado • já ativo • \(snapshot().summary)")
            return
        }

        try activateSessionAndEngine(reason: "start")
        emit("ATIVO • AVAudioSession=playback • AVAudioEngine loop PCM real • \(snapshot().summary)")
    }

    private func activateSessionAndEngine(reason: String) throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playback, mode: .default, options: [.mixWithOthers])
        try session.setActive(true)

        if !prepared {
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: format)
            engine.mainMixerNode.outputVolume = 1.0
            engine.prepare()
            prepared = true
        }

        if !engine.isRunning {
            try engine.start()
        }

        if !player.isPlaying {
            player.stop()
            player.scheduleBuffer(loopBuffer, at: nil, options: [.loops], completionHandler: nil)
            player.play()
        }

        running = true
        emit("runtime confirmado • motivo=\(reason) • \(snapshot().summary)")
    }

    func ensureActive(reason: String) -> Bool {
        let before = snapshot()
        if before.active { return true }

        do {
            try activateSessionAndEngine(reason: reason)
            emit("RECUPERADO • motivo=\(reason) • antes={\(before.summary)} • depois={\(snapshot().summary)}")
            return snapshot().active
        } catch {
            emit("FALHA recovery • motivo=\(reason) • \(error.localizedDescription) • estado={\(snapshot().summary)}")
            return false
        }
    }

    func stop() {
        let before = snapshot()
        guard running || engine.isRunning || player.isPlaying else {
            removeObservers()
            eventSink = nil
            return
        }

        player.stop()
        engine.stop()
        running = false

        do {
            try AVAudioSession.sharedInstance().setActive(
                false,
                options: [.notifyOthersOnDeactivation]
            )
        } catch {
            emit("WARN ao desativar AVAudioSession • \(error.localizedDescription)")
        }

        emit("INATIVO • antes={\(before.summary)}")
        removeObservers()
        eventSink = nil
    }

    func snapshot() -> Snapshot {
        let route = AVAudioSession.sharedInstance().currentRoute.outputs
            .map { output in
                let port = output.portType.rawValue
                let name = output.portName.replacingOccurrences(of: " • ", with: " ")
                return "\(port):\(name)"
            }
            .joined(separator: ",")
        return Snapshot(
            runningFlag: running,
            engineRunning: engine.isRunning,
            playerPlaying: player.isPlaying,
            route: route.isEmpty ? "sem-output" : route
        )
    }

    var isActive: Bool { snapshot().active }

    private func installObserversIfNeeded() {
        guard observerTokens.isEmpty else { return }

        let center = NotificationCenter.default
        let session = AVAudioSession.sharedInstance()

        observerTokens.append(
            center.addObserver(
                forName: AVAudioSession.interruptionNotification,
                object: session,
                queue: .main
            ) { [weak self] notification in
                self?.handleInterruption(notification)
            }
        )

        observerTokens.append(
            center.addObserver(
                forName: AVAudioSession.routeChangeNotification,
                object: session,
                queue: .main
            ) { [weak self] notification in
                self?.handleRouteChange(notification)
            }
        )

        observerTokens.append(
            center.addObserver(
                forName: AVAudioSession.mediaServicesWereLostNotification,
                object: session,
                queue: .main
            ) { [weak self] _ in
                self?.emit("MEDIA SERVICES LOST • \(self?.snapshot().summary ?? "estado indisponível")")
            }
        )

        observerTokens.append(
            center.addObserver(
                forName: AVAudioSession.mediaServicesWereResetNotification,
                object: session,
                queue: .main
            ) { [weak self] _ in
                guard let self else { return }
                self.prepared = false
                self.running = false
                self.emit("MEDIA SERVICES RESET • tentando reconstruir runtime")
                _ = self.ensureActive(reason: "media-services-reset")
            }
        )

        observerTokens.append(
            center.addObserver(
                forName: .AVAudioEngineConfigurationChange,
                object: engine,
                queue: .main
            ) { [weak self] _ in
                guard let self else { return }
                self.emit("ENGINE CONFIG CHANGE • \(self.snapshot().summary)")
                _ = self.ensureActive(reason: "engine-config-change")
            }
        )
    }

    private func handleInterruption(_ notification: Notification) {
        guard let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw)
        else {
            emit("INTERRUPÇÃO desconhecida • \(snapshot().summary)")
            return
        }

        switch type {
        case .began:
            emit("INTERRUPÇÃO começou • \(snapshot().summary)")
        case .ended:
            let rawOptions = notification.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            let options = AVAudioSession.InterruptionOptions(rawValue: rawOptions)
            emit("INTERRUPÇÃO terminou • shouldResume=\(options.contains(.shouldResume) ? "sim" : "não") • \(snapshot().summary)")
            _ = ensureActive(reason: "interruption-ended")
        @unknown default:
            emit("INTERRUPÇÃO tipo futuro • \(snapshot().summary)")
        }
    }

    private func handleRouteChange(_ notification: Notification) {
        let raw = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt ?? 0
        let reason = AVAudioSession.RouteChangeReason(rawValue: raw)
        emit("ROUTE CHANGE • reason=\(reason.map { String($0.rawValue) } ?? "?") • \(snapshot().summary)")
        if running {
            _ = ensureActive(reason: "route-change")
        }
    }

    private func removeObservers() {
        let center = NotificationCenter.default
        observerTokens.forEach { center.removeObserver($0) }
        observerTokens.removeAll()
    }

    private func emit(_ message: String) {
        eventSink?("[BG][AUDIO] \(message)")
    }
}

private final class BGHeadlessGate: @unchecked Sendable {
    struct BufferedLine: Sendable {
        let date: Date
        let value: String
        let visible: Bool
    }

    private let lock = NSLock()
    private var enabledValue = false
    private var suppressVisualEventsValue = false
    private var bufferedLines: [BufferedLine] = []

    func set(enabled: Bool, suppressVisualEvents: Bool) {
        lock.lock()
        enabledValue = enabled
        suppressVisualEventsValue = enabled && suppressVisualEvents
        lock.unlock()
    }

    func snapshot() -> (enabled: Bool, suppressVisualEvents: Bool) {
        lock.lock()
        defer { lock.unlock() }
        return (enabledValue, suppressVisualEventsValue)
    }

    func buffer(_ value: String, visible: Bool, at date: Date = .now) {
        lock.lock()
        bufferedLines.append(BufferedLine(date: date, value: value, visible: visible))
        if bufferedLines.count > 6_000 {
            bufferedLines.removeFirst(bufferedLines.count - 5_000)
        }
        lock.unlock()
    }

    func drain() -> [BufferedLine] {
        lock.lock()
        defer { lock.unlock() }
        let copy = bufferedLines
        bufferedLines.removeAll(keepingCapacity: true)
        return copy
    }
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
    @Published var selectedRoastMode: RoastPitMode = .trout
    @Published var selectedBlacksmith: BlacksmithSelection = .smith(.copperIngot, batch: 1, smeltGoal: 100)
    @Published private(set) var characterProfile = CharacterProfile()
    @Published private(set) var characterProfileLoading = false
    @Published private(set) var characterProfileError: String?
    @Published private(set) var characterArtwork: UIImage?
    @Published private(set) var dailyQuests: [DailyQuest] = []
    @Published private(set) var dailyQuestDay: String?
    @Published private(set) var dailyQuestsLoading = false
    @Published private(set) var dailyQuestsError: String?

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
    // iOS 26 introduziu BGContinuedProcessingTask para trabalhos iniciados por
    // uma ação explícita do usuário. Desde a Build 127, o runtime de áudio real é
    // a fonte principal de continuidade observada em BG; Continued Processing
    // permanece como integração/progresso do sistema e superfície da Dynamic Island.
    // Se o CP expirar mas o áudio continuar vivo, a engine/Presence permanecem ativas.
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
    // Build 126: Dynamic Island gather wear is kept in a non-published lane.
    // This lets BG show 1/6...6/6 without waking SwiftUI/headless visuals.
    private var continuedGatherStatus: String?
    private var lastScenePhaseKey: String?
    private var backgroundEnteredAt: Date?
    private var accumulatedBackgroundSeconds: TimeInterval = 0
    private var legacyBackgroundTask: UIBackgroundTaskIdentifier = .invalid
    private var lastContinuedTitleSuccesses = -1
    private var lastContinuedPublicStatus = ""
    private var lastContinuedTitleUpdateAt: Date?

    // Build 123 BG Headless: intentionally non-published.
    private let bgHeadlessGate = BGHeadlessGate()
    private var bgHeadlessActive = false

    // Build 124 criou o runtime real; Build 127 o promove a autoridade de
    // continuidade em BG para todos os modos. Protocolos de gather/proof/socket
    // continuam intocados; apenas a decisão de preservar/encerrar usa este estado.
    private let backgroundAudioRuntime = BackgroundAudioRuntime()

    private var continuedTaskIdentifierPrefix: String {
        let bundleID = Bundle.main.bundleIdentifier ?? "com.joaopedro.kinttany"
        return "\(bundleID).continuedBot"
    }

    var hasSession: Bool {
        guard let cookie = session.cookie else { return false }
        return !cookie.isEmpty
    }

    /// A sessão só é entregue à visualização oficial de outfit, em memória,
    /// para que o próprio renderer do jogo produza o personagem autenticado.
    /// O valor nunca é incluído em logs nem persistido fora do Keychain.
    var authenticatedCookieForCharacter: String? {
        session.cookie
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

    private func resolvedSessionGoal(for mode: ActivityMode) -> Int {
        guard mode == .blacksmith else {
            return min(100_000, max(1, goal))
        }
        switch selectedBlacksmith {
        case .smith(let recipe, let batch, let smeltGoal):
            return BlacksmithProtocolPolicy.smithSessionGoal(
                recipe: recipe,
                batch: batch,
                smeltGoal: smeltGoal
            )
        case .repair:
            return 1
        }
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
        sessionGoal = resolvedSessionGoal(for: mode)

        // Build 127: Continued Processing must never inherit counters from the
        // previous activity (e.g. Dragão 52/100 -> Carvão 52/500).
        // Freeze a fresh session before submitting the new CP request.
        stats = ActivitySessionPolicy.freshStats()

        let runID = UUID()
        activeRunID = runID
        requestedStopReason = nil

        // A solicitação precisa nascer do toque do usuário, antes de o app ser
        // colocado em segundo plano.
        prepareContinuedProcessing(for: mode)

        do {
            try backgroundAudioRuntime.start { [weak self] message in
                Task { @MainActor [weak self] in
                    self?.diagnostic(message)
                }
            }
        } catch {
            diagnostic("[BG][AUDIO] FALHA ao iniciar • \(error.localizedDescription)")
        }

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

        // Build 2: if a Dunes checkpoint is already in World/Bank/The Shores,
        // STOP is authoritative at the session level. Do not send it only to the
        // temporary bank engine and, above all, never create another Desert Presence.
        if let stoppedMode,
           DunesStopPolicy.canFinishWithoutDunesReentry(mode: stoppedMode, phase: dunesPresencePhase) {
            state = .recovering
            statusMessage = "STOP • encerrando em área segura"
            stats.lastEvent = "STOP global • sem reentrada Dunes"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                log("STOP registrado em fase segura das Dunes • nenhuma nova Presence desert será aberta")
            }
            return
        }

        // Em regiões full-loot o STOP é cooperativo. A engine deixa de criar
        // novas ações e confirma World/The Shores antes de liberar a Presence.
        if let stoppedMode,
           stoppedMode.requiresSafeExit,
           connected,
           let activeEngine {
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: .user)
            }
            state = .recovering
            statusMessage = stoppedMode.isDunesGathering
                ? "Saindo das Dunes com segurança"
                : "Saindo do combate com segurança"
            stats.lastEvent = "safe stop solicitado"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                let region = stoppedMode.isDunesGathering ? "Dunes" : "Wilderness"
                log("STOP solicitado — encerrando \(region) com segurança antes de fechar a conexão")
            }
            return
        }

        // v4.0: transactional safe modes finish/reconcile the operation already
        // in flight, but never start a new cycle after STOP.
        if activity?.supportsAtomicStop == true, connected, let activeEngine {
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: .user)
            }
            state = .recovering
            statusMessage = "STOP • finalizando operação atual"
            stats.lastEvent = "STOP atômico solicitado"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            if !silent {
                log("STOP solicitado • concluindo/reconciliando somente a operação em andamento antes de fechar")
            }
            return
        }

        // Demais modos seguros usam cancelamento imediato.
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

        backgroundAudioRuntime.stop()

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
        let gate = bgHeadlessGate
        return { [weak self] event in
            if case .diagnostic(let value) = event,
               value.hasPrefix("[GATHER][TRACE]") {
                return
            }

            let bg = gate.snapshot()
            if bg.enabled {
                switch event {
                case .log(let value):
                    gate.buffer(value, visible: true)
                    return
                case .diagnostic(let value):
                    gate.buffer(value, visible: false)
                    return
                default:
                    break
                }

                // Safe gathering keeps authoritative counters/progress/failures,
                // but drops MainActor-only presentation chatter entirely.
                if bg.suppressVisualEvents {
                    switch event {
                    case .state, .target, .player, .world, .roastCountdown, .smithCountdown:
                        return
                    default:
                        break
                    }
                }
            }

            Task { @MainActor [weak self] in
                self?.handleEngineEvent(event, runID: runID)
            }
        }
    }

    enum WildRecoveryOwnershipPolicy {
        static func shouldStartNewRecoveryOwner(recoveryAlreadyInProgress: Bool) -> Bool {
            !recoveryAlreadyInProgress
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
    ) async -> Task<Void, Never> {
        return Task.detached(priority: .userInitiated) { [weak self] in
            for await data in stream {
                if Task.isCancelled { break }
                await engine.ingest(data)
            }

            if notifyUnexpectedEnd, !Task.isCancelled {
                await self?.handleUnexpectedRealtimeEnd(for: mode, runID: runID)
            }
        }
    }

    /// Wild operational failures are recovery boundaries, never session endings.
    /// If this is called from inside the existing recovery owner, it only proves
    /// the safe boundary and returns ownership to that same loop. It must never
    /// recursively launch a second recovery while connectionRecoveryInProgress.
    @discardableResult
    private func containWildTerminalFailure(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        engine: AutomationEngine,
        failure: String,
        resumeSessionAfterBoundary: Bool = true
    ) async -> Bool {
        guard activeRunID == runID, activity == mode, mode.isWildCombat else { return false }

        diagnostic("[WILD][FAILSAFE] \(failure) • convertendo falha operacional em recovery contínuo")
        state = .recovering
        statusMessage = "Falha detectada • recuperando fluxo do combate"
        stats.lastEvent = "failsafe Wild • recovery contínuo"
        updateContinuedProcessingProgress(forceTitleUpdate: true)

        do {
            let outcome = try await engine.runEmergencyWildExit(
                mode: mode,
                reason: "falha operacional: \(failure)"
            )
            await importSocketTrace()

            guard activeRunID == runID, activity == mode else { return false }

            switch outcome {
            case .worldSafe, .alreadyWorld, .respawnConfirmed:
                connectionRecoveryRequested = true
                connectionRecoveryDetail = "falha operacional contida em World seguro: \(failure)"
                state = .recovering
                statusMessage = "World seguro • reconstruindo combate"
                stats.lastEvent = "Wild • World seguro após falha"
                log("🛡️ Falha operacional contida • World/respawn seguro confirmado • progresso \(stats.successes)/\(sessionGoal) preservado")
                log("🔄 \(mode.localizedTitle) • reconstruindo BANK-FIRST, espada, poções e vitais para continuar a mesma meta")

                if resumeSessionAfterBoundary &&
                   WildRecoveryOwnershipPolicy.shouldStartNewRecoveryOwner(
                       recoveryAlreadyInProgress: connectionRecoveryInProgress
                   ) {
                    _ = await recoverWildAfterUnexpectedDisconnect(
                        mode: mode,
                        runID: runID,
                        shard: shard,
                        cookie: cookie,
                        confirmedWorldBoundary: true
                    )
                } else if connectionRecoveryInProgress {
                    diagnostic("[WILD][RECOVERY] fronteira World confirmada dentro do recovery ativo • devolvendo controle ao owner atual")
                }
                return true

            case .dead:
                connectionRecoveryRequested = true
                connectionRecoveryDetail = "morte observada durante falha operacional; aguardando respawn"
                state = .recovering
                statusMessage = "Morte detectada • aguardando respawn"
                stats.lastEvent = "Wild • aguardando respawn"
                log("💀 Wild • morte observada durante falha operacional • progresso \(stats.successes)/\(sessionGoal) preservado • aguardando respawn para continuar")

                if resumeSessionAfterBoundary &&
                   WildRecoveryOwnershipPolicy.shouldStartNewRecoveryOwner(
                       recoveryAlreadyInProgress: connectionRecoveryInProgress
                   ) {
                    await socket.close()
                    _ = await recoverWildAfterUnexpectedDisconnect(
                        mode: mode,
                        runID: runID,
                        shard: shard,
                        cookie: cookie
                    )
                } else if connectionRecoveryInProgress {
                    diagnostic("[WILD][RECOVERY] morte observada dentro do recovery ativo • owner atual aguardará o respawn")
                }
                return false
            }
        } catch {
            diagnostic("[WILD][FAILSAFE] fronteira segura não confirmou na Presence atual: \(error.localizedDescription) • recovery por reconexão assumirá o fluxo")
            requestWildConnectionRecovery(
                reason: "Falha operacional no Wild; reconectando para confirmar World/respawn e continuar a meta",
                runID: runID
            )
            await socket.close()

            if resumeSessionAfterBoundary &&
               WildRecoveryOwnershipPolicy.shouldStartNewRecoveryOwner(
                   recoveryAlreadyInProgress: connectionRecoveryInProgress
               ) {
                _ = await recoverWildAfterUnexpectedDisconnect(
                    mode: mode,
                    runID: runID,
                    shard: shard,
                    cookie: cookie
                )
            } else if connectionRecoveryInProgress {
                diagnostic("[WILD][RECOVERY] falha de saída dentro do recovery ativo • owner atual continuará a reconexão")
            }
            return false
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

    /// Trout can enter a server-side state where every valid cell across several
    /// authoritative spots stops producing fish_bite. Recreate only the activity
    /// Presence on the same shard; rod/bait stay carried, so World/bank preflight
    /// is intentionally NOT repeated. Progress is accumulated across Presences.
    private func runFishingWithPresenceRecovery(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        initialEngine: AutomationEngine,
        runGoal: Int
    ) async throws -> EngineRunResult {
        var phaseEngine = initialEngine
        var completedBeforePhase = stats.successes
        var recoveries = 0

        while completedBeforePhase < runGoal {
            guard activeRunID == runID, activity == mode, !terminalFailureHandled else { throw CancellationError() }
            let remaining = max(1, runGoal - completedBeforePhase)
            do {
                let engineForPhase = phaseEngine
                let child = Task.detached(priority: .userInitiated) {
                    try await engineForPhase.run(mode: mode, goal: remaining)
                }
                engineRunTask = child
                let phaseResult = try await child.value
                engineRunTask = nil
                await importSocketTrace()
                await Task.yield()
                guard activeRunID == runID, activity == mode else { throw CancellationError() }
                let total = max(stats.successes, completedBeforePhase + phaseResult.successes)
                stats.successes = total
                return EngineRunResult(
                    successes: total,
                    completedGoal: total >= runGoal,
                    stoppedSafely: phaseResult.stoppedSafely,
                    stopReason: phaseResult.stopReason
                )
            } catch let EngineError.fishingPresenceStalled(phaseSuccesses) {
                engineRunTask = nil
                recoveries += 1
                completedBeforePhase = max(stats.successes, completedBeforePhase + phaseSuccesses)
                stats.successes = completedBeforePhase
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                log("🔄 Trout • Presence sem fish_bite global • progresso \(completedBeforePhase)/\(runGoal) preservado • recovery #\(recoveries)")

                guard recoveries <= 6 else {
                    throw EngineError.fishingPresenceStalled(successes: completedBeforePhase)
                }
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                guard activeRunID == runID, activity == mode else { throw CancellationError() }

                let bootstrap = AutomationEngine.bootstrap(for: mode, fishingBait: selectedFishingBait)
                state = .connecting
                statusMessage = "Trout • renovando Presence de ElderGrove"
                stats.lastEvent = "recovery Trout • nova Presence"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                let stream = try await socket.connect(session: session, shard: shard, bootstrap: bootstrap)
                let replacement = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: shard,
                    bootstrap: bootstrap,
                    fishingBait: selectedFishingBait,
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                phaseEngine = replacement
                activeEngine = replacement
                receiverTask = await makeReceiverTask(stream: stream, engine: replacement, mode: mode, runID: runID)
                connected = true
                state = .syncing
                statusMessage = "Trout • Presence renovada"
                await replacement.prepareIdentity()
                log("✅ Trout • nova Presence \(bootstrap.region) ativa no mesmo shard \(shard) • retomando em \(completedBeforePhase)/\(runGoal)")
            }
        }
        return EngineRunResult(successes: completedBeforePhase, completedGoal: true, stoppedSafely: false, stopReason: nil)
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
        var deathRecoveries = 0

        while completedBeforePhase < runGoal {
            guard activeRunID == runID, activity == mode, !terminalFailureHandled else {
                throw CancellationError()
            }
            if requestedStopReason == .user {
                log("STOP confirmado no orquestrador Dunes • progresso \(completedBeforePhase)/\(runGoal) preservado • sem nova reentrada")
                return EngineRunResult(
                    successes: completedBeforePhase,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
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
            let phaseResult: EngineRunResult
            var recoveringFromDeath = false
            do {
                phaseResult = try await child.value
            } catch let EngineError.dunesDeathDuringExit(detail) {
                engineRunTask = nil
                await importSocketTrace()
                await Task.yield()
                guard activeRunID == runID, activity == mode else { throw CancellationError() }

                deathRecoveries += 1
                recoveringFromDeath = true
                let preserved = max(completedBeforePhase, stats.successes)
                stats.successes = preserved
                state = .recovering
                statusMessage = "Respawn detectado • reconstruindo loadout"
                stats.lastEvent = "Dunes • respawn #\(deathRecoveries)"
                log("💀 Dunes • respawn/full-loot confirmado • recovery #\(deathRecoveries) • progresso \(preserved)/\(runGoal) preservado • sessão continuará")
                log("💀 Evidência: \(detail)")
                phaseResult = EngineRunResult(
                    successes: max(0, preserved - phaseStart),
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .dunesCheckpoint
                )
            }
            engineRunTask = nil
            await importSocketTrace()
            await Task.yield()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let total = max(stats.successes, phaseStart + phaseResult.successes)
            stats.successes = total
            let checkpointHPHandoff = await phaseEngine.latestTrustedHPForHandoff()

            if requestedStopReason == .user || phaseResult.stopReason == .user {
                log("STOP confirmado após saída segura das Dunes • progresso \(total)/\(runGoal) preservado • checkpoint não será reaberto")
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }

            let resumableSafeExit = phaseResult.stoppedSafely
                && DunesCheckpointContinuationPolicy.shouldResumeAfterSafeExit(phaseResult.stopReason)
            if phaseResult.stoppedSafely && !resumableSafeExit {
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: phaseResult.stopReason
                )
            }
            guard phaseResult.completedGoal || resumableSafeExit else {
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
            let checkpointTrigger: String
            if recoveringFromDeath {
                checkpointTrigger = "respawn confirmado"
            } else if resumableSafeExit {
                checkpointTrigger = DunesCheckpointContinuationPolicy.triggerLabel(for: phaseResult.stopReason)
            } else {
                checkpointTrigger = "\(DunesCheckpointPolicy.successInterval) sucessos"
            }
            if phaseResult.stopReason == .dunesDangerSafety {
                log("🛡️ Dunes • dano externo sobrevivido • progresso \(total)/\(runGoal) preservado • convertendo fuga em checkpoint recuperável")
            }
            let rotatedToolIID = phaseResult.stopReason == .dunesToolRotation ? dunesExpectedTool?.iid : nil
            if let rotatedToolIID {
                diagnostic("[DUNES][TOOL] iid recusada nesta rotação=\(rotatedToolIID)")
            }
            if recoveringFromDeath {
                log("🔄 Dunes • respawn confirmado • reconstruindo BANK-FIRST + ferramenta + HP antes de reentrar • \(total)/\(runGoal)")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
            } else {
                log("🏦 Dunes CHECKPOINT \(total)/\(runGoal) • gatilho=\(checkpointTrigger) • The Shores + sobrevivência confirmadas • protegendo recursos no banco")
                await closeDunesPresenceAfterConfirmedShores()
            }
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            dunesPresencePhase = .preflightSafe
            if requestedStopReason == .user {
                log("STOP confirmado em The Shores/World antes do banco • progresso \(total)/\(runGoal) preservado")
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }
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
                roastMode: selectedRoastMode,
                blacksmithSelection: selectedBlacksmith,
                inheritedPlayerHP: checkpointHPHandoff,
                reporter: engineReporter(runID: runID)
            )
            activeEngine = bankEngine
            receiverTask = await makeReceiverTask(stream: bankStream, engine: bankEngine, mode: mode, runID: runID)
            connected = true
            await bankEngine.prepareIdentity()
            let loadout: (tool: String, healthPotionPlus: Int, toolIdentity: DunesToolInstanceIdentity, lifeEpoch: Int)
            do {
                loadout = try await bankEngine.prepareDunesLoadoutFromWorld(
                    for: mode,
                    excludingToolIID: rotatedToolIID
                )
            } catch let EngineError.gatherLoadoutNotReady(detail) {
                log("🧰 Dunes • \(detail) • progresso \(total)/\(runGoal) preservado no World/Bank")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .dunesToolRotation
                )
            }
            dunesExpectedTool = loadout.toolIdentity
            dunesExpectedLifeEpoch = loadout.lifeEpoch
            player.lifeEpoch = max(player.lifeEpoch, loadout.lifeEpoch)
            let reentryHPHandoff = await bankEngine.latestTrustedHPForHandoff()
            let toolName = ActivityToolPolicy.displayName(loadout.tool)
            log("🏦 Dunes CHECKPOINT • recursos protegidos no banco • \(toolName) única mantida ✅")
            if loadout.healthPotionPlus > 0 {
                log("❤️‍🔥 Checkpoint • Health Potion+ carregadas: \(loadout.healthPotionPlus)")
            } else {
                log("⚠️ Checkpoint • sem Health Potion+ • próximo lote usa piso de \(DunesHeatSafetyPolicy.minimumSafeHP) HP")
            }

            if requestedStopReason == .user {
                log("STOP confirmado após BANK-FIRST • World seguro • progresso \(total)/\(runGoal) preservado • Desert NÃO será reaberta")
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }

            receiverTask?.cancel()
            receiverTask = nil
            activeEngine = nil
            connected = false
            await socket.close()
            await importSocketTrace()
            guard activeRunID == runID, activity == mode else { throw CancellationError() }

            let activityBootstrap = AutomationEngine.bootstrap(for: mode)
            if requestedStopReason == .user {
                log("STOP confirmado antes da nova Presence desert • progresso \(total)/\(runGoal) preservado")
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }
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

            if requestedStopReason == .user {
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                dunesPresencePhase = .preflightSafe
                log("STOP venceu corrida de reconexão • nova Presence desert fechada antes de coletar • progresso \(total)/\(runGoal) preservado")
                return EngineRunResult(
                    successes: total,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }

            let activityEngine = AutomationEngine(
                socket: socket,
                cookie: cookie,
                shard: shard,
                bootstrap: activityBootstrap,
                fishingBait: selectedFishingBait,
                roastMode: selectedRoastMode,
                blacksmithSelection: selectedBlacksmith,
                inheritedPlayerHP: reentryHPHandoff,
                reporter: engineReporter(runID: runID)
            )
            phaseEngine = activityEngine
            activeEngine = activityEngine
            receiverTask = await makeReceiverTask(
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
        if mode == .roastPit {
            log("🔥 Roast Pit • ciclos \(stats.successes)/\(sessionGoal) • cozidos \(stats.roastCooked) • queimados \(stats.roastBurned)")
            log("📈 Cooking XP • ganho na sessão +\(stats.roastSessionXPGained) • total final \(stats.roastCookingXPTotal)")
        }
        if mode == .blacksmith {
            log("⚒️ Frostmere Smith • ciclos \(stats.successes)/\(sessionGoal) • itens \(stats.smithProduced) • repairs \(stats.smithRepairs)")
            log("📈 Smithing XP • ganho +\(stats.smithSessionXPGained) • total \(stats.smithingXPTotal)")
        }
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
        if bgHeadlessActive {
            bgHeadlessGate.buffer(value, visible: true)
            return
        }

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

        if bgHeadlessActive {
            bgHeadlessGate.buffer(value, visible: false)
            return
        }

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
            value.hasPrefix("[SMITH]") ||
            value.hasPrefix("[GATHER][TIMING]") ||
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

    private func flushBGHeadlessLogs() {
        let buffered = bgHeadlessGate.drain()
        guard !buffered.isEmpty else { return }

        var visibleLines: [String] = []
        var fullLines: [String] = []
        visibleLines.reserveCapacity(buffered.count)
        fullLines.reserveCapacity(buffered.count)

        for item in buffered {
            let line = timestamped(item.value, at: item.date)
            if item.visible {
                visibleLines.append(line)
                fullLines.append(line)
            } else if shouldKeepDiagnostic(item.value) {
                fullLines.append(line)
            }
        }

        if !visibleLines.isEmpty {
            logs.append(contentsOf: visibleLines)
        }
        if !fullLines.isEmpty {
            diagnosticLogs.append(contentsOf: fullLines)
        }
        trimLogs()
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
        characterProfile = CharacterProfile()
        characterArtwork = nil
        characterProfileError = nil
        state = .idle
        connected = false
        statusMessage = "Sessão salva"
        log("Sessão autenticada e salva no Keychain; realtime será conectado ao iniciar uma atividade")
        Task { [weak self] in
            await self?.refreshCharacterProfile(force: true)
        }
    }

    func refreshCharacterProfile(force: Bool = false) async {
        guard let cookie = session.cookie, !cookie.isEmpty else {
            characterProfile = CharacterProfile()
            characterArtwork = nil
            characterProfileError = "Faça login para carregar o personagem."
            return
        }
        guard !characterProfileLoading else { return }
        if characterProfile.loaded, characterProfile.skills.loaded, !force { return }

        characterProfileLoading = true
        characterProfileError = nil
        defer { characterProfileLoading = false }

        do {
            let client = CharacterProfileHTTPClient(cookie: cookie)
            let me = try await client.get("/api/auth/me")
            let provisional = CharacterProfilePayloadParser.profile(me: me, playerStats: nil)

            var statsPayload: [String: Any]?
            if let playerID = provisional.playerID {
                do {
                    statsPayload = try await client.playerStats(playerID: playerID)
                } catch {
                    // /me já inclui meta.skillXp no bootstrap atual. Se a rota
                    // dedicada estiver temporariamente indisponível, preservamos
                    // o perfil autoritativo e exibimos esses mesmos valores.
                    characterProfileError = "Stats não puderam ser atualizados agora."
                }
            }

            let refreshedProfile = CharacterProfilePayloadParser.profile(
                me: me,
                playerStats: statsPayload
            )
            if characterProfile.loaded,
               characterProfile.appearance != refreshedProfile.appearance {
                characterArtwork = nil
            }
            characterProfile = refreshedProfile
            if characterProfile.skills.loaded {
                characterProfileError = nil
            }
        } catch {
            characterProfileError = "Não foi possível carregar o personagem."
            diagnostic("[PROFILE] atualização falhou • \(error.localizedDescription)")
        }
    }

    func storeCharacterArtwork(_ image: UIImage) {
        characterArtwork = image
    }

    func loadBlacksmithRepairTargets() async -> [RepairTarget] {
        guard let cookie = session.cookie, !cookie.isEmpty else { return [] }
        do { return try await AutomationEngine.blacksmithRepairTargets(cookie: cookie) }
        catch { diagnostic("[SMITH] Repair targets falhou • \(error.localizedDescription)"); return [] }
    }

    func refreshDailyQuests() async {
        guard let cookie = session.cookie, !cookie.isEmpty else {
            dailyQuests = []
            dailyQuestsError = "Faça login para carregar as quests."
            return
        }
        guard !dailyQuestsLoading else { return }
        dailyQuestsLoading = true
        dailyQuestsError = nil
        defer { dailyQuestsLoading = false }

        do {
            let payload = try await CharacterProfileHTTPClient(cookie: cookie).post("/api/auth/daily-quest-progress")
            let config = payload["dailyQuestConfig"] as? [String: Any] ?? [:]
            let state = payload["dailyQuest"] as? [String: Any] ?? [:]
            let quests = config["quests"] as? [[String: Any]] ?? []
            let prog = state["prog"] as? [String: Any] ?? [:]
            let claimed = state["claimed"] as? [String: Any] ?? [:]
            dailyQuestDay = state["day"] as? String

            dailyQuests = quests.compactMap { q in
                guard let id = q["id"] as? String else { return nil }
                let target = max(1, Self.questInt(q["target"]) ?? 1)
                let progress = min(target, max(0, Self.questInt(prog[id]) ?? 0))
                let rawRewards = q["rewards"] as? [[String: Any]] ?? []
                let rewards = rawRewards.compactMap { item -> String? in
                    guard let type = item["t"] as? String, let count = Self.questInt(item["n"]), count > 0 else { return nil }
                    return "\(count)× \(type)"
                }
                return DailyQuest(
                    id: id,
                    kind: q["kind"] as? String ?? "",
                    label: q["label"] as? String ?? (q["kind"] as? String ?? "Daily Quest"),
                    target: target,
                    progress: progress,
                    claimed: (claimed[id] as? Bool) ?? false,
                    rewardXpSkill: q["rewardXpSkill"] as? String,
                    rewardXpAmount: max(0, Self.questInt(q["rewardXpAmount"]) ?? 0),
                    rewardXpSpreadTotal: max(0, Self.questInt(q["rewardXpSpreadTotal"]) ?? 0),
                    rewardXpAll: (q["rewardXpAll"] as? Bool) ?? ((q["rewardXpSkill"] as? String)?.isEmpty != false),
                    rewards: rewards,
                    rewardBadges: q["rewardBadges"] as? [String] ?? []
                )
            }
        } catch {
            dailyQuestsError = "Não foi possível carregar as Daily Quests."
            diagnostic("[QUESTS] atualização falhou • \(error.localizedDescription)")
        }
    }

    private static func questInt(_ value: Any?) -> Int? {
        if let v = value as? Int { return v }
        if let v = value as? NSNumber { return v.intValue }
        if let v = value as? String { return Int(v) }
        return nil
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
        sessionGoal = resolvedSessionGoal(for: mode)
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
            if mode == .fishing || mode == .roastPit || mode == .blacksmith {
                // Fishing, Roast Pit and Frostmere Smith start with a safe World Presence for
                // transactional bank preflight. A fresh activity Presence is
                // opened only after World/bank_shop/World completes.
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
                    roastMode: selectedRoastMode,
                blacksmithSelection: selectedBlacksmith,
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
            receiverTask = await makeReceiverTask(stream: stream, engine: engine, mode: mode, runID: runID)

            await engine.prepareIdentity()
            guard activeRunID == runID else { return }

            if mode == .roastPit {
                state = .syncing
                statusMessage = "🔥 Preparando alimento e Wood no banco"
                stats.lastEvent = "preflight Roast Pit • World/bank_shop"
                updateContinuedProcessingProgress(forceTitleUpdate: true)

                try await engine.prepareRoastPitLoadoutFromWorld(goal: runGoal)
                guard activeRunID == runID, !terminalFailureHandled else { return }

                diagnostic("[ROAST] preflight World concluído • encerrando Presence bancária antes do Pond")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityBootstrap = AutomationEngine.bootstrap(for: .roastPit)
                state = .connecting
                statusMessage = "Conectando ao Pond"
                stats.lastEvent = "handoff Roast Pit • pond"
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
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = await makeReceiverTask(
                    stream: activityStream,
                    engine: activityEngine,
                    mode: mode,
                    runID: runID
                )
                connected = true
                state = .syncing
                statusMessage = "Sincronizando Roast Pit no Pond"
                log("🔥 Presence World encerrada • nova Presence pond aberta no mesmo shard \(selectedShard)")
                await activityEngine.prepareIdentity()
                guard activeRunID == runID else { return }
            }


            if mode == .blacksmith {
                state = .syncing
                statusMessage = "⚒️ Preparando Frostmere Smith no banco"
                stats.lastEvent = "preflight Frostmere Smith • World/bank_shop"
                updateContinuedProcessingProgress(forceTitleUpdate: true)

                try await engine.prepareBlacksmithLoadoutFromWorld(goal: runGoal)
                guard activeRunID == runID, !terminalFailureHandled else { return }

                diagnostic("[SMITH] preflight World concluído • encerrando Presence bancária antes de Frostmere")
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                await socket.close()
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityBootstrap = AutomationEngine.bootstrap(for: .blacksmith)
                state = .connecting
                statusMessage = "Conectando a Frostmere"
                stats.lastEvent = "handoff Frostmere Smith • frostmere"
                updateContinuedProcessingProgress()

                let activityStream = try await socket.connect(session: session, shard: selectedShard, bootstrap: activityBootstrap)
                await importSocketTrace()
                guard activeRunID == runID else { return }

                let activityEngine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: selectedShard,
                    bootstrap: activityBootstrap,
                    fishingBait: selectedFishingBait,
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = await makeReceiverTask(stream: activityStream, engine: activityEngine, mode: mode, runID: runID)
                connected = true
                state = .syncing
                statusMessage = "Sincronizando Frostmere Smith"
                log("⚒️ Presence World encerrada • nova Presence frostmere aberta no mesmo shard \(selectedShard)")
                await activityEngine.prepareIdentity()
                guard activeRunID == runID else { return }
            }

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
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = await makeReceiverTask(
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
                var initialDunesHPHandoff: Int?
                if mode.isDunesGathering {
                    let dunesLoadout = try await engine.prepareDunesLoadoutFromWorld(for: mode)
                    initialDunesHPHandoff = await engine.latestTrustedHPForHandoff()
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
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    inheritedPlayerHP: initialDunesHPHandoff,
                    reporter: engineReporter(runID: runID)
                )
                engine = activityEngine
                activeEngine = activityEngine
                receiverTask = await makeReceiverTask(
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
            } else if mode.resumesAfterSafeRealtimeLoss {
                result = try await runSafeModeWithPresenceRecovery(
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
                case .dunesToolRotation:
                    statusMessage = "Sem ferramenta Dunes com durabilidade >100"
                    stats.lastEvent = "rotação de ferramenta indisponível"
                    log("🧰 Dunes • nenhuma ferramenta compatível com durabilidade >100 • progresso \(stats.successes)/\(sessionGoal) preservado")
                    logSessionSummary(mode: mode, outcome: "SEM FERRAMENTA SEGURA")
                    finishContinuedProcessing(success: false, reason: "sem ferramenta Dunes com durabilidade segura")
                case .user, .none:
                    statusMessage = mode.supportsAtomicStop
                        ? "Atividade encerrada após operação atual"
                        : "Atividade encerrada com segurança"
                    stats.lastEvent = "atividade cancelada pelo usuário"
                    if mode.supportsAtomicStop {
                        log("STOP confirmado • operação em andamento reconciliada • nenhuma nova operação será iniciada")
                        logSessionSummary(mode: mode, outcome: "STOP ATÔMICO")
                    } else {
                        let destination = mode.isDunesGathering ? "The Shores" : "World"
                        log("STOP confirmado — \(destination) seguro e nenhuma nova ação será enviada")
                        logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                    }
                    finishContinuedProcessing(success: false, reason: "interrompida com segurança")
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
               mode.isDunesGathering,
               let shard = activeShard {
                log("💀 Dunes • respawn/full-loot confirmado fora do checkpoint • \(detail) • progresso \(stats.successes)/\(runGoal) preservado")
                requestGatherConnectionRecovery(
                    reason: "respawn/full-loot confirmado: \(detail)",
                    runID: runID
                )
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
            if let engineError = error as? EngineError,
               case .playerDead = engineError,
               mode.isWildCombat,
               let shard = activeShard {
                log("💀 \(mode.localizedTitle) • morte detectada • aguardando respawn autoritativo para continuar \(stats.successes)/\(runGoal)")
                requestWildConnectionRecovery(
                    reason: "morte detectada no Wild • aguardando respawn",
                    runID: runID
                )
                await socket.close()
                _ = await recoverWildAfterUnexpectedDisconnect(mode: mode, runID: runID, shard: shard, cookie: cookie)
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

        if mode.resumesAfterSafeRealtimeLoss {
            requestSafeConnectionRecovery(reason: reason, runID: runID)
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

    private func requestSafeConnectionRecovery(reason: String, runID: UUID) {
        guard activeRunID == runID,
              let mode = activity,
              mode.resumesAfterSafeRealtimeLoss,
              !terminalFailureHandled else { return }

        if !connectionRecoveryRequested {
            connectionRecoveryDetail = reason
            diagnostic("[WARN] \(reason) • \(mode.localizedTitle): retomada segura no mesmo shard solicitada")
            log("⚠️ Conexão perdida em \(mode.localizedTitle) • progresso confirmado preservado • reconectando no mesmo shard")
        }
        connectionRecoveryRequested = true
        connected = false
        state = .recovering
        statusMessage = "Conexão perdida • retomando \(mode.localizedTitle)"
        stats.lastEvent = "reconexão segura • \(mode.localizedTitle)"
        updateContinuedProcessingProgress(forceTitleUpdate: true)
        engineRunTask?.cancel()
        receiverTask?.cancel()
    }

    private func runSafeModeWithPresenceRecovery(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        initialEngine: AutomationEngine,
        runGoal: Int
    ) async throws -> EngineRunResult {
        var phaseEngine = initialEngine
        var completedBeforePhase = stats.successes
        var recoveryCount = 0
        let started = Date()
        let recoveryDeadline: TimeInterval = 300
        let anchor = await phaseEngine.makeRecoveryProgressAnchor(for: mode)

        while completedBeforePhase < runGoal {
            guard activeRunID == runID, activity == mode, !terminalFailureHandled else {
                throw CancellationError()
            }

            if requestedStopReason == .user {
                return EngineRunResult(
                    successes: completedBeforePhase,
                    completedGoal: false,
                    stoppedSafely: true,
                    stopReason: .user
                )
            }

            let remaining = max(1, runGoal - completedBeforePhase)
            do {
                let engineForPhase = phaseEngine
                let offset = completedBeforePhase
                let child = Task.detached(priority: .userInitiated) {
                    try await engineForPhase.run(
                        mode: mode,
                        goal: remaining,
                        successOffset: offset,
                        displayGoal: runGoal
                    )
                }
                engineRunTask = child
                let phaseResult = try await child.value
                engineRunTask = nil
                await importSocketTrace()
                await Task.yield()
                guard activeRunID == runID, activity == mode else { throw CancellationError() }

                let total = max(stats.successes, completedBeforePhase + phaseResult.successes)
                stats.successes = total
                return EngineRunResult(
                    successes: total,
                    completedGoal: total >= runGoal,
                    stoppedSafely: phaseResult.stoppedSafely,
                    stopReason: phaseResult.stopReason
                )
            } catch let EngineError.fishingPresenceStalled(phaseSuccesses) {
                engineRunTask = nil
                completedBeforePhase = max(stats.successes, completedBeforePhase + phaseSuccesses)
                stats.successes = completedBeforePhase
                connectionRecoveryRequested = true
                connectionRecoveryDetail = "Presence de pesca sem fish_bite autoritativo"
                log("🔄 Pesca • Presence estagnada • progresso \(completedBeforePhase)/\(runGoal) preservado • renovando no mesmo shard")
            } catch is CancellationError {
                engineRunTask = nil
                guard connectionRecoveryRequested,
                      activeRunID == runID,
                      activity == mode,
                      !terminalFailureHandled
                else { throw CancellationError() }
            } catch {
                engineRunTask = nil
                let disconnectDetail = await socket.disconnectReason()
                guard connectionRecoveryRequested || disconnectDetail != nil else { throw error }
                if !connectionRecoveryRequested {
                    requestSafeConnectionRecovery(
                        reason: disconnectDetail.map { "Conexão realtime perdida: \($0)" } ?? error.localizedDescription,
                        runID: runID
                    )
                }
            }

            guard Date().timeIntervalSince(started) < recoveryDeadline else {
                throw EngineError.regionNotConfirmed("realtime não recuperou em \(Int(recoveryDeadline))s")
            }

            recoveryCount += 1
            let waitSeconds = min(6.0, 1.0 + Double(max(0, recoveryCount - 1)) * 0.5)
            receiverTask?.cancel()
            receiverTask = nil
            activeEngine = nil
            connected = false
            await socket.close()
            try await Task.sleep(for: .seconds(waitSeconds))

            guard activeRunID == runID, activity == mode, !terminalFailureHandled else {
                throw CancellationError()
            }

            let bootstrap = AutomationEngine.bootstrap(for: mode, fishingBait: selectedFishingBait)
            state = .connecting
            statusMessage = "Reconectando \(mode.localizedTitle)"
            stats.lastEvent = "recovery realtime #\(recoveryCount)"
            updateContinuedProcessingProgress(forceTitleUpdate: true)

            do {
                let stream = try await socket.connect(session: session, shard: shard, bootstrap: bootstrap)
                let replacement = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: shard,
                    bootstrap: bootstrap,
                    fishingBait: selectedFishingBait,
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                phaseEngine = replacement
                activeEngine = replacement
                receiverTask = await makeReceiverTask(stream: stream, engine: replacement, mode: mode, runID: runID)
                connected = true
                await replacement.prepareIdentity()

                if let anchor,
                   let inferred = await replacement.inferredCompletedSuccesses(from: anchor) {
                    let reconciled = min(runGoal, max(stats.successes, inferred))
                    if reconciled > stats.successes {
                        let delta = reconciled - stats.successes
                        stats.successes = reconciled
                        if mode == .blacksmith {
                            switch selectedBlacksmith {
                            case .smith(let recipe, let batch, _):
                                let units = recipe.stackable ? BlacksmithProtocolPolicy.normalizedBatchQuantity(batch) : 1
                                stats.smithProduced += delta * units
                            case .repair:
                                stats.smithRepairs = max(stats.smithRepairs, reconciled)
                            }
                        }
                        log("✅ Recovery autoritativo • servidor confirmou +\(delta) operação(ões) durante a queda • progresso \(reconciled)/\(runGoal)")
                    }
                }

                completedBeforePhase = stats.successes
                connectionRecoveryRequested = false
                connectionRecoveryDetail = nil
                state = .syncing
                statusMessage = "\(mode.localizedTitle) • Presence recuperada"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                log("✅ \(mode.localizedTitle) • nova Presence \(bootstrap.region) ativa no mesmo shard \(shard) • retomando em \(completedBeforePhase)/\(runGoal)")

                if requestedStopReason == .user {
                    return EngineRunResult(
                        successes: completedBeforePhase,
                        completedGoal: false,
                        stoppedSafely: true,
                        stopReason: .user
                    )
                }
            } catch {
                await importSocketTrace()
                connectionRecoveryRequested = true
                connectionRecoveryDetail = error.localizedDescription
                diagnostic("[WARN] Recovery \(mode.localizedTitle) #\(recoveryCount) falhou: \(error.localizedDescription)")
                continue
            }
        }

        return EngineRunResult(successes: completedBeforePhase, completedGoal: true, stoppedSafely: false, stopReason: nil)
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
                diagnostic("[WARN] \(reason) • Dunes: reconexão de segurança antes da retomada")
                log("⚠️ Conexão perdida nas Dunes • pausando coleta • primeiro confirmará The Shores/respawn e depois retomará a mesma meta")
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

    private func continueDunesSessionAfterEmergencyBoundary(
        mode: ActivityMode,
        runID: UUID,
        shard: String,
        cookie: String,
        runGoal: Int,
        outcome: EmergencyDunesExitResult,
        recoveryEngine: AutomationEngine
    ) async throws -> EngineRunResult {
        guard activeRunID == runID, activity == mode, mode.isDunesGathering else {
            throw CancellationError()
        }

        let preserved = stats.successes
        let inheritedHP = await recoveryEngine.latestTrustedHPForHandoff()

        switch outcome {
        case .respawnConfirmed(let detail):
            state = .recovering
            statusMessage = "Respawn confirmado • reconstruindo fluxo"
            stats.lastEvent = "Dunes • respawn confirmado após reconexão"
            log("💀 Dunes • respawn/full-loot confirmado após queda • \(detail)")
            log("🔄 Dunes • progresso \(preserved)/\(runGoal) preservado • reconstruindo banco, ferramenta e HP para continuar")
        case .alreadySafe, .shoresSafe:
            state = .recovering
            statusMessage = "The Shores segura • retomando sessão"
            stats.lastEvent = "Dunes • sobrevivência confirmada após reconexão"
            log("🛡️ Dunes • sobrevivência confirmada após queda • progresso \(preserved)/\(runGoal) preservado • sessão continuará")
        }

        receiverTask?.cancel()
        receiverTask = nil
        activeEngine = nil
        connected = false
        await socket.close()
        await importSocketTrace()
        dunesPresencePhase = .preflightSafe

        if requestedStopReason == .user {
            return EngineRunResult(
                successes: preserved,
                completedGoal: false,
                stoppedSafely: true,
                stopReason: .user
            )
        }
        if preserved >= runGoal {
            return EngineRunResult(
                successes: preserved,
                completedGoal: true,
                stoppedSafely: false,
                stopReason: nil
            )
        }

        state = .connecting
        statusMessage = "Recovery Dunes • protegendo e reconstruindo loadout"
        stats.lastEvent = "recovery Dunes • World/bank"
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
            roastMode: selectedRoastMode,
            blacksmithSelection: selectedBlacksmith,
            inheritedPlayerHP: inheritedHP,
            reporter: engineReporter(runID: runID)
        )
        activeEngine = bankEngine
        receiverTask = await makeReceiverTask(
            stream: bankStream,
            engine: bankEngine,
            mode: mode,
            runID: runID
        )
        connected = true
        await bankEngine.prepareIdentity()

        let loadout: (tool: String, healthPotionPlus: Int, toolIdentity: DunesToolInstanceIdentity, lifeEpoch: Int)
        do {
            loadout = try await bankEngine.prepareDunesLoadoutFromWorld(for: mode)
        } catch let EngineError.gatherLoadoutNotReady(detail) {
            log("🧰 Dunes recovery • \(detail) • progresso \(preserved)/\(runGoal) preservado no World/Bank")
            receiverTask?.cancel()
            receiverTask = nil
            activeEngine = nil
            connected = false
            await socket.close()
            await importSocketTrace()
            return EngineRunResult(
                successes: preserved,
                completedGoal: false,
                stoppedSafely: true,
                stopReason: .dunesToolRotation
            )
        }

        dunesExpectedTool = loadout.toolIdentity
        dunesExpectedLifeEpoch = loadout.lifeEpoch
        player.lifeEpoch = max(player.lifeEpoch, loadout.lifeEpoch)
        let reentryHP = await bankEngine.latestTrustedHPForHandoff()
        let toolName = ActivityToolPolicy.displayName(loadout.tool)
        log("🏦 Dunes recovery • BANK-FIRST concluído • \(toolName) pronta • HP World confirmado • retomando \(preserved)/\(runGoal)")

        if requestedStopReason == .user {
            receiverTask?.cancel()
            receiverTask = nil
            activeEngine = nil
            connected = false
            await socket.close()
            await importSocketTrace()
            return EngineRunResult(
                successes: preserved,
                completedGoal: false,
                stoppedSafely: true,
                stopReason: .user
            )
        }

        receiverTask?.cancel()
        receiverTask = nil
        activeEngine = nil
        connected = false
        await socket.close()
        await importSocketTrace()

        let activityBootstrap = AutomationEngine.bootstrap(for: mode)
        dunesPresencePhase = .fullLootOrEntering
        state = .connecting
        statusMessage = "Recovery concluído • reentrando nas Dunes"
        stats.lastEvent = "Dunes recovery • nova Presence desert"
        updateContinuedProcessingProgress(forceTitleUpdate: true)

        let activityStream = try await socket.connect(
            session: session,
            shard: shard,
            bootstrap: activityBootstrap
        )
        await importSocketTrace()
        guard activeRunID == runID, activity == mode else { throw CancellationError() }

        if requestedStopReason == .user {
            await socket.close()
            dunesPresencePhase = .preflightSafe
            return EngineRunResult(
                successes: preserved,
                completedGoal: false,
                stoppedSafely: true,
                stopReason: .user
            )
        }

        let activityEngine = AutomationEngine(
            socket: socket,
            cookie: cookie,
            shard: shard,
            bootstrap: activityBootstrap,
            fishingBait: selectedFishingBait,
            roastMode: selectedRoastMode,
            blacksmithSelection: selectedBlacksmith,
            inheritedPlayerHP: reentryHP,
            reporter: engineReporter(runID: runID)
        )
        activeEngine = activityEngine
        receiverTask = await makeReceiverTask(
            stream: activityStream,
            engine: activityEngine,
            mode: mode,
            runID: runID
        )
        connected = true
        connectionRecoveryRequested = false
        connectionRecoveryDetail = nil
        state = .syncing
        statusMessage = "Dunes recuperada • retomando coleta"
        stats.lastEvent = "Dunes • coleta retomada após recovery"
        await activityEngine.prepareIdentity()
        log("✅ Dunes recovery concluído • nova Presence desert no mesmo shard \(shard) • retomando em \(preserved)/\(runGoal)")

        return try await runDunesCheckpointed(
            mode: mode,
            runID: runID,
            shard: shard,
            cookie: cookie,
            initialEngine: activityEngine,
            runGoal: runGoal
        )
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
        let recoveryDeadline: TimeInterval = 300
        var attempt = 0

        // Build 6: an active full-loot Dunes session has no client-side recovery
        // deadline. If connectivity is absent we keep the session/progress alive
        // and retry until the server is reachable (or the user explicitly STOPs).
        while mode.isDunesGathering || Date().timeIntervalSince(started) < recoveryDeadline {
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
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                activeEngine = engine
                receiverTask = await makeReceiverTask(
                    stream: stream,
                    engine: engine,
                    mode: mode,
                    runID: runID
                )
                await engine.prepareIdentity()

                // Full-loot recovery is a safety boundary, not a terminal
                // session outcome. Confirm Shores/respawn first, then rebuild
                // World/bank loadout and continue the same session goal.
                if mode.isDunesGathering {
                    connected = true
                    state = .recovering
                    statusMessage = "Reconectado • verificando The Shores/respawn"
                    stats.lastEvent = "Dunes • recovery de segurança"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    log("🔁 Conexão restaurada no \(shard) • prioridade: confirmar sobrevivência/respawn antes de retomar")

                    let outcome = try await engine.runEmergencyDunesExit(
                        reason: requestedStopReason == .user ? "STOP após perda de conexão" : "perda de conexão",
                        expectedTool: dunesExpectedTool,
                        expectedLifeEpoch: dunesExpectedLifeEpoch,
                        allowInconclusiveSurvivalAfterConfirmedShores: requestedStopReason == .user
                    )
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil

                    let result = try await continueDunesSessionAfterEmergencyBoundary(
                        mode: mode,
                        runID: runID,
                        shard: shard,
                        cookie: cookie,
                        runGoal: runGoal,
                        outcome: outcome,
                        recoveryEngine: engine
                    )
                    stats.successes = max(stats.successes, result.successes)

                    if result.completedGoal || stats.successes >= runGoal {
                        await closeDunesPresenceAfterConfirmedShores()
                        connectionRecoveryRequested = false
                        connectionRecoveryDetail = nil
                        currentTarget = nil
                        activity = nil
                        state = .completed
                        statusMessage = "Meta concluída"
                        stats.lastEvent = "meta concluída após recovery Dunes"
                        updateContinuedProcessingProgress(forceTitleUpdate: true)
                        log("✅ Meta concluída: \(stats.successes)/\(runGoal) • sessão Dunes continuou após recovery")
                        logSessionSummary(mode: mode, outcome: "META CONCLUÍDA APÓS RECOVERY")
                        finishContinuedProcessing(success: true, reason: "meta concluída após recovery Dunes")
                        return true
                    }

                    if result.stoppedSafely {
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        await importSocketTrace()
                        connectionRecoveryRequested = false
                        connectionRecoveryDetail = nil
                        currentTarget = nil
                        activity = nil
                        state = .cancelled
                        switch result.stopReason {
                        case .user:
                            statusMessage = "Atividade encerrada com segurança"
                            stats.lastEvent = "STOP após recovery Dunes"
                            log("STOP confirmado • recovery terminou em área segura • nenhuma nova ação será enviada")
                            logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                            finishContinuedProcessing(success: false, reason: "STOP seguro após recovery")
                        case .dunesToolRotation:
                            statusMessage = "Sem ferramenta Dunes segura"
                            stats.lastEvent = "recovery sem ferramenta segura"
                            log("🧰 Dunes • recovery não encontrou ferramenta compatível segura • progresso \(stats.successes)/\(runGoal) preservado")
                            logSessionSummary(mode: mode, outcome: "SEM FERRAMENTA SEGURA")
                            finishContinuedProcessing(success: false, reason: "sem ferramenta Dunes segura")
                        default:
                            statusMessage = "Recovery Dunes encerrado em segurança"
                            stats.lastEvent = "recovery Dunes encerrado"
                            logSessionSummary(mode: mode, outcome: "RECOVERY ENCERRADO EM SEGURANÇA")
                            finishContinuedProcessing(success: false, reason: "recovery Dunes encerrado")
                        }
                        return true
                    }

                    throw EngineError.gatherEndedBeforeGoal
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
                    try await engine.run(
                        mode: mode,
                        goal: phaseGoal,
                        successOffset: completedBeforePhase,
                        displayGoal: runGoal
                    )
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
                    log("💀 Dunes • respawn detectado durante recovery • \(detail) • sessão permanece ativa")
                    connectionRecoveryRequested = true
                    connectionRecoveryDetail = "respawn durante recovery: \(detail)"
                    await socket.close()
                    continue
                }

                if let engineError = error as? EngineError,
                   case .dunesExitSurvivalUnconfirmed(let detail) = engineError,
                   mode.isDunesGathering,
                   requestedStopReason == .user {
                    terminalFailureHandled = true
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    currentTarget = nil
                    activity = nil
                    state = .cancelled
                    statusMessage = "STOP • The Shores alcançada"
                    stats.lastEvent = "STOP encerrado após Shores inconclusiva"
                    log("🛑 STOP • The Shores alcançada; verificação auxiliar inconclusiva (\(detail)) • nenhuma nova Presence desert será aberta")
                    logSessionSummary(mode: mode, outcome: "STOP • SHORES")
                    finishContinuedProcessing(success: false, reason: "STOP após The Shores")
                    await socket.close()
                    return true
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
        let deathRecovery = lower.contains("morte") || lower.contains("respawn")

        if !connectionRecoveryRequested {
            connectionRecoveryDetail = reason
            diagnostic("[WARN] \(reason) • Wilderness: reconexão de emergência solicitada")
            if deathRecovery {
                log("💀 Morte/respawn em verificação no Wild • ataques suspensos • progresso preservado • recovery continuará até reconstruir o fluxo")
            } else if worldVerification {
                log("🔎 Saída para World sem confirmação • nenhum novo ataque será enviado • verificando região por reconexão")
            } else if degradedPresence {
                log("⚠️ Presence degradada no Wild • ataques suspensos • reconectando para confirmar estado e sair com segurança")
            } else {
                log("⚠️ Conexão perdida no Wild • nenhum novo ataque será enviado • aguardando rede para retornar ao World e continuar a meta")
            }
        }
        connectionRecoveryRequested = true
        connected = false
        state = .recovering
        if requestedStopReason == .user {
            statusMessage = "STOP • aguardando rede para saída segura"
        } else if deathRecovery {
            statusMessage = "Aguardando respawn • sessão preservada"
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
        cookie: String,
        confirmedWorldBoundary: Bool = false
    ) async -> Bool {
        guard activeRunID == runID, mode.isWildCombat else { return false }
        guard !connectionRecoveryInProgress else { return false }
        connectionRecoveryInProgress = true
        defer { connectionRecoveryInProgress = false }

        engineRunTask = nil
        receiverTask?.cancel()
        receiverTask = nil
        await socket.close()

        var attempt = 0
        var worldBoundaryAlreadyConfirmed = confirmedWorldBoundary

        // Build 7: a safe World boundary reached by the operational failsafe can
        // jump directly to reconstruction. Do not bootstrap a fake Wild recovery
        // Presence after the server already confirmed that the player is safe.
        // Network loss or a confirmed death remains a recovery boundary, not
        // a terminal session outcome. Keep retrying while this run is still the
        // active one. A user STOP still waits for the same safe World boundary.
        while activeRunID == runID,
              activity == mode,
              !terminalFailureHandled {
            attempt += 1
            state = .recovering
            statusMessage = requestedStopReason == .user
                ? "STOP • recuperando World seguro"
                : "Reconectando Wild • tentativa \(attempt)"
            stats.lastEvent = "recovery Wild \(attempt)"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[NET] Recovery Wild • \(shard) • tentativa \(attempt) • progresso=\(stats.successes)/\(sessionGoal)")

            do {
                let outcome: EmergencyWildExitResult

                if worldBoundaryAlreadyConfirmed {
                    worldBoundaryAlreadyConfirmed = false
                    outcome = .alreadyWorld
                    diagnostic("[WILD][RECOVERY] World já confirmado pela Presence anterior • pulando bootstrap Wild de verificação")
                    log("🛡️ Wild recovery • World seguro já confirmado • reconstruindo fluxo sem reabrir Wilderness prematuramente")
                } else {
                    let recoveryRegion = player.region.lowercased().hasPrefix("wild") ? player.region : "wild"
                    let recoveryBootstrap = PresenceBootstrap(
                        region: recoveryRegion,
                        position: player.position,
                        lifeEpoch: max(1, player.lifeEpoch)
                    )

                    let stream = try await socket.connect(session: session, shard: shard, bootstrap: recoveryBootstrap)
                    await importSocketTrace()
                    guard activeRunID == runID, activity == mode else { return false }

                    let recoveryEngine = AutomationEngine(
                        socket: socket,
                        cookie: cookie,
                        shard: shard,
                        bootstrap: recoveryBootstrap,
                        fishingBait: selectedFishingBait,
                        roastMode: selectedRoastMode,
                        blacksmithSelection: selectedBlacksmith,
                        reporter: engineReporter(runID: runID)
                    )
                    activeEngine = recoveryEngine
                    await recoveryEngine.prepareIdentity()

                    receiverTask?.cancel()
                    receiverTask = await makeReceiverTask(
                        stream: stream,
                        engine: recoveryEngine,
                        mode: mode,
                        runID: runID,
                        notifyUnexpectedEnd: false
                    )

                    connected = true
                    statusMessage = "Reconectado • confirmando sobrevivência/respawn"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    log("🔁 Conexão Wild restaurada no \(shard) • confirmando World/respawn antes de retomar")

                    outcome = try await recoveryEngine.runEmergencyWildExit(
                        mode: mode,
                        reason: requestedStopReason == .user ? "STOP após recovery" : "recovery de sessão"
                    )

                    receiverTask?.cancel()
                    receiverTask = nil
                    activeEngine = nil
                    connected = false
                    await importSocketTrace()
                    await socket.close()
                    await importSocketTrace()
                }

                if WildRecoveryContinuationPolicy.shouldKeepWaitingForRespawn(after: outcome) {
                    connectionRecoveryRequested = true
                    connectionRecoveryDetail = "morte observada; respawn ainda não confirmado"
                    state = .recovering
                    statusMessage = "Morte detectada • aguardando respawn"
                    stats.lastEvent = "Wild • aguardando respawn"
                    log("💀 Wild • morte observada, mas respawn ainda não confirmou HP positivo • progresso \(stats.successes)/\(sessionGoal) preservado • tentando novamente")
                    let wait = min(6.0, 1.5 + Double(attempt) * 0.5)
                    try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
                    continue
                }

                guard WildRecoveryContinuationPolicy.shouldResume(after: outcome) else {
                    connectionRecoveryRequested = true
                    continue
                }

                switch outcome {
                case .respawnConfirmed:
                    log("♻️ Wild • respawn confirmado • reconstruindo banco, espada, poções e vitais • sessão continuará em \(stats.successes)/\(sessionGoal)")
                case .alreadyWorld:
                    log("🛡️ Wild • personagem vivo já estava no World • sessão continuará em \(stats.successes)/\(sessionGoal)")
                case .worldSafe:
                    log("🛡️ Wild • saída segura para World confirmada após recovery • sessão continuará em \(stats.successes)/\(sessionGoal)")
                case .dead:
                    break
                }

                if requestedStopReason == .user {
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    currentTarget = nil
                    activity = nil
                    state = .cancelled
                    statusMessage = "Atividade encerrada com segurança"
                    stats.lastEvent = "STOP • World seguro após recovery"
                    log("STOP confirmado • World/respawn seguro confirmado • nenhuma nova ação será enviada")
                    logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                    finishContinuedProcessing(success: false, reason: "STOP seguro após recovery Wild")
                    return true
                }

                let preserved = stats.successes
                if preserved >= sessionGoal {
                    connectionRecoveryRequested = false
                    connectionRecoveryDetail = nil
                    currentTarget = nil
                    activity = nil
                    state = .completed
                    statusMessage = "Meta concluída"
                    updateContinuedProcessingProgress(forceTitleUpdate: true)
                    log("✅ Meta concluída: \(preserved)/\(sessionGoal) • confirmada após recovery Wild")
                    logSessionSummary(mode: mode, outcome: "META CONCLUÍDA APÓS RECOVERY")
                    finishContinuedProcessing(success: true, reason: "meta concluída após recovery Wild")
                    return true
                }

                // Start a completely fresh World Presence on the same shard.
                // runWild will re-run BANK-FIRST, select/equip the best sword,
                // replenish potions/vitals and enter Wilderness again.
                let worldBootstrap = AutomationEngine.bootstrap(for: mode)
                state = .connecting
                statusMessage = "Recovery concluído • reconstruindo combate"
                stats.lastEvent = "Wild recovery • World/bank"
                updateContinuedProcessingProgress(forceTitleUpdate: true)

                let worldStream = try await socket.connect(
                    session: session,
                    shard: shard,
                    bootstrap: worldBootstrap
                )
                await importSocketTrace()
                guard activeRunID == runID, activity == mode else { return false }

                let resumedEngine = AutomationEngine(
                    socket: socket,
                    cookie: cookie,
                    shard: shard,
                    bootstrap: worldBootstrap,
                    fishingBait: selectedFishingBait,
                    roastMode: selectedRoastMode,
                    blacksmithSelection: selectedBlacksmith,
                    reporter: engineReporter(runID: runID)
                )
                activeEngine = resumedEngine
                receiverTask = await makeReceiverTask(
                    stream: worldStream,
                    engine: resumedEngine,
                    mode: mode,
                    runID: runID
                )
                connected = true
                await resumedEngine.prepareIdentity()

                connectionRecoveryRequested = false
                connectionRecoveryDetail = nil
                state = .syncing
                statusMessage = "\(mode.localizedTitle) • retomando \(preserved)/\(sessionGoal)"
                stats.lastEvent = "Wild • sessão retomada"
                updateContinuedProcessingProgress(forceTitleUpdate: true)
                log("✅ Wild recovery concluído • nova Presence World no mesmo shard \(shard) • retomando meta em \(preserved)/\(sessionGoal)")

                let remaining = max(1, sessionGoal - preserved)
                let child = Task.detached(priority: .userInitiated) {
                    try await resumedEngine.run(mode: mode, goal: remaining)
                }
                engineRunTask = child

                do {
                    let phaseResult = try await child.value
                    engineRunTask = nil
                    await importSocketTrace()
                    await Task.yield()
                    guard activeRunID == runID, activity == mode else { return false }

                    stats.successes = max(stats.successes, preserved + phaseResult.successes)

                    if phaseResult.completedGoal || stats.successes >= sessionGoal {
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        await importSocketTrace()
                        connectionRecoveryRequested = false
                        connectionRecoveryDetail = nil
                        currentTarget = nil
                        activity = nil
                        state = .completed
                        statusMessage = "Meta concluída"
                        updateContinuedProcessingProgress(forceTitleUpdate: true)
                        log("✅ Meta concluída: \(stats.successes)/\(sessionGoal) • combate retomado após recovery")
                        logSessionSummary(mode: mode, outcome: "META CONCLUÍDA APÓS RECOVERY")
                        finishContinuedProcessing(success: true, reason: "meta concluída após recovery Wild")
                        return true
                    }

                    if phaseResult.stoppedSafely,
                       phaseResult.stopReason == .user || requestedStopReason == .user {
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        await importSocketTrace()
                        connectionRecoveryRequested = false
                        connectionRecoveryDetail = nil
                        currentTarget = nil
                        activity = nil
                        state = .cancelled
                        statusMessage = "Atividade encerrada com segurança"
                        stats.lastEvent = "STOP seguro após retomada Wild"
                        logSessionSummary(mode: mode, outcome: "STOP SEGURO")
                        finishContinuedProcessing(success: false, reason: "STOP seguro após retomada Wild")
                        return true
                    }

                    // No terminal condition was requested and the goal remains:
                    // treat this as another recoverable boundary instead of
                    // silently ending the user's session.
                    connectionRecoveryRequested = true
                    connectionRecoveryDetail = "engine Wild encerrou antes da meta"
                    log("🔄 Wild • engine encerrou antes da meta sem STOP • progresso \(stats.successes)/\(sessionGoal) preservado • retomando recovery")
                    receiverTask?.cancel()
                    receiverTask = nil
                    activeEngine = nil
                    connected = false
                    await socket.close()
                    continue
                } catch is CancellationError {
                    engineRunTask = nil
                    await importSocketTrace()
                    if connectionRecoveryRequested,
                       activeRunID == runID,
                       activity == mode {
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        continue
                    }
                    return false
                } catch {
                    engineRunTask = nil
                    await importSocketTrace()

                    if let engineError = error as? EngineError,
                       case .playerDead = engineError {
                        log("💀 Wild • morte detectada durante retomada • progresso \(stats.successes)/\(sessionGoal) preservado • aguardando respawn")
                        connectionRecoveryRequested = true
                        connectionRecoveryDetail = "morte detectada durante retomada"
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        continue
                    }

                    let disconnectDetail = await socket.disconnectReason()
                    let isClosedSocket: Bool
                    if let socketError = error as? SocketError, case .notConnected = socketError {
                        isClosedSocket = true
                    } else {
                        isClosedSocket = false
                    }
                    if connectionRecoveryRequested || disconnectDetail != nil || isClosedSocket {
                        connectionRecoveryRequested = true
                        connectionRecoveryDetail = disconnectDetail ?? error.localizedDescription
                        receiverTask?.cancel()
                        receiverTask = nil
                        activeEngine = nil
                        connected = false
                        await socket.close()
                        continue
                    }

                    // Build 8: this catch already runs inside the single Wild
                    // recovery owner. Prove a safe boundary, then continue THIS
                    // loop. Never call a second recoverWild... from inside it.
                    let confirmedWorldBoundary = await containWildTerminalFailure(
                        mode: mode,
                        runID: runID,
                        shard: shard,
                        cookie: cookie,
                        engine: resumedEngine,
                        failure: error.localizedDescription,
                        resumeSessionAfterBoundary: false
                    )

                    guard activeRunID == runID, activity == mode else { return false }
                    connectionRecoveryRequested = true
                    connectionRecoveryDetail = confirmedWorldBoundary
                        ? "falha operacional contida; World confirmado dentro do recovery"
                        : "falha operacional durante recovery; reconexão continuará"
                    receiverTask?.cancel()
                    receiverTask = nil
                    activeEngine = nil
                    connected = false
                    await socket.close()
                    worldBoundaryAlreadyConfirmed = confirmedWorldBoundary
                    diagnostic(
                        confirmedWorldBoundary
                            ? "[WILD][RECOVERY] owner preservado • World confirmado • reconstruindo mesma sessão"
                            : "[WILD][RECOVERY] owner preservado • retomando verificação de rede/respawn"
                    )
                    continue
                }
            } catch is CancellationError {
                if activeRunID == runID,
                   activity == mode,
                   connectionRecoveryRequested {
                    receiverTask?.cancel()
                    receiverTask = nil
                    activeEngine = nil
                    connected = false
                    await socket.close()
                    continue
                }
                return false
            } catch {
                await importSocketTrace()
                receiverTask?.cancel()
                receiverTask = nil
                activeEngine = nil
                connected = false
                connectionRecoveryRequested = true
                connectionRecoveryDetail = error.localizedDescription
                await socket.close()
                let wait = min(6.0, 1.5 + Double(attempt) * 0.5)
                diagnostic("[WARN] Recovery Wild tentativa \(attempt) falhou: \(error.localizedDescription) • sessão permanece ativa")
                try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
            }
        }

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
            // Gathering subprogress comes from authoritative h/hm wear below.
            // Generic UI state changes must not fake work for the scheduler.
            if changed, activity?.isGathering != true {
                advanceContinuedProcessingSubprogress()
            }
            updateContinuedProcessingProgress()

        case .log(let message):
            if activity == .roastPit, message.hasPrefix("🎣 Spots do servidor:") {
                break
            }
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

        case .roastCountdown(let mode, let cycle, let goal, let secondsRemaining):
            stats.roastCycleRemaining = secondsRemaining
            state = .cooldown
            statusMessage = "🔥 \(mode.label) • \(secondsRemaining)s • ciclo \(cycle)/\(goal)"
            stats.lastEvent = secondsRemaining > 0
                ? "assando • \(secondsRemaining)s"
                : "confirmando resultado"
            updateContinuedProcessingProgress()

        case .roastResult(let mode, let cycle, let goal, let burned, let xpGained, let cookingXPTotal, _, _):
            stats.successes = max(stats.successes, cycle)
            stats.roastCycleRemaining = 0
            // Replacement engines restart their local counters after a realtime
            // recovery. Session counters are therefore accumulated here instead
            // of trusting phase-local totals.
            stats.roastCooked += burned ? 0 : 1
            stats.roastBurned += burned ? 1 : 0
            stats.roastLastXPGained = xpGained
            stats.roastSessionXPGained += xpGained
            stats.roastCookingXPTotal = cookingXPTotal
            continuedProgressSubunit = 0
            state = .acting
            statusMessage = burned
                ? "🔥 Queimou • +0 XP • Cooking \(cookingXPTotal)"
                : "✅ Assado • +\(xpGained) XP • Cooking \(cookingXPTotal)"
            stats.lastEvent = burned
                ? "\(mode.label) queimou • +0 XP"
                : "\(mode.label) assado • +\(xpGained) XP"
            updateContinuedProcessingProgress(forceTitleUpdate: true)

        case .smithPreflight(let recipe, let batch, let required):
            stats.smithBatchSize = batch
            stats.smithRecipeLabel = recipe.label
            stats.smithRequiredSummary = required.sorted { $0.key < $1.key }
                .map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) \($0.value)" }
                .joined(separator: " • ")
            statusMessage = "⚒️ \(recipe.label) ×\(batch) • preparando recursos"
            stats.lastEvent = "Precisa • \(stats.smithRequiredSummary)"
            updateContinuedProcessingProgress()

        case .smithBank(let recipe, let batch, let withdrawn, let remaining):
            stats.smithBatchSize = batch
            stats.smithRecipeLabel = recipe.label
            stats.smithBankRemainingSummary = remaining.sorted { $0.key < $1.key }
                .map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) \($0.value)" }
                .joined(separator: " • ")
            let withdrawnText = withdrawn
                .filter { $0.value > 0 }
                .sorted { $0.key < $1.key }
                .map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) \($0.value)" }
                .joined(separator: " • ")
            stats.lastEvent = withdrawnText.isEmpty ? "Banco • sem saque necessário" : "Saque • \(withdrawnText)"
            updateContinuedProcessingProgress()

        case .smithCountdown(let recipe, let completed, let goal, let batch, let secondsRemaining):
            stats.smithCycleRemaining = secondsRemaining
            stats.smithBatchSize = batch
            state = .cooldown
            statusMessage = "⚒️ \(recipe.label) ×\(batch) • \(secondsRemaining)s • \(completed)/\(goal)"
            stats.lastEvent = secondsRemaining > 0 ? "forjando • \(secondsRemaining)s" : "confirmando resultado"
            updateContinuedProcessingProgress()

        case .smithResult(let recipe, let completed, let goal, let produced, let inventoryTotal, let xpGained, let smithingXPTotal):
            stats.successes = max(stats.successes, completed)
            stats.smithCycleRemaining = 0
            stats.smithProduced += produced
            stats.smithLastXPGained = xpGained
            stats.smithSessionXPGained += xpGained
            stats.smithingXPTotal = smithingXPTotal
            stats.smithLastInventoryTotal = inventoryTotal
            state = .acting
            statusMessage = "✅ \(recipe.label) +\(produced) • Inv \(inventoryTotal) • +\(xpGained) XP"
            stats.lastEvent = "Inv \(recipe.label) \(inventoryTotal) • \(completed)/\(goal)"
            updateContinuedProcessingProgress(forceTitleUpdate: true)

        case .repairResult(let target, let durabilityAfter, let costs):
            stats.successes = max(stats.successes, 1)
            stats.smithRepairs += 1
            stats.smithCycleRemaining = 0
            state = .acting
            statusMessage = "✅ \(target.label) reparado • \(durabilityAfter)/\(target.maxDurability)"
            let costText = costs.sorted { $0.key < $1.key }.map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) -\($0.value)" }.joined(separator: " • ")
            stats.lastEvent = costText.isEmpty ? "Repair concluído" : "Repair • \(costText)"
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

        case .gatherProgress(let h, let hm):
            // Build 126: this event is authoritative and is intentionally allowed
            // through the BG headless gate. Keep its public text out of @Published
            // statusMessage so SwiftUI remains frozen, while the Dynamic Island
            // can still follow the live wear counter 1/6...6/6.
            continuedGatherStatus = GatherProgressPolicy.publicStatus(h: h, hm: hm)
            continuedProgressSubunit = max(
                continuedProgressSubunit,
                GatherProgressPolicy.continuedSubunit(h: h, hm: hm)
            )
            updateContinuedProcessingProgress(
                forceTitleUpdate: lastScenePhaseKey == "background"
            )

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

            if currentMode.resumesAfterSafeRealtimeLoss {
                requestSafeConnectionRecovery(reason: reason, runID: runID)
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
            if activity?.isGathering != true {
                advanceContinuedProcessingSubprogress()
            }
            updateContinuedProcessingProgress()

        case .stateConfirmedHit:
            stats.stateConfirmedHits += 1
            stats.lastEvent = "hit correlacionado por estado"
            if activity?.isGathering != true {
                advanceContinuedProcessingSubprogress()
            }
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

    /// Recebe as transições do SwiftUI. Na Build 127, áudio real mantém o runtime
    /// quando disponível; Continued Processing fornece integração/progresso do
    /// sistema e pode ser rearmado ao voltar ao foreground. `beginBackgroundTask`
    /// permanece somente como ponte curta.
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

            let headlessSafe = activity?.supportsBackgroundHeadless == true
            bgHeadlessActive = true
            bgHeadlessGate.set(enabled: true, suppressVisualEvents: headlessSafe)
            diagnostic("[BG][HEADLESS] ATIVO • UI/SceneKit/WebKit fora da hierarquia • logs bufferizados • eventos visuais \(headlessSafe ? "suprimidos em atividade segura" : "preservados por segurança")")

            let audioSnapshot = backgroundAudioRuntime.snapshot()
            diagnostic("[BG][AUDIO] entrada BG • \(audioSnapshot.summary)")
            if !audioSnapshot.active {
                let recovered = backgroundAudioRuntime.ensureActive(reason: "scene-background")
                diagnostic("[BG][AUDIO] recovery na entrada BG • sucesso=\(recovered ? "sim" : "não") • \(backgroundAudioRuntime.snapshot().summary)")
            }

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

            bgHeadlessActive = false
            bgHeadlessGate.set(enabled: false, suppressVisualEvents: false)
            flushBGHeadlessLogs()
            diagnostic("[BG][HEADLESS] INATIVO • UI reconstruída no foreground")
            if activity != nil {
                diagnostic("[BG][AUDIO] retorno FG • \(backgroundAudioRuntime.snapshot().summary)")
            }

            if activity != nil {
                if continuedTaskObject != nil {
                    diagnostic("[BG] App em primeiro plano • Continued Processing continua ativa")
                } else if continuedTaskRequested {
                    diagnostic("[BG] App em primeiro plano • engine continua na mesma sessão • Continued Processing ainda pendente")
                } else {
                    diagnostic("[BG] App em primeiro plano • engine continua na mesma sessão")
                }
                rearmContinuedProcessingForActiveSessionIfNeeded()
            }
            endLegacyBackgroundTask()

        case .inactive:
            break

        @unknown default:
            break
        }
    }

    private func rearmContinuedProcessingForActiveSessionIfNeeded() {
        guard #available(iOS 26.0, *), let mode = activity else { return }

        let audioSnapshot = backgroundAudioRuntime.snapshot()
        let shouldRearm = BackgroundRuntimePolicy.shouldRearmContinuedProcessing(
            hasActivity: true,
            hasContinuedTask: continuedTaskObject != nil,
            continuedTaskRequested: continuedTaskRequested,
            appIsActive: UIApplication.shared.applicationState == .active,
            audioAlive: audioSnapshot.active
        )
        guard shouldRearm else { return }

        // This is the same engine/run. Never reset stats, socket, target catalog
        // or sessionGoal here; only request a fresh system CP surface.
        continuedTaskMode = mode
        continuedTaskIdentifier = nil
        continuedTaskSubmissionAttempt = 0
        lastContinuedTitleSuccesses = -1
        lastContinuedPublicStatus = ""
        lastContinuedTitleUpdateAt = nil

        diagnostic("[BG] Rearmando Continued Processing para sessão existente • \(mode.localizedTitle) • \(stats.successes)/\(max(1, sessionGoal)) • áudio ativo")
        submitContinuedProcessingAttempt(
            for: mode,
            requestedGoal: min(100_000, max(1, sessionGoal)),
            attempt: 1
        )
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
        continuedGatherStatus = nil
        lastContinuedTitleSuccesses = -1
        lastContinuedPublicStatus = ""
        lastContinuedTitleUpdateAt = nil
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

        // Build 113: progress is cheap and updated whenever authoritative work
        // advances. The Dynamic Island/title surface is deliberately throttled:
        // repeatedly calling updateTitle for every preparing/waiting state was
        // unnecessary work on MainActor while iOS was already scheduling BG.
        let goalUnits = Int64(max(1, sessionGoal))
        let total = goalUnits * 100
        let successBase = Int64(min(max(0, stats.successes), max(1, sessionGoal))) * 100
        let completed = min(total, successBase + Int64(continuedProgressSubunit))
        backgroundTask.progress.totalUnitCount = total
        backgroundTask.progress.completedUnitCount = completed

        guard let mode = activity ?? continuedTaskMode else { return }
        let publicStatus: String
        if mode.isGathering, let continuedGatherStatus {
            publicStatus = continuedGatherStatus
        } else {
            publicStatus = displayStatusMessage
        }
        let successChanged = lastContinuedTitleSuccesses != stats.successes
        let statusChanged = lastContinuedPublicStatus != publicStatus
        let now = Date()
        let statusRefreshDue = statusChanged && (
            lastContinuedTitleUpdateAt == nil ||
            now.timeIntervalSince(lastContinuedTitleUpdateAt ?? .distantPast) >= 4.0
        )

        guard forceTitleUpdate || successChanged || statusRefreshDue else { return }

        backgroundTask.updateTitle(
            "Kintarabot • \(mode.localizedTitle)",
            subtitle: "\(stats.successes)/\(max(1, sessionGoal)) • \(publicStatus)"
        )
        lastContinuedTitleSuccesses = stats.successes
        lastContinuedPublicStatus = publicStatus
        lastContinuedTitleUpdateAt = now
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
        continuedGatherStatus = nil
        lastContinuedTitleUpdateAt = nil
        endLegacyBackgroundTask()
    }

    @available(iOS 26.0, *)
    private func handleContinuedProcessingExpiration(_ backgroundTask: BGContinuedProcessingTask) {
        guard continuedTaskObject === backgroundTask else {
            backgroundTask.setTaskCompleted(success: false)
            return
        }

        // Build 127: audio is the runtime authority for every mode. CP expiry
        // only removes the system/Dynamic Island lease; it no longer forces an
        // activity to stop when genuine playback is still alive.
        if let currentMode = activity {
            let before = backgroundAudioRuntime.snapshot()
            let audioAlive = before.active || backgroundAudioRuntime.ensureActive(reason: "continued-processing-expiration")
            let after = backgroundAudioRuntime.snapshot()

            diagnostic("[BG][AUDIO] CP expirou • antes={\(before.summary)} • depois={\(after.summary)} • continuidade=\(audioAlive ? "sim" : "não")")

            if BackgroundRuntimePolicy.preservesExecution(mode: currentMode, audioAlive: audioAlive) {
                continuedTaskActivationWatchdog?.cancel()
                continuedTaskActivationWatchdog = nil
                continuedTaskObject = nil
                continuedTaskRequested = false
                continuedTaskMode = currentMode
                continuedTaskIdentifier = nil
                continuedTaskSubmissionAttempt = 0
                lastContinuedTitleUpdateAt = nil

                backgroundTask.expirationHandler = nil
                backgroundTask.setTaskCompleted(success: false)
                endLegacyBackgroundTask()

                if currentMode.requiresSafeExit {
                    diagnostic("[BG] Continued Processing encerrou • sessão full-loot PRESERVADA pelo áudio • proteções HP/térmica/rede permanecem ativas")
                } else {
                    diagnostic("[BG] Continued Processing encerrou • sessão PRESERVADA pelo runtime de áudio • Presence/engine mantidas")
                }
                return
            }

            diagnostic("[BG] Continued Processing encerrou e áudio não permaneceu ativo • aplicando política segura de encerramento")
        }

        // Without genuine audio runtime, retain the existing full-loot fallback:
        // preserve emergency reconnection or cooperatively exit to a safe region.
        if activity?.requiresSafeExit == true, connectionRecoveryRequested {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            state = .recovering
            statusMessage = "Continued Processing encerrada • aguardando rede para saída segura"
            stats.lastEvent = activity?.isDunesGathering == true
                ? "encerramento externo durante reconexão Dunes"
                : "encerramento externo durante reconexão Wild"
            diagnostic("[BG] Encerramento externo sem áudio durante queda de conexão em região de risco • preservando reconexão de emergência")
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            return
        }

        if activity?.requiresSafeExit == true, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            let reason = requestedStopReason ?? .backgroundExpiration
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: reason)
            }
            state = .recovering
            statusMessage = activity?.isDunesGathering == true
                ? "Runtime de áudio indisponível • saída para The Shores"
                : "Runtime de áudio indisponível • saída imediata para o World"
            stats.lastEvent = "saída de emergência por perda do runtime"
            updateContinuedProcessingProgress(forceTitleUpdate: true)
            diagnostic("[BG] CP e áudio indisponíveis em região de risco • saída segura cooperativa solicitada")
            return
        }

        // O mesmo callback é usado pelo sistema para expiração real e para um
        // encerramento solicitado pela superfície de Continued Processing.
        // A API não informa qual ocorreu. Se também não há runtime de áudio,
        // preserve o cleanup terminal existente para atividades não full-loot.
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
        guard let currentMode = activity else { return }

        let before = backgroundAudioRuntime.snapshot()
        let audioAlive = before.active || backgroundAudioRuntime.ensureActive(reason: "legacy-background-expiration")
        let after = backgroundAudioRuntime.snapshot()
        diagnostic("[BG][AUDIO] Janela curta expirou • antes={\(before.summary)} • depois={\(after.summary)} • continuidade=\(audioAlive ? "sim" : "não")")

        if BackgroundRuntimePolicy.preservesExecution(mode: currentMode, audioAlive: audioAlive) {
            diagnostic("[BG] Janela curta UIKit encerrou • sessão PRESERVADA pelo runtime de áudio • \(currentMode.localizedTitle)")
            return
        }

        if currentMode.requiresSafeExit, connected, let activeEngine {
            if requestedStopReason == nil { requestedStopReason = .backgroundExpiration }
            let reason = requestedStopReason ?? .backgroundExpiration
            Task.detached(priority: .userInitiated) {
                await activeEngine.requestSafeStop(reason: reason)
            }
            state = .recovering
            statusMessage = currentMode.isDunesGathering
                ? "Background e áudio indisponíveis • saída para The Shores"
                : "Background e áudio indisponíveis • saída imediata para o World"
            stats.lastEvent = "saída de emergência por perda do runtime"
            let region = currentMode.isDunesGathering ? "Dunes" : "Wild"
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
        timestamped(value, at: .now)
    }

    private func timestamped(_ value: String, at date: Date) -> String {
        "\(date.formatted(date: .omitted, time: .standard))  \(value)"
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

private struct CharacterProfileHTTPClient {
    let cookie: String
    private let baseURL = URL(string: "https://kintara.com")!

    func get(_ path: String) async throws -> [String: Any] {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw CharacterProfileHTTPError.invalidURL
        }
        return try await request(url)
    }

    func post(_ path: String) async throws -> [String: Any] {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw CharacterProfileHTTPError.invalidURL
        }
        return try await request(url, method: "POST", body: Data("{}".utf8))
    }

    func playerStats(playerID: Int) async throws -> [String: Any] {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent("api/auth/player-stats"),
            resolvingAgainstBaseURL: false
        ) else {
            throw CharacterProfileHTTPError.invalidURL
        }
        components.queryItems = [URLQueryItem(name: "playerId", value: String(playerID))]
        guard let url = components.url else { throw CharacterProfileHTTPError.invalidURL }
        return try await request(url)
    }

    private func request(_ url: URL, method: String = "GET", body: Data? = nil) async throws -> [String: Any] {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpBody = body
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await URLSession(configuration: configuration).data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw CharacterProfileHTTPError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            throw CharacterProfileHTTPError.http(http.statusCode)
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CharacterProfileHTTPError.invalidPayload
        }
        return object
    }
}

private enum CharacterProfileHTTPError: LocalizedError {
    case invalidURL
    case invalidResponse
    case invalidPayload
    case http(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "URL de perfil inválida"
        case .invalidResponse: "Resposta de perfil inválida"
        case .invalidPayload: "Dados de perfil inválidos"
        case .http(let status): "Perfil retornou HTTP \(status)"
        }
    }
}

final class SessionManager {
    private let key = "kinttany.session.cookie"
    var cookie: String? { KeychainStore.get(key) }
    func save(cookie: String) { KeychainStore.set(key, cookie) }
    func clear() { KeychainStore.delete(key) }
}
