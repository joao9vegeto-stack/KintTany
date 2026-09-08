import Foundation

enum EngineEvent {
    case state(ActivityState, String)
    case log(String)
    case diagnostic(String)
    case target(String?)
    case attempt
    case success(String?)
    case failure(String)
    case hitSent
    case confirmedHit
    case kill
    case player(Position, hp: Int, shield: Int, region: String)
    case world(nodes: Int, mobs: Int, serverRegion: String?)
}

struct EngineRunResult {
    let successes: Int
    let completedGoal: Bool
}

@MainActor
final class AutomationEngine {
    typealias Reporter = (EngineEvent) -> Void

    private let socket: RealtimeSocket
    private let cookie: String
    private let shard: String
    private let reporter: Reporter
    private let http: KintaraHTTPClient

    private var region: String
    private var serverRegion: String?
    private var position: Position
    private var lifeEpoch = 1
    private var equipment: String?
    private var playerID: Int?
    private var playerHP = 100
    private var playerShield = 0

    private var firstResourceSnapshotSeen = false
    private var cooldownUntil: [String: Double] = [:]
    private var recentRetryUntil: [String: Double] = [:]

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

    private var successes = 0

    init(socket: RealtimeSocket, cookie: String, shard: String, bootstrap: PresenceBootstrap, reporter: @escaping Reporter) {
        self.socket = socket
        self.cookie = cookie
        self.shard = shard
        self.reporter = reporter
        self.http = KintaraHTTPClient(cookie: cookie)
        self.region = bootstrap.region
        self.position = bootstrap.position
    }

