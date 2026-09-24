import Foundation

enum EngineEvent {
    case state(ActivityState, String)
    case log(String)
    case diagnostic(String)
    case target(String?)
    case attempt
    case success(String?)
    case roastCountdown(mode: RoastPitMode, cycle: Int, goal: Int, secondsRemaining: Int)
    case roastResult(mode: RoastPitMode, cycle: Int, goal: Int, burned: Bool, xpGained: Int, cookingXPTotal: Int, cookedCount: Int, burnedCount: Int)
    case smithPreflight(recipe: BlacksmithRecipe, batch: Int, required: [String: Int])
    case smithBank(recipe: BlacksmithRecipe, batch: Int, withdrawn: [String: Int], remaining: [String: Int])
    case smithCountdown(recipe: BlacksmithRecipe, completed: Int, goal: Int, batch: Int, secondsRemaining: Int)
    case smithResult(recipe: BlacksmithRecipe, completed: Int, goal: Int, produced: Int, inventoryTotal: Int, xpGained: Int, smithingXPTotal: Int)
    case repairResult(target: RepairTarget, durabilityAfter: Int, costs: [String: Int])
    case gatherSuccess(String?, absolute: Int)
    case gatherProgress(h: Int, hm: Int)
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
    case dunesExposure(tool: DunesToolInstanceIdentity, lifeEpoch: Int)
    case world(nodes: Int, mobs: Int, serverRegion: String?)
}

enum EngineStopReason: Equatable {
    case user
    case backgroundExpiration
    case connectionLoss
    case dunesCheckpoint
    case dunesHeatSafety
    case dunesDangerSafety
}

enum EmergencyWildExitResult: Equatable {
    case worldSafe
    case alreadyWorld
    case dead
}

enum EmergencyDunesExitResult: Equatable {
    case shoresSafe
    case alreadySafe
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

/// Build 74: Silver/Cacti are full-loot activities, so their loadout is always
/// prepared in a dedicated World/bank_shop Presence before the Dunes Presence
/// is opened. Even when the tool is already carried, BANK-FIRST and Health
/// Potion+ preparation still require bank_shop.
struct DunesWorldPreflightPolicy {
    static let bankBootstrap = PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))

    static func requiresWorldBankService(for mode: ActivityMode) -> Bool {
        mode.isDunesGathering
    }
}

/// Build 93: after every safe Dunes bank checkpoint, recover in the World
/// regeneration area captured from the official client before exposing the
/// full-loot loadout again. The capture traversed the regeneration area around
/// the World origin; use an interior point rather than an observed edge.
struct DunesWorldRecoveryPolicy {
    static let safePoint = Position(x: 0.5, z: 0.5)
    static let requiredHP = 100
    static let timeoutMS: Double = 45_000

    static func isRecovered(hp: Int) -> Bool {
        hp >= requiredHP
    }
}

struct DunesCheckpointContinuationPolicy {
    /// Build 95: an external-damage escape is terminal only if survival cannot
    /// be confirmed. Once The Shores + exposed tool are confirmed, reuse the
    /// normal protected checkpoint pipeline (bank → World HP recovery → Dunes).
    static func shouldResumeAfterSafeExit(_ reason: EngineStopReason?) -> Bool {
        reason == .dunesCheckpoint || reason == .dunesDangerSafety
    }

    static func triggerLabel(for reason: EngineStopReason?) -> String {
        switch reason {
        case .dunesDangerSafety:
            return "dano externo sobrevivido"
        case .dunesCheckpoint:
            return "180s de exposição"
        default:
            return "checkpoint seguro"
        }
    }
}


/// Build 76: full-loot loadouts preserve exactly one physical tool instance.
/// The activity tier/type is still selected by ActivityToolPolicy; among copies
/// of that same type, prefer the lowest positive durability that is already
/// carried. Only when none is carried do we select an exact bank slot.
struct DunesToolInstanceIdentity: Equatable {
    let type: String
    let iid: String?
    let durability: Int?
}

struct DunesToolInstanceSelection: Equatable {
    let type: String
    let iid: String?
    let durability: Int?
    let sourceKey: String
    let sourceIndex: Int

    var isCarried: Bool { sourceKey == "hotbar" || sourceKey == "invSlots" }
    var bankIndex: Int? { sourceKey == "bankSlots" ? sourceIndex : nil }
    var identity: DunesToolInstanceIdentity {
        DunesToolInstanceIdentity(type: type, iid: iid, durability: durability)
    }
}

struct DunesToolInstancePolicy {
    static func preferredInstance(in backpack: [String: Any], type: String) -> DunesToolInstanceSelection? {
        func candidates(in sourceKey: String) -> [DunesToolInstanceSelection] {
            guard let slots = backpack[sourceKey] as? [Any] else { return [] }
            return slots.enumerated().compactMap { index, raw in
                guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return nil }
                let durability = RealtimeProtocol.int(slot["d"] ?? slot["durability"])
                // A confirmed zero/negative durability is not intentionally exposed
                // to a full-loot realm. Unknown durability remains eligible.
                if let durability, durability <= 0 { return nil }
                return DunesToolInstanceSelection(
                    type: type,
                    iid: SaveBackpackConflictPolicy.normalizedIID(slot["iid"]),
                    durability: durability,
                    sourceKey: sourceKey,
                    sourceIndex: index
                )
            }
        }

        func best(_ values: [DunesToolInstanceSelection]) -> DunesToolInstanceSelection? {
            values.sorted { lhs, rhs in
                let ld = lhs.durability ?? Int.max
                let rd = rhs.durability ?? Int.max
                if ld != rd { return ld < rd }
                if lhs.sourceKey != rhs.sourceKey { return lhs.sourceKey < rhs.sourceKey }
                return lhs.sourceIndex < rhs.sourceIndex
            }.first
        }

        let carried = candidates(in: "hotbar") + candidates(in: "invSlots")
        if let selected = best(carried) { return selected }
        return best(candidates(in: "bankSlots"))
    }
}

struct BankDepositPreservationPolicy {
    static func matchesSelectedTool(_ slot: [String: Any], selected: DunesToolInstanceIdentity) -> Bool {
        guard slot["t"] as? String == selected.type else { return false }
        if let iid = selected.iid {
            return SaveBackpackConflictPolicy.normalizedIID(slot["iid"]) == iid
        }
        if let durability = selected.durability {
            return RealtimeProtocol.int(slot["d"] ?? slot["durability"]) == durability
        }
        return true
    }
}

struct DunesExitSurvivalPolicy {
    static func toolStillCarried(_ selected: DunesToolInstanceIdentity, in backpack: [String: Any]) -> Bool {
        for key in ["hotbar", "invSlots"] {
            guard let slots = backpack[key] as? [Any] else { continue }
            for raw in slots {
                guard let slot = raw as? [String: Any], slot["t"] as? String == selected.type else { continue }
                if let iid = selected.iid {
                    if SaveBackpackConflictPolicy.normalizedIID(slot["iid"]) == iid { return true }
                } else {
                    // Build 76 guarantees one carried instance before Dunes entry.
                    // Without iid, type presence is safer than durability equality
                    // because durability legitimately changes while gathering.
                    return true
                }
            }
        }
        return false
    }

    static func survived(
        expectedLifeEpoch: Int,
        observedLifeEpoch: Int?,
        hp: Int?,
        toolStillCarried: Bool
    ) -> Bool {
        if let observedLifeEpoch, observedLifeEpoch > expectedLifeEpoch { return false }
        if let hp, hp <= 0 { return false }
        return toolStillCarried
    }
}

struct DunesDamageSafetyPolicy {
    static let toleranceHP = 4
    // Build 85: external damage in a full-loot realm gets an emergency heal
    // before movement when HP is already at/below the thermal floor.
    static func shouldEmergencyHeal(observedHP: Int) -> Bool {
        observedHP <= DunesHeatSafetyPolicy.minimumSafeHP
    }

    /// A heat clock already predicts expected HP loss. A trusted HP materially
    /// below that projection is treated as mob/PvP damage and forces exit.
    static func isUnexpectedDamage(observedHP: Int, conservativeHP: Int) -> Bool {
        observedHP < max(0, conservativeHP - toleranceHP)
    }
}

/// UI telemetry must describe actionable/live mobs rather than every record
/// retained in the latest snapshot dictionary. Dead/despawned entries may stay
/// cached briefly and must not inflate the dashboard counter.
struct MobTelemetryPolicy {
    static func visibleCount(chickenAlive: Int, wildAlive: Int) -> Int {
        max(0, max(chickenAlive, wildAlive))
    }
}

/// Ground-bag association is intentionally conservative: only a bag that did
/// not exist before this fight, belongs to the player (when owner identity is
/// exposed), and spawned close to the authoritative kill position can be
/// attributed to this kill.
struct WildGroundBagPolicy {
    static let associationRadius: Double = 3.25

    static func candidateIDs(
        bags: [[String: Any]],
        excluding baseline: Set<String>,
        ownerID: Int?,
        killX: Double,
        killZ: Double,
        radius: Double = associationRadius
    ) -> [String] {
        bags.compactMap { bag -> String? in
            guard let id = bagID(bag), !baseline.contains(id) else { return nil }
            if let ownerID, let observedOwner = bagOwnerID(bag), observedOwner != ownerID { return nil }
            guard let point = bagPosition(bag), hypot(point.x - killX, point.z - killZ) <= radius else { return nil }
            return id
        }.sorted()
    }

    static func bagID(_ bag: [String: Any]) -> String? {
        for key in ["id", "bagId", "bag_id", "_id"] {
            if let value = bag[key] as? String, !value.isEmpty { return value }
            if let value = RealtimeProtocol.int(bag[key]) { return String(value) }
        }
        return nil
    }

    static func bagOwnerID(_ bag: [String: Any]) -> Int? {
        let raw = bag["ownerId"] ?? bag["playerId"] ?? bag["pid"] ?? bag["by"] ?? (bag["owner"] as? [String: Any])?["id"]
        return RealtimeProtocol.int(raw)
    }

    static func bagPosition(_ bag: [String: Any]) -> (x: Double, z: Double)? {
        let nested = bag["position"] as? [String: Any]
        guard let x = RealtimeProtocol.double(bag["x"] ?? bag["px"] ?? nested?["x"]),
              let z = RealtimeProtocol.double(bag["z"] ?? bag["pz"] ?? nested?["z"])
        else { return nil }
        return (x, z)
    }
}

enum RoastPitMode: String, CaseIterable, Codable, Identifiable {
    case herring, trout, bass, tuna, swordfish, chicken

    var id: String { rawValue }
    var label: String { rawValue.prefix(1).uppercased() + rawValue.dropFirst() }

    var rawItem: String {
        switch self {
        case .herring: return "fish"
        case .trout: return "fish_trout"
        case .bass: return "fish_bass"
        case .tuna: return "fish_tuna"
        case .swordfish: return "fish_swordfish"
        case .chicken: return "raw_chicken"
        }
    }

    var cookedItem: String {
        switch self {
        case .herring: return "cooked_fish_meat"
        case .trout: return "cooked_trout"
        case .bass: return "cooked_bass"
        case .tuna: return "cooked_tuna"
        case .swordfish: return "cooked_swordfish"
        case .chicken: return "cooked_chicken"
        }
    }

    var minCookingLevel: Int {
        switch self {
        case .herring, .chicken: return 1
        case .trout: return 6
        case .bass: return 13
        case .tuna: return 20
        case .swordfish: return 28
        }
    }

    /// Official inventory sprite paths extracted from the supplied game client.
    var iconPath: String {
        switch self {
        case .herring: return "/assets/hud/resources/fish.png"
        case .trout: return "/assets/hud/resources/fish_trout.png"
        case .bass: return "/assets/hud/resources/fish_bass.png"
        case .tuna: return "/assets/hud/resources/fish_tuna.png"
        case .swordfish: return "/assets/hud/resources/fish_swordfish.png"
        case .chicken: return "/assets/hud/resources/rawchicken.png"
        }
    }

    var iconURL: URL? {
        URL(string: "https://us.kintara.com" + iconPath)
    }
}


enum BlacksmithPanelMode: String, CaseIterable, Identifiable {
    case smelt, forge, repair
    var id: String { rawValue }
    var label: String {
        switch self {
        case .smelt: return "SMELT"
        case .forge: return "FORGE"
        case .repair: return "REPAIR"
        }
    }
}

struct BlacksmithRecipe: Identifiable, Equatable {
    let id: String
    let result: String
    let label: String
    let materials: [String: Int]
    let smithingLevel: Int
    let stackable: Bool
    let iconPath: String
    let panel: BlacksmithPanelMode
    var iconURL: URL? { URL(string: "https://us.kintara.com" + iconPath) }

    static let copperIngot = BlacksmithRecipe(id: "copper_ingot", result: "copper_ingot", label: "Copper Ingot", materials: ["stone": 10, "coal": 5], smithingLevel: 0, stackable: true, iconPath: "/assets/hud/resources/copperingot.png", panel: .smelt)
    static let ironIngot = BlacksmithRecipe(id: "iron_ingot", result: "iron_ore", label: "Iron Ingot", materials: ["metal": 6, "coal": 6], smithingLevel: 0, stackable: true, iconPath: "/assets/hud/resources/ironingot.png", panel: .smelt)
    static let silverIngot = BlacksmithRecipe(id: "silver_ingot", result: "silver_ingot", label: "Silver Ingot", materials: ["silver_ore": 4, "coal": 8], smithingLevel: 0, stackable: true, iconPath: "/assets/hud/resources/silveringot.png", panel: .smelt)
    static let copperAxe = BlacksmithRecipe(id: "copper_axe", result: "copper_axe", label: "Copper Axe", materials: ["copper_ingot": 20, "wood": 400], smithingLevel: 0, stackable: false, iconPath: "/assets/hud/tools/copperaxe.png", panel: .forge)
    static let copperSword = BlacksmithRecipe(id: "copper_sword", result: "copper_sword", label: "Copper Sword", materials: ["copper_ingot": 25, "wood": 600], smithingLevel: 3, stackable: false, iconPath: "/assets/hud/tools/coppersword.png", panel: .forge)
    static let copperPickaxe = BlacksmithRecipe(id: "copper_pickaxe", result: "copper_pickaxe", label: "Copper Pickaxe", materials: ["copper_ingot": 28, "wood": 850], smithingLevel: 7, stackable: false, iconPath: "/assets/hud/tools/copperpickaxe.png", panel: .forge)
    static let ironAxe = BlacksmithRecipe(id: "iron_axe", result: "tool_axe_l2", label: "Iron Axe", materials: ["iron_ore": 40, "wood": 1000], smithingLevel: 10, stackable: false, iconPath: "/assets/hud/tools/ironaxe.png", panel: .forge)
    static let ironSword = BlacksmithRecipe(id: "iron_sword", result: "wild_sword_l2", label: "Iron Sword", materials: ["iron_ore": 55, "wood": 1300], smithingLevel: 13, stackable: false, iconPath: "/assets/hud/tools/ironsword.png", panel: .forge)
    static let ironPickaxe = BlacksmithRecipe(id: "iron_pickaxe", result: "tool_pickaxe_l2", label: "Iron Pickaxe", materials: ["iron_ore": 60, "wood": 1600], smithingLevel: 17, stackable: false, iconPath: "/assets/hud/tools/ironpickaxe.png", panel: .forge)
    static let silverAxe = BlacksmithRecipe(id: "silver_axe", result: "silver_axe", label: "Silver Axe", materials: ["silver_ingot": 80, "wood": 2000], smithingLevel: 20, stackable: false, iconPath: "/assets/hud/tools/silveraxe.png", panel: .forge)
    static let silverSword = BlacksmithRecipe(id: "silver_sword", result: "silver_sword", label: "Silver Sword", materials: ["silver_ingot": 90, "wood": 2500], smithingLevel: 23, stackable: false, iconPath: "/assets/hud/tools/silversword.png", panel: .forge)
    static let silverPickaxe = BlacksmithRecipe(id: "silver_pickaxe", result: "silver_pickaxe", label: "Silver Pickaxe", materials: ["silver_ingot": 100, "wood": 3000], smithingLevel: 27, stackable: false, iconPath: "/assets/hud/tools/silverpickaxe.png", panel: .forge)

    static let smeltRecipes = [copperIngot, ironIngot, silverIngot]
    static let forgeRecipes = [copperAxe, copperSword, copperPickaxe, ironAxe, ironSword, ironPickaxe, silverAxe, silverSword, silverPickaxe]
}

struct RepairTarget: Identifiable, Equatable {
    let slotKind: String
    let slotIdx: Int
    let type: String
    let iid: String?
    let durability: Int
    let maxDurability: Int
    var id: String { "\(slotKind):\(slotIdx):\(iid ?? type)" }
    var label: String { BlacksmithProtocolPolicy.toolLabel(type) }
    var iconURL: URL? { URL(string: "https://us.kintara.com" + BlacksmithProtocolPolicy.toolIconPath(type)) }
}

enum BlacksmithSelection: Equatable {
    case smith(BlacksmithRecipe, batch: Int, smeltGoal: Int)
    case repair(RepairTarget)
}

struct BlacksmithProtocolPolicy {
    static let smithEndpoint = "/api/auth/blacksmith-smith"
    static let repairEndpoint = "/api/auth/blacksmith-repair"
    static let region = "blacksmith_shop"
    static let smithSecondsPerUnit = 1
    static let batchQuantities = [1, 5, 10]

    static func normalizedBatchQuantity(_ value: Int) -> Int {
        batchQuantities.contains(value) ? value : 1
    }

    static func smithMaterialCosts(recipe: BlacksmithRecipe, quantity: Int) -> [String: Int] {
        let units = normalizedBatchQuantity(quantity)
        var costs: [String: Int] = [:]
        for (material, perUnit) in recipe.materials {
            costs[material] = perUnit * units
        }
        return costs
    }

    static func normalizedSmeltGoal(_ value: Int) -> Int {
        min(100_000, max(1, value))
    }

    /// Smelt: a meta pertence ao próprio HUD e representa ciclos; o lote multiplica
    /// cada ciclo. Forge: o lote é a quantidade final total (1/5/10).
    static func smithSessionGoal(recipe: BlacksmithRecipe, batch: Int, smeltGoal: Int) -> Int {
        recipe.stackable
            ? normalizedSmeltGoal(smeltGoal)
            : normalizedBatchQuantity(batch)
    }

    static func smithOutputUnits(recipe: BlacksmithRecipe, batch: Int, smeltGoal: Int) -> Int {
        let normalizedBatch = normalizedBatchQuantity(batch)
        return recipe.stackable
            ? normalizedBatch * normalizedSmeltGoal(smeltGoal)
            : normalizedBatch
    }

    static func smithMaterialCosts(recipe: BlacksmithRecipe, batch: Int, smeltGoal: Int) -> [String: Int] {
        let units = smithOutputUnits(recipe: recipe, batch: batch, smeltGoal: smeltGoal)
        var costs: [String: Int] = [:]
        for (material, perUnit) in recipe.materials {
            costs[material] = perUnit * units
        }
        return costs
    }

    static let frostmereGridOffset = 19.5
    static let entranceTileColumn = 22
    static let entranceTileRow = 20
    static let interiorPosition = Position(x: 2, z: 0)
    static let repairMaxDurability = 4_000
    static let repairCostFactor = 0.6
    static let repairableToolTypes: Set<String> = ["tool_pickaxe_l2","tool_axe_l2","wild_sword_l2","copper_pickaxe","copper_axe","copper_sword","silver_pickaxe","silver_axe","silver_sword"]

    static var frostmereEntrancePosition: Position {
        Position(x: Double(entranceTileColumn) - frostmereGridOffset, z: Double(entranceTileRow) - frostmereGridOffset)
    }

    static func smithBody(recipe: String, quantity: Int, fleet: String, shardID: Int?) -> [String: Any] {
        var body: [String: Any] = ["recipe": recipe, "quantity": max(1, quantity), "fleet": fleet]
        if let shardID { body["shardId"] = shardID }
        return body
    }

    static func repairBody(slotKind: String, slotIdx: Int, fleet: String, shardID: Int?) -> [String: Any] {
        var body: [String: Any] = ["slotKind": slotKind, "slotIdx": slotIdx, "fleet": fleet]
        if let shardID { body["shardId"] = shardID }
        return body
    }

    static func recipeForResult(_ type: String) -> BlacksmithRecipe? {
        BlacksmithRecipe.forgeRecipes.first { $0.result == type }
    }

    static func repairMaterialCosts(type: String, missingDurability: Int) -> [String: Int] {
        guard let recipe = recipeForResult(type), missingDurability > 0 else { return [:] }
        let fraction = Double(missingDurability) / Double(repairMaxDurability)
        var costs: [String: Int] = [:]
        for (material, quantity) in recipe.materials {
            costs[material] = max(1, Int(ceil(Double(quantity) * repairCostFactor * fraction)))
        }
        return costs
    }

    static func repairTargets(in backpack: [String: Any]) -> [RepairTarget] {
        var result: [RepairTarget] = []
        func scan(_ value: Any?, slotKind: String) {
            guard let slots = value as? [Any] else { return }
            for idx in slots.indices {
                guard let slot = slots[idx] as? [String: Any] else { continue }
                let type = (slot["t"] as? String) ?? (slot["type"] as? String) ?? ""
                guard repairableToolTypes.contains(type) else { continue }
                let count = RealtimeProtocol.int(slot["n"] ?? slot["count"]) ?? 1
                guard count > 0 else { continue }
                let durability = max(0, min(repairMaxDurability, RealtimeProtocol.int(slot["d"] ?? slot["durability"]) ?? repairMaxDurability))
                guard durability < repairMaxDurability else { continue }
                let rawIID = slot["iid"]
                let iid: String?
                if let text = rawIID as? String { iid = text }
                else if let number = rawIID as? NSNumber { iid = number.stringValue }
                else { iid = nil }
                result.append(RepairTarget(slotKind: slotKind, slotIdx: idx, type: type, iid: iid, durability: durability, maxDurability: repairMaxDurability))
            }
        }
        scan(backpack["hotbar"], slotKind: "hot")
        scan(backpack["invSlots"], slotKind: "inv")
        return result.sorted {
            let lm = $0.maxDurability - $0.durability
            let rm = $1.maxDurability - $1.durability
            if lm != rm { return lm > rm }
            if $0.slotKind != $1.slotKind { return $0.slotKind < $1.slotKind }
            return $0.slotIdx < $1.slotIdx
        }
    }

    static func currentTarget(_ target: RepairTarget, in backpack: [String: Any]) -> RepairTarget? {
        repairTargets(in: backpack).first {
            $0.slotKind == target.slotKind && $0.slotIdx == target.slotIdx && $0.type == target.type &&
            (target.iid == nil || $0.iid == target.iid)
        }
    }

    static func slotDurability(_ target: RepairTarget, in backpack: [String: Any]) -> Int? {
        let key = target.slotKind == "hot" ? "hotbar" : "invSlots"
        guard let slots = backpack[key] as? [Any], slots.indices.contains(target.slotIdx),
              let slot = slots[target.slotIdx] as? [String: Any] else { return nil }
        let type = (slot["t"] as? String) ?? (slot["type"] as? String) ?? ""
        guard type == target.type else { return nil }
        return max(0, min(repairMaxDurability, RealtimeProtocol.int(slot["d"] ?? slot["durability"]) ?? repairMaxDurability))
    }

    static func toolLabel(_ type: String) -> String {
        switch type {
        case "tool_pickaxe_l2": return "Iron Pickaxe"
        case "tool_axe_l2": return "Iron Axe"
        case "wild_sword_l2": return "Iron Sword"
        case "copper_pickaxe": return "Copper Pickaxe"
        case "copper_axe": return "Copper Axe"
        case "copper_sword": return "Copper Sword"
        case "silver_pickaxe": return "Silver Pickaxe"
        case "silver_axe": return "Silver Axe"
        case "silver_sword": return "Silver Sword"
        default: return type
        }
    }

    static func toolIconPath(_ type: String) -> String {
        switch type {
        case "tool_pickaxe_l2": return "/assets/hud/tools/ironpickaxe.png"
        case "tool_axe_l2": return "/assets/hud/tools/ironaxe.png"
        case "wild_sword_l2": return "/assets/hud/tools/ironsword.png"
        case "copper_pickaxe": return "/assets/hud/tools/copperpickaxe.png"
        case "copper_axe": return "/assets/hud/tools/copperaxe.png"
        case "copper_sword": return "/assets/hud/tools/coppersword.png"
        case "silver_pickaxe": return "/assets/hud/tools/silverpickaxe.png"
        case "silver_axe": return "/assets/hud/tools/silveraxe.png"
        case "silver_sword": return "/assets/hud/tools/silversword.png"
        default: return "/assets/hud/tools/hammer.png"
        }
    }

    static func materialLabel(_ type: String) -> String {
        switch type {
        case "metal": return "Iron Ore"
        case "wood": return "Wood"
        case "coal": return "Coal"
        case "stone": return "Stone"
        case "copper_ingot": return "Copper Ingot"
        case "iron_ore": return "Iron Ingot"
        case "silver_ore": return "Silver Ore"
        case "silver_ingot": return "Silver Ingot"
        default: return type
        }
    }

    static func serverErrorMessage(code: String, payload: [String: Any]?) -> String {
        switch code {
        case "missing_base_tool":
            return "Servidor não encontrou a ferramenta-base (missing_base_tool). Nenhuma cadeia local foi presumida."
        case "smithing_level_required":
            return "Smithing \(RealtimeProtocol.int(payload?["need"]) ?? 0) necessário (smithing_level_required)"
        case "missing_materials": return "Servidor não confirmou os materiais (missing_materials)"
        case "inventory_full": return "Inventário cheio (inventory_full)"
        case "smith_grant_failed": return "Servidor não conseguiu entregar o item forjado (smith_grant_failed)"
        case "already_full": return "A ferramenta já está com durabilidade máxima (already_full)"
        case "not_repairable": return "Item não reparável pelo servidor (not_repairable)"
        case "bad_slot": return "Slot de Repair não é mais válido (bad_slot)"
        default: return code
        }
    }
}

struct RoastPitProtocolPolicy {
    static let endpoint = "/api/auth/grant-cook-xp"
    static let batchDelayMS = 10_000
    static let proximityRetryMS = 700

    // Official client tutorial points "Cook Your Catch" at Pond tile 18,34.
    // Pond wire coordinates use the same 19.5 grid offset already validated by
    // Feather fishing, so this tile is (-1.5, 14.5) in Presence coordinates.
    static let pondGridOffset = 19.5
    static let tutorialPitColumn = 18
    static let tutorialPitRow = 34

    /// Cardinal approach candidates around the official Roast Pit tutorial tile.
    /// The server validates _lastPresencePos, so HTTP cooking is only attempted
    /// after a real Presence walk and a short propagation grace period.
    static var approachPositions: [Position] {
        [
            (18, 33), (17, 34), (19, 34), (18, 35),
            (18, 32), (16, 34), (20, 34), (18, 36)
        ].map { col, row in
            Position(
                x: Double(col) - pondGridOffset,
                z: Double(row) - pondGridOffset
            )
        }
    }

    static func body(mode: RoastPitMode, fleet: String, shardID: Int?) -> [String: Any] {
        var body: [String: Any] = ["mode": mode.rawValue, "fleet": fleet]
        if let shardID { body["shardId"] = shardID }
        return body
    }
}