    static func bootstrap(for mode: ActivityMode) -> PresenceBootstrap {
        switch mode {
        case .tree:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: -6.5, z: -18.5))
        case .coal, .stone, .chicken:
            return PresenceBootstrap(region: "eldergrove", position: Position(x: 22.5, z: -3.5))
        case .fishing, .zombie, .dragon:
            return PresenceBootstrap(region: "world", position: Position(x: 22.5, z: -3.5))
        }
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

    func ingest(_ data: Data) {
        guard let packet = RealtimeProtocol.packet(data), let type = packet["t"] as? String else { return }

        if let le = RealtimeProtocol.int(packet["le"]), le > lifeEpoch {
            lifeEpoch = le
        }

        switch type {
        case "region_ack":
            if let value = packet["region"] as? String, !value.isEmpty {
                serverRegion = value
                region = value
                reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
                reporter(.diagnostic("[REGION] ACK \(value)"))
            }

        case "snap":
            ingestSnapshot(packet)

        case "res_evt", "res_snap":
            ingestResourceEvent(packet)

        case "action_proof":
            ingestActionProof(packet)

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
                let killedType: String? = RealtimeProtocol.int(packet["dr"]) == 1 ? "dragon" : (RealtimeProtocol.int(packet["zm"]) == 1 ? "zombie" : nil)
                lastWildHit = WildHitAck(serial: wildHitSerial, index: index, killedType: killedType)
                reporter(.diagnostic("[COMBAT] wm_ev hit confirmado i=\(index)\(killedType.map { " kill=\($0)" } ?? "")"))
            }

        case "pvit", "wild_mb_ack":
            ingestVitals(packet)

        default:
            break
        }
    }

    func run(mode: ActivityMode, goal: Int) async throws -> EngineRunResult {
        successes = 0
        try Task.checkCancellation()

        switch mode {
        case .tree, .coal, .stone:
            try await runGather(mode: mode, goal: goal)
        case .fishing:
            try await runFishing(goal: goal)
        case .chicken:
            try await runChicken(goal: goal)
        case .zombie, .dragon:
            try await runWild(mode: mode, goal: goal)
        }

        return EngineRunResult(successes: successes, completedGoal: successes >= goal)
    }

    // MARK: - Common state

    private func ingestSnapshot(_ packet: [String: Any]) {
        if let packetRegion = packet["region"] as? String, !packetRegion.isEmpty {
            serverRegion = packetRegion
        }

        if let res = packet["res"] as? [[String: Any]] {
            firstResourceSnapshotSeen = true
            let now = nowMS
            for group in res {
                let kind = ((group["kind"] ?? group["k"]) as? String) ?? ""
                guard !kind.isEmpty else { continue }
                let keys = stringArray(group["keys"] ?? group["key"])
                guard !keys.isEmpty else { continue }
                let until = RealtimeProtocol.double(group["until"]) ?? (now + 2_500)
                for key in keys {
                    cooldownUntil["\(kind):\(key)"] = until
                }
            }
        }

        if let players = packet["players"] as? [[String: Any]], let id = playerID,
           let me = players.first(where: { RealtimeProtocol.int($0["id"]) == id }) {
            if let x = RealtimeProtocol.double(me["x"]), let z = RealtimeProtocol.double(me["z"]) {
                position.x = x
                position.z = z
                if let y = RealtimeProtocol.double(me["y"]) { position.y = y }
                if let ry = RealtimeProtocol.double(me["ry"]) { position.ry = ry }
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
                guard matchesCurrentGather(kind: kind, keys: keys) else { continue }
                if let h = RealtimeProtocol.int(item["h"]), h > harvestH { harvestH = h }
                if let hm = RealtimeProtocol.int(item["hm"]), hm > 0 { harvestHM = hm }
            }
        }

        if let npcs = packet["npcs"] as? [String: Any] {
            ingestChickenCollections(npcs)
            if let wild = npcs["wildMobs"] as? [[String: Any]] {
                ingestWildMobs(wild)
            }
        }
        if let wild = packet["wildMobs"] as? [[String: Any]] {
            ingestWildMobs(wild)
        }

        reporter(.player(position, hp: playerHP, shield: playerShield, region: serverRegion ?? region))
        reporter(.world(nodes: availableSeedCount(), mobs: max(chickens.count, wildMobs.count), serverRegion: serverRegion))
    }

    private func ingestVitals(_ packet: [String: Any]) {
        if let pid = RealtimeProtocol.int(packet["pid"] ?? packet["id"]), let playerID, pid != playerID { return }
        if let hp = RealtimeProtocol.int(packet["php"]) { playerHP = hp }
        if let shield = RealtimeProtocol.int(packet["wsh"]) { playerShield = shield }
        if let le = RealtimeProtocol.int(packet["le"]), le > lifeEpoch { lifeEpoch = le }
        reporter(.player(position, hp: playerHP, shield: playerShield, region: region))
    }

    private func sendPosition(moving: Bool, full: Bool = false, action: [String: Any] = [:]) async throws {
        var extra = action
        if let equipment, extra["eq"] == nil { extra["eq"] = equipment }
        if region.hasPrefix("wild") {
            extra["php"] = playerHP
            extra["wsh"] = playerShield
            extra["wsp"] = extra["wsp"] ?? 0
        }
        let data = try RealtimeProtocol.position(region: region, position: position, lifeEpoch: lifeEpoch, moving: moving, full: full, action: extra)
        try await socket.send(data)
    }

    private func setRegion(_ value: String, at pos: Position, extras: [String: Any] = [:]) async throws {
        region = value
        position = pos
        serverRegion = nil
        reporter(.state(.syncing, "Entrando em \(prettyRegion(value))"))
        reporter(.log("🌍 Entrando em \(prettyRegion(value))…"))
        try await sendPosition(moving: false, full: true, action: extras)
    }

    private func waitForRegion(_ expected: String, timeoutMS: Int) async throws -> Bool {
        let deadline = nowMS + Double(timeoutMS)
        while nowMS < deadline {
            try Task.checkCancellation()
            if serverRegion?.lowercased() == expected.lowercased() { return true }
            if expected == "pond", !fishSpots.isEmpty { return true }
            try await sleep(50)
        }
        return false
    }

    private func equip(_ item: String) async throws {
        equipment = item
        try await sendPosition(moving: false)
        reporter(.diagnostic("[EQUIP] \(item)"))
        try await sleep(120)
    }

    private func clearAction() async throws {
        position.y = 0.25
        try await sendPosition(moving: false)
    }

    private func walk(to target: Position, maxSeconds: Double = 35) async throws {
        reporter(.state(.moving, "Movendo até o alvo"))
        let started = nowMS
        let speed = 3.5
        let dt = 0.15

        while true {
            try Task.checkCancellation()
            let dx = target.x - position.x
            let dz = target.z - position.z
            let distance = hypot(dx, dz)
            if distance < 0.4 { break }
            if (nowMS - started) / 1_000 > maxSeconds {
                throw EngineError.movementTimeout
            }

            let amount = min(distance, speed * dt)
            position.x += (dx / distance) * amount
            position.z += (dz / distance) * amount
            position.y = 0.2978266400228179
            position.ry = atan2(dx, dz)
            try await sendPosition(moving: true)
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
                try await sendPosition(moving: false)
            } catch {
                return
            }
        }
    }

    // MARK: - Gathering

    private func runGather(mode: ActivityMode, goal: Int) async throws {
        reporter(.state(.syncing, "Sincronizando Whisperwood"))
        if serverRegion?.lowercased() != "eldergrove" {
            let start = mode == .tree ? Position(x: -6.5, z: -18.5) : Position(x: 22.5, z: -3.5)
            try await setRegion("eldergrove", at: start)
        }
        _ = try await waitForRegion("eldergrove", timeoutMS: 6_000)

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        reporter(.state(.searching, "Sincronizando recursos"))
        let resourceDeadline = nowMS + 7_000
        while !firstResourceSnapshotSeen && nowMS < resourceDeadline {
            try Task.checkCancellation()
            try await sleep(80)
        }
        if !firstResourceSnapshotSeen {
            reporter(.diagnostic("[GATHER] snap.res ainda não chegou; mantendo catálogo conhecido, sem assumir cooldown inexistente"))
        } else {
            reporter(.log("🗺️ Catálogo v5.2 carregado • \(availableSeedCount(for: mode)) alvos disponíveis"))
        }

        while successes < goal {
            try Task.checkCancellation()
            reporter(.state(.searching, "Procurando \(mode.displayName.lowercased())"))

            guard let seed = selectGatherSeed(for: mode) else {
                reporter(.target(nil))
                reporter(.diagnostic("[GATHER] Nenhum alvo disponível agora; aguardando cooldown"))
                try await sleep(1_500)
                continue
            }

            reporter(.target("\(mode.displayName) • \(seed.keys.joined(separator: ","))"))
            reporter(.state(.selectingTarget, "Alvo \(seed.targetKey)"))
            reporter(.log("🎯 \(mode.displayName) \(seed.targetKey) selecionado"))

            try await walk(to: seed.position)
            reporter(.diagnostic("[MOVE] arrived \(seed.targetKey) pos=\(format(position.x)),\(format(position.z)) ry=\(format(position.ry))"))

            reporter(.attempt)
            let result = try await harvest(seed: seed, mode: mode)
            if result.felled {
                let signature = seed.signature
                let localCooldown = nowMS + 12_000
                for key in seed.keys { cooldownUntil["\(seed.kind):\(key)"] = localCooldown }
                recentRetryUntil.removeValue(forKey: signature)

                var persistenceLabel = "sem loot confirmado"
                if let loot = result.loot, !loot.isEmpty {
                    do {
                        let total = try await http.persistLoot(loot, amount: 1)
                        persistenceLabel = total.map { "\(loot)=\($0)" } ?? "\(loot) persistido"
                    } catch {
                        persistenceLabel = "persistência falhou: \(error.localizedDescription)"
                        reporter(.diagnostic("[INVENTORY][ERROR] \(error.localizedDescription)"))
                    }
                }

                successes += 1
                reporter(.success(result.loot))
                reporter(.state(.cooldown, "Concluído \(successes)/\(goal)"))
                reporter(.log("✅ \(mode.displayName) concluído • h=\(result.h)/\(result.hm) • \(persistenceLabel) • \(successes)/\(goal)"))
                try await sleep(280)
            } else {
                recentRetryUntil[seed.signature] = nowMS + 8_000
                reporter(.failure(result.reason))
                reporter(.state(.recovering, "Reavaliando alvo"))
                reporter(.log("⚠️ \(mode.displayName) \(seed.targetKey): \(result.reason); outro alvo será tentado"))
                try await sleep(650)
            }
        }
    }

    private func harvest(seed: GatherSeed, mode: ActivityMode) async throws -> HarvestResult {
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

        position.ry = seed.position.ry
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
            if kind == "tree" {
                let profile = second ? Self.treeY2 : Self.treeY1
                let gap = max(35, Int(500.0 / Double(max(1, profile.count - 1))))
                for delta in profile {
                    position.y = 0.25 + delta
                    try await sendPosition(moving: false, action: ["act": "chop", "eq": tool])
                    try await sleep(gap)
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
                        let shape = Self.mineMP1[index] / shapeMax
                        let value = min(1, mineProgress + max(0, next - mineProgress) * shape)
                        position.y = 0.25 + Self.mineY1[index]
                        try await sendPosition(moving: false, action: ["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": value])
                        mineProgress = max(mineProgress, value)
                        try await sleep(65)
                    }
                } else {
                    for index in mpProfile.indices {
                        mineProgress = max(mineProgress, mpProfile[index])
                        position.y = 0.25 + yProfile[index % yProfile.count]
                        try await sendPosition(moving: false, action: ["act": "mine", "eq": tool, "mc": tile.0, "mr": tile.1, "mp": mineProgress])
                        try await sleep(65)
                    }
                }
            }
        }

        func sendHit(proof: String?) async throws {
            let data = try RealtimeProtocol.harvestHit(region: region, kind: kind, keys: seed.keys, hasCoal: seed.hasCoal, hasMetal: false, proof: proof)
            try await socket.send(data)
            totalHits += 1
            reporter(.hitSent)
            lastHitAt = nowMS
        }

        func waitForAck(proofBefore: Int, wearBefore: Int, hBefore: Int, timeoutMS: Int) async throws -> HarvestAck {
            let deadline = nowMS + Double(timeoutMS)
            while nowMS < deadline {
                try Task.checkCancellation()
                if harvestHM < 99, harvestH >= harvestHM { return .felled }
                if harvestProofSerial > proofBefore, harvestWearSerial > wearBefore, harvestH > hBefore, !harvestProof.isEmpty {
                    return .accepted
                }
                try await sleep(20)
            }
            if harvestHM < 99, harvestH >= harvestHM { return .felled }
            return .timeout
        }

        var handshake: HarvestAck = harvestProof.isEmpty ? .timeout : .accepted
        if harvestProof.isEmpty {
            for attempt in 1...3 {
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

                reporter(.state(.waitingProof, "Handshake \(attempt)/3"))
                reporter(.diagnostic("[GATHER] handshake #\(attempt) \(kind) keys=\(seed.keys) proof=none"))
                handshake = try await waitForAck(proofBefore: proofBefore, wearBefore: wearBefore, hBefore: hBefore, timeoutMS: attempt == 1 ? 900 : 1_200)
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
            return HarvestResult(felled: true, h: harvestH, hm: harvestHM, loot: harvestLoot, reason: "felled_during_handshake")
        }
        guard handshake == .accepted, !harvestProof.isEmpty else {
            try? await clearAction()
            return HarvestResult(felled: false, h: harvestH, hm: harvestHM, loot: harvestLoot, reason: "sem action_proof próprio após handshake")
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

        let settle = nowMS + 1_200
        while nowMS < settle, !(harvestHM < 99 && harvestH >= harvestHM) {
            try await sleep(40)
        }
        try? await clearAction()

        let felled = harvestHM < 99 && harvestH >= harvestHM
        return HarvestResult(
            felled: felled,
            h: harvestH,
            hm: harvestHM,
            loot: harvestLoot,
            reason: felled ? "FELLED" : (harvestClearSeen ? "clear sem h/hm conclusivo" : "ação não concluiu o wear")
        )
    }

    private func ingestActionProof(_ packet: [String: Any]) {
        guard currentGatherSignature != nil else { return }
        if let by = RealtimeProtocol.int(packet["by"]), let playerID, by != playerID { return }
        let keys = stringArray(packet["keys"] ?? packet["key"])
        if !keys.isEmpty && currentGatherKeys.isDisjoint(with: keys) { return }
        let proof = proofString(packet)
        guard !proof.isEmpty, proof != harvestProof else { return }
        harvestProof = proof
        harvestProofSerial += 1
        reporter(.diagnostic("[GATHER] action_proof #\(harvestProofSerial)"))
    }

    private func ingestResourceEvent(_ packet: [String: Any]) {
        let kind = ((packet["kind"] ?? packet["k"]) as? String) ?? ""
        let keys = stringArray(packet["keys"] ?? packet["key"])
        guard matchesCurrentGather(kind: kind, keys: keys) else { return }
        if let by = RealtimeProtocol.int(packet["by"]), let playerID, by != playerID { return }

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
        reporter(.diagnostic("[GATHER] res_evt h=\(harvestH) hm=\(harvestHM) proof=\(!harvestProof.isEmpty) loot=\(harvestLoot ?? "-")"))
    }

    private func matchesCurrentGather(kind: String, keys: [String]) -> Bool {
        guard let currentGatherKind, currentGatherSignature != nil else { return false }
        if !kind.isEmpty && kind != currentGatherKind { return false }
        if keys.isEmpty { return true }
        return !currentGatherKeys.isDisjoint(with: keys)
    }

    private func selectGatherSeed(for mode: ActivityMode) -> GatherSeed? {
        let now = nowMS
        return Self.gatherSeeds
            .filter { seed in
                switch mode {
                case .tree: return seed.kind == "tree"
                case .coal: return seed.kind == "rock" && seed.hasCoal
                case .stone: return seed.kind == "rock" && !seed.hasCoal
                default: return false
                }
            }
            .filter { seed in
                if let until = recentRetryUntil[seed.signature], until > now { return false }
                return seed.keys.allSatisfy { (cooldownUntil["\(seed.kind):\($0)"] ?? 0) <= now }
            }
            .min { a, b in
                distance(from: position, to: a.position) < distance(from: position, to: b.position)
            }
    }

    private func availableSeedCount(for mode: ActivityMode? = nil) -> Int {
        let now = nowMS
        return Self.gatherSeeds.filter { seed in
            let modeOK: Bool
            if let mode {
                switch mode {
                case .tree: modeOK = seed.kind == "tree"
                case .coal: modeOK = seed.kind == "rock" && seed.hasCoal
                case .stone: modeOK = seed.kind == "rock" && !seed.hasCoal
                default: modeOK = false
                }
            } else {
                modeOK = true
            }
            return modeOK && seed.keys.allSatisfy { (cooldownUntil["\(seed.kind):\($0)"] ?? 0) <= now }
        }.count
    }

    // MARK: - Fishing

    private func runFishing(goal: Int) async throws {
        if serverRegion?.lowercased() != "world" {
            try await setRegion("world", at: Position(x: 22.5, z: -3.5))
            _ = try await waitForRegion("world", timeoutMS: 4_000)
        }

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }

        reporter(.state(.moving, "Indo ao portal de The Pond"))
        try await walk(to: Position(x: 30.5, z: 0.5), maxSeconds: 20)

        var pondConfirmed = try await waitForRegion("pond", timeoutMS: 5_000)
        if !pondConfirmed {
            let probes = [
                Position(x: 30.5, z: 0.5),
                Position(x: -18.5, z: 0),
                Position(x: -1.5, z: -1.5)
            ]
            for probe in probes {
                try await setRegion("pond", at: probe)
                if try await waitForRegion("pond", timeoutMS: 2_500) {
                    pondConfirmed = true
                    break
                }
            }
        }
        guard pondConfirmed else { throw EngineError.regionNotConfirmed("pond") }

        region = "pond"
        reporter(.log("✅ The Pond confirmado"))
        try await walk(to: Position(x: -1.5, z: -1.5), maxSeconds: 20)
        try await equip("tool_fishing_rod")

        while successes < goal {
            try Task.checkCancellation()
            reporter(.state(.searching, "Procurando spot de pesca"))
            guard let target = selectFishTarget() else {
                reporter(.target(nil))
                try await sleep(700)
                continue
            }

            reporter(.target("Spot #\(target.slot) • \(target.fc),\(target.fr)"))
            reporter(.attempt)
            reporter(.state(.acting, "Lançando linha"))

            let snapshotBefore = fishSnapshotSerial
            let biteBefore = fishBiteSerial
            let generation = target.generation
            try await sendPosition(moving: false, action: ["act": "fish", "eq": "tool_fishing_rod", "fc": target.fc, "fr": target.fr, "fph": 0])

            let biteDeadline = nowMS + 3_500
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
                reporter(.failure(fishSnapshotSerial != snapshotBefore ? "spot mudou antes da fisgada" : "fish_bite não recebido"))
                try await sleep(650)
                continue
            }

            let ttl = remainingMS(for: fishSpots[target.slot])
            guard ttl >= Double(bite.ms + 4_500) else {
                try? await clearAction()
                reporter(.diagnostic("[FISH] cast descartado: TTL \(Int(ttl))ms < bite+margin"))
                try await sleep(500)
                continue
            }

            reporter(.state(.waitingResult, "Fisgada em \(String(format: "%.1f", Double(bite.ms) / 1000))s"))
            let waitUntil = nowMS + Double(bite.ms + 70)
            while nowMS < waitUntil {
                try Task.checkCancellation()
                guard fishTargetStillValid(target, generation: generation) else {
                    try? await clearAction()
                    reporter(.failure("spot rotacionou durante a espera"))
                    break
                }
                try await sleep(100)
            }
            guard fishTargetStillValid(target, generation: generation) else { continue }

            try await sendPosition(moving: false, action: ["act": "fish", "eq": "tool_fishing_rod", "fc": target.fc, "fr": target.fr, "fph": 1])
            try await sleep(180)
            try await sendPosition(moving: false, action: ["act": "fish", "eq": "tool_fishing_rod", "fc": target.fc, "fr": target.fr, "fph": 2])
            try await sleep(220)

            guard fishTargetStillValid(target, generation: generation) else {
                try? await clearAction()
                reporter(.failure("spot mudou antes do grant"))
                continue
            }

            do {
                let shardID = Int(shard.replacingOccurrences(of: "s", with: "")) ?? 4
                let response = try await http.post("/api/auth/grant-fish-xp", body: ["mountCatch": true, "fleet": "us", "shardId": shardID])
                try? await clearAction()
                guard RealtimeProtocol.bool(response["ok"]) != false else {
                    reporter(.failure((response["error"] as? String) ?? (response["message"] as? String) ?? "grant-fish-xp recusado"))
                    try await sleep(1_000)
                    continue
                }
                successes += 1
                reporter(.success("fish"))
                reporter(.log("✅ Peixe confirmado • \(successes)/\(goal)"))
                try await sleep(650)
            } catch {
                try? await clearAction()
                reporter(.failure("grant-fish-xp: \(error.localizedDescription)"))
                try await sleep(1_200)
            }
        }
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
            next[slot] = FishSpot(slot: slot, c: c, r: r, expiresAt: now + Double(max(0, ms)), generation: generation)
        }
        fishSpots = next
        fishSnapshotSerial += 1
        reporter(.world(nodes: availableSeedCount(), mobs: max(chickens.count, wildMobs.count), serverRegion: "pond"))
    }

    private func ingestFishSpotMoved(_ packet: [String: Any]) {
        let source = (packet["spot"] as? [String: Any]) ?? (packet["to"] as? [String: Any]) ?? (packet["newSpot"] as? [String: Any]) ?? packet
        guard let slot = RealtimeProtocol.int(source["s"] ?? packet["s"]),
              let c = RealtimeProtocol.int(source["c"] ?? packet["c"]),
              let r = RealtimeProtocol.int(source["r"] ?? packet["r"]),
              let ms = RealtimeProtocol.int(source["ms"] ?? packet["ms"]) else { return }
        let generation = (fishSpots[slot]?.generation ?? 0) + 1
        fishSpots[slot] = FishSpot(slot: slot, c: c, r: r, expiresAt: nowMS + Double(max(0, ms)), generation: generation)
        fishSnapshotSerial += 1
    }

    private func selectFishTarget() -> FishTarget? {
        let playerCol = Int(round(position.x + 19.5))
        let playerRow = Int(round(position.z + 19.5))
        let minTTL = 38_000.0
        var candidates: [FishTarget] = []
        for spot in fishSpots.values where remainingMS(for: spot) >= minTTL {
            for (fc, fr) in [(spot.c, spot.r), (spot.c + 1, spot.r), (spot.c, spot.r + 1), (spot.c + 1, spot.r + 1)] {
                let dist = hypot(Double(fc - playerCol), Double(fr - playerRow))
                if dist <= 6.5 {
                    candidates.append(FishTarget(slot: spot.slot, c: spot.c, r: spot.r, fc: fc, fr: fr, generation: spot.generation, distance: dist, ttl: remainingMS(for: spot)))
                }
            }
        }
        return candidates.sorted { a, b in
            if abs(a.ttl - b.ttl) > 10_000 { return a.ttl > b.ttl }
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
            try await walk(to: Position(x: 0, z: 0), maxSeconds: 20)
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

            var acceptedHits = 0
            var confirmedKill = false
            var noAck = 0

            for _ in 1...12 {
                try Task.checkCancellation()
                guard let live = chickens[target.index], live.alive else {
                    confirmedKill = acceptedHits > 0
                    break
                }
                target = live
                if distance(from: position, to: live.position) > 1.10 {
                    try await moveAdjacent(to: live, gap: 0.65)
                    try await equip("wild_sword")
                } else {
                    position.ry = atan2(live.position.x - position.x, live.position.z - position.z)
                    try await sendPosition(moving: false)
                }

                let before = ambientHitSerial
                let sentAt = nowMS
                let data = try RealtimeProtocol.ambientHit(region: "eldergrove", index: live.index, lifeEpoch: lifeEpoch, position: position)
                try await socket.send(data)
                reporter(.hitSent)

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

                if accepted {
                    acceptedHits += 1
                    noAck = 0
                    reporter(.confirmedHit)
                } else {
                    noAck += 1
                }

                let nextSwing = sentAt + 2_050
                if nowMS < nextSwing { try await sleep(Int(nextSwing - nowMS)) }
                if let refreshed = chickens[live.index] {
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
                reporter(.log("✅ Galinha derrotada • \(successes)/\(goal) • hits confirmados=\(acceptedHits)"))
                try await sleep(450)
            } else {
                reporter(.failure("galinha não teve morte confirmada"))
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
        if serverRegion?.lowercased() != "world" {
            try await setRegion("world", at: Position(x: 0.5, z: -29.5))
            _ = try await waitForRegion("world", timeoutMS: 5_000)
        }

        reporter(.state(.moving, "Indo ao portal da Wilderness"))
        try await walk(to: Position(x: 0.5, z: -30.5), maxSeconds: 25)

        reporter(.state(.syncing, "Entrando na Wilderness"))
        try await setRegion("wild", at: Position(x: 0.5, z: 23.5), extras: ["wblk": Self.wildBlockedTiles])
        guard try await waitForRegion("wild", timeoutMS: 6_000) else {
            throw EngineError.regionNotConfirmed("wild")
        }

        let hb = Task { [weak self] in await self?.heartbeat() }
        defer { hb.cancel() }
        try await equip("wild_sword")

        while successes < goal {
            try Task.checkCancellation()
            guard playerHP > 0 else { throw EngineError.playerDead }
            if playerHP + playerShield <= (mode == .dragon ? 80 : 55) {
                reporter(.log("🛡️ Vitais baixos (HP \(playerHP) + shield \(playerShield)); atividade interrompida para evitar morte"))
                throw EngineError.unsafeVitals
            }

            reporter(.state(.searching, "Procurando \(mode.displayName.lowercased())"))
            let candidates = wildMobs.values.filter { $0.alive && $0.type == targetType }
            guard var target = nearestMob(in: candidates) else {
                reporter(.target(nil))
                try await sleep(900)
                continue
            }

            reporter(.target("\(mode.displayName) #\(target.index) • HP \(target.hp.map { String($0) } ?? "?")"))
            reporter(.attempt)
            try await moveWildAdjacent(to: target)
            try await equip("wild_sword")

            var killed = false
            var acceptedHits = 0
            for _ in 0..<30 {
                try Task.checkCancellation()
                guard let live = wildMobs[target.index], live.alive, live.type == targetType else {
                    break
                }
                target = live
                if playerHP + playerShield <= (mode == .dragon ? 80 : 55) {
                    break
                }

                if chebyshevDistance(to: live.position) > 1 {
                    try await moveWildAdjacent(to: live)
                }
                position.ry = atan2(live.position.x - position.x, live.position.z - position.z)
                wildSwordSeq += 1
                try await sendPosition(moving: false, action: ["wss": wildSwordSeq, "eq": "wild_sword"])

                let ackBefore = wildHitSerial
                let sentAt = nowMS
                let hit = try RealtimeProtocol.wildHit(region: "wild", index: live.index, lifeEpoch: lifeEpoch, position: position)
                try await socket.send(hit)
                reporter(.hitSent)

                // Replica o contato wmb do cliente oficial apenas quando adjacente.
                let dx = position.x - live.position.x
                let dz = position.z - live.position.z
                let len = max(0.001, hypot(dx, dz))
                wildContactSeq += 1
                try await sendPosition(moving: false, action: ["wmb": wildContactSeq, "wmx": dx / len, "wmz": dz / len, "eq": "wild_sword"])

                let ackDeadline = nowMS + 1_450
                var ack: WildHitAck?
                while nowMS < ackDeadline {
                    try Task.checkCancellation()
                    if wildHitSerial > ackBefore, let candidate = lastWildHit, candidate.index == live.index {
                        ack = candidate
                        break
                    }
                    try await sleep(25)
                }

                if let ack {
                    acceptedHits += 1
                    reporter(.confirmedHit)
                    if ack.killedType == targetType {
                        killed = true
                        break
                    }
                }

                try await sleep(280)
                if playerHP <= 0 { throw EngineError.playerDead }
                let cadenceLeft = 1_650.0 - (nowMS - sentAt)
                if cadenceLeft > 0 { try await sleep(Int(cadenceLeft)) }
            }

            if killed {
                successes += 1
                reporter(.kill)
                reporter(.success(nil))
                reporter(.log("✅ \(mode.displayName) derrotado • \(successes)/\(goal) • hits confirmados=\(acceptedHits)"))
                try await sleep(mode == .dragon ? 1_200 : 900)
            } else {
                reporter(.failure("\(mode.displayName) sem kill autoritativa"))
                try await sleep(1_000)
            }
        }
    }

    private func ingestWildMobs(_ array: [[String: Any]]) {
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
    }

    private func moveAdjacent(to mob: LiveMob, gap: Double) async throws {
        let dx = position.x - mob.position.x
        let dz = position.z - mob.position.z
        let len = hypot(dx, dz)
        let ux = len > 0.001 ? dx / len : 1
        let uz = len > 0.001 ? dz / len : 0
        let target = Position(x: mob.position.x + ux * gap, z: mob.position.z + uz * gap)
        try await walk(to: target)
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
        try await walk(to: target, maxSeconds: 30)
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
    let kind: String
    let keys: [String]
    let position: Position
    let targetKey: String
    let hasCoal: Bool
    var signature: String { "\(kind):\(keys.sorted().joined(separator: "|"))" }
}

private struct HarvestResult {
    let felled: Bool
    let h: Int
    let hm: Int
    let loot: String?
    let reason: String
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

private enum EngineError: LocalizedError {
    case movementTimeout
    case regionNotConfirmed(String)
    case playerDead
    case unsafeVitals

    var errorDescription: String? {
        switch self {
        case .movementTimeout: return "Movimento excedeu o tempo limite"
        case .regionNotConfirmed(let region): return "O servidor não confirmou a região \(region)"
        case .playerDead: return "O personagem morreu"
        case .unsafeVitals: return "Combate interrompido por HP/Shield baixos"
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
        guard let url = URL(string: path, relativeTo: base) else { throw HTTPError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 15
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw HTTPError.invalidResponse }
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw HTTPError.nonJSON(http.statusCode)
        }
        guard (200...299).contains(http.statusCode) else {
            throw HTTPError.server((object["error"] as? String) ?? (object["message"] as? String) ?? "HTTP \(http.statusCode)")
        }
        return object
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
        case .fishing: return "Pesca"
        case .chicken: return "Galinha"
        case .zombie: return "Zumbi"
        case .dragon: return "Dragão"
        }
    }
}