struct GatherProgressPolicy {
    /// Converts the authoritative wear of the current resource into the 0...99
    /// subunit used by BGContinuedProcessingTask. A completed resource is still
    /// committed only by gatherSuccess, so partial wear can never over-count.
    static func continuedSubunit(h: Int, hm: Int) -> Int {
        guard hm > 0 else { return 0 }
        let clampedH = min(max(0, h), hm)
        if clampedH >= hm { return 99 }
        return min(98, max(0, Int((Double(clampedH) / Double(hm) * 99.0).rounded(.down))))
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

/// Build 72: fluxo capturado do cliente oficial em 17/09/2026. O banco não é
/// apenas uma coordenada no World; ele é uma região autoritativa própria.
struct BankShopProtocolPolicy {
    static let region = "bank_shop"
    static let worldEntranceX = -21.5
    static let worldEntranceZ = -17.5
    static let interiorX = 2.5
    static let interiorZ = -0.5

    static func acceptedTransitionSequence(baseSeq: Int, responseSeq: Int?) -> Int? {
        guard let responseSeq, responseSeq == baseSeq + 1 else { return nil }
        return responseSeq
    }
}

/// Quando existem duas instâncias do mesmo `t`, preserve a identidade do slot
/// escolhido. Para ferramentas com durabilidade, prefira a de maior `d`; em
/// empate, mantenha a ordem autoritativa do banco.
struct BankItemSelectionPolicy {
    static func preferredBankSlotIndex(type: String, bank: [Any]) -> Int? {
        let candidates = bank.indices.filter { index in
            guard let slot = bank[index] as? [String: Any] else { return false }
            return slot["t"] as? String == type
        }
        return candidates.sorted { lhs, rhs in
            let left = bank[lhs] as? [String: Any] ?? [:]
            let right = bank[rhs] as? [String: Any] ?? [:]
            let leftDurability = RealtimeProtocol.int(left["d"]) ?? -1
            let rightDurability = RealtimeProtocol.int(right["d"]) ?? -1
            if leftDurability != rightDurability { return leftDurability > rightDurability }
            return lhs < rhs
        }.first
    }
}

/// Contrato de `save-backpack` alinhado ao cliente oficial atual. Campos
/// opcionais só são copiados quando vieram do snapshot autoritativo de `/me`.
struct BackpackSavePayloadPolicy {
    static let resourceKeys = [
        "wood", "stone", "coal", "metal", "copper_ingot", "iron_ore", "silver_ore", "silver_ingot", "cacti", "gold", "fish",
        "cooked_fish_meat", "raw_chicken", "cooked_chicken",
        "potion_health", "potion_health_l2", "potion_shield", "potion_strength", "potion_poison"
    ]

    static let slotKeys = [
        "invSlots", "hotbar", "mountSlots", "cosmeticSlots",
        "petSlots", "furnitureSlots", "bankSlots"
    ]

    static let mountFlags = [
        "mountDragonRiding", "mountWhaleRiding", "mountSpiderRiding",
        "mountWolfRiding", "mountTigerRiding", "mountUnicornRiding",
        "mountCrocodileRiding", "mountGiraffeRiding", "mountWoolyMammothRiding",
        "mountHarambeRiding", "mountTralaleroRiding"
    ]

    static func makeBody(
        backpack: [String: Any],
        baseSeq: Int,
        fleet: String? = nil,
        shardID: Int? = nil
    ) -> [String: Any] {
        var resources: [String: Any] = [:]
        for key in resourceKeys {
            resources[key] = RealtimeProtocol.int(backpack[key]) ?? 0
        }

        var body: [String: Any] = [
            "resources": resources,
            "baseSeq": baseSeq,
            "intentionalRemovals": [],
            "intentionalRelicRemovals": []
        ]
        if let fleet, !fleet.isEmpty { body["fleet"] = fleet }
        if let shardID { body["shardId"] = shardID }
        for key in slotKeys {
            body[key] = backpack[key] ?? []
        }
        body["equippedHotbar"] = backpack["equippedHotbar"] ?? 0
        for flag in mountFlags {
            body[flag] = backpack[flag] ?? false
        }
        return body
    }
}

enum SaveBackpackConflictClassification: String, Equatable {
    case sequenceAdvanced = "sequence_advanced"
    case sameSequenceRejected = "same_sequence_rejected"
    case sequenceUnavailable = "sequence_unavailable"
}

struct SaveBackpackConflictPolicy {
    static func authoritativeSequence(from payload: [String: Any]?) -> Int? {
        guard let payload else { return nil }

        func decode(_ object: [String: Any]) -> Int? {
            if let seq = RealtimeProtocol.int(
                object["stateSeq"] ?? object["currentStateSeq"] ?? object["serverStateSeq"] ?? object["latestStateSeq"]
            ) {
                return seq
            }
            for key in ["current", "state", "authoritative", "latest", "data"] {
                if let child = object[key] as? [String: Any], let seq = decode(child) { return seq }
            }
            return nil
        }

        return decode(payload)
    }

    static func classify(sentSeq: Int, responseSeq: Int?, freshSeq: Int?) -> SaveBackpackConflictClassification {
        if let responseSeq, responseSeq > sentSeq { return .sequenceAdvanced }
        if let freshSeq, freshSeq > sentSeq { return .sequenceAdvanced }
        if responseSeq == sentSeq || freshSeq == sentSeq { return .sameSequenceRejected }
        return .sequenceUnavailable
    }

    static func safeTopLevelKeys(from payload: [String: Any]?) -> [String] {
        payload.map { $0.keys.sorted() } ?? []
    }

    static func safeReason(from payload: [String: Any]?) -> String {
        guard let raw = payload?["reason"] else { return "-" }
        let text: String
        if let value = raw as? String {
            text = value
        } else if let value = raw as? NSNumber {
            text = value.stringValue
        } else if let value = raw as? [String: Any] {
            text = "object{" + value.keys.sorted().joined(separator: ",") + "}"
        } else if let value = raw as? [Any] {
            text = "array[count=\(value.count)]"
        } else {
            text = String(describing: raw)
        }
        let flattened = text.replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return flattened.isEmpty ? "-" : String(flattened.prefix(180))
    }

    static func equipmentLabel(type: String) -> String {
        let family: String
        switch EquipmentTierPolicy.family(of: type) {
        case .axe: family = "axe"
        case .pickaxe: family = "pickaxe"
        case .sword: family = "sword"
        case nil: family = "other"
        }
        return "\(family):T\(EquipmentTierPolicy.tier(of: type)):\(type)"
    }

    static func itemLocation(type: String, iid: String?, in backpack: [String: Any]) -> String {
        matchingItem(type: type, iid: iid, in: backpack)?.location ?? "-"
    }

    static func itemKeys(type: String, iid: String?, in backpack: [String: Any]) -> [String] {
        matchingItem(type: type, iid: iid, in: backpack)?.slot.keys.sorted() ?? []
    }

    static func unrepresentedAuthoritativeBackpackKeys(_ backpack: [String: Any]) -> [String] {
        let represented = Set(
            BackpackSavePayloadPolicy.resourceKeys
            + BackpackSavePayloadPolicy.slotKeys
            + BackpackSavePayloadPolicy.mountFlags
            + ["equippedHotbar"]
        )
        return backpack.keys.filter { !represented.contains($0) }.sorted()
    }

    private static func matchingItem(
        type: String,
        iid: String?,
        in backpack: [String: Any]
    ) -> (location: String, slot: [String: Any])? {
        for key in ["hotbar", "invSlots", "bankSlots", "armorSlots"] {
            guard let slots = backpack[key] as? [Any] else { continue }
            for (index, raw) in slots.enumerated() {
                guard let slot = raw as? [String: Any], slot["t"] as? String == type else { continue }
                if let iid {
                    guard normalizedIID(slot["iid"]) == iid else { continue }
                }
                return ("\(key)[\(index)]", slot)
            }
        }
        return nil
    }

    static func normalizedIID(_ raw: Any?) -> String? {
        if let value = raw as? String, !value.isEmpty { return value }
        if let value = raw as? NSNumber { return value.stringValue }
        if let value = RealtimeProtocol.int(raw) { return String(value) }
        return nil
    }
}

private struct SaveBackpackItemDiagnosticContext {
    let type: String
    let iid: String?
    let beforeBackpack: [String: Any]
}

struct ItemConservationPolicy {
    static func slotCount(_ value: Any?, type: String) -> Int {
        guard let slots = value as? [Any] else { return 0 }
        return slots.reduce(0) { partial, raw in
            guard let slot = raw as? [String: Any], slot["t"] as? String == type else { return partial }
            return partial + CombatBankFirstPolicy.slotQuantity(slot)
        }
    }

    static func total(type: String, in backpack: [String: Any]) -> Int {
        slotCount(backpack["hotbar"], type: type)
            + slotCount(backpack["invSlots"], type: type)
            + slotCount(backpack["bankSlots"], type: type)
    }

    static func isConserved(type: String, before: [String: Any], after: [String: Any]) -> Bool {
        total(type: type, in: before) == total(type: type, in: after)
    }
}

struct OwnVitalsPolicy {
    /// `pvit` is a broadcast. Only an explicitly identified packet for this
    /// player is allowed to mutate local HP/Shield, matching Node v5.2.
    static func shouldApplyPvit(packetPlayerID: Int?, playerID: Int?) -> Bool {
        guard let packetPlayerID, let playerID else { return false }
        return packetPlayerID == playerID
    }
}

struct DunesSnapshotHPPolicy {
    /// Heat normal pode chegar um pouco fora de fase com o relógio local.
    /// Quedas de snapshot além desta margem são confirmadas em `/me` antes de
    /// substituir HP local. `pvit` próprio continua imediato para não mascarar PvP.
    static let heatToleranceHP = DunesDamageSafetyPolicy.toleranceHP

    static func requiresHTTPConfirmation(currentHP: Int, snapshotHP: Int, conservativeHP: Int, region: String) -> Bool {
        guard GatherRegionPolicy.isDunesRegion(region), snapshotHP < currentHP else { return false }
        return DunesDamageSafetyPolicy.isUnexpectedDamage(observedHP: snapshotHP, conservativeHP: conservativeHP)
    }
}

struct DunesHeatSafetyPolicy {
    /// Build 77: Dunes are full-loot and Giant Scorpion/PvP damage can arrive
    /// on top of heat. At 70 HP we either confirm one Health Potion+ recovery
    /// or stop gathering immediately and leave for The Shores.
    static let minimumSafeHP = 70
    static let recoveryGoalHP = 90
    static let healthPotionPlusType = "potion_health_l2"
    static let carriedHealthPotionPlusTarget = 6

    static func requiresRecovery(hp: Int, mode: ActivityMode) -> Bool {
        mode.isDunesGathering && hp <= minimumSafeHP
    }

    static func estimatedHP(baselineHP: Int, elapsedMS: Double) -> Int {
        let exposedMS = max(0, elapsedMS)
        let expectedDamage = Int(floor(exposedMS / 10_000))
        return max(0, baselineHP - expectedDamage)
    }
}

struct GatherLootMarkerPolicy {
    static func resource(for mode: ActivityMode) -> String? {
        switch mode {
        case .tree: return "wood"
        case .stone: return "stone"
        case .coal: return "coal"
        case .iron: return "metal"
        case .silver: return "silver_ore"
        case .cacti: return "cacti"
        default: return nil
        }
    }

    /// `h/hm` is action progress, not an inventory award. A balance delta may
    /// contain grants accumulated during partial/recovery cycles, so never label
    /// it as the yield of the one target that just completed.
    static func confirmedDelta(previous: Int?, current: Int) -> Int? {
        previous.map { max(0, current - $0) }
    }

    static func label(item: String, previous: Int?, current: Int) -> String {
        guard let previous, let delta = confirmedDelta(previous: previous, current: current) else {
            return "\(item)=\(current) • saldo autoritativo inicial"
        }
        if delta == 0 {
            return "\(item)=\(current) • saldo \(previous)→\(current) • sem variação nova"
        }
        return "\(item)=\(current) • saldo \(previous)→\(current) • variação acumulada +\(delta)"
    }
}

enum HealthPotionEffectResult: Equatable {
    case confirmed
    case noAuthoritativeGain
    case interrupted
}

struct HealthPotionEffectPolicy {
    static func result(before: Int, after: Int, interrupted: Bool) -> HealthPotionEffectResult {
        if interrupted { return .interrupted }
        return after > before ? .confirmed : .noAuthoritativeGain
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

enum EquipmentFamily: Equatable {
    case sword
    case pickaxe
    case axe
}

struct EquipmentSelection: Equatable {
    let type: String
    let tier: Int
    let carried: Int
    let bank: Int
}

/// O cliente atual possui famílias Starter/Copper/Iron/Silver. IDs novos podem
/// variar entre famílias, então a seleção não fica presa a uma lista incompleta:
/// reconhecemos a classe pelo próprio type e priorizamos o maior tier observado.
struct EquipmentTierPolicy {
    static func family(of type: String) -> EquipmentFamily? {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized.contains("pickaxe") { return .pickaxe }
        if normalized.contains("sword") { return .sword }
        if normalized.contains("axe") { return .axe }
        return nil
    }

    static func tier(of type: String) -> Int {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized.contains("silver") { return 4 }
        if normalized.contains("iron") || normalized.hasSuffix("_l2") { return 3 }
        if normalized.contains("copper") { return 2 }
        return family(of: normalized) == nil ? 0 : 1
    }

    static func bestSelection(
        in backpack: [String: Any],
        family: EquipmentFamily,
        minimumTier: Int
    ) -> EquipmentSelection? {
        var carried: [String: Int] = [:]
        var bank: [String: Int] = [:]

        func collect(_ raw: Any?, into counts: inout [String: Int]) {
            guard let slots = raw as? [Any] else { return }
            for value in slots {
                guard let slot = value as? [String: Any], let type = slot["t"] as? String else { continue }
                guard self.family(of: type) == family, tier(of: type) >= minimumTier else { continue }
                counts[type, default: 0] += max(1, RealtimeProtocol.int(slot["n"]) ?? 1)
            }
        }

        collect(backpack["hotbar"], into: &carried)
        collect(backpack["invSlots"], into: &carried)
        collect(backpack["bankSlots"], into: &bank)

        let types = Set(carried.keys).union(bank.keys)
        return types.map { type in
            EquipmentSelection(type: type, tier: tier(of: type), carried: carried[type] ?? 0, bank: bank[type] ?? 0)
        }.sorted { lhs, rhs in
            if lhs.tier != rhs.tier { return lhs.tier > rhs.tier }
            if (lhs.carried > 0) != (rhs.carried > 0) { return lhs.carried > 0 }
            return lhs.type < rhs.type
        }.first
    }
}

struct ActivityToolPolicy {
    static func acceptedTools(for mode: ActivityMode) -> [String] {
        switch mode {
        case .tree: return ["silver_axe", "tool_axe_l2", "tool_axe"]
        case .coal, .stone, .iron: return ["silver_pickaxe", "tool_pickaxe_l2", "copper_pickaxe", "tool_pickaxe"]
        case .silver: return ["silver_pickaxe", "tool_pickaxe_l2", "copper_pickaxe"]
        case .cacti: return ["silver_axe", "tool_axe_l2"]
        case .fishing: return ["tool_fishing_rod"]
        case .roastPit, .blacksmith, .chicken, .zombie, .dragon: return []
        }
    }

    static func requiredTool(for mode: ActivityMode) -> String? {
        switch mode {
        case .tree: return "tool_axe"
        case .coal, .stone, .iron: return "tool_pickaxe"
        case .silver: return "copper_pickaxe"
        case .cacti: return "tool_axe_l2"
        case .fishing: return "tool_fishing_rod"
        case .roastPit, .blacksmith, .chicken, .zombie, .dragon: return nil
        }
    }

    static func isCompatible(type: String, with mode: ActivityMode) -> Bool {
        if mode == .fishing { return type == "tool_fishing_rod" }
        guard let family = equipmentFamily(for: mode) else { return false }
        return EquipmentTierPolicy.family(of: type) == family && EquipmentTierPolicy.tier(of: type) >= minimumTier(for: mode)
    }

    static func bestSelection(in backpack: [String: Any], for mode: ActivityMode) -> EquipmentSelection? {
        guard let family = equipmentFamily(for: mode) else { return nil }
        return EquipmentTierPolicy.bestSelection(in: backpack, family: family, minimumTier: minimumTier(for: mode))
    }

    static func displayName(_ type: String) -> String {
        switch type {
        case "tool_axe": return "Starter Axe"
        case "tool_pickaxe": return "Starter Pickaxe"
        case "copper_pickaxe": return "Copper Pickaxe"
        case "tool_pickaxe_l2": return "Iron Pickaxe"
        case "silver_pickaxe": return "Silver Pickaxe"
        case "tool_axe_l2": return "Iron Axe"
        case "silver_axe": return "Silver Axe"
        case "tool_fishing_rod": return "Fishing Rod"
        default:
            let normalized = type.lowercased()
            if normalized.contains("silver") && normalized.contains("axe") { return "Silver Axe" }
            if normalized.contains("iron") && normalized.contains("axe") { return "Iron Axe" }
            if normalized.contains("copper") && normalized.contains("axe") { return "Copper Axe" }
            return type
        }
    }

    private static func equipmentFamily(for mode: ActivityMode) -> EquipmentFamily? {
        switch mode {
        case .tree, .cacti: return .axe
        case .coal, .stone, .iron, .silver: return .pickaxe
        default: return nil
        }
    }

    private static func minimumTier(for mode: ActivityMode) -> Int {
        switch mode {
        case .silver:
            // Kintara Wiki / runtime Build 74: Silver Ore in The Dunes refuses
            // Starter Pickaxe. A forged Copper Pickaxe or better is required.
            return 2
        case .cacti:
            return 3
        default:
            return 1
        }
    }
}

struct GatherResourcePolicy {
    static func matches(mode: ActivityMode, kind: String, hasCoal: Bool, hasMetal: Bool) -> Bool {
        matches(mode: mode, region: GatherRegionPolicy.region(for: mode), kind: kind, hasCoal: hasCoal, hasMetal: hasMetal)
    }

    static func matches(mode: ActivityMode, region: String, kind: String, hasCoal: Bool, hasMetal: Bool) -> Bool {
        let normalizedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch mode {
        case .tree: return normalizedRegion == "eldergrove" && kind == "tree"
        case .coal: return normalizedRegion == "eldergrove" && kind == "rock" && hasCoal && !hasMetal
        case .stone: return normalizedRegion == "eldergrove" && kind == "rock" && !hasCoal && !hasMetal
        case .iron: return normalizedRegion == "frostmere" && kind == "rock" && !hasCoal && hasMetal
        case .silver: return GatherRegionPolicy.isDunesRegion(normalizedRegion) && kind == "rock"
        case .cacti: return GatherRegionPolicy.isDunesRegion(normalizedRegion) && kind == "tree"
        default: return false
        }
    }
}

struct GatherRegionPolicy {
    static func region(for mode: ActivityMode) -> String {
        if mode == .iron { return "frostmere" }
        if mode.isDunesGathering { return "desert" }
        return "eldergrove"
    }

    static func startPosition(for mode: ActivityMode) -> Position {
        switch mode {
        case .tree: return Position(x: -6.5, z: -18.5)
        case .iron: return Position(x: 5.5, z: -18.5)
        case .silver, .cacti: return Position(x: -9.5, z: -18.5)
        default: return Position(x: 22.5, z: -3.5)
        }
    }

    static let dunesExitPosition = Position(x: -9.5, z: -19.5, ry: .pi)
    static let shoresArrivalPosition = Position(x: -9.5, z: 18.5, ry: .pi)

    static func isDunesRegion(_ region: String) -> Bool {
        let normalized = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "desert" || normalized == "desert_west" || normalized == "desert_south"
    }

    static func isGatherRegion(_ region: String) -> Bool {
        let normalized = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "eldergrove" || normalized == "frostmere" || isDunesRegion(normalized)
    }

    static func gridOffset(for region: String) -> Double {
        let normalized = region.lowercased()
        return normalized == "frostmere" || isDunesRegion(normalized) ? 19.5 : 24.5
    }

    static func hasCoal(region: String, packetValue: Bool?) -> Bool? {
        let normalized = region.lowercased()
        if normalized == "frostmere" || isDunesRegion(normalized) { return packetValue ?? false }
        return packetValue
    }

    static func hasMetal(region: String, packetValue: Bool?) -> Bool? {
        switch region.lowercased() {
        case "frostmere": return packetValue ?? true
        case "eldergrove": return packetValue ?? false
        case "desert", "desert_west", "desert_south": return packetValue ?? false
        default: return packetValue
        }
    }
}

struct DunesResourceDiscovery {
    struct Observation: Equatable {
        let observedKind: String?
        let wireKind: String
        let keys: [String]
        let mode: ActivityMode?
        let hasCoal: Bool?
        let hasMetal: Bool?
        let lootHint: String?
        let fieldNames: [String]

        var classificationLabel: String {
            mode?.rawValue ?? "unknown"
        }
    }

    /// Dunes launched after the legacy v5.2 tree/rock catalog. Classify newer
    /// snapshot aliases independently, but keep harvest traffic on the observed
    /// v5.2 wire kinds (`rock` / `tree`) instead of inventing a new action kind.
    static func observe(_ packet: [String: Any]) -> Observation {
        let fieldNames = packet.keys
            .filter { !sensitiveFieldNames.contains($0.lowercased()) }
            .sorted()

        let observedKind = firstString(in: packet, keys: ["kind", "k"])
        let classificationHint = firstString(in: packet, keys: [
            "resourceKind", "nodeKind", "resourceType", "nodeType", "subtype",
            "loot", "drop", "item", "resource", "material", "name", "type"
        ])
        let normalizedKind = normalizeToken(observedKind)
        let normalizedHint = normalizeToken(classificationHint)
        let combined = [normalizedKind, normalizedHint].filter { !$0.isEmpty }.joined(separator: " ")

        let mode: ActivityMode?
        if combined.contains("cact") {
            mode = .cacti
        } else if combined.contains("silver") {
            mode = .silver
        } else if ["tree", "plant", "cactus", "cacti"].contains(normalizedKind) {
            mode = .cacti
        } else if ["rock", "ore", "mineral", "silver_ore", "silverore"].contains(normalizedKind) {
            mode = .silver
        } else {
            mode = nil
        }

        let fallbackKind: String
        switch mode {
        case .silver?: fallbackKind = "rock"
        case .cacti?: fallbackKind = "tree"
        default: fallbackKind = ""
        }

        let wireKind = ["tree", "rock"].contains(normalizedKind) ? normalizedKind : fallbackKind

        return Observation(
            observedKind: observedKind?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
            wireKind: wireKind,
            keys: extractKeys(from: packet),
            mode: mode,
            hasCoal: RealtimeProtocol.bool(packet["hasCoal"] ?? packet["coal"]),
            hasMetal: RealtimeProtocol.bool(packet["hasMetal"] ?? packet["metal"]),
            lootHint: firstString(in: packet, keys: ["loot", "drop", "item", "resource", "material"]),
            fieldNames: fieldNames
        )
    }

    static func diagnosticSummary(_ observation: Observation) -> String {
        let observedKind = observation.observedKind?.isEmpty == false ? observation.observedKind! : "-"
        let wireKind = observation.wireKind.isEmpty ? "-" : observation.wireKind
        let loot = observation.lootHint?.trimmingCharacters(in: .whitespacesAndNewlines)
        let lootLabel = (loot?.isEmpty == false) ? loot! : "-"
        let coal = observation.hasCoal.map(String.init) ?? "-"
        let metal = observation.hasMetal.map(String.init) ?? "-"
        return "campos=\(observation.fieldNames.joined(separator: ",")) • kind observado=\(observedKind) • wire=\(wireKind) • classe=\(observation.classificationLabel) • keys=\(observation.keys.count) • coal=\(coal) • metal=\(metal) • loot=\(lootLabel)"
    }

    private static let sensitiveFieldNames: Set<String> = [
        "actionproof", "proof", "token", "kt", "cookie", "authorization", "privatekey", "private_key"
    ]

    private static func normalizeToken(_ value: String?) -> String {
        (value ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
    }

    private static func firstString(in packet: [String: Any], keys: [String]) -> String? {
        for key in keys {
            if let value = packet[key] as? String, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return value
            }
        }
        return nil
    }

    private static func extractKeys(from packet: [String: Any]) -> [String] {
        var candidates: [String] = []
        for key in ["keys", "key", "tiles", "tile", "cells", "cell", "footprint", "nodes"] {
            appendKeyCandidates(packet[key], into: &candidates, depth: 0)
        }
        return GatherKnowledgeStore.normalizeKeys(candidates)
    }

    private static func appendKeyCandidates(_ value: Any?, into output: inout [String], depth: Int) {
        guard let value, depth <= 2 else { return }
        if let string = value as? String {
            output.append(string)
            return
        }
        if let strings = value as? [String] {
            output.append(contentsOf: strings)
            return
        }
        if let values = value as? [Any] {
            for child in values { appendKeyCandidates(child, into: &output, depth: depth + 1) }
            return
        }
        guard let object = value as? [String: Any] else { return }

        for key in ["keys", "key", "tiles", "tile", "cells", "cell", "footprint"] {
            appendKeyCandidates(object[key], into: &output, depth: depth + 1)
        }

        let column = RealtimeProtocol.int(object["c"] ?? object["col"] ?? object["column"])
        let row = RealtimeProtocol.int(object["r"] ?? object["row"])
        if let column, let row { output.append("\(column),\(row)") }
    }
}

struct CombatBankFirstPolicy {
    // RC3.2: o BANK-FIRST não é mais limitado à allowlist histórica de seis
    // recursos. Todo item core materializado em invSlots pode ser protegido,
    // exceto o que precisa permanecer carregado para o combate e categorias
    // conhecidamente especiais/soulbound. Arrays especiais nunca são tocados.
    static let maxStackCount = 10_000
    static let combatRequiredTypes: Set<String> = [
        "potion_health", "potion_shield", "potion_strength"
    ]

    static func isCombatRequiredType(_ type: String) -> Bool {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return combatRequiredTypes.contains(normalized) || EquipmentTierPolicy.family(of: normalized) == .sword
    }
    static let protectedPrefixes = ["mount_", "pet_", "cosmetic_", "furniture_"]
    static let protectedFragments = ["scroll", "soulbound"]

    static func shouldBankFirst(type: String, slot: [String: Any]) -> Bool {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalized.isEmpty else { return false }
        if isCombatRequiredType(normalized) { return false }
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
        bank: inout [Any],
        preferredBankIndex: Int? = nil
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

        var orderedBankIndices: [Int] = []
        if let preferredBankIndex, bank.indices.contains(preferredBankIndex) {
            orderedBankIndices.append(preferredBankIndex)
        }
        orderedBankIndices.append(contentsOf: bank.indices.filter { $0 != preferredBankIndex })

        for index in orderedBankIndices where need > 0 {
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
    private let roastMode: RoastPitMode
    private let blacksmithSelection: BlacksmithSelection

    private var region: String
    private var serverRegion: String?
    private var lastRegionConfirmationSource: String?
    private var lastSnapshotRegion: String?
    private var regionSnapshotSerial = 0
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
    // Build 83: observabilidade de latência do gather. Nunca registra proof/token/cookie;
    // somente tipo de evento, latência, h/hm e FG/BG já exposto pelo app.
    private var gatherTraceHitSentAtMS: Double?
    private var gatherTraceFirstProofAtMS: Double?
    private var gatherTraceFirstProgressAtMS: Double?
    private var gatherTraceTarget = ""
    private var gatherTraceLastSchedulerReportAtMS: Double = 0
    private let gatherEventGate = RealtimeEventGate()
    private let wildStateEventGate = RealtimeEventGate()
    private var liveDunesSeeds: [String: GatherSeed] = [:]
    private var dunesSnapshotVisibleCount = 0
    private var dunesDiscoverySeen = Set<String>()
    private var dunesScoutVisited = Set<String>()
    private var dunesScoutMoves = 0
    private var dunesZeroTargetSinceMS: Double?
    private var dunesLastZeroTargetDiagnosticAt: Double = 0
    private var dunesHeatBaselineAtMS: Double?
    private var dunesHeatBaselineHP = 100
    private var lastTrustedOwnHPAtMS: Double?
    private var lastTrustedOwnHPRegion: String?
    private var ownHPRevision = 0
    private var activeGatherMode: ActivityMode?
    private var activeDunesToolIdentity: DunesToolInstanceIdentity?
    private var dunesUnexpectedDamageDetail: String?

    private var currentGatherSignature: String?
    private var currentGatherKind: String?
    /// Último frame de ação de gather aceito como estado ativo. O heartbeat de
    /// Presence precisa repetir este frame, e não um pos vazio que equivale a
    /// limpar chop/mine enquanto o iOS atrasa a task em background.
    private var activeGatherAction: [String: Any]?
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
    /// Falhas consecutivas sem fish_bite atravessando células/spots. O log real
    /// mostrou que, quando este estado se torna global, trocar de spot não cura a
    /// Presence; o owner deve recriá-la preservando o progresso da sessão.
    private var fishGlobalNoBiteStreak = 0

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
    private var gatherSuccessOffset = 0
    private var gatherDisplayGoal: Int?
    private var safeStopReason: EngineStopReason?
    private var activeGatherToolType: String?
    private var activeCombatWeaponType = "wild_sword"
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
        roastMode: RoastPitMode = .trout,
        blacksmithSelection: BlacksmithSelection = .smith(.copperIngot, batch: 1, smeltGoal: 100),
        reporter: @escaping Reporter
    ) {
        self.socket = socket
        self.cookie = cookie
        self.shard = shard
        self.fishingBait = fishingBait
        self.roastMode = roastMode
        self.blacksmithSelection = blacksmithSelection
        self.reporter = reporter
        self.http = KintaraHTTPClient(cookie: cookie, shard: shard)
        self.gatherKnowledge = GatherKnowledgeStore()
        self.region = bootstrap.region
        self.position = bootstrap.position
        self.lifeEpoch = max(1, bootstrap.lifeEpoch)
        self.gatherPositionMemory = gatherKnowledge.positionSnapshot(region: bootstrap.region)
    }

    static func bootstrap(for mode: ActivityMode, fishingBait: FishingBait) -> PresenceBootstrap {
        guard mode == .fishing else { return bootstrap(for: mode) }
        switch fishingBait {
        case .trout:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: -17.5, z: -11.5))
        case .feather:
            return PresenceBootstrap(region: "pond", position: Position(x: -1.5, z: -1.5))
        default:
            // Unvalidated bait profiles are rejected before a fishing run.
            return bootstrap(for: mode)
        }
    }

    static func bootstrap(for mode: ActivityMode) -> PresenceBootstrap {
        switch mode {
        case .tree:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: -6.5, z: -18.5))
        case .iron, .blacksmith:
            return PresenceBootstrap(region: "frostmere", position: Position(x: 5.5, z: -18.5))
        case .silver, .cacti:
            return PresenceBootstrap(region: "desert", position: GatherRegionPolicy.startPosition(for: mode))
        case .coal, .stone, .chicken:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: 22.5, z: -3.5))
        case .fishing, .zombie, .dragon:
            return PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
        case .roastPit:
            return PresenceBootstrap(region: "pond", position: Position(x: -1.5, z: -1.5))
        }
    }

    /// Compatibilidade com chamadas antigas que ainda pedem o bootstrap sem
    /// fornecer a decisão autoritativa do preflight.
    static func bootstrapForRun(for mode: ActivityMode, cookie: String) async -> PresenceBootstrap {
        bootstrap(for: mode)
    }

    /// Build 73/74 architecture: if preflight needs bank service, the first
    /// Presence starts in World. AppStore closes it after World/bank_shop/World
    /// and opens a fresh Presence already bootstraped in the activity region.
    static func bootstrapForRun(
        for mode: ActivityMode,
        gatherDisposition: GatherToolPreflightDisposition
    ) -> PresenceBootstrap {
        guard mode.isGathering else { return bootstrap(for: mode) }
        if case .needsWorld = gatherDisposition {
            if DunesWorldPreflightPolicy.requiresWorldBankService(for: mode) {
                return DunesWorldPreflightPolicy.bankBootstrap
            }
            return PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
        }
        return bootstrap(for: mode)
    }

    static func blacksmithRepairTargets(cookie: String) async throws -> [RepairTarget] {
        let state = try await KintaraHTTPClient(cookie: cookie).backpackState()
        return BlacksmithProtocolPolicy.repairTargets(in: state.backpack)
    }

    static func gatherToolPreflightDisposition(for mode: ActivityMode, cookie: String) async -> GatherToolPreflightDisposition {
        guard mode.isGathering, let fallback = ActivityToolPolicy.requiredTool(for: mode) else { return .ready }

        do {
            let state = try await KintaraHTTPClient(cookie: cookie).backpackState()
            guard let best = ActivityToolPolicy.bestSelection(in: state.backpack, for: mode) else {
                return .missing(tool: fallback)
            }
            return GatherToolPreflightPolicy.disposition(
                tool: best.type,
                carried: best.carried,
                bank: best.bank
            )
        } catch {
            // Same fail-closed behavior as the stable v3.0 flow: a read failure
            // starts in World and lets the definitive engine re-read inventory.
            return .needsWorld(tool: fallback)
        }
    }

    @discardableResult
    static func ensureGatherToolCarried(for mode: ActivityMode, cookie: String) async throws -> Int {
        guard mode.isGathering, let fallback = ActivityToolPolicy.requiredTool(for: mode) else { return 0 }
        let client = KintaraHTTPClient(cookie: cookie)
        let state = try await client.backpackState()
        guard let best = ActivityToolPolicy.bestSelection(in: state.backpack, for: mode) else {
            throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(fallback))
        }
        if best.carried >= 1 { return best.carried }
        guard best.bank >= 1 else { throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(fallback)) }
        let tool = best.type
        let carried = try await client.ensureCarriedItem(type: tool, quantity: 1, preferHotbar: true)
        let confirmed = try await client.itemLocationCounts(type: tool)
        guard carried >= 1 || confirmed.carried >= 1 else {
            throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(tool))
        }
        return max(carried, confirmed.carried)
    }

    /// Roast Pit uses the same proven transactional pattern as Fishing:
    /// World -> bank_shop -> World, then AppStore closes that Presence and opens
    /// a fresh Pond Presence on the same shard. Only the exact amount required
    /// for this goal is exposed in the activity region.
    func prepareRoastPitLoadoutFromWorld(goal: Int) async throws {
        let wanted = max(1, goal)

        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }

        var food = try await http.itemLocationCounts(type: roastMode.rawItem)
        var wood = try await http.itemLocationCounts(type: "wood")
        let foodTotal = food.carried + food.bank
        let woodTotal = wood.carried + wood.bank

        guard foodTotal >= wanted else {
            throw EngineError.missingRequiredItem("\(roastMode.label) \(foodTotal)/\(wanted)")
        }
        guard woodTotal >= wanted else {
            throw EngineError.missingRequiredItem("Wood \(woodTotal)/\(wanted)")
        }

        reporter(.log("🔥 Preflight Roast Pit • \(roastMode.label) total=\(foodTotal) • Wood total=\(woodTotal) • meta=\(wanted)"))

        if food.carried < wanted || wood.carried < wanted {
            reporter(.state(.syncing, "🏦 Preparando Roast Pit no banco"))
            try await ensureWorldBankAccess(reason: "Roast Pit • \(roastMode.label) + Wood")

            if food.carried < wanted {
                _ = try await http.ensureCarriedItem(
                    type: roastMode.rawItem,
                    quantity: wanted,
                    preferHotbar: false
                )
            }

            if wood.carried < wanted {
                _ = try await http.ensureCarriedItem(
                    type: "wood",
                    quantity: wanted,
                    preferHotbar: false
                )
            }

            food = try await http.itemLocationCounts(type: roastMode.rawItem)
            wood = try await http.itemLocationCounts(type: "wood")

            guard food.carried >= wanted else {
                throw EngineError.missingRequiredItem("\(roastMode.label) carregada \(food.carried)/\(wanted)")
            }
            guard wood.carried >= wanted else {
                throw EngineError.missingRequiredItem("Wood carregada \(wood.carried)/\(wanted)")
            }

            reporter(.log("🏦 Roast Pit • retirado do banco: \(roastMode.label) \(food.carried)/\(wanted) + Wood \(wood.carried)/\(wanted) ✅"))
            try await leaveBankShopToWorld(reason: "Roast Pit preparado")
        } else {
            reporter(.log("🔥 Roast Pit • materiais já carregados: \(roastMode.label) \(food.carried)/\(wanted) + Wood \(wood.carried)/\(wanted) ✅"))
        }

        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }

        reporter(.log("🔥 Preflight Roast Pit concluído • Presence World pronta para handoff ao Pond"))
    }

    private func runRoastPit(goal: Int) async throws {
        let target = max(1, goal)

        reporter(.state(.syncing, "Sincronizando The Pond"))
        guard try await waitForRegion("pond", timeoutMS: 6_000) else {
            throw EngineError.regionNotConfirmed("pond")
        }
        region = "pond"

        let rawCounts = try await http.itemLocationCounts(type: roastMode.rawItem)
        let woodCounts = try await http.itemLocationCounts(type: "wood")
        guard rawCounts.carried >= target else {
            throw EngineError.missingRequiredItem("\(roastMode.label) carregada \(rawCounts.carried)/\(target)")
        }
        guard woodCounts.carried >= target else {
            throw EngineError.missingRequiredItem("Wood carregada \(woodCounts.carried)/\(target)")
        }

        var cookingXPTotal = 0
        if let playerID {
            cookingXPTotal = (try? await http.skillXP(playerID: playerID, skill: "cooking")) ?? 0
        }

        reporter(.log("🔥 Roast Pit iniciado • \(roastMode.label) • meta \(target) • Cooking Lv. mínimo \(roastMode.minCookingLevel) • Cooking XP inicial \(cookingXPTotal)"))

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        var confirmedApproach: Position?
        var candidateIndex = 0
        var cookedCount = 0
        var burnedCount = 0

        while successes < target {
            try Task.checkCancellation()
            let cycle = successes + 1

            if confirmedApproach == nil {
                let candidate = RoastPitProtocolPolicy.approachPositions[candidateIndex % RoastPitProtocolPolicy.approachPositions.count]
                reporter(.state(.moving, "Indo até o Roast Pit"))
                try await walk(to: candidate, maxSeconds: 45, status: "Indo até o Roast Pit")
                try await sleep(RoastPitProtocolPolicy.proximityRetryMS)
            }

            // The official client schedules one batch every 10 seconds. Expose
            // that exact window to the HUD instead of a generic "cooldown".
            for second in stride(from: 10, through: 1, by: -1) {
                try Task.checkCancellation()
                reporter(.roastCountdown(
                    mode: roastMode,
                    cycle: cycle,
                    goal: target,
                    secondsRemaining: second
                ))
                try await sleep(1_000)
            }
            reporter(.roastCountdown(
                mode: roastMode,
                cycle: cycle,
                goal: target,
                secondsRemaining: 0
            ))

            var response: [String: Any]
            do {
                response = try await http.grantCook(mode: roastMode)
                if confirmedApproach == nil {
                    confirmedApproach = RoastPitProtocolPolicy.approachPositions[candidateIndex % RoastPitProtocolPolicy.approachPositions.count]
                    reporter(.diagnostic("[ROAST] proximidade autoritativa confirmada no candidato #\(candidateIndex + 1)"))
                }
            } catch HTTPError.response(_, let message, _) where message == "not_at_roast_pit" {
                confirmedApproach = nil
                candidateIndex = (candidateIndex + 1) % RoastPitProtocolPolicy.approachPositions.count
                reporter(.log("🔥 Roast Pit • posição rejeitada pelo servidor • reposicionando antes de repetir o ciclo \(cycle)/\(target)"))
                continue
            }

            let burned = RealtimeProtocol.bool(response["burned"]) ?? false
            let previousCookingXP = cookingXPTotal
            if let xp = response["xp"] as? [String: Any],
               let serverCookingXP = RealtimeProtocol.int(xp["cooking"]) {
                cookingXPTotal = max(0, serverCookingXP)
            } else if let playerID,
                      let refreshed = try? await http.skillXP(playerID: playerID, skill: "cooking") {
                cookingXPTotal = max(0, refreshed)
            }

            let xpGained = burned ? 0 : max(0, cookingXPTotal - previousCookingXP)
            if burned {
                burnedCount += 1
            } else {
                cookedCount += 1
            }

            successes += 1
            reporter(.attempt)
            reporter(.roastResult(
                mode: roastMode,
                cycle: successes,
                goal: target,
                burned: burned,
                xpGained: xpGained,
                cookingXPTotal: cookingXPTotal,
                cookedCount: cookedCount,
                burnedCount: burnedCount
            ))

            if burned {
                reporter(.log("🔥 Ciclo \(successes)/\(target) • \(roastMode.label) QUEIMOU • +0 Cooking XP • Cooking XP total \(cookingXPTotal) • cozidos \(cookedCount) • queimados \(burnedCount)"))
            } else {
                reporter(.log("✅ Ciclo \(successes)/\(target) • \(roastMode.label) assado • +\(xpGained) Cooking XP • Cooking XP total \(cookingXPTotal) • cozidos \(cookedCount) • queimados \(burnedCount)"))
            }
        }
    }


    func prepareBlacksmithLoadoutFromWorld(goal: Int) async throws {
        guard try await waitForRegion("world", timeoutMS: 5_000) else { throw EngineError.regionNotConfirmed("world") }

        var required: [String: Int] = [:]
        var smithRecipe: BlacksmithRecipe?
        var smithBatch = 1

        switch blacksmithSelection {
        case .smith(let recipe, let selectedBatch, let selectedSmeltGoal):
            let batch = BlacksmithProtocolPolicy.normalizedBatchQuantity(selectedBatch)
            let sessionGoal = BlacksmithProtocolPolicy.smithSessionGoal(
                recipe: recipe,
                batch: batch,
                smeltGoal: selectedSmeltGoal
            )
            let totalUnits = BlacksmithProtocolPolicy.smithOutputUnits(
                recipe: recipe,
                batch: batch,
                smeltGoal: selectedSmeltGoal
            )
            smithRecipe = recipe
            smithBatch = batch
            required = BlacksmithProtocolPolicy.smithMaterialCosts(
                recipe: recipe,
                batch: batch,
                smeltGoal: selectedSmeltGoal
            )
            reporter(.smithPreflight(recipe: recipe, batch: batch, required: required))
            if recipe.stackable {
                reporter(.log("⚒️ Preflight • \(recipe.label) • meta \(sessionGoal) × lote \(batch) = \(totalUnits) itens • \(required.sorted { $0.key < $1.key }.map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) \($0.value)" }.joined(separator: " • "))"))
            } else {
                reporter(.log("⚒️ Preflight • \(recipe.label) • lote ×\(batch) = \(totalUnits) ferramentas • \(required.sorted { $0.key < $1.key }.map { "\(BlacksmithProtocolPolicy.materialLabel($0.key)) \($0.value)" }.joined(separator: " • "))"))
            }
        case .repair(let target):
            let state = try await http.backpackState()
            guard let current = BlacksmithProtocolPolicy.currentTarget(target, in: state.backpack) else { throw EngineError.blacksmithRepairTargetChanged }
            required = BlacksmithProtocolPolicy.repairMaterialCosts(type: current.type, missingDurability: current.maxDurability - current.durability)
            reporter(.log("🔧 Repair preflight • \(current.label) • \(current.durability)/\(current.maxDurability)"))
        }

        var bankNeeded = false
        for (material, quantity) in required {
            let counts = try await http.itemLocationCounts(type: material)
            guard counts.carried + counts.bank >= quantity else {
                throw EngineError.missingRequiredItem("\(BlacksmithProtocolPolicy.materialLabel(material)) \(counts.carried + counts.bank)/\(quantity)")
            }
            if counts.carried < quantity { bankNeeded = true }
        }

        if bankNeeded {
            try await ensureWorldBankAccess(reason: "Frostmere Smith")
        }

        var withdrawn: [String: Int] = [:]
        var remaining: [String: Int] = [:]

        for (material, quantity) in required.sorted(by: { $0.key < $1.key }) {
            let before = try await http.itemLocationCounts(type: material)
            if before.carried < quantity {
                _ = try await http.ensureCarriedItem(type: material, quantity: quantity, preferHotbar: false)
            }

            let verified = try await http.itemLocationCounts(type: material)
            guard verified.carried >= quantity else {
                throw EngineError.missingRequiredItem("\(BlacksmithProtocolPolicy.materialLabel(material)) carregado \(verified.carried)/\(quantity)")
            }

            let moved = max(0, verified.carried - before.carried)
            withdrawn[material] = moved
            remaining[material] = verified.bank
            reporter(.log("🏦 \(BlacksmithProtocolPolicy.materialLabel(material)) • retirado \(moved) • banco restante \(verified.bank)"))
        }

        if let smithRecipe {
            reporter(.smithBank(recipe: smithRecipe, batch: smithBatch, withdrawn: withdrawn, remaining: remaining))
        }

        if bankNeeded {
            try await leaveBankShopToWorld(reason: "Frostmere Smith preparado")
        }

        guard try await waitForRegion("world", timeoutMS: 5_000) else { throw EngineError.regionNotConfirmed("world") }
        reporter(.log("⚒️ Preflight Frostmere Smith concluído"))
    }

    private func enterFrostmereSmith() async throws {
        guard try await waitForRegion("frostmere", timeoutMS: 6_000) else { throw EngineError.regionNotConfirmed("frostmere") }
        reporter(.state(.moving, "Indo ao Frostmere Smith"))
        try await walk(to: BlacksmithProtocolPolicy.frostmereEntrancePosition, maxSeconds: 45, status: "Indo ao Frostmere Smith")
        try await setRegion(BlacksmithProtocolPolicy.region, at: BlacksmithProtocolPolicy.interiorPosition)
        guard try await waitForRegion(BlacksmithProtocolPolicy.region, timeoutMS: 6_000) else { throw EngineError.regionNotConfirmed(BlacksmithProtocolPolicy.region) }
        reporter(.log("⚒️ Frostmere Smith confirmado • blacksmith_shop"))
    }

    private func runBlacksmith(goal: Int) async throws {
        try await enterFrostmereSmith()
        switch blacksmithSelection {
        case .repair(let selected):
            let before = try await http.backpackState()
            guard let target = BlacksmithProtocolPolicy.currentTarget(selected, in: before.backpack) else { throw EngineError.blacksmithRepairTargetChanged }
            let expected = BlacksmithProtocolPolicy.repairMaterialCosts(type: target.type, missingDurability: target.maxDurability - target.durability)
            reporter(.attempt)
            do {
                let response = try await http.blacksmithRepair(target: target)
                let refreshed = try await http.backpackState()
                let after = BlacksmithProtocolPolicy.slotDurability(target, in: refreshed.backpack) ?? target.maxDurability
                let costs = Self.intDictionary(response["costs"]) ?? expected
                successes = 1
                reporter(.repairResult(target: target, durabilityAfter: after, costs: costs))
                reporter(.log("✅ Repair • \(target.label) • \(target.durability)→\(after)/\(target.maxDurability)"))
            } catch HTTPError.response(_, let code, let payload) {
                throw EngineError.blacksmithFailure(BlacksmithProtocolPolicy.serverErrorMessage(code: code, payload: payload))
            }

        case .smith(let recipe, let selectedBatch, let selectedSmeltGoal):
            let batch = BlacksmithProtocolPolicy.normalizedBatchQuantity(selectedBatch)
            let target = BlacksmithProtocolPolicy.smithSessionGoal(
                recipe: recipe,
                batch: batch,
                smeltGoal: selectedSmeltGoal
            )
            let expectedOutput = BlacksmithProtocolPolicy.smithOutputUnits(
                recipe: recipe,
                batch: batch,
                smeltGoal: selectedSmeltGoal
            )
            var xpTotal = 0
            if let playerID {
                xpTotal = (try? await http.skillXP(playerID: playerID, skill: "smithing")) ?? 0
            }

            if recipe.stackable {
                reporter(.log("⚒️ \(recipe.label) • meta \(target) ciclos • lote ×\(batch) • produção prevista \(expectedOutput) • Smithing mínimo \(recipe.smithingLevel) • XP inicial \(xpTotal)"))
            } else {
                reporter(.log("⚒️ \(recipe.label) • Forge ×\(batch) • total \(expectedOutput) ferramentas • Smithing mínimo \(recipe.smithingLevel) • XP inicial \(xpTotal)"))
            }

            let hb = Task { [weak self] in await self?.heartbeat() }
            defer { hb.cancel() }

            while successes < target {
                try Task.checkCancellation()

                let cycle = successes + 1
                // Smelt respeita o lote por chamada (1/5/10). Forge volta à
                // semântica original: cada chamada produz uma ferramenta e o
                // seletor 1/5/10 define somente quantas ferramentas serão feitas.
                let requestQuantity = recipe.stackable ? batch : 1
                let waitSeconds = max(1, BlacksmithProtocolPolicy.smithSecondsPerUnit * requestQuantity)

                for seconds in stride(from: waitSeconds, through: 1, by: -1) {
                    reporter(.smithCountdown(recipe: recipe, completed: successes, goal: target, batch: batch, secondsRemaining: seconds))
                    try await sleep(1_000)
                }
                reporter(.smithCountdown(recipe: recipe, completed: successes, goal: target, batch: batch, secondsRemaining: 0))
                reporter(.attempt)

                let response: [String: Any]
                do {
                    response = try await http.blacksmithSmith(recipe: recipe.id, quantity: requestQuantity)
                } catch HTTPError.response(_, let code, let payload) {
                    throw EngineError.blacksmithFailure(BlacksmithProtocolPolicy.serverErrorMessage(code: code, payload: payload))
                }

                let previousXP = xpTotal
                if let xp = response["xp"] as? [String: Any],
                   let value = RealtimeProtocol.int(xp["smithing"]) {
                    xpTotal = max(0, value)
                } else if let playerID,
                          let value = try? await http.skillXP(playerID: playerID, skill: "smithing") {
                    xpTotal = max(0, value)
                }

                let gained = max(0, xpTotal - previousXP)
                let produced = max(1, RealtimeProtocol.int(response["resultQty"]) ?? requestQuantity)
                successes += 1
                let inventoryTotal = (try? await http.itemLocationCounts(type: recipe.result).carried) ?? 0

                reporter(.smithResult(
                    recipe: recipe,
                    completed: successes,
                    goal: target,
                    produced: produced,
                    inventoryTotal: inventoryTotal,
                    xpGained: gained,
                    smithingXPTotal: xpTotal
                ))
                reporter(.log("✅ Ciclo \(cycle)/\(target) • \(recipe.label) ×\(produced) • inventário \(inventoryTotal) • +\(gained) Smithing XP • XP total \(xpTotal)"))
            }
        }
    }

    private static func intDictionary(_ value: Any?) -> [String:Int]? {
        guard let raw=value as? [String:Any] else { return nil }
        var out:[String:Int]=[:]
        for (k,v) in raw { if let n=RealtimeProtocol.int(v) { out[k]=n } }
        return out
    }

    func prepareIdentity() async {
        do {
            let me = try await http.get("/api/auth/me")
            if let player = me["player"] as? [String: Any], let id = RealtimeProtocol.int(player["id"]) {
                playerID = id
                if let hp = RealtimeProtocol.int(player["php"] ?? player["hp"]) { playerHP = hp }
                reporter(.diagnostic("[PLAYER] /api/auth/me confirmou playerId=\(id) • HP=\(playerHP)"))
            } else {
                reporter(.diagnostic("[PLAYER] /api/auth/me não trouxe player.id; confirmações by=self ficarão conservadoras"))
            }
        } catch {
            reporter(.diagnostic("[PLAYER] /api/auth/me falhou: \(error.localizedDescription)"))
        }
    }

    /// Build 98 fast path: critical gather packets are delivered straight from
    /// RealtimeSocket before the general AsyncStream/receiver chain. Processing
    /// still happens on this actor, preserving a single authoritative harvest
    /// state, but the waiting gather task is already suspended on its event gate.

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

        case "pvit":
            ingestPlayerVitals(packet)

        case "wild_mb_ack":
            ingestWildVitals(packet)

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
        case .dunesCheckpoint: label = "checkpoint adaptativo das Dunes"
        case .dunesHeatSafety: label = "proteção contra calor das Dunes"
        case .dunesDangerSafety: label = "dano não-térmico detectado nas Dunes"
        }
        reporter(.diagnostic("[STATE] safe-stop solicitado • motivo=\(label)"))
    }

    func run(
        mode: ActivityMode,
        goal: Int,
        successOffset: Int = 0,
        displayGoal: Int? = nil
    ) async throws -> EngineRunResult {
        successes = 0
        gatherSuccessOffset = max(0, successOffset)
        gatherDisplayGoal = displayGoal
        safeStopCompleted = false
        try Task.checkCancellation()

        switch mode {
        case .tree, .coal, .stone, .iron, .silver, .cacti:
            try await runGather(mode: mode, goal: goal)
        case .fishing:
            try await runFishing(goal: goal)
        case .roastPit:
            try await runRoastPit(goal: goal)
        case .blacksmith:
            try await runBlacksmith(goal: goal)
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

    /// A reconnection in the Dunes never resumes gathering. Its only allowed
    /// action is to recover authoritative state and leave through the East→Shores
    /// north portal, waiting for fresh beach snapshots before teardown.
    func runEmergencyDunesExit(
        reason: String = "reconexão de emergência",
        expectedTool: DunesToolInstanceIdentity? = nil,
        expectedLifeEpoch: Int? = nil
    ) async throws -> EmergencyDunesExitResult {
        reporter(.state(.recovering, "Sincronizando estado das Dunes"))
        let syncDeadline = nowMS + 8_000
        while nowMS < syncDeadline {
            try Task.checkCancellation()
            if let authoritative = serverRegion?.lowercased(), !authoritative.isEmpty {
                if !GatherRegionPolicy.isDunesRegion(authoritative) {
                    region = authoritative
                    if authoritative == "beach" {
                        var observedSerial = regionSnapshotSerial
                        for confirmation in 1...2 {
                            try await sendPosition(moving: false, full: true)
                            let deadline = nowMS + 5_000
                            var confirmed = false
                            while nowMS < deadline {
                                try Task.checkCancellation()
                                if lastSnapshotRegion == "beach", regionSnapshotSerial > observedSerial {
                                    observedSerial = regionSnapshotSerial
                                    confirmed = true
                                    break
                                }
                                try await sleep(80)
                            }
                            guard confirmed else {
                                throw EngineError.regionNotConfirmed("The Shores por snapshot autoritativo \(confirmation)/2")
                            }
                        }
                        try await verifyDunesExitSurvival(
                            expectedLifeEpoch: expectedLifeEpoch ?? lifeEpoch,
                            expectedTool: expectedTool ?? activeDunesToolIdentity
                        )
                    }
                    reporter(.log("✅ Estado autoritativo • região=\(authoritative) • personagem fora das Dunes"))
                    return .alreadySafe
                }
                region = authoritative
                break
            }
            try await sleep(80)
        }
        guard let authoritative = serverRegion?.lowercased(), GatherRegionPolicy.isDunesRegion(authoritative) else {
            throw EngineError.regionNotConfirmed("estado autoritativo das Dunes após reconexão")
        }
        if safeStopReason == nil { safeStopReason = .connectionLoss }
        try await exitDunesToShores(
            reason: reason,
            expectedTool: expectedTool,
            expectedLifeEpoch: expectedLifeEpoch
        )
        safeStopCompleted = true
        return .shoresSafe
    }

    // MARK: - Common state

    private func ingestSnapshot(_ packet: [String: Any]) async {
        let previousHP = playerHP
        let previousShield = playerShield

        if let packetRegion = packet["region"] as? String, !packetRegion.isEmpty {
            serverRegion = packetRegion
            lastRegionConfirmationSource = "snapshot"
            lastSnapshotRegion = packetRegion.lowercased()
            regionSnapshotSerial += 1
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
                var nextDunesSeeds: [String: GatherSeed] = [:]
                if GatherRegionPolicy.isDunesRegion(snapshotRegion) {
                    dunesSnapshotVisibleCount = res.count
                }

                for group in res {
                    if GatherRegionPolicy.isDunesRegion(snapshotRegion) {
                        let observation = DunesResourceDiscovery.observe(group)
                        rememberDunesDiscovery(observation, region: snapshotRegion, source: "snap.res")
                        if let seed = makeDunesSeed(from: observation, region: snapshotRegion) {
                            nextDunesSeeds[seed.signature] = seed
                            let until = RealtimeProtocol.double(group["until"]) ?? (now + 2_500)
                            for key in seed.keys { cooldownUntil["\(seed.kind):\(key)"] = until }
                        }
                    }

                    let kind = ((group["kind"] ?? group["k"]) as? String) ?? ""
                    let keys = stringArray(group["keys"] ?? group["key"])
                    guard !kind.isEmpty, !keys.isEmpty else { continue }
                    rememberGatherMetadata(
                        region: snapshotRegion,
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

                if GatherRegionPolicy.isDunesRegion(snapshotRegion) {
                    // Dunes availability is generation-local. Replace, do not merge,
                    // so a resource that vanished from the authoritative snapshot is
                    // never chased from stale memory.
                    liveDunesSeeds = nextDunesSeeds
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
        var snapshotPosition = position
        if let players = packet["players"] as? [[String: Any]], let id = playerID,
           let me = players.first(where: { RealtimeProtocol.int($0["id"]) == id }) {
            if let x = RealtimeProtocol.double(me["x"]), let z = RealtimeProtocol.double(me["z"]) {
                snapshotPosition.x = x
                snapshotPosition.z = z
                if let y = RealtimeProtocol.double(me["y"]) { snapshotPosition.y = y }
                if let ry = RealtimeProtocol.double(me["ry"]) { snapshotPosition.ry = ry }
            }
            if let hp = RealtimeProtocol.int(me["php"]) { await recordSnapshotOwnHP(hp, source: "snap.players", regionHint: serverRegion) }
            if let shield = RealtimeProtocol.int(me["wsh"]) { playerShield = shield }
            if let le = RealtimeProtocol.int(me["le"]), le > lifeEpoch { lifeEpoch = le }
        }

        if let vitals = packet["playersVital"] as? [[String: Any]], let id = playerID,
           let me = vitals.first(where: { RealtimeProtocol.int($0["id"] ?? $0["pid"]) == id }) {
            if let hp = RealtimeProtocol.int(me["php"]) { await recordSnapshotOwnHP(hp, source: "snap.playersVital", regionHint: serverRegion) }
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

        reporter(.player(snapshotPosition, hp: playerHP, shield: playerShield, region: serverRegion ?? region))
        let aliveChickenCount = chickens.values.filter { $0.alive }.count
        let aliveWildCount = wildMobs.values.filter { $0.alive }.count
        reporter(.world(
            nodes: availableSeedCount(),
            mobs: MobTelemetryPolicy.visibleCount(chickenAlive: aliveChickenCount, wildAlive: aliveWildCount),
            serverRegion: serverRegion
        ))
    }

    private func recordTrustedOwnHP(_ hp: Int, regionHint: String? = nil) {
        let previousHP = playerHP
        let trustedRegion = (regionHint ?? serverRegion ?? region)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let timestamp = nowMS

        if GatherRegionPolicy.isDunesRegion(trustedRegion),
           let baseline = dunesHeatBaselineAtMS,
           hp < previousHP {
            let conservativeBefore = DunesHeatSafetyPolicy.estimatedHP(
                baselineHP: dunesHeatBaselineHP,
                elapsedMS: timestamp - baseline
            )
            if DunesDamageSafetyPolicy.isUnexpectedDamage(observedHP: hp, conservativeHP: conservativeBefore),
               activeGatherMode?.isDunesGathering == true,
               safeStopReason == nil {
                dunesUnexpectedDamageDetail = "HP \(previousHP)→\(hp) • térmico esperado≈\(conservativeBefore)"
                safeStopReason = .dunesDangerSafety
                reporter(.state(.recovering, "Dano externo nas Dunes • saída imediata"))
                reporter(.log("🚨 Proteção das Dunes • queda de HP incompatível com calor • \(dunesUnexpectedDamageDetail ?? "-") • coleta bloqueada • saída imediata para The Shores"))
            }
        }

        playerHP = hp
        ownHPRevision += 1
        lastTrustedOwnHPAtMS = timestamp
        lastTrustedOwnHPRegion = trustedRegion

        guard GatherRegionPolicy.isDunesRegion(trustedRegion) else { return }
        guard let baseline = dunesHeatBaselineAtMS else {
            dunesHeatBaselineAtMS = timestamp
            dunesHeatBaselineHP = hp
            return
        }

        // Repeated/stale snapshots with the same or a higher HP must not restart
        // the heat clock. Only a value at-or-below the already conservative
        // estimate may tighten the baseline. A confirmed Potion+ recovery resets
        // the baseline explicitly in enforceDunesHeatSafetyIfNeeded().
        let conservativeBefore = DunesHeatSafetyPolicy.estimatedHP(
            baselineHP: dunesHeatBaselineHP,
            elapsedMS: timestamp - baseline
        )
        if hp < dunesHeatBaselineHP, hp <= conservativeBefore {
            dunesHeatBaselineAtMS = timestamp
            dunesHeatBaselineHP = hp
        }
    }

    private func recordSnapshotOwnHP(_ hp: Int, source: String, regionHint: String? = nil) async {
        let trustedRegion = (regionHint ?? serverRegion ?? region)
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let conservative = estimatedDunesHPFromMonotonicClock()
        guard DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: playerHP, snapshotHP: hp, conservativeHP: conservative, region: trustedRegion
        ) else {
            recordTrustedOwnHP(hp, regionHint: trustedRegion)
            return
        }
        let revision = ownHPRevision
        reporter(.diagnostic("[DUNES][HP] snapshot suspeito • fonte=\(source) • atual=\(playerHP) • snapshot=\(hp) • conservador=\(conservative)"))
        // Build 86 protection from main3: Presence-opening snapshots may be stale.
        // A suspicious snapshot is not damage proof; /me must confirm it before
        // HP is changed or dunesDangerSafety is triggered. Authoritative own pvit
        // is still applied immediately by recordTrustedOwnHP.
        reporter(.diagnostic("[DUNES][HP] aguardando /me antes de classificar snapshot suspeito"))
        do {
            let me = try await http.get("/api/auth/me")
            guard ownHPRevision == revision else {
                reporter(.diagnostic("[DUNES][HP] confirmação descartada • vital mais novo chegou durante /me"))
                return
            }
            if let player = me["player"] as? [String: Any],
               let authoritativeHP = RealtimeProtocol.int(player["php"] ?? player["hp"]) {
                reporter(.diagnostic("[DUNES][HP] snapshot=\(hp) • /me=\(authoritativeHP) • fonte=\(source)"))
                recordTrustedOwnHP(authoritativeHP, regionHint: trustedRegion)
                return
            }
        } catch {
            reporter(.diagnostic("[DUNES][HP] /me indisponível • fail-safe aceita HP baixo • \(error.localizedDescription)"))
        }
        if ownHPRevision == revision { recordTrustedOwnHP(hp, regionHint: trustedRegion) }
    }

    private func hasRecentTrustedDunesHP(maxAgeMS: Double = 5_000) -> Bool {
        guard let at = lastTrustedOwnHPAtMS,
              let trustedRegion = lastTrustedOwnHPRegion,
              GatherRegionPolicy.isDunesRegion(trustedRegion)
        else { return false }
        return nowMS - at <= maxAgeMS
    }

    private func ingestPlayerVitals(_ packet: [String: Any]) {
        let packetPlayerID = RealtimeProtocol.int(packet["pid"] ?? packet["id"])
        guard OwnVitalsPolicy.shouldApplyPvit(packetPlayerID: packetPlayerID, playerID: playerID) else { return }
        let previousHP = playerHP
        let previousShield = playerShield
        if let hp = RealtimeProtocol.int(packet["php"]) { recordTrustedOwnHP(hp) }
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

    /// `wild_mb_ack` is a direct reply to this client's Wild contact and Node
    /// v5.2 accepts its vitals without requiring pid/id. Keep that semantic
    /// separate from the broadcast `pvit` identity gate.
    private func ingestWildVitals(_ packet: [String: Any]) {
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
        lastSnapshotRegion = nil
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
        activeGatherAction = nil
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
        let stopReasonAtEntry = safeStopReason
        if let status, !status.isEmpty {
            reporter(.state(.moving, status))
        }
        let speed = MovementProgressPolicy.speed
        let dt = MovementProgressPolicy.frameSeconds
        var sentFrames = 0

        while true {
            try Task.checkCancellation()
            // Se uma vital autoritativa disparar o firewall das Dunes enquanto
            // caminhamos para um recurso, abandone esse deslocamento no próximo
            // frame (~150 ms). Quando a caminhada já começou como parte da saída
            // segura, `stopReasonAtEntry` não é nil e ela deve continuar.
            if stopReasonAtEntry == nil,
               safeStopReason != nil,
               activeGatherMode?.isDunesGathering == true {
                return
            }
            if safeStopReason == nil,
               let mode = activeGatherMode,
               mode.isDunesGathering,
               try await enforceDunesHeatSafetyIfNeeded(mode: mode) == false {
                return
            }
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

        if stopReasonAtEntry == nil,
           safeStopReason != nil,
           activeGatherMode?.isDunesGathering == true { return }
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
                if let action = activeFishingAction {
                    try await sendPosition(moving: false, action: action)
                } else if let action = activeGatherAction {
                    // Build 113: no BG heartbeat is allowed to clear an in-flight
                    // chop/mine. Re-send only the latest authoritative action
                    // frame; no catch-up/burst and no extra hit is generated.
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
        activeGatherMode = mode
        activeGatherAction = nil
        defer {
            activeGatherAction = nil
            activeGatherMode = nil
        }
        // Build 62: ordinary Gathering reaches this point with its tool already
        // materialized before Presence; Dunes keeps its dedicated preflight.
        // The tool still must be authoritatively present before any action.
        try await ensureActivityToolLoadout(for: mode)

        let targetRegion = GatherRegionPolicy.region(for: mode)
        let start = GatherRegionPolicy.startPosition(for: mode)
        if mode.isDunesGathering {
            liveDunesSeeds.removeAll(keepingCapacity: true)
            dunesSnapshotVisibleCount = 0
            dunesDiscoverySeen.removeAll(keepingCapacity: true)
            dunesScoutVisited.removeAll(keepingCapacity: true)
            dunesScoutMoves = 0
            dunesZeroTargetSinceMS = nil
            dunesLastZeroTargetDiagnosticAt = 0
        }
        reporter(.state(.syncing, "Sincronizando \(prettyRegion(targetRegion))"))
        if serverRegion?.lowercased() != targetRegion {
            try await setRegion(targetRegion, at: start)
        }
        guard try await waitForRegion(targetRegion, timeoutMS: 6_000) else {
            throw EngineError.regionNotConfirmed(targetRegion)
        }
        let dunesExposureStartedAtMS = mode.isDunesGathering ? nowMS : nil
        if mode.isDunesGathering {
            // Never start a full-loot harvest from an unverified/local HP value.
            // Wait briefly for an own-player snapshot/pvit from this Dunes Presence.
            let vitalsDeadline = nowMS + 5_000
            while !hasRecentTrustedDunesHP(), nowMS < vitalsDeadline {
                try Task.checkCancellation()
                try await sleep(80)
            }
            guard hasRecentTrustedDunesHP() else {
                safeStopReason = .dunesHeatSafety
                reporter(.state(.recovering, "HP autoritativo indisponível • saindo das Dunes"))
                reporter(.log("🛑 Proteção das Dunes • HP próprio não confirmado por snapshot/pvit • nenhuma coleta iniciada • saída para The Shores obrigatória"))
                try await exitDunesToShores(reason: "HP autoritativo indisponível")
                safeStopCompleted = true
                return
            }
            guard let exposedTool = activeDunesToolIdentity else {
                throw EngineError.gatherLoadoutNotReady("identidade física da ferramenta das Dunes")
            }
            reporter(.dunesExposure(tool: exposedTool, lifeEpoch: lifeEpoch))
            reporter(.diagnostic("[DUNES][SAFETY] proteção Build 78 iniciada • HP autoritativo base=\(dunesHeatBaselineHP) • 1 HP/10s conservador • limite=\(DunesHeatSafetyPolicy.minimumSafeHP) • lifeEpoch=\(lifeEpoch)"))
            reporter(.log("❤️‍🔥 Proteção Dunes Build 78 • limite efetivo=\(DunesHeatSafetyPolicy.minimumSafeHP) HP • dano não-térmico força saída • checkpoint em até \(DunesCheckpointPolicy.successInterval) sucessos ou 180s"))
            if try await enforceDunesHeatSafetyIfNeeded(mode: mode) == false {
                try await exitDunesToShores(reason: "proteção contra calor")
                safeStopCompleted = true
                return
            }
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

        var confirmedResourceBalances: [String: Int] = [:]
        if let expectedResource = GatherLootMarkerPolicy.resource(for: mode),
           let initialBalance = try? await http.resourceBalance(expectedResource) {
            confirmedResourceBalances[expectedResource] = initialBalance
            reporter(.diagnostic("[INVENTORY] saldo inicial autoritativo • \(expectedResource)=\(initialBalance)"))
        }

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
            if safeStopReason != nil { break }
            if try await enforceDunesHeatSafetyIfNeeded(mode: mode) == false { break }
            if let dunesExposureStartedAtMS,
               DunesCheckpointPolicy.exposureLimitReached(startedAtMS: dunesExposureStartedAtMS, nowMS: nowMS) {
                safeStopReason = .dunesCheckpoint
                reporter(.state(.recovering, "Checkpoint por tempo • saindo das Dunes"))
                reporter(.log("⏱️ Dunes • 180s de exposição atingidos com \(successes)/\(goal) sucessos no lote • saindo para The Shores e protegendo recursos"))
                break
            }
            reporter(.state(.searching, "Procurando \(mode.displayName.lowercased())"))

            guard let seed = selectGatherSeed(for: mode) else {
                reporter(.target(nil))
                if mode.isDunesGathering {
                    if let scout = selectDunesScoutSeed(for: mode) {
                        dunesScoutVisited.insert(scout.signature)
                        dunesScoutMoves += 1
                        let scoutLabel = scout.modeHint?.displayName ?? scout.kind
                        reporter(.state(.moving, "Explorando as Dunes"))
                        reporter(.log("🧭 \(mode.displayName) • nenhum alvo elegível no snapshot atual • scout \(dunesScoutMoves)/3 usando \(scoutLabel) \(scout.targetKey) apenas como âncora; nenhuma coleta do recurso errado será enviada"))
                        let scoutPosition = gatherPositionMemory[scout.signature] ?? scout.position
                        try await walk(to: scoutPosition, status: "Explorando recursos das Dunes")
                        if safeStopReason != nil { break }
                        if try await enforceDunesHeatSafetyIfNeeded(mode: mode) == false { break }
                        position.ry = scoutPosition.ry
                        try await sendPosition(moving: false)
                        try await sleep(900)
                        continue
                    }
                    reportDunesZeroTargetIfNeeded(mode: mode)
                } else {
                    reporter(.diagnostic("[GATHER] Nenhum alvo disponível agora; aguardando cooldown/defer"))
                }
                try await sleep(1_500)
                continue
            }
            dunesZeroTargetSinceMS = nil

            reporter(.target("\(mode.displayName) • \(seed.keys.joined(separator: ","))"))
            reporter(.state(.selectingTarget, "Alvo \(seed.targetKey)"))
            reporter(.log("🎯 \(mode.displayName) \(seed.targetKey) selecionado"))

            let interactionPosition = gatherPositionMemory[seed.signature] ?? seed.position
            try await walk(to: interactionPosition, status: "Indo até \(mode.displayName) \(seed.targetKey)")
            if safeStopReason != nil { break }
            if try await enforceDunesHeatSafetyIfNeeded(mode: mode) == false { break }
            position.ry = interactionPosition.ry
            try await sendPosition(moving: false)
            reporter(.diagnostic("[MOVE] arrived \(seed.targetKey) pos=\(format(position.x)),\(format(position.z)) ry=\(format(position.ry))"))

            let result = try await harvestWithRecovery(seed: seed, mode: mode)
            if safeStopReason != nil { break }
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
                var resourceMarker: String?
                if let loot = result.loot, !loot.isEmpty {
                    do {
                        // Fluxo síncrono já comprovado no 100/100: o próximo
                        // alvo só nasce depois que este FELLED foi salvo e o
                        // saldo autoritativo correspondente foi confirmado.
                        let total = try await http.persistLoot(loot, amount: 1)
                        if let total {
                            let previous = confirmedResourceBalances[loot]
                            let marker = GatherLootMarkerPolicy.label(item: loot, previous: previous, current: total)
                            confirmedResourceBalances[loot] = total
                            persistenceLabel = marker
                            resourceMarker = marker
                        } else {
                            persistenceLabel = "\(loot) persistido • saldo não retornado"
                        }
                    } catch {
                        persistenceLabel = "persistência falhou: \(error.localizedDescription)"
                        reporter(.diagnostic("[INVENTORY][ERROR] \(error.localizedDescription)"))
                    }
                }

                successes += 1
                let displaySuccesses = gatherSuccessOffset + successes
                let displayGoal = gatherDisplayGoal ?? goal
                reporter(.gatherSuccess(result.loot, absolute: displaySuccesses))
                reporter(.state(.cooldown, "Concluído \(displaySuccesses)/\(displayGoal)"))
                reporter(.log("✅ \(mode.displayName) concluído • h=\(result.h)/\(result.hm) • \(persistenceLabel) • \(displaySuccesses)/\(displayGoal)"))
                if let resourceMarker {
                    reporter(.log("📦 Marcador de recurso • \(mode.displayName) • \(resourceMarker)"))
                }
                if mode.isDunesGathering {
                    reporter(.diagnostic("[DUNES] alvo confirmado • kind=\(seed.kind) • keys=\(seed.keys.joined(separator: ",")) • loot=\(result.loot ?? "-")"))
                }
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

        if mode.isDunesGathering {
            let reason: String
            switch safeStopReason {
            case .dunesCheckpoint: reason = "checkpoint por 180s de exposição"
            case .dunesHeatSafety: reason = "proteção térmica"
            case .dunesDangerSafety: reason = "dano não-térmico / risco externo"
            case .backgroundExpiration: reason = "encerramento externo"
            case .user: reason = "STOP"
            case .connectionLoss: reason = "perda de conexão"
            case .none: reason = "meta concluída"
            }
            try await exitDunesToShores(reason: reason)
            if safeStopReason != nil { safeStopCompleted = true }
        }

        let displaySuccesses = gatherSuccessOffset + successes
        let displayGoal = gatherDisplayGoal ?? goal
        reporter(.log("📊 Coleta encerrada • \(mode.displayName) • sucessos=\(displaySuccesses)/\(displayGoal) • recoveries internos=\(gatherInternalRecoveries) • proof misses=\(gatherProofMisses)"))
    }

    /// Dunes are full-loot and heat continues while the player remains there.
    /// Completion is not returned until two fresh authoritative beach snapshots
    /// have stabilized the supported north-portal transition.
    private func verifyDunesExitSurvival(
        expectedLifeEpoch: Int,
        expectedTool: DunesToolInstanceIdentity?
    ) async throws {
        guard let expectedTool else {
            throw EngineError.dunesExitSurvivalUnconfirmed("ferramenta exposta sem identidade")
        }
        if lifeEpoch > expectedLifeEpoch {
            throw EngineError.dunesDeathDuringExit("lifeEpoch \(expectedLifeEpoch)→\(lifeEpoch)")
        }

        var lastError: Error?
        for attempt in 1...3 {
            do {
                let me = try await http.get("/api/auth/me")
                let player = me["player"] as? [String: Any]
                let backpack = (me["backpack"] as? [String: Any])
                    ?? (player?["backpack"] as? [String: Any])
                    ?? [:]
                let observedEpoch = RealtimeProtocol.int(player?["le"] ?? me["lifeEpoch"] ?? me["le"])
                let observedHP = RealtimeProtocol.int(player?["php"] ?? player?["hp"] ?? me["php"] ?? me["hp"])
                let toolPresent = DunesExitSurvivalPolicy.toolStillCarried(expectedTool, in: backpack)

                guard DunesExitSurvivalPolicy.survived(
                    expectedLifeEpoch: expectedLifeEpoch,
                    observedLifeEpoch: observedEpoch,
                    hp: observedHP,
                    toolStillCarried: toolPresent
                ) else {
                    let iidLabel = expectedTool.iid == nil ? "sem-iid" : "iid-confirmável"
                    throw EngineError.dunesDeathDuringExit(
                        "Shores recebida, mas sobrevivência falhou • lifeEpoch=\(observedEpoch.map(String.init) ?? "?") esperado<=\(expectedLifeEpoch) • HP=\(observedHP.map(String.init) ?? "?") • ferramenta \(iidLabel)=\(toolPresent ? "presente" : "ausente")"
                    )
                }
                reporter(.log("🛡️ Sobrevivência confirmada em The Shores • lifeEpoch=\(observedEpoch.map(String.init) ?? String(lifeEpoch)) • ferramenta exposta preservada ✅"))
                return
            } catch let error as EngineError {
                switch error {
                case .dunesDeathDuringExit:
                    throw error
                default:
                    lastError = error
                }
            } catch {
                lastError = error
            }
            if attempt < 3 { try await sleep(250) }
        }
        throw EngineError.dunesExitSurvivalUnconfirmed(lastError?.localizedDescription ?? "/api/auth/me indisponível")
    }

    private func exitDunesToShores(
        reason: String,
        expectedTool overrideTool: DunesToolInstanceIdentity? = nil,
        expectedLifeEpoch overrideLifeEpoch: Int? = nil
    ) async throws {
        let expectedLifeEpoch = overrideLifeEpoch ?? lifeEpoch
        let expectedTool = overrideTool ?? activeDunesToolIdentity

        // Build 85: dunesDangerSafety is irreversible. If the external hit has
        // already put us at/below the thermal floor, spend at most one Potion+
        // before walking. Never run the synthetic heat-tick driver here: escape
        // remains the only objective after this point.
        if safeStopReason == .dunesDangerSafety,
           GatherRegionPolicy.isDunesRegion((serverRegion ?? region).lowercased()),
           DunesDamageSafetyPolicy.shouldEmergencyHeal(observedHP: playerHP) {
            let before = playerHP
            let type = DunesHeatSafetyPolicy.healthPotionPlusType
            if !potionStockLoaded { try? await refreshPotionStock(logSummary: false) }
            if currentPotionStock(type) > 0 {
                reporter(.log("🆘 Dunes • emergência irreversível • HP \(before) • tentando uma Health Potion+ antes da fuga"))
                let consumed = (try? await consumePotion(type)) ?? false
                if consumed {
                    reporter(.log("💚 Dunes • Health Potion+ aceita em emergência • fuga continua imediatamente"))
                } else {
                    reporter(.log("⚠️ Dunes • poção de emergência não confirmada • fuga continua sem nova tentativa"))
                }
            } else {
                reporter(.log("⚠️ Dunes • HP \(before) em emergência e sem Health Potion+ confirmada • fuga imediata"))
            }
        }
        let authoritative = (serverRegion ?? region).lowercased()
        guard GatherRegionPolicy.isDunesRegion(authoritative) else {
            guard authoritative == "beach" else {
                throw EngineError.regionNotConfirmed("The Shores antes do encerramento")
            }
            region = "beach"
            var observedSerial = regionSnapshotSerial
            for confirmation in 1...2 {
                try await sendPosition(moving: false, full: true)
                let deadline = nowMS + 5_000
                var confirmed = false
                while nowMS < deadline {
                    try Task.checkCancellation()
                    if lastSnapshotRegion == "beach", regionSnapshotSerial > observedSerial {
                        observedSerial = regionSnapshotSerial
                        confirmed = true
                        break
                    }
                    try await sleep(80)
                }
                guard confirmed else {
                    throw EngineError.regionNotConfirmed("The Shores por snapshot autoritativo \(confirmation)/2")
                }
            }
            try await verifyDunesExitSurvival(expectedLifeEpoch: expectedLifeEpoch, expectedTool: expectedTool)
            reporter(.log("🛡️ Dunes • personagem já está em The Shores • snapshots + sobrevivência confirmados"))
            return
        }
        guard authoritative == "desert" else {
            throw EngineError.regionNotConfirmed("saída segura disponível somente pelas Dunes East")
        }

        reporter(.state(.recovering, "Saindo das Dunes com segurança"))
        reporter(.log("🛡️ Dunes • \(reason) • caminhando até a saída norte para The Shores"))
        let pen = GatherRegionPolicy.startPosition(for: .silver)
        try await walk(to: pen, maxSeconds: 70, status: "Retornando à saída das Dunes")
        try await walk(to: GatherRegionPolicy.dunesExitPosition, maxSeconds: 12, status: "Cruzando para The Shores")

        for probe in 1...3 {
            let serialBefore = regionSnapshotSerial
            try await setRegion("beach", at: GatherRegionPolicy.shoresArrivalPosition)
            guard try await waitForRegion("beach", timeoutMS: 5_000) else {
                reporter(.diagnostic("[DUNES] The Shores sem ACK/snapshot • probe \(probe)/3"))
                continue
            }

            let firstDeadline = nowMS + 5_000
            while nowMS < firstDeadline {
                try Task.checkCancellation()
                if lastSnapshotRegion == "beach", regionSnapshotSerial > serialBefore { break }
                try await sleep(80)
            }
            guard lastSnapshotRegion == "beach", regionSnapshotSerial > serialBefore else {
                reporter(.diagnostic("[DUNES] beach ACK recebido, mas snapshot autoritativo não estabilizou • probe \(probe)/3"))
                continue
            }

            let firstSnapshotSerial = regionSnapshotSerial
            try await sendPosition(moving: false, full: true)
            let stableDeadline = nowMS + 5_000
            while nowMS < stableDeadline {
                try Task.checkCancellation()
                if lastSnapshotRegion == "beach", regionSnapshotSerial > firstSnapshotSerial {
                    try await verifyDunesExitSurvival(expectedLifeEpoch: expectedLifeEpoch, expectedTool: expectedTool)
                    reporter(.log("✅ The Shores confirmada • 2 snapshots + sobrevivência + ferramenta preservada • Presence pronta para encerramento"))
                    return
                }
                try await sleep(80)
            }
            reporter(.diagnostic("[DUNES] primeiro snapshot beach recebido, mas faltou confirmação estável • probe \(probe)/3"))
        }
        throw EngineError.regionNotConfirmed("The Shores por snapshots autoritativos após saída das Dunes")
    }

    /// Heat bypasses shield in Dunes East. At the authoritative HP threshold,
    /// attempt one Health Potion+; without a confirmed recovery, stop creating
    /// gather actions and force the terminal path through The Shores.
    private func enforceDunesHeatSafetyIfNeeded(mode: ActivityMode) async throws -> Bool {
        if safeStopReason == .dunesDangerSafety {
            reporter(.state(.recovering, "Risco externo nas Dunes • saindo"))
            return false
        }
        let safetyHP = min(playerHP, estimatedDunesHPFromMonotonicClock())
        guard DunesHeatSafetyPolicy.requiresRecovery(hp: safetyHP, mode: mode) else { return true }

        if !potionStockLoaded { try await refreshPotionStock(logSummary: false) }
        let type = DunesHeatSafetyPolicy.healthPotionPlusType
        if currentPotionStock(type) > 0 {
            let before = playerHP
            if try await consumePotion(type) {
                reporter(.log("❤️‍🔥 Calor das Dunes • Health Potion+ aceita com HP \(before) • aguardando pvit/snapshot"))
                let confirmed = try await driveDunesHealthPotionPlusTicks(beforeDoseHP: before)
                if confirmed, playerHP > DunesHeatSafetyPolicy.minimumSafeHP {
                    dunesHeatBaselineAtMS = nowMS
                    dunesHeatBaselineHP = playerHP
                    reporter(.log("✅ Proteção térmica confirmada • HP \(before) → \(playerHP) • coleta retomada"))
                    return true
                }
                reporter(.log("⚠️ Health Potion+ consumida, mas o servidor não confirmou recuperação suficiente • nenhuma segunda dose será arriscada"))
            }
        }

        safeStopReason = .dunesHeatSafety
        reporter(.state(.recovering, "Proteção contra calor • encerrando coleta"))
        reporter(.log("🛑 Proteção das Dunes • HP servidor=\(playerHP)/100 • HP conservador=\(safetyHP)/100 • coleta interrompida • saída para The Shores obrigatória"))
        return false
    }

    private func estimatedDunesHPFromMonotonicClock() -> Int {
        guard let baseline = dunesHeatBaselineAtMS else { return playerHP }
        return DunesHeatSafetyPolicy.estimatedHP(
            baselineHP: dunesHeatBaselineHP,
            elapsedMS: nowMS - baseline
        )
    }

    private func maySendGatherAction(for mode: ActivityMode) async throws -> Bool {
        guard safeStopReason == nil else { return false }
        if mode.isDunesGathering {
            return try await enforceDunesHeatSafetyIfNeeded(mode: mode)
        }
        return true
    }

    private func driveDunesHealthPotionPlusTicks(beforeDoseHP: Int) async throws -> Bool {
        let maximumAfterDose = min(100, beforeDoseHP + 50)
        try await sleep(650)
        for _ in 0..<5 {
            try Task.checkCancellation()
            guard playerHP > 0 else { throw EngineError.playerDead }
            if playerHP >= maximumAfterDose || playerHP >= DunesHeatSafetyPolicy.recoveryGoalHP { break }
            let beforeTick = playerHP
            let proposed = min(maximumAfterDose, min(100, beforeTick + 10))
            try await sendPosition(moving: false, action: ["php": proposed])
            try await sleep(35)
            try await sendPosition(moving: false, action: ["php": proposed])

            let deadline = nowMS + 1_100
            while nowMS < deadline, playerHP <= beforeTick {
                try Task.checkCancellation()
                try await sleep(60)
            }
            if playerHP <= beforeTick { break }
        }
        return playerHP > beforeDoseHP
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
            try await equip(activeGatherToolType ?? ActivityToolPolicy.requiredTool(for: mode) ?? (seed.kind == "tree" ? "tool_axe" : "tool_pickaxe"))
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
        activeGatherAction = nil
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
        gatherTraceHitSentAtMS = nil
        gatherTraceFirstProofAtMS = nil
        gatherTraceFirstProgressAtMS = nil
        gatherTraceTarget = seed.targetKey

        let tool = activeGatherToolType ?? ActivityToolPolicy.requiredTool(for: mode) ?? (kind == "tree" ? "tool_axe" : "tool_pickaxe")
        try await equip(tool)

        position.ry = position.ry.isFinite ? position.ry : seed.position.ry
        position.y = 0.25
        guard try await maySendGatherAction(for: mode) else {
            return HarvestResult(felled: false, h: harvestH, hm: harvestHM, loot: harvestLoot, reason: "Dunes safety stop", accepted: false, proofMiss: false)
        }
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

        func sendGatherFrame(_ action: [String: Any]) async throws {
            activeGatherAction = action
            try await sendPosition(moving: false, action: action)
        }

        func sendProfile(_ second: Bool, progressive: Bool) async throws {
            if safeStopReason != nil { return }
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
                    guard try await maySendGatherAction(for: mode) else { return }
                    position.y = 0.25 + delta
                    try await sendGatherFrame(["act": "chop", "eq": tool])
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
                        guard try await maySendGatherAction(for: mode) else { return }
                        let shape = Self.mineMP1[index] / shapeMax
                        let value = min(1, mineProgress + max(0, next - mineProgress) * shape)
                        position.y = 0.25 + Self.mineY1[index]
                        try await sendGatherFrame(["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": value])
                        mineProgress = max(mineProgress, value)
                    }
                } else {
                    for index in mpProfile.indices {
                        if index > 0 { try await waitRelative(GatherTimingPolicy.mineFrameGapMS) }
                        guard try await maySendGatherAction(for: mode) else { return }
                        mineProgress = max(mineProgress, mpProfile[index])
                        position.y = 0.25 + yProfile[index % yProfile.count]
                        try await sendGatherFrame(["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": mineProgress])
                    }
                }
            }

            if maxSchedulerDelayMS >= GatherTimingPolicy.delayedFrameDiagnosticThresholdMS,
               gatherLastTimingDiagnosticAt == 0 || nowMS - gatherLastTimingDiagnosticAt >= GatherTimingPolicy.timingDiagnosticCooldownMS {
                gatherLastTimingDiagnosticAt = nowMS
                reporter(.diagnostic("[GATHER][TIMING] scheduler atrasou até \(maxSchedulerDelayMS)ms • perfil preservado com espaçamento relativo • nenhuma rajada enviada"))
            }
            if maxSchedulerDelayMS > 0,
               gatherTraceLastSchedulerReportAtMS == 0 || nowMS - gatherTraceLastSchedulerReportAtMS >= 5_000 {
                gatherTraceLastSchedulerReportAtMS = nowMS
                reporter(.diagnostic("[GATHER][TRACE] scheduler • alvo=\(seed.targetKey) • drift_max=\(maxSchedulerDelayMS)ms • perfil=\(kind)"))
            }
        }

        func sendHit(proof: String?) async throws {
            guard try await maySendGatherAction(for: mode) else { return }
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
            gatherTraceHitSentAtMS = lastHitAt
            gatherTraceFirstProofAtMS = nil
            gatherTraceFirstProgressAtMS = nil
            reporter(.diagnostic("[GATHER][TRACE] hit enviado • alvo=\(seed.targetKey) • h=\(harvestH)/\(harvestHM < 99 ? String(harvestHM) : "?")"))
        }

        func waitForAck(proofBefore: Int, wearBefore: Int, hBefore: Int, timeoutMS: Int) async throws -> HarvestAck {
            func inspect() -> HarvestAck? {
                if harvestHM < 99, harvestH >= harvestHM { return .felled }
                let sawFreshProof = harvestProofSerial > proofBefore && !harvestProof.isEmpty
                let sawProgress = harvestWearSerial > wearBefore || harvestH > hBefore
                if sawFreshProof && sawProgress { return .accepted }
                return nil
            }

            if let immediate = inspect() {
                let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
                reporter(.diagnostic("[GATHER][TRACE] ACK imediato • alvo=\(seed.targetKey) • total=\(elapsed)ms • h=\(harvestH)/\(harvestHM)"))
                return immediate
            }
            let ackWaitStartedAt = nowMS
            let deadline = nowMS + Double(timeoutMS)
            var eventSerial = await gatherEventGate.serial
            while nowMS < deadline {
                try Task.checkCancellation()
                let remaining = max(1, Int(deadline - nowMS))
                let signaled = try await gatherEventGate.wait(after: eventSerial, timeoutMS: remaining)
                eventSerial = await gatherEventGate.serial
                if let state = inspect() {
                    let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
                    reporter(.diagnostic("[GATHER][TRACE] ACK aceito • alvo=\(seed.targetKey) • total=\(elapsed)ms • espera=\(max(0, Int((nowMS - ackWaitStartedAt).rounded())))ms • h=\(harvestH)/\(harvestHM)"))
                    return state
                }
                if !signaled { break }
            }

            if let final = inspect() {
                let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
                reporter(.diagnostic("[GATHER][TRACE] ACK no limite • alvo=\(seed.targetKey) • total=\(elapsed)ms • espera=\(max(0, Int((nowMS - ackWaitStartedAt).rounded())))ms • h=\(harvestH)/\(harvestHM)"))
                return final
            }

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
                if let graceState = inspect() {
                    let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
                    reporter(.diagnostic("[GATHER][TRACE] ACK grace • alvo=\(seed.targetKey) • total=\(elapsed)ms • h=\(harvestH)/\(harvestHM)"))
                    return graceState
                }
            }
            let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
            reporter(.diagnostic("[GATHER][TRACE] ACK timeout • alvo=\(seed.targetKey) • total=\(elapsed)ms • espera=\(max(0, Int((nowMS - ackWaitStartedAt).rounded())))ms • h=\(harvestH)/\(harvestHM)"))
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
                    // Reset explícito do handshake: impedir que o heartbeat
                    // ressuscite o frame anterior durante esta janela.
                    activeGatherAction = nil
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
            guard try await maySendGatherAction(for: mode) else { break }
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
                let elapsed = gatherTraceHitSentAtMS.map { max(0, Int((nowMS - $0).rounded())) } ?? -1
                let proofMS = gatherTraceFirstProofAtMS.flatMap { sent in gatherTraceHitSentAtMS.map { max(0, Int((sent - $0).rounded())) } } ?? -1
                let progressMS = gatherTraceFirstProgressAtMS.flatMap { seen in gatherTraceHitSentAtMS.map { max(0, Int((seen - $0).rounded())) } } ?? -1
                reporter(.diagnostic("[GATHER][TRACE] ACK incompleto • alvo=\(seed.targetKey) • total=\(elapsed)ms • proof=\(proofMS)ms • progresso=\(progressMS)ms • h=\(harvestH)/\(harvestHM)"))
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
        if gatherTraceFirstProofAtMS == nil {
            gatherTraceFirstProofAtMS = nowMS
            if let sent = gatherTraceHitSentAtMS {
                reporter(.diagnostic("[GATHER][TRACE] action_proof • alvo=\(gatherTraceTarget) • +\(max(0, Int((nowMS - sent).rounded())))ms"))
            }
        }
        gatherResourceSerial += 1
        await gatherEventGate.signal()
        reporter(.diagnostic("[GATHER] action_proof #\(harvestProofSerial)"))
    }

    private func ingestResourceEvent(_ packet: [String: Any]) async {
        let eventRegion = ((packet["region"] as? String) ?? serverRegion ?? region)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let dunesObservation = GatherRegionPolicy.isDunesRegion(eventRegion)
            ? DunesResourceDiscovery.observe(packet)
            : nil
        let kind = dunesObservation?.wireKind ?? (((packet["kind"] ?? packet["k"]) as? String) ?? "")
        let keys = dunesObservation?.keys ?? stringArray(packet["keys"] ?? packet["key"])
        let by = RealtimeProtocol.int(packet["by"])

        if let dunesObservation {
            rememberDunesDiscovery(dunesObservation, region: eventRegion, source: "res_evt")
            if let seed = makeDunesSeed(from: dunesObservation, region: eventRegion) {
                liveDunesSeeds[seed.signature] = seed
            }
        }

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
        if changed {
            harvestWearSerial += 1
            if harvestHM < 99 {
                reporter(.gatherProgress(h: harvestH, hm: harvestHM))
            }
            if gatherTraceFirstProgressAtMS == nil {
                gatherTraceFirstProgressAtMS = nowMS
                if let sent = gatherTraceHitSentAtMS {
                    reporter(.diagnostic("[GATHER][TRACE] res_evt progresso • alvo=\(gatherTraceTarget) • +\(max(0, Int((nowMS - sent).rounded())))ms • h=\(harvestH)/\(harvestHM)"))
                }
            }
        }
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
            subtype = GatherRegionPolicy.isDunesRegion(normalizedRegion) ? "cacti" : "tree"
        } else if GatherRegionPolicy.isDunesRegion(normalizedRegion) {
            subtype = "silver"
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
        if GatherRegionPolicy.isDunesRegion(normalizedRegion) {
            result.append(contentsOf: liveDunesSeeds.values.filter { $0.region == normalizedRegion })
        }
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

    private func makeDunesSeed(from observation: DunesResourceDiscovery.Observation, region: String) -> GatherSeed? {
        guard let mode = observation.mode,
              !observation.wireKind.isEmpty,
              !observation.keys.isEmpty else { return nil }
        guard let interaction = canonicalGatherPositions(keys: observation.keys, region: region).first else { return nil }
        return GatherSeed(
            region: region,
            kind: observation.wireKind,
            keys: observation.keys,
            position: interaction,
            targetKey: observation.keys.first ?? "?",
            hasCoal: observation.hasCoal ?? false,
            hasMetal: observation.hasMetal ?? (mode == .silver),
            modeHint: mode
        )
    }

    private func rememberDunesDiscovery(
        _ observation: DunesResourceDiscovery.Observation,
        region: String,
        source: String
    ) {
        let signature = "\(source)|\(observation.classificationLabel)|\(observation.wireKind)|\(observation.keys.joined(separator: "|"))|\(observation.fieldNames.joined(separator: ","))"
        guard dunesDiscoverySeen.insert(signature).inserted else { return }
        reporter(.diagnostic("[DUNES DISCOVERY] \(source) • \(DunesResourceDiscovery.diagnosticSummary(observation))"))
        if observation.mode == nil || observation.keys.isEmpty {
            reporter(.log("🧭 Dunes discovery • recurso ainda não classificável • \(DunesResourceDiscovery.diagnosticSummary(observation))"))
        }
    }

    private func selectDunesScoutSeed(for mode: ActivityMode) -> GatherSeed? {
        guard mode.isDunesGathering, dunesScoutMoves < 3 else { return nil }
        return liveDunesSeeds.values
            .filter { seed in
                seed.modeHint != nil &&
                seed.modeHint != mode &&
                !dunesScoutVisited.contains(seed.signature)
            }
            .min { a, b in
                let pa = gatherPositionMemory[a.signature] ?? a.position
                let pb = gatherPositionMemory[b.signature] ?? b.position
                return distance(from: position, to: pa) < distance(from: position, to: pb)
            }
    }

    private func reportDunesZeroTargetIfNeeded(mode: ActivityMode) {
        let now = nowMS
        if dunesZeroTargetSinceMS == nil { dunesZeroTargetSinceMS = now }
        guard let since = dunesZeroTargetSinceMS, now - since >= 15_000 else {
            reporter(.diagnostic("[GATHER][DUNES] nenhum \(mode.displayName) elegível agora • visíveis=\(dunesSnapshotVisibleCount) • silver=\(liveDunesSeeds.values.filter { $0.modeHint == .silver }.count) • cacti=\(liveDunesSeeds.values.filter { $0.modeHint == .cacti }.count)"))
            return
        }
        guard now - dunesLastZeroTargetDiagnosticAt >= 15_000 else { return }
        dunesLastZeroTargetDiagnosticAt = now
        let silver = liveDunesSeeds.values.filter { $0.modeHint == .silver }.count
        let cacti = liveDunesSeeds.values.filter { $0.modeHint == .cacti }.count
        reporter(.log("⚠️ \(mode.displayName) • \(dunesSnapshotVisibleCount) recursos no snapshot, mas 0 alvos elegíveis após 15s • reconhecidos: silver=\(silver), cacti=\(cacti) • aguardando estado autoritativo, sem enviar ação às cegas"))
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
                region: targetRegion,
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
                seed.modeHint.map { $0 == mode } ??
                    GatherResourcePolicy.matches(mode: mode, region: seed.region, kind: seed.kind, hasCoal: seed.hasCoal, hasMetal: seed.hasMetal)
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
                modeOK = seed.modeHint.map { $0 == mode } ??
                    GatherResourcePolicy.matches(mode: mode, region: seed.region, kind: seed.kind, hasCoal: seed.hasCoal, hasMetal: seed.hasMetal)
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
        if serverRegion?.lowercased() == BankShopProtocolPolicy.region,
           region.lowercased() == BankShopProtocolPolicy.region {
            return
        }

        if serverRegion?.lowercased() != "world" || region.lowercased() != "world" {
            reporter(.state(.syncing, "🌍 Indo ao World • \(reason)"))
            try await setRegion(
                "world",
                at: Position(x: BankShopProtocolPolicy.worldEntranceX, z: BankShopProtocolPolicy.worldEntranceZ)
            )
            guard try await waitForRegion("world", timeoutMS: 5_000) else {
                throw EngineError.regionNotConfirmed("world")
            }
        }

        let entrance = Position(
            x: BankShopProtocolPolicy.worldEntranceX,
            z: BankShopProtocolPolicy.worldEntranceZ
        )
        if hypot(position.x - entrance.x, position.z - entrance.z) > 0.4 {
            try await walk(to: entrance, maxSeconds: 35, status: "🏦 Indo à entrada do banco • \(reason)")
        } else {
            position = entrance
            try await sendPosition(moving: false)
        }

        // Captura oficial: o save de entrada usa o stateSeq do World e acontece
        // imediatamente após o primeiro Presence em bank_shop, antes da retirada.
        let preTransition = try await http.backpackState()
        reporter(.diagnostic("[BANK] entrada • worldSeq=\(preTransition.stateSeq) • shard=\(shard) • reason=\(reason)"))

        try await setRegion(
            BankShopProtocolPolicy.region,
            at: Position(x: BankShopProtocolPolicy.interiorX, z: BankShopProtocolPolicy.interiorZ)
        )
        let transition = try await http.synchronizeBankShopEntry(from: preTransition)

        guard try await waitForRegion(BankShopProtocolPolicy.region, timeoutMS: 6_000) else {
            throw EngineError.bankTransitionFailed("region_ack(bank_shop) ausente")
        }

        let fresh = try await http.backpackState()
        guard fresh.stateSeq == transition.responseSeq else {
            throw EngineError.bankTransitionFailed(
                "stateSeq após entrada divergiu • resposta \(transition.responseSeq) • /me \(fresh.stateSeq)"
            )
        }
        reporter(.diagnostic("[BANK] bank_shop confirmado • stateSeq \(transition.baseSeq)→\(transition.responseSeq) • /me=\(fresh.stateSeq) • shard=\(shard)"))
    }

    private func leaveBankShopToWorld(reason: String) async throws {
        guard serverRegion?.lowercased() == BankShopProtocolPolicy.region ||
                region.lowercased() == BankShopProtocolPolicy.region else { return }
        reporter(.state(.syncing, "🌍 Saindo do banco • \(reason)"))
        try await setRegion(
            "world",
            at: Position(x: BankShopProtocolPolicy.worldEntranceX, z: BankShopProtocolPolicy.worldEntranceZ)
        )
        guard try await waitForRegion("world", timeoutMS: 6_000) else {
            throw EngineError.bankTransitionFailed("saída bank_shop→world sem confirmação")
        }
        reporter(.diagnostic("[BANK] saída bank_shop→world confirmada • shard=\(shard) • reason=\(reason)"))
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

    /// Tier-aware World bank path for ordinary Gathering. AppStore performs the
    /// Build 73 handoff after this method returns: this Presence ends in World
    /// and a fresh activity Presence is opened on the same shard.
    @discardableResult
    func prepareGatherToolFromWorld(for mode: ActivityMode) async throws -> Int {
        guard mode.isGathering, let fallback = ActivityToolPolicy.requiredTool(for: mode) else { return 0 }

        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }

        let state = try await http.backpackState()
        guard let best = ActivityToolPolicy.bestSelection(in: state.backpack, for: mode) else {
            throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(fallback))
        }
        let tool = best.type
        let name = ActivityToolPolicy.displayName(tool)

        if best.carried >= 1 {
            activeGatherToolType = tool
            reporter(.log("🧰 Preflight transacional • \(name) já está carregada ✅"))
            return best.carried
        }
        guard best.bank >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }

        try await ensureWorldBankAccess(reason: "buscar \(name)")
        let carried = try await http.ensureCarriedItem(type: tool, quantity: 1, preferHotbar: true)
        let confirmed = try await http.itemLocationCounts(type: tool)
        let finalCount = max(carried, confirmed.carried)
        guard finalCount >= 1 else {
            throw EngineError.missingRequiredItem(name)
        }
        activeGatherToolType = tool
        reporter(.log("🧰 Preflight transacional • \(name) retirada do banco e carregada ✅"))
        try await leaveBankShopToWorld(reason: "\(name) carregada")
        return finalCount
    }

    /// Build 74: full-loot Dunes preflight runs inside the proven
    /// World → bank_shop → World transaction. It selects the best valid tier,
    /// loads up to six Health Potion+, banks every other bankable carried item,
    /// verifies tool conservation, and returns to World before AppStore closes
    /// this Presence and opens a fresh `desert` Presence on the same shard.
    func prepareDunesLoadoutFromWorld(for mode: ActivityMode) async throws -> (
        tool: String,
        healthPotionPlus: Int,
        toolIdentity: DunesToolInstanceIdentity,
        lifeEpoch: Int
    ) {
        guard DunesWorldPreflightPolicy.requiresWorldBankService(for: mode),
              let fallback = ActivityToolPolicy.requiredTool(for: mode)
        else {
            throw EngineError.bankTransitionFailed("preflight Dunes solicitado para atividade incompatível")
        }

        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }

        try await ensureWorldBankAccess(reason: "preflight Dunes")
        do {
            let initial = try await http.backpackState()
            guard let best = ActivityToolPolicy.bestSelection(in: initial.backpack, for: mode) else {
                throw EngineError.missingRequiredItem(ActivityToolPolicy.displayName(fallback))
            }

            let selected = best.type
            let selectedName = ActivityToolPolicy.displayName(selected)
            let selectedInitialTotal = best.carried + best.bank
            guard let selectedInstance = DunesToolInstancePolicy.preferredInstance(in: initial.backpack, type: selected) else {
                throw EngineError.missingRequiredItem(selectedName)
            }

            if !selectedInstance.isCarried {
                let carried = try await http.ensureCarriedItem(
                    type: selected,
                    quantity: 1,
                    preferHotbar: true,
                    preferredBankIndex: selectedInstance.bankIndex
                )
                guard carried >= 1 else { throw EngineError.missingRequiredItem(selectedName) }
            }

            _ = try await http.ensurePotionLoadout(targets: [
                DunesHeatSafetyPolicy.healthPotionPlusType: DunesHeatSafetyPolicy.carriedHealthPotionPlusTarget
            ])

            // Health Potion+ is preserved by type because it is a consumable stack.
            // The gathering tool is preserved by exact physical identity; every
            // duplicate of the same tool type is banked before entering full-loot.
            let keep: Set<String> = [DunesHeatSafetyPolicy.healthPotionPlusType]
            let deposit = try await http.depositAllBankFirstInventory(
                preservingTypes: keep,
                preservingTool: selectedInstance.identity,
                preserveCombatLoadout: false
            )
            guard deposit.unresolved.isEmpty else {
                throw EngineError.bankDepositFailed(deposit.unresolved.sorted().joined(separator: ", "))
            }

            for (type, quantity) in deposit.confirmed.sorted(by: { $0.key < $1.key }) {
                reporter(.log("🏦 Dunes BANK-FIRST • \(quantity)x \(prettyItem(type)) → banco ✅"))
            }
            for detail in deposit.diagnostics {
                reporter(.diagnostic("[DUNES][BANK] \(detail)"))
            }

            let finalTool = try await http.itemLocationCounts(type: selected)
            let selectedFinalTotal = finalTool.carried + finalTool.bank
            guard selectedFinalTotal == selectedInitialTotal else {
                throw EngineError.bankDepositFailed(
                    "conservação de \(selectedName) falhou • total \(selectedInitialTotal)→\(selectedFinalTotal)"
                )
            }
            guard finalTool.carried == 1 else {
                throw EngineError.bankDepositFailed(
                    "full-loot exige exatamente 1x \(selectedName) carregada • confirmado=\(finalTool.carried)"
                )
            }

            let healthPotionPlus = try await http.itemLocationCounts(type: DunesHeatSafetyPolicy.healthPotionPlusType)
            activeGatherToolType = selected
            let durabilityLabel = selectedInstance.durability.map(String.init) ?? "?"
            let duplicatesProtected = deposit.confirmed[selected] ?? 0
            reporter(.log("🧰 Preflight Dunes • \(selectedName) carregada ✅ • d=\(durabilityLabel) • instâncias expostas=1"))
            if duplicatesProtected > 0 {
                reporter(.log("🏦 Dunes FULL-LOOT • \(duplicatesProtected)x \(selectedName) duplicada(s) protegida(s) no banco ✅"))
            }
            reporter(.log("❤️‍🔥 Preflight Dunes • Health Potion+ carregadas: \(healthPotionPlus.carried)/\(DunesHeatSafetyPolicy.carriedHealthPotionPlusTarget)"))
            try await leaveBankShopToWorld(reason: "preflight Dunes concluído")
            try await recoverDunesHPInWorldBeforeEntry()
            return (selected, healthPotionPlus.carried, selectedInstance.identity, lifeEpoch)
        } catch {
            // Ainda não entramos em full-loot. Tente abandonar o bank_shop antes
            // de propagar a falha, sem mascarar o erro original.
            try? await leaveBankShopToWorld(reason: "preflight Dunes abortado")
            throw error
        }
    }

    /// Build 93: the World regeneration zone is a safe checkpoint stage.
    /// Do not re-enter Dunes until HP=100 is observed authoritatively.
    private func recoverDunesHPInWorldBeforeEntry() async throws {
        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world para regeneração")
        }

        // Build 94: do not make an unnecessary trip when the authoritative
        // World Presence already confirms full HP. playerHP is only updated by
        // trusted pvit/snapshot or the /me confirmation path.
        if DunesWorldRecoveryPolicy.isRecovered(hp: playerHP) {
            reporter(.log("❤️ HP real confirmado • \(playerHP)/100 • regeneração dispensada"))
            return
        }

        reporter(.state(.recovering, "Recuperando HP no World"))
        reporter(.log("❤️ HP real confirmado • \(playerHP)/100 • recuperação necessária"))
        reporter(.log("💚 Dunes CHECKPOINT • indo à zona segura de regeneração no World"))
        try await walk(
            to: DunesWorldRecoveryPolicy.safePoint,
            maxSeconds: 35,
            status: "Indo à zona de regeneração"
        )
        try await sendPosition(moving: false, full: true)

        let deadline = nowMS + DunesWorldRecoveryPolicy.timeoutMS
        var lastReportedHP = -1
        while nowMS < deadline {
            try Task.checkCancellation()
            guard (serverRegion ?? region).lowercased() == "world" else {
                throw EngineError.regionNotConfirmed("world durante regeneração")
            }

            if DunesWorldRecoveryPolicy.isRecovered(hp: playerHP) {
                reporter(.log("💚 HP real confirmado • \(playerHP)/100 • retorno às Dunes liberado"))
                return
            }

            if playerHP != lastReportedHP {
                lastReportedHP = playerHP
                reporter(.log("❤️ Regeneração • HP real \(playerHP)/100"))
                reporter(.diagnostic("[DUNES][RECOVERY] zona World • HP autoritativo=\(playerHP)/100"))
            }

            // A posição fica parada dentro da área; heartbeats/snapshots são a
            // fonte da confirmação. Não sintetize HP e não use poção.
            try await sendPosition(moving: false)
            try await sleep(500)
        }

        throw EngineError.gatherLoadoutNotReady(
            "HP não chegou a 100/100 na zona de regeneração do World; reentrada nas Dunes bloqueada"
        )
    }

    private func ensureActivityToolLoadout(for mode: ActivityMode) async throws {
        guard let fallback = ActivityToolPolicy.requiredTool(for: mode) else { return }
        if mode.isGathering {
            let state = try await http.backpackState()
            if let best = ActivityToolPolicy.bestSelection(in: state.backpack, for: mode), best.carried >= 1 {
                activeGatherToolType = best.type
                if mode.isDunesGathering {
                    activeDunesToolIdentity = DunesToolInstancePolicy
                        .preferredInstance(in: state.backpack, type: best.type)?
                        .identity
                }
                reporter(.log("🧰 Preflight • \(ActivityToolPolicy.displayName(best.type)) carregada ✅"))
                return
            }
        } else {
            for tool in ActivityToolPolicy.acceptedTools(for: mode) {
                let counts = try await http.itemLocationCounts(type: tool)
                if counts.carried >= 1 {
                    reporter(.log("🧰 Preflight • \(ActivityToolPolicy.displayName(tool)) carregada ✅"))
                    return
                }
            }
        }
        let name = ActivityToolPolicy.displayName(fallback)

        // RC3.6: Gathering nunca volta da região de coleta ao World para buscar ferramenta.
        // Quando a ferramenta estava no banco, esta mesma engine já a trouxe em
        // World antes de iniciar o hot path de Gathering.
        if mode.isGathering {
            throw EngineError.gatherLoadoutNotReady(name)
        }

        let bankTool: String?
        if mode.isGathering {
            let state = try await http.backpackState()
            bankTool = ActivityToolPolicy.bestSelection(in: state.backpack, for: mode).flatMap { $0.bank >= 1 ? $0.type : nil }
        } else {
            var selected: String?
            for candidate in ActivityToolPolicy.acceptedTools(for: mode) {
                let counts = try await http.itemLocationCounts(type: candidate)
                if counts.bank >= 1 { selected = candidate; break }
            }
            bankTool = selected
        }
        guard let tool = bankTool else { throw EngineError.missingRequiredItem(name) }

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
        try await leaveBankShopToWorld(reason: "loadout de \(name) concluído")
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
            try await leaveBankShopToWorld(reason: "isca carregada")
        } else {
            reporter(.log("🪱 Preflight • \(fishingBait.displayName) \(counts.carried)/\(wanted) carregada ✅"))
        }
    }

    /// Fishing transaction: the first Presence is always World. It prepares
    /// rod + selected bait through World/bank_shop/World. AppStore then closes
    /// this Presence and opens a fresh Presence directly in the fishing region.
    func prepareFishingLoadoutFromWorld(goal: Int) async throws {
        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }
        try await ensureActivityToolLoadout(for: .fishing)
        guard let baitType = fishingBait.confirmedInventoryKey else {
            throw EngineError.unsupportedFishingBait(fishingBait.displayName)
        }
        try await ensureFishingBaitLoadout(type: baitType, goal: goal)
        guard try await waitForRegion("world", timeoutMS: 5_000) else {
            throw EngineError.regionNotConfirmed("world")
        }
        reporter(.log("🎣 Preflight Pesca concluído • vara + \(fishingBait.displayName) carregadas • Presence World pronta para handoff"))
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

        // Loadout was completed transactionally in the World Presence before
        // this activity Presence was created. Never return to World from here.
        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        let fishingRegion = fishingBait == .trout ? "eldergrove" : "pond"
        let fishingStand: Position
        if fishingRegion == "pond" {
            fishingStand = Position(x: -1.5, z: -1.5)
            reporter(.state(.moving, "Sincronizando The Pond"))
            guard try await waitForRegion("pond", timeoutMS: 6_000) else {
                throw EngineError.regionNotConfirmed("pond")
            }
            region = "pond"
            position = fishingStand
            try await sendPosition(moving: false)
            reporter(.log("✅ The Pond confirmado pela nova Presence • Herring/Feather"))
        } else {
            fishingStand = Position(x: -17.5, z: -11.5)
            reporter(.state(.moving, "Sincronizando Whisperwood para Trout"))
            // Presence was opened directly in ElderGrove. This avoids the same
            // World→ElderGrove transition timeout previously fixed for gathering.
            guard try await waitForRegion("eldergrove", timeoutMS: 6_000) else { throw EngineError.regionNotConfirmed("eldergrove") }
            region = "eldergrove"
            position = fishingStand
            try await sendPosition(moving: false)
            reporter(.log("✅ Whisperwood/Eldergrove confirmado pela Presence • Trout Bait"))
            reporter(.diagnostic("[FISH][TROUT] Presence direta eldergrove • gridOffset=24.5 • catch=fish_trout • bait=bait_trout"))
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

                // ElderGrove is much larger than The Pond. A healthy authoritative
                // spot can still exist outside the 6.5-cell casting radius. Do not
                // freeze on the original stand waiting for the nearby slot to move:
                // walk to another healthy server spot and resume there.
                if fishingBait == .trout, let recovery = selectFishRecoveryPosition() {
                    try? await clearAction()
                    reporter(.state(.moving, "Trout • reposicionando para outro spot válido"))
                    reporter(.log("🎣 Trout • spot próximo esgotado • indo ao Spot #\(recovery.slot) em \(recovery.c),\(recovery.r)"))
                    try await walk(to: recovery.position, maxSeconds: 30, status: "Indo para outro spot de Trout")
                    try await equip("tool_fishing_rod")
                    fishHealthWaitSerial = -1
                    try await sleep(500)
                    continue
                }

                // If no healthy reachable generation exists, wait only for a real
                // authoritative movement/refresh instead of hammering dead cells.
                if !fishBlockedCells.isEmpty || !fishQuarantinedGenerations.isEmpty {
                    if fishHealthWaitSerial != fishSnapshotSerial {
                        fishHealthWaitSerial = fishSnapshotSerial
                        reporter(.log("🎣 Spots atuais temporariamente descartados • aguardando nova geração autoritativa"))
                    }
                    reporter(.state(.recovering, "Pesca • aguardando novo spot válido"))
                }
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
                if changed {
                    fishingStats.spotChanged += 1
                } else {
                    fishingStats.noBite += 1
                    fishGlobalNoBiteStreak += 1
                }
                reporter(.failure("Peixe #\(fishNumber) • \(targetLabel) • \(reason)"))
                recordFishTargetFailure(target, reason: reason)
                if fishingBait == .trout, fishGlobalNoBiteStreak >= 12 {
                    reporter(.log("🔄 Trout • falha global de fish_bite detectada após \(fishGlobalNoBiteStreak) casts • recriando Presence sem voltar ao banco"))
                    throw EngineError.fishingPresenceStalled(successes: successes)
                }
                try await sleep(650)
                continue
            }

            // fish_bite autoritativo prova que a Presence e esta célula estão saudáveis agora.
            fishGlobalNoBiteStreak = 0
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

            let waitUntil = nowMS + Double(bite.ms + 70)
            var spotRotatedDuringWait = false
            var lastDisplayedTenth = Int.max
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

                let remainingMS = max(0, waitUntil - nowMS)
                let remainingTenth = Int(ceil(remainingMS / 100.0))
                if remainingTenth != lastDisplayedTenth {
                    lastDisplayedTenth = remainingTenth
                    let remainingSeconds = Double(remainingTenth) / 10.0
                    reporter(.state(.waitingResult, String(format: "Peixe #%d • fisgada em %.1fs", fishNumber, remainingSeconds)))
                }
                try await sleep(80)
            }
            if !spotRotatedDuringWait {
                reporter(.state(.waitingResult, "Peixe #\(fishNumber) • fisgada em 0.0s"))
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
                        try await recoverFishingAfterStale(stand: fishingStand)
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
                    try await recoverFishingAfterStale(stand: fishingStand)
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
                fish: fishingResourceCount(backpack, key: fishingCatchInventoryKey),
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
            lastFishingInventory.fish = fishingResourceCount(backpack, key: fishingCatchInventoryKey)
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

    private var fishingRegionName: String { fishingBait == .trout ? "eldergrove" : "pond" }
    private var fishingGridOffset: Double { fishingBait == .trout ? 24.5 : 19.5 }
    private var fishingCatchInventoryKey: String { fishingBait == .trout ? "fish_trout" : "fish" }

    private func ingestFishSpots(_ packet: [String: Any]) {
        if let packetRegion = packet["region"] as? String, !packetRegion.isEmpty, packetRegion.lowercased() != fishingRegionName { return }
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

        reporter(.world(
            nodes: availableSeedCount(),
            mobs: MobTelemetryPolicy.visibleCount(
                chickenAlive: chickens.values.filter { $0.alive }.count,
                wildAlive: wildMobs.values.filter { $0.alive }.count
            ),
            serverRegion: fishingRegionName
        ))
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

        let gridOffset = fishingGridOffset
        let playerCol = Int(round(position.x + gridOffset))
        let playerRow = Int(round(position.z + gridOffset))
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
        let gridOffset = fishingGridOffset
        let playerCol = Int(round(position.x + gridOffset))
        let playerRow = Int(round(position.z + gridOffset))
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

    private func selectFishRecoveryPosition() -> (slot: Int, c: Int, r: Int, position: Position)? {
        let minTTL = FishingRecoveryPolicy.minStartTTLMS
        let offset = fishingGridOffset
        let healthy = fishSpots.values
            .filter { remainingMS(for: $0) >= minTTL }
            .filter { !fishQuarantinedGenerations.contains(fishGenerationKey(slot: $0.slot, generation: $0.generation)) }
            .sorted { a, b in remainingMS(for: a) > remainingMS(for: b) }

        guard let spot = healthy.first else { return nil }
        // Put the player on the center of the authoritative 2x2 fishing cell.
        // Grid coordinates map to world coordinates through the same offset used
        // by selectFishTarget(). Keep y/rotation neutral; walk() supplies frames.
        let pos = Position(
            x: Double(spot.c) + 0.5 - offset,
            y: 0.25,
            z: Double(spot.r) + 0.5 - offset,
            ry: position.ry
        )
        return (spot.slot, spot.c, spot.r, pos)
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
        try await selectBestCarriedCombatWeapon()
        try await equip(activeCombatWeaponType)

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
            try await equip(activeCombatWeaponType)
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
                    try await equip(activeCombatWeaponType)
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
            try await equip(activeCombatWeaponType)
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
                try await sendPosition(moving: false, action: ["wss": wildSwordSeq, "eq": activeCombatWeaponType])

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
                try await sendPosition(moving: false, action: ["wmb": wildContactSeq, "wmx": dx / len, "wmz": dz / len, "eq": activeCombatWeaponType])

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

                // O probe de ground-bag começa em paralelo e nunca bloqueia o
                // recuo defensivo. Se o servidor exigir proximidade, esta é a
                // melhor janela: a requisição nasce enquanto o personagem ainda
                // está junto da posição da kill. O movimento para SAFE_CAMP segue
                // imediatamente no actor principal.
                let immediateGroundBagTask = startImmediateGroundBagCollection(
                    killPosition: lastTargetPosition,
                    baseline: groundBagBaseline
                )

                // Node v5.2.1: sobreviver aos pacotes/danos atrasados vem ANTES
                // de XP, loot ou seleção do próximo mob. O teste real de Dragon
                // morreu ~5 s após a kill com HP81/shield0, exatamente esta janela.
                do {
                    try await postKillSafety(mode: mode, defeatedMob: target, killPosition: lastTargetPosition)
                } catch {
                    immediateGroundBagTask?.cancel()
                    throw error
                }
                if emergencyBackgroundExitRequested {
                    immediateGroundBagTask?.cancel()
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

                let immediateGroundBagProbe = await immediateGroundBagTask?.value
                let drops = try await collectWildDrops(
                    mode: mode,
                    targetNumber: target.index,
                    killPosition: lastTargetPosition,
                    backpackBefore: backpackBefore?.backpack,
                    groundBagBaseline: groundBagBaseline,
                    immediateGroundBagProbe: immediateGroundBagProbe,
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
        try await equip(activeCombatWeaponType)
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

    private func selectBestCarriedCombatWeapon() async throws {
        let state = try await http.backpackState()
        guard let best = EquipmentTierPolicy.bestSelection(in: state.backpack, family: .sword, minimumTier: 1),
              best.carried >= 1 else {
            throw EngineError.missingRequiredItem("Sword")
        }
        activeCombatWeaponType = best.type
        reporter(.log("⚔️ Arma selecionada • \(best.type) • tier \(best.tier)"))
    }

    private func ensureBestCombatWeaponFromWorld() async throws {
        let state = try await http.backpackState()
        guard let best = EquipmentTierPolicy.bestSelection(in: state.backpack, family: .sword, minimumTier: 1) else {
            throw EngineError.missingRequiredItem("Sword")
        }

        var carried = best.carried
        if carried < 1, best.bank >= 1 {
            carried = try await http.ensureCarriedItem(type: best.type, quantity: 1, preferHotbar: true)
        }
        guard carried >= 1 else { throw EngineError.missingRequiredItem(best.type) }
        activeCombatWeaponType = best.type
        reporter(.log("⚔️ Melhor espada disponível carregada • \(best.type) • tier \(best.tier) ✅"))
    }

    /// Preparação BANK-FIRST da v5.2.1. Toda entrada inicial no Wild passa aqui:
    /// primeiro protege recursos comuns materializados em invSlots e só depois
    /// completa poções, quando necessário. Itens especiais nunca entram na allowlist.
    private func prepareWorldCombatSession(resupplyReason: String?) async throws {
        if serverRegion?.lowercased().hasPrefix("wild") == true || region.hasPrefix("wild") {
            throw EngineError.combatSupplyFailed("preparação de combate solicitada fora do World")
        }
        reporter(.state(.moving, "Protegendo inventário no banco"))
        try await ensureWorldBankAccess(reason: "BANK-FIRST")
        try await performCombatBankFirstSafety()
        try await ensureBestCombatWeaponFromWorld()
        if resupplyReason != nil {
            try await ensureCombatSupplies()
        } else {
            reporter(.log("🛡️ BANK-FIRST concluído • poções já suficientes • entrada no Wild liberada"))
        }
        try await leaveBankShopToWorld(reason: "BANK-FIRST concluído")
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

        reporter(.state(.moving, "Indo ao banco"))
        try await ensureWorldBankAccess(reason: "protegendo itens")

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
            reporter(.diagnostic("[STATE] safe-stop ativo • reposição cancelada no banco"))
        }

        try await leaveBankShopToWorld(reason: "serviço de banco concluído")

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
                try await equip(activeCombatWeaponType)
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
                try await equip(activeCombatWeaponType)
                return
            }

            if playerHP < hpGoal {
                if potionStock.health > 0 {
                    let before = playerHP
                    if try await consumePotion("potion_health") {
                        usedAny = true
                        reporter(.log("❤️ Poção de vida aceita • HP antes \(before) • aguardando pvit/snapshot"))
                        switch try await driveHealthPotionTicks(goal: hpGoal, beforeDoseHP: before) {
                        case .confirmed:
                            continue
                        case .interrupted:
                            return
                        case .noAuthoritativeGain:
                            reporter(.log("⚠️ Poção de vida consumida, mas pvit/snapshot não confirmou aumento de HP • novas doses bloqueadas nesta recuperação"))
                            throw EngineError.potionRecoveryFailed("poção de vida sem efeito autoritativo • HP permaneceu \(playerHP); nenhuma segunda dose foi consumida")
                        }
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
                try await equip(activeCombatWeaponType)
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
            try await equip(activeCombatWeaponType)
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
            try await equip(activeCombatWeaponType)
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
            "potion_health_l2": max(0, RealtimeProtocol.int(bp["potion_health_l2"]) ?? 0),
            "potion_shield": max(0, RealtimeProtocol.int(bp["potion_shield"]) ?? 0),
            "potion_strength": max(0, RealtimeProtocol.int(bp["potion_strength"]) ?? 0)
        ]
        potionStock.health = carriedPotionCount(bp, type: "potion_health")
        potionStock.healthPlus = carriedPotionCount(bp, type: "potion_health_l2")
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
        case "potion_health_l2": potionStock.healthPlus = max(0, potionStock.healthPlus - 1)
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
        case "potion_health_l2": potionStock.healthPlus
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

    private func driveHealthPotionTicks(goal: Int, beforeDoseHP: Int) async throws -> HealthPotionEffectResult {
        try await sleep(1_250)
        if emergencyBackgroundExitRequested { return .interrupted }
        for _ in 0..<10 {
            try Task.checkCancellation()
            if emergencyBackgroundExitRequested { return .interrupted }
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
                if emergencyBackgroundExitRequested { return .interrupted }
                try await sleep(60)
            }
            reporter(.log("❤️ Tick de vida • \(before) → \(playerHP)\(playerHP <= before ? " (sem confirmação)" : "")"))
            if playerHP >= goal { break }
        }
        return HealthPotionEffectPolicy.result(
            before: beforeDoseHP,
            after: playerHP,
            interrupted: emergencyBackgroundExitRequested
        )
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
        try await equip(activeCombatWeaponType)
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

    private func startImmediateGroundBagCollection(
        killPosition: Position,
        baseline: Set<String>?
    ) -> Task<WildGroundBagProbeResult, Never>? {
        guard let baseline else { return nil }
        let client = http
        let shardID = shardNumber
        let ownerID = playerID
        let killX = killPosition.x
        let killZ = killPosition.z

        return Task {
            if Task.isCancelled { return .empty }
            do {
                let bags = try await client.groundBags(shardID: shardID)
                let candidates = WildGroundBagPolicy.candidateIDs(
                    bags: bags,
                    excluding: baseline,
                    ownerID: ownerID,
                    killX: killX,
                    killZ: killZ
                )
                if candidates.isEmpty { return .empty }

                var collected: [String] = []
                var failures: [String] = []
                for id in candidates {
                    if Task.isCancelled { break }
                    do {
                        let response = try await client.lootBag(id)
                        if RealtimeProtocol.bool(response["ok"]) == false {
                            failures.append("\(id):\((response["error"] as? String) ?? "rejected")")
                        } else {
                            collected.append(id)
                        }
                    } catch {
                        failures.append("\(id):\(error.localizedDescription)")
                    }
                }
                return WildGroundBagProbeResult(
                    observedIDs: candidates,
                    collectedIDs: collected,
                    failures: failures,
                    fetchError: nil
                )
            } catch {
                return WildGroundBagProbeResult(
                    observedIDs: [],
                    collectedIDs: [],
                    failures: [],
                    fetchError: error.localizedDescription
                )
            }
        }
    }

    private func collectWildDrops(
        mode: ActivityMode,
        targetNumber: Int,
        killPosition: Position,
        backpackBefore: [String: Any]?,
        groundBagBaseline: Set<String>?,
        immediateGroundBagProbe: WildGroundBagProbeResult?,
        grantBaseline: Int
    ) async throws -> WildDropCollection {
        let mobName = "\(mode.displayName) #\(targetNumber)"
        let immediatelyCollected = Set(immediateGroundBagProbe?.collectedIDs ?? [])

        if let probe = immediateGroundBagProbe {
            if !probe.observedIDs.isEmpty {
                reporter(.diagnostic("[LOOT] \(mobName) • bags observadas durante recuo=\(probe.observedIDs.joined(separator: ","))"))
            }
            for id in probe.collectedIDs {
                reporter(.log("🎁 \(mobName) • drop bag \(id) coletado durante recuo defensivo ✅"))
            }
            for failure in probe.failures {
                reporter(.diagnostic("[LOOT] coleta imediata falhou • \(failure) • fallback pós-segurança será tentado"))
            }
            if let fetchError = probe.fetchError {
                reporter(.diagnostic("[LOOT] probe imediato de ground-bags indisponível: \(fetchError)"))
            }
        }

        // Fallback após a estabilização: procura bags novas, próximas da kill e
        // pertencentes ao jogador. Bags já coletadas pelo probe paralelo nunca
        // são solicitadas novamente.
        if let groundBagBaseline {
            do {
                let bags = try await http.groundBags(shardID: shardNumber)
                let candidateIDs = WildGroundBagPolicy.candidateIDs(
                    bags: bags,
                    excluding: groundBagBaseline,
                    ownerID: playerID,
                    killX: killPosition.x,
                    killZ: killPosition.z
                )
                for id in candidateIDs where !immediatelyCollected.contains(id) {
                    let response = try await http.lootBag(id)
                    if RealtimeProtocol.bool(response["ok"]) == false {
                        reporter(.log("⚠️ \(mobName) • drop bag \(id) recusado pelo servidor"))
                    } else {
                        reporter(.log("🎁 \(mobName) • drop bag coletado após estabilização"))
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
        case "desert": return "The Dunes East"
        case "beach": return "The Shores"
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
    let modeHint: ActivityMode?

    init(
        region: String = "eldergrove",
        kind: String,
        keys: [String],
        position: Position,
        targetKey: String,
        hasCoal: Bool,
        hasMetal: Bool = false,
        modeHint: ActivityMode? = nil
    ) {
        self.region = region
        self.kind = kind
        self.keys = keys
        self.position = position
        self.targetKey = targetKey
        self.hasCoal = hasCoal
        self.hasMetal = hasMetal
        self.modeHint = modeHint
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
    var healthPlus = 0
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

private struct WildGroundBagProbeResult: Sendable {
    let observedIDs: [String]
    let collectedIDs: [String]
    let failures: [String]
    let fetchError: String?

    static let empty = WildGroundBagProbeResult(observedIDs: [], collectedIDs: [], failures: [], fetchError: nil)
}

struct BackpackState {
    let stateSeq: Int
    let backpack: [String: Any]
}

private struct BankShopTransitionResult {
    let baseSeq: Int
    let responseSeq: Int
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
    case bankTransitionFailed(String)
    case dunesDeathDuringExit(String)
    case dunesExitSurvivalUnconfirmed(String)
    case missingRequiredItem(String)
    case gatherLoadoutNotReady(String)
    case gatherEndedBeforeGoal
    case missingFishingBait(String)
    case insufficientFishingBait(String, have: Int, need: Int)
    case unsupportedFishingBait(String)
    case unsupportedMode(String)
    case roastPitNotReachable
    case fishingPresenceStalled(successes: Int)
    case blacksmithRepairTargetChanged
    case blacksmithFailure(String)

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
        case .bankTransitionFailed(let detail): return "Transição do banco não confirmada: \(detail)"
        case .dunesDeathDuringExit(let detail): return "Morte/full-loot detectado durante saída das Dunes: \(detail)"
        case .dunesExitSurvivalUnconfirmed(let detail): return "The Shores recebida, mas sobrevivência não pôde ser confirmada: \(detail)"
        case .missingRequiredItem(let item): return "Item obrigatório não encontrado no inventário/banco: \(item)"
        case .gatherLoadoutNotReady(let item): return "Preflight de ferramenta não materializou \(item) antes de entrar na região de coleta"
        case .gatherEndedBeforeGoal: return "Engine de coleta encerrou antes da meta após reconexão"
        case .missingFishingBait(let bait): return "Isca selecionada sem estoque: \(bait)"
        case .insufficientFishingBait(let bait, let have, let need): return "Isca insuficiente: \(bait) \(have)/\(need)"
        case .unsupportedFishingBait(let bait): return "Automação ainda não validada para \(bait)"
        case .unsupportedMode(let mode): return mode
        case .roastPitNotReachable: return "Não foi possível confirmar proximidade com o Roast Pit"
        case .fishingPresenceStalled(let successes): return "Presence de pesca sem fish_bite após falha global • progresso \(successes)"
        case .blacksmithRepairTargetChanged: return "Ferramenta escolhida para Repair mudou de slot ou já não precisa de reparo"
        case .blacksmithFailure(let detail): return "Frostmere Smith: \(detail)"
        }
    }
}

private struct KintaraHTTPClient {
    let cookie: String
    let fleet: String
    let shardID: Int?
    private let base = URL(string: "https://kintara.com")!

    init(cookie: String, shard: String? = nil, fleet: String = "us") {
        self.cookie = cookie
        self.fleet = fleet
        if let shard {
            self.shardID = Int(shard.trimmingCharacters(in: .whitespacesAndNewlines).lowercased().replacingOccurrences(of: "s", with: ""))
        } else {
            self.shardID = nil
        }
    }

    func get(_ path: String) async throws -> [String: Any] {
        try await request(method: "GET", path: path, body: nil)
    }

    func post(_ path: String, body: [String: Any]) async throws -> [String: Any] {
        try await request(method: "POST", path: path, body: body)
    }

    func grantCook(mode: RoastPitMode) async throws -> [String: Any] { try await post(RoastPitProtocolPolicy.endpoint, body: RoastPitProtocolPolicy.body(mode: mode, fleet: fleet, shardID: shardID)) }

    func blacksmithSmith(recipe: String, quantity: Int) async throws -> [String: Any] {
        try await post(BlacksmithProtocolPolicy.smithEndpoint, body: BlacksmithProtocolPolicy.smithBody(recipe: recipe, quantity: quantity, fleet: fleet, shardID: shardID))
    }

    func blacksmithRepair(target: RepairTarget) async throws -> [String: Any] {
        try await post(BlacksmithProtocolPolicy.repairEndpoint, body: BlacksmithProtocolPolicy.repairBody(slotKind: target.slotKind, slotIdx: target.slotIdx, fleet: fleet, shardID: shardID))
    }

    func consumePotion(_ type: String) async throws -> [String: Any] {
        try await post("/api/auth/consume-potion", body: ["type": type])
    }

    func alchemistPotionBuy(type: String, quantity: Int = 1) async throws -> [String: Any] {
        try await post("/api/auth/alchemist-potion-buy", body: ["potionType": type, "qty": max(1, quantity)])
    }

    func skillXP(playerID: Int, skill: String) async throws -> Int? {
        let response = try await get("/api/auth/player-stats?playerId=\(playerID)")
        if let xp = response["skillXp"] as? [String: Any], let value = RealtimeProtocol.int(xp[skill]) {
            return max(0, value)
        }
        if let data = response["data"] as? [String: Any],
           let xp = data["skillXp"] as? [String: Any],
           let value = RealtimeProtocol.int(xp[skill]) {
            return max(0, value)
        }
        return nil
    }

    func combatXP(playerID: Int) async throws -> Int? {
        try await skillXP(playerID: playerID, skill: "combat")
    }

    func totalResource(_ backpack: [String: Any], type: String) -> Int {
        let carried = max(0, RealtimeProtocol.int(backpack[type]) ?? 0)
        return carried + slotCount(backpack["bankSlots"], type: type)
    }

    /// Save neutro observado na transição World → bank_shop. Não move item:
    /// apenas persiste o mesmo backpack com o baseSeq pré-transição e exige que
    /// a resposta do servidor avance a sequência antes de qualquer withdraw.
    func synchronizeBankShopEntry(from state: BackpackState) async throws -> BankShopTransitionResult {
        let response = try await saveBackpack(
            state.backpack,
            baseSeq: state.stateSeq,
            operation: "bank-entry-sync"
        )
        let rawResponseSeq = SaveBackpackConflictPolicy.authoritativeSequence(from: response)
        guard let responseSeq = BankShopProtocolPolicy.acceptedTransitionSequence(
            baseSeq: state.stateSeq,
            responseSeq: rawResponseSeq
        ) else {
            let label = rawResponseSeq.map(String.init) ?? "-"
            throw HTTPError.server("bank_entry_seq_not_advanced • baseSeq=\(state.stateSeq) • responseSeq=\(label)")
        }
        return BankShopTransitionResult(baseSeq: state.stateSeq, responseSeq: responseSeq)
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
            _ = try await saveBackpack(backpack, baseSeq: state.stateSeq, operation: "potion-loadout:\(targets.keys.sorted().joined(separator: ","))")
            return try await backpackState()
        }
        return state
    }

    func itemLocationCounts(type: String) async throws -> ItemLocationCounts {
        let state = try await backpackState()
        let hotbar = state.backpack["hotbar"] as? [Any] ?? []
        let inv = state.backpack["invSlots"] as? [Any] ?? []
        let bank = state.backpack["bankSlots"] as? [Any] ?? []
        let slotted = InventoryLoadoutAllocator.carriedCount(type: type, hotbar: hotbar, inventory: inv)
        let flat = max(0, RealtimeProtocol.int(state.backpack[type]) ?? 0)
        return ItemLocationCounts(
            carried: max(slotted, flat),
            bank: slotCount(bank, type: type)
        )
    }

    /// Garante que um item necessário à próxima atividade esteja carregado.
    /// Usa o mesmo save-backpack já comprovado para poções/BANK-FIRST; não cria
    /// item e não altera bags especiais. Ferramentas com metadados são movidas
    /// como objeto inteiro. Stacks simples (ex.: bait) podem ser retirados
    /// parcialmente do banco até a quantidade solicitada.
    @discardableResult
    func ensureCarriedItem(
        type: String,
        quantity targetRaw: Int,
        preferHotbar: Bool,
        preferredBankIndex: Int? = nil
    ) async throws -> Int {
        let target = max(1, targetRaw)
        let state = try await backpackState()
        var backpack = state.backpack
        var hotbar = backpack["hotbar"] as? [Any] ?? Array(repeating: NSNull(), count: 6)
        var inv = backpack["invSlots"] as? [Any] ?? Array(repeating: NSNull(), count: 24)
        var bank = backpack["bankSlots"] as? [Any] ?? []

        let before = InventoryLoadoutAllocator.carriedCount(type: type, hotbar: hotbar, inventory: inv)
        if before >= target { return before }

        let sourceIndex = preferredBankIndex ?? BankItemSelectionPolicy.preferredBankSlotIndex(type: type, bank: bank)
        let sourceItem = sourceIndex.flatMap { bank[$0] as? [String: Any] }
        let sourceItemKeys = sourceItem?.keys.sorted().joined(separator: ",") ?? "-"
        let sourceIID = SaveBackpackConflictPolicy.normalizedIID(sourceItem?["iid"])
        let flatCounterPresent = backpack[type] != nil ? "yes" : "no"

        let moved = InventoryLoadoutAllocator.withdraw(
            type: type,
            quantity: target,
            preferHotbar: preferHotbar,
            hotbar: &hotbar,
            inventory: &inv,
            bank: &bank,
            preferredBankIndex: sourceIndex
        )
        guard moved > 0 else { return before }

        backpack["hotbar"] = hotbar
        backpack["invSlots"] = inv
        backpack["bankSlots"] = bank
        if backpack[type] != nil {
            backpack[type] = max(0, RealtimeProtocol.int(backpack[type]) ?? 0) + moved
        }
        _ = try await saveBackpack(
            backpack,
            baseSeq: state.stateSeq,
            operation: "withdraw:\(type):bankSlot=\(sourceIndex.map(String.init) ?? "-"):itemKeys=\(sourceItemKeys):flat=\(flatCounterPresent)",
            itemDiagnostic: SaveBackpackItemDiagnosticContext(
                type: type,
                iid: sourceIID,
                beforeBackpack: state.backpack
            )
        )

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





    func resourceBalance(_ item: String) async throws -> Int {
        let state = try await backpackState()
        return max(0, RealtimeProtocol.int(state.backpack[item]) ?? 0)
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
    func depositAllBankFirstInventory(
        preservingTypes: Set<String> = [],
        preservingTool: DunesToolInstanceIdentity? = nil,
        preserveCombatLoadout: Bool = true
    ) async throws -> BankDepositResult {
        let state = try await backpackState()
        var wanted: [String: Int] = [:]
        var fallbackToolPreserved = false

        for key in ["invSlots", "hotbar"] {
            guard let slots = state.backpack[key] as? [Any] else { continue }
            for raw in slots {
                guard let slot = raw as? [String: Any], let type = slot["t"] as? String else { continue }
                if preservingTypes.contains(type) { continue }
                if let preservingTool, BankDepositPreservationPolicy.matchesSelectedTool(slot, selected: preservingTool) {
                    if preservingTool.iid != nil {
                        continue
                    }
                    if !fallbackToolPreserved {
                        fallbackToolPreserved = true
                        continue
                    }
                }
                let policyCandidate = CombatBankFirstPolicy.shouldBankFirst(type: type, slot: slot)
                let dunesCombatCandidate = !preserveCombatLoadout && CombatBankFirstPolicy.isCombatRequiredType(type)
                guard policyCandidate || dunesCombatCandidate else { continue }
                wanted[type, default: 0] += CombatBankFirstPolicy.slotQuantity(slot)
            }
        }

        guard !wanted.isEmpty else {
            return BankDepositResult(confirmed: [:], unresolved: [], diagnostics: [])
        }

        // Fluxo comprovado na v3.0 FINAL/build 43 e na v5.2: cada tipo parte de
        // uma leitura /me nova. Um item recusado nunca invalida a proteção dos
        // demais, e a entrada no Wild continua bloqueada enquanto restar algum.
        var confirmed: [String: Int] = [:]
        var unresolved = Set<String>()
        var diagnostics: [String] = []
        for (type, quantity) in wanted.sorted(by: { $0.key < $1.key }) {
            do {
                let result = try await depositIntoBank(
                    [type: quantity],
                    sourceKeys: ["invSlots", "hotbar"],
                    preservingTool: preservingTool
                )
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
        try await depositIntoBank(wanted, sourceKeys: ["invSlots"], preservingTool: nil)
    }

    private func depositIntoBank(
        _ wanted: [String: Int],
        sourceKeys: [String],
        preservingTool: DunesToolInstanceIdentity?
    ) async throws -> BankDepositResult {
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

        var fallbackToolPreserved = false
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

                    if let preservingTool, BankDepositPreservationPolicy.matchesSelectedTool(slot, selected: preservingTool) {
                        if preservingTool.iid != nil {
                            continue
                        }
                        if !fallbackToolPreserved {
                            fallbackToolPreserved = true
                            continue
                        }
                    }

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
            _ = try await saveBackpack(backpack, baseSeq: state.stateSeq, operation: "bank-deposit:\(moved.keys.sorted().joined(separator: ","))")
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

    private func saveBackpack(
        _ backpack: [String: Any],
        baseSeq: Int,
        operation: String,
        itemDiagnostic: SaveBackpackItemDiagnosticContext? = nil
    ) async throws -> [String: Any] {
        let body = BackpackSavePayloadPolicy.makeBody(
            backpack: backpack,
            baseSeq: baseSeq,
            fleet: fleet,
            shardID: shardID
        )
        do {
            let response = try await post("/api/auth/save-backpack", body: body)
            guard RealtimeProtocol.bool(response["ok"]) != false else {
                throw HTTPError.server((response["error"] as? String) ?? "save-backpack recusado")
            }
            return response
        } catch let HTTPError.response(status, message, payload)
            where status == 409 && message.lowercased().contains("stale_save") {
            let responseSeq = SaveBackpackConflictPolicy.authoritativeSequence(from: payload)
            let freshSeq = try? await backpackState().stateSeq
            let classification = SaveBackpackConflictPolicy.classify(
                sentSeq: baseSeq, responseSeq: responseSeq, freshSeq: freshSeq
            )
            let responseLabel = responseSeq.map(String.init) ?? "-"
            let freshLabel = freshSeq.map(String.init) ?? "-"
            let keys = SaveBackpackConflictPolicy.safeTopLevelKeys(from: payload)
            let keyLabel = keys.isEmpty ? "-" : keys.joined(separator: ",")
            let reason = SaveBackpackConflictPolicy.safeReason(from: payload)

            var itemEvidence = ""
            if let itemDiagnostic {
                let authoritativeBackpack = payload?["backpack"] as? [String: Any] ?? [:]
                let beforeLocation = SaveBackpackConflictPolicy.itemLocation(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: itemDiagnostic.beforeBackpack
                )
                let sentLocation = SaveBackpackConflictPolicy.itemLocation(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: backpack
                )
                let serverLocation = SaveBackpackConflictPolicy.itemLocation(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: authoritativeBackpack
                )
                let beforeKeys = SaveBackpackConflictPolicy.itemKeys(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: itemDiagnostic.beforeBackpack
                ).joined(separator: ",")
                let sentKeys = SaveBackpackConflictPolicy.itemKeys(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: backpack
                ).joined(separator: ",")
                let serverKeys = SaveBackpackConflictPolicy.itemKeys(
                    type: itemDiagnostic.type, iid: itemDiagnostic.iid, in: authoritativeBackpack
                ).joined(separator: ",")
                let gap = SaveBackpackConflictPolicy.unrepresentedAuthoritativeBackpackKeys(authoritativeBackpack)
                let gapLabel = gap.isEmpty ? "-" : gap.prefix(32).joined(separator: ",")
                itemEvidence = " • equip=\(SaveBackpackConflictPolicy.equipmentLabel(type: itemDiagnostic.type)) • iid=\(itemDiagnostic.iid == nil ? "não" : "sim") • loc=\(beforeLocation)→\(sentLocation)→server:\(serverLocation) • itemKeys=\(beforeKeys.isEmpty ? "-" : beforeKeys)|\(sentKeys.isEmpty ? "-" : sentKeys)|\(serverKeys.isEmpty ? "-" : serverKeys) • nãoRepresentadoNoSave=\(gapLabel)"
            }

            throw HTTPError.server(
                "stale_save • op=\(operation) • reason=\(reason) • baseSeq=\(baseSeq) • responseSeq=\(responseLabel) • freshSeq=\(freshLabel) • classe=\(classification.rawValue) • payloadKeys=\(keyLabel)\(itemEvidence)"
            )
        }
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

        let response = try await saveBackpack(backpack, baseSeq: stateSeq, operation: "persist-loot:\(item)")
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
            let object = any as? [String: Any]
            let message = (object?["error"] as? String)
                ?? (object?["message"] as? String)
                ?? "HTTP \(http.statusCode)"
            throw HTTPError.response(status: http.statusCode, message: message, payload: object)
        }
        return any
    }
}

private enum HTTPError: LocalizedError {
    case invalidURL
    case invalidResponse
    case nonJSON(Int)
    case invalidState
    case response(status: Int, message: String, payload: [String: Any]?)
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "URL HTTP inválida"
        case .invalidResponse: return "Resposta HTTP inválida"
        case .nonJSON(let status): return "Resposta não JSON (HTTP \(status))"
        case .invalidState: return "Estado de inventário incompleto"
        case .response(_, let message, _): return message
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
        case .silver: return "Silver Ore"
        case .cacti: return "Cacti"
        case .fishing: return "Pesca"
        case .chicken: return "Galinha"
        case .zombie: return "Zumbi"
        case .dragon: return "Dragão"
        case .roastPit: return "Roast Pit"
        case .blacksmith: return "Frostmere Smith"
        }
    }
}
