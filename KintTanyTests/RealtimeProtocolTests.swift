import Foundation
import XCTest
@testable import KintTany

final class RealtimeProtocolTests: XCTestCase {
    func testQueuePingUsesDocumentedEventName() throws {
        let data = try RealtimeProtocol.queuePing()
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["t"] as? String, "q_ping")
    }

    func testTreeHarvestUsesTreeWireKindAndNeverCoal() throws {
        let data = try RealtimeProtocol.harvest(region: "eldergrove", kind: "tree", keys: ["42,35"], hasCoal: false)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["k"] as? String, "tree")
        XCTAssertEqual(object["keys"] as? [String], ["42,35"])
        XCTAssertEqual(object["hasCoal"] as? Bool, false)
    }

    func testStoneAndCoalRemainRockButAreSeparatedByHasCoal() throws {
        let stoneData = try RealtimeProtocol.harvestHit(
            region: "eldergrove", kind: "rock", keys: ["33,9"], hasCoal: false, proof: "p1"
        )
        let coalData = try RealtimeProtocol.harvestHit(
            region: "eldergrove", kind: "rock", keys: ["3,12"], hasCoal: true, proof: "p2"
        )
        let stone = try XCTUnwrap(JSONSerialization.jsonObject(with: stoneData) as? [String: Any])
        let coal = try XCTUnwrap(JSONSerialization.jsonObject(with: coalData) as? [String: Any])

        XCTAssertEqual(stone["k"] as? String, "rock")
        XCTAssertEqual(stone["hasCoal"] as? Bool, false)
        XCTAssertEqual(coal["k"] as? String, "rock")
        XCTAssertEqual(coal["hasCoal"] as? Bool, true)
    }

    func testHarvestHitCarriesActionProofOnlyWhenAvailable() throws {
        let withProof = try RealtimeProtocol.harvestHit(
            region: "eldergrove", kind: "tree", keys: ["42,35"], hasCoal: false, proof: "proof-123"
        )
        let withoutProof = try RealtimeProtocol.harvestHit(
            region: "eldergrove", kind: "tree", keys: ["42,35"], hasCoal: false, proof: nil
        )
        let a = try XCTUnwrap(JSONSerialization.jsonObject(with: withProof) as? [String: Any])
        let b = try XCTUnwrap(JSONSerialization.jsonObject(with: withoutProof) as? [String: Any])
        XCTAssertEqual(a["actionProof"] as? String, "proof-123")
        XCTAssertNil(b["actionProof"])
    }

    func testPositionMovementFrameContainsAuthoritativeShape() throws {
        let data = try RealtimeProtocol.position(
            region: "eldergrove",
            position: Position(x: 20.5, y: 0.2978266400228179, z: 11.5, ry: 3.14159),
            lifeEpoch: 2,
            moving: true,
            action: ["eq": "tool_axe"]
        )
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["t"] as? String, "pos")
        XCTAssertEqual(object["region"] as? String, "eldergrove")
        XCTAssertEqual(object["mov"] as? Bool, true)
        XCTAssertEqual(object["eq"] as? String, "tool_axe")
        XCTAssertEqual(object["le"] as? Int, 2)
    }

    func testAmbientAndWildCombatEventsAreSeparated() throws {
        let p = Position(x: 1.5, z: 2.5)
        let chicken = try RealtimeProtocol.ambientHit(region: "eldergrove", index: 7, lifeEpoch: 3, position: p)
        let wild = try RealtimeProtocol.wildHit(region: "wild", index: 9, lifeEpoch: 3, position: p)
        let a = try XCTUnwrap(JSONSerialization.jsonObject(with: chicken) as? [String: Any])
        let w = try XCTUnwrap(JSONSerialization.jsonObject(with: wild) as? [String: Any])
        XCTAssertEqual(a["t"] as? String, "am_ev")
        XCTAssertEqual(w["t"] as? String, "wm_ev")
        XCTAssertEqual(a["a"] as? String, "hit")
        XCTAssertEqual(w["a"] as? String, "hit")
    }

    func testConfirmedHarvestHitDecodesWithoutCountingItAsSuccess() throws {
        let data = try RealtimeProtocol.harvestHit(
            region: "eldergrove", kind: "rock", keys: ["33,9"], hasCoal: false, proof: "proof"
        )
        guard case .harvestHit(let packet) = RealtimeProtocol.decode(data) else {
            return XCTFail("harv_hit must decode as a protocol event")
        }
        XCTAssertEqual(packet["t"] as? String, "harv_hit")
    }

    func testFishingRecoveryPolicyMatchesNodeV52() {
        XCTAssertEqual(FishingRecoveryPolicy.minStartTTLMS, 38_000)
        XCTAssertEqual(FishingRecoveryPolicy.biteExpiryMarginMS, 4_500)
        XCTAssertEqual(FishingRecoveryPolicy.biteScheduleTimeoutMS, 3_500)
        XCTAssertEqual(FishingRecoveryPolicy.betweenCatchMS, 4_800)
        XCTAssertEqual(FishingRecoveryPolicy.staleRecoveryMS, 4_500)
        XCTAssertEqual(FishingRecoveryPolicy.ttlPriorityDifferenceMS, 5_000)
        XCTAssertTrue(FishingRecoveryPolicy.isStale("fish_action_stale"))
        XCTAssertTrue(FishingRecoveryPolicy.isStale("grant failed: FISH_ACTION_STALE"))
        XCTAssertFalse(FishingRecoveryPolicy.isStale("no_bite"))
    }

    func testGatherRetryPolicyDefersPureProofMissWithoutFailureStreak() {
        var policy = GatherRetryPolicy()
        policy.deferProofMiss(signature: "tree:3,26", nowMS: 1_000)
        XCTAssertFalse(policy.isEligible(signature: "tree:3,26", nowMS: 10_999))
        XCTAssertTrue(policy.isEligible(signature: "tree:3,26", nowMS: 11_000))
        XCTAssertFalse(policy.hasRetryPriority(signature: "tree:3,26"))
        XCTAssertNil(policy.retryStreaks["tree:3,26"])
    }

    func testGatherRetryPolicyAcceptedPartialGetsShortRetryPriority() {
        var policy = GatherRetryPolicy()
        policy.deferAcceptedPartial(signature: "rock:12,46|12,47", nowMS: 5_000)
        XCTAssertTrue(policy.hasRetryPriority(signature: "rock:12,46|12,47"))
        XCTAssertFalse(policy.isEligible(signature: "rock:12,46|12,47", nowMS: 6_199))
        XCTAssertTrue(policy.isEligible(signature: "rock:12,46|12,47", nowMS: 6_200))
    }

    func testGatherRetryPolicyDefersAfterThreeRealFailures() {
        var policy = GatherRetryPolicy()
        let signature = "rock:12,46|12,47"
        XCTAssertFalse(policy.markRealFailure(signature: signature, nowMS: 0))
        XCTAssertEqual(policy.retryStreaks[signature], 1)
        XCTAssertFalse(policy.markRealFailure(signature: signature, nowMS: 8_000))
        XCTAssertEqual(policy.retryStreaks[signature], 2)
        XCTAssertTrue(policy.markRealFailure(signature: signature, nowMS: 16_000))
        XCTAssertNil(policy.retryStreaks[signature])
        XCTAssertFalse(policy.isEligible(signature: signature, nowMS: 25_999))
        XCTAssertTrue(policy.isEligible(signature: signature, nowMS: 26_000))
    }

    func testWildCombatModesRequireSafeStop() {
        XCTAssertTrue(ActivityMode.zombie.isWildCombat)
        XCTAssertTrue(ActivityMode.dragon.isWildCombat)
        XCTAssertFalse(ActivityMode.tree.isWildCombat)
        XCTAssertFalse(ActivityMode.coal.isWildCombat)
        XCTAssertFalse(ActivityMode.stone.isWildCombat)
        XCTAssertFalse(ActivityMode.fishing.isWildCombat)
        XCTAssertFalse(ActivityMode.chicken.isWildCombat)
    }

    func testContinuedStatusMirrorsVisibleActivityStatus() {
        let fishing = ContinuedActivityStatusFormatter.status(
            mode: .fishing,
            state: .preparingAction,
            currentTarget: "Spot #1 • 19,23",
            rawStatus: "Peixe #3 • fisgada em 25.7s"
        )
        let tree = ContinuedActivityStatusFormatter.status(
            mode: .tree,
            state: .waitingProof,
            currentTarget: "Madeira • 3,26",
            rawStatus: "Handshake 1/3"
        )
        XCTAssertEqual(fishing, "Peixe #3 • fisgada em 25.7s")
        XCTAssertEqual(tree, "Handshake 1/3")
    }

    func testContinuedStatusFallsBackOnlyWhenRawStatusIsEmpty() {
        let value = ContinuedActivityStatusFormatter.status(
            mode: .fishing,
            state: .preparingAction,
            currentTarget: nil,
            rawStatus: "   "
        )
        XCTAssertEqual(value, "Preparando pesca")
    }

    func testContinuedStatusUsesSafeCombatExitCopy() {
        let value = ContinuedActivityStatusFormatter.status(
            mode: .dragon,
            state: .recovering,
            currentTarget: "Dragão #7",
            rawStatus: "Saindo do combate com segurança"
        )
        XCTAssertEqual(value, "Saindo do combate com segurança")
    }

    func testFishingPublicNumberAdvancesOnlyAfterSuccess() {
        XCTAssertEqual(FishingNumberingPolicy.publicFishNumber(successes: 0), 1)
        XCTAssertEqual(FishingNumberingPolicy.publicFishNumber(successes: 0), 1) // retry after failure
        XCTAssertEqual(FishingNumberingPolicy.publicFishNumber(successes: 1), 2)
        XCTAssertEqual(FishingNumberingPolicy.publicFishNumber(successes: 14), 15)
    }

    func testFishingBaitCatalogDoesNotPretendUnverifiedWireIDs() {
        XCTAssertEqual(FishingBait.allCases.map(\.rawValue), [
            "feather", "trout", "bass", "tuna", "squid"
        ])
        XCTAssertEqual(FishingBait.feather.confirmedInventoryKey, "bait_feather")
        XCTAssertEqual(FishingBait.trout.confirmedInventoryKey, "bait_trout")
        XCTAssertNil(FishingBait.bass.confirmedInventoryKey)
        XCTAssertNil(FishingBait.tuna.confirmedInventoryKey)
        XCTAssertNil(FishingBait.squid.confirmedInventoryKey)
        XCTAssertTrue(FishingBait.feather.isAutomationValidated)
        XCTAssertFalse(FishingBait.trout.isAutomationValidated)
        XCTAssertEqual(FishingBait.squid.displayName, "Squid Bait")
    }

    func testBankFirstPolicyProtectsCoreInventoryButKeepsCombatAndSpecialItemsOut() {
        XCTAssertTrue(CombatBankFirstPolicy.shouldBankFirst(type: "wood", slot: ["t": "wood", "n": 2583]))
        XCTAssertTrue(CombatBankFirstPolicy.shouldBankFirst(type: "bait_feather", slot: ["t": "bait_feather", "n": 111]))
        XCTAssertTrue(CombatBankFirstPolicy.shouldBankFirst(type: "tool_axe", slot: ["t": "tool_axe", "n": 1, "durability": 77]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "potion_strength", slot: ["t": "potion_strength", "n": 6]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "wild_sword", slot: ["t": "wild_sword", "n": 1]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "mount_dragon", slot: ["t": "mount_dragon", "n": 1]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "item_scroll_x", slot: ["t": "item_scroll_x", "n": 1]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "quest_item", slot: ["t": "quest_item", "n": 1, "soulbound": true]))
    }

    func testBankAllocatorSkipsFullTenKStackAndUsesNextPartialStack() throws {
        var bank: [Any] = [
            ["t": "wood", "n": 10_000],
            ["t": "wood", "n": 5_100],
            NSNull(),
        ]
        let moved = BankSlotAllocator.place(slot: ["t": "wood", "n": 2_583], quantity: 2_583, into: &bank)
        XCTAssertEqual(moved, 2_583)
        XCTAssertEqual(try XCTUnwrap((bank[0] as? [String: Any])?["n"] as? Int), 10_000)
        XCTAssertEqual(try XCTUnwrap((bank[1] as? [String: Any])?["n"] as? Int), 7_683)
        XCTAssertTrue(bank[2] is NSNull)
    }

    func testBankAllocatorSplitsSimpleStackAcrossTenKBoundary() throws {
        var bank: [Any] = [
            ["t": "stone", "n": 9_800],
            NSNull(),
            NSNull(),
        ]
        let moved = BankSlotAllocator.place(slot: ["t": "stone", "n": 799], quantity: 799, into: &bank)
        XCTAssertEqual(moved, 799)
        XCTAssertEqual(try XCTUnwrap((bank[0] as? [String: Any])?["n"] as? Int), 10_000)
        XCTAssertEqual(try XCTUnwrap((bank[1] as? [String: Any])?["n"] as? Int), 599)
    }

    func testBankAllocatorPreservesMetadataForNonStackableItem() throws {
        let tool: [String: Any] = ["t": "tool_pickaxe", "n": 1, "durability": 83, "quality": "rare"]
        var bank: [Any] = [NSNull(), NSNull()]
        XCTAssertEqual(BankSlotAllocator.place(slot: tool, quantity: 1, into: &bank), 1)
        let stored = try XCTUnwrap(bank[0] as? [String: Any])
        XCTAssertEqual(stored["t"] as? String, "tool_pickaxe")
        XCTAssertEqual(stored["durability"] as? Int, 83)
        XCTAssertEqual(stored["quality"] as? String, "rare")
    }

    func testWildAckCadenceBacksOffOnMissAndRecoversAfterThreeAcks() {
        var cadence = CombatAckCadence()
        XCTAssertEqual(cadence.cooldownMS, 1_650)
        cadence.record(acknowledged: false)
        XCTAssertEqual(cadence.cooldownMS, 1_775)
        cadence.record(acknowledged: false)
        XCTAssertEqual(cadence.cooldownMS, 1_900)
        cadence.record(acknowledged: true)
        cadence.record(acknowledged: true)
        cadence.record(acknowledged: true)
        XCTAssertEqual(cadence.cooldownMS, 1_850)
    }

    func testDragonSafetyPolicyMatchesNodeV521() {
        let dragon = WildCombatSafetyPolicy.policy(for: .dragon)
        XCTAssertEqual(dragon.emergencyEffectiveHP, 160)
        XCTAssertEqual(dragon.finisherEffectiveHP, 175)
        XCTAssertEqual(dragon.postKillSafeHP, 95)
        XCTAssertEqual(dragon.postKillSafeShield, 90)
        XCTAssertEqual(dragon.postKillDamageQuietMS, 1_400)
        XCTAssertEqual(dragon.quickPostEffective, 185)
    }

    func testZombieGeneralLowVitalsRuleRemainsSeparateFromDragonSafetyLayer() {
        let zombie = WildCombatSafetyPolicy.policy(for: .zombie)
        XCTAssertEqual(zombie.emergencyEffectiveHP, 95)
        XCTAssertEqual(zombie.finisherEffectiveHP, 135)
        XCTAssertEqual(zombie.postKillSafeHP, 90)
        XCTAssertEqual(zombie.postKillSafeShield, 65)
    }

    func testGatherKnowledgeNormalizesFootprintAndBuildsStableSignature() {
        XCTAssertEqual(
            GatherKnowledgeStore.normalizeKeys([" 12,46 ", "12,47", "12,46", "bad"]),
            ["12,46", "12,47"]
        )
        XCTAssertEqual(
            GatherKnowledgeStore.signature(kind: " ROCK ", keys: ["12,47", "12,46"]),
            "rock:12,46|12,47"
        )
        XCTAssertEqual(
            GatherKnowledgeStore.entryID(region: " ElderGrove ", kind: "rock", keys: ["12,47", "12,46"]),
            "eldergrove|rock:12,46|12,47"
        )
    }

    func testGatherResourceCatalogPersistsLearnedSubtypeAcrossStoreReload() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherCatalog-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        let now = Date().timeIntervalSince1970 * 1_000
        var store: GatherKnowledgeStore? = GatherKnowledgeStore(directoryURL: dir)
        XCTAssertEqual(
            store?.rememberResource(
                region: "eldergrove",
                kind: "rock",
                keys: ["40,10", "40,11"],
                hasCoal: true,
                source: "res_evt",
                confirmedAt: now
            ),
            .added
        )
        store = nil

        let reloaded = GatherKnowledgeStore(directoryURL: dir)
        let entries = reloaded.catalogEntries(region: "eldergrove", kind: "rock", nowMS: now + 100)
        XCTAssertEqual(entries.count, 1)
        XCTAssertEqual(entries.first?.resourceKeys, ["40,10", "40,11"])
        XCTAssertEqual(entries.first?.hasCoal, true)
    }

    func testGatherCatalogDoesNotDowngradeKnownRockSubtypeWhenLaterPacketOmitsFlag() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherSubtype-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let now = Date().timeIntervalSince1970 * 1_000
        let store = GatherKnowledgeStore(directoryURL: dir, confirmationRefreshMS: 10_000)

        _ = store.rememberResource(
            region: "eldergrove",
            kind: "rock",
            keys: ["33,44"],
            hasCoal: false,
            source: "self_felled",
            confirmedAt: now
        )
        _ = store.rememberResource(
            region: "eldergrove",
            kind: "rock",
            keys: ["33,44"],
            hasCoal: nil,
            source: "snap_cooldown",
            confirmedAt: now + 20_000
        )

        let entry = try XCTUnwrap(store.catalogEntries(region: "eldergrove", kind: "rock", nowMS: now + 20_100).first)
        XCTAssertEqual(entry.hasCoal, false)
    }

    func testGatherSuccessfulPositionPersistsAcrossStoreReload() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherPosition-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let now = Date().timeIntervalSince1970 * 1_000
        let expected = Position(x: -12.5, y: 0.25, z: 20.5, ry: 1.570796326795)

        var store: GatherKnowledgeStore? = GatherKnowledgeStore(directoryURL: dir)
        XCTAssertTrue(store?.rememberPosition(
            region: "eldergrove",
            kind: "rock",
            keys: ["12,46", "12,47"],
            position: expected,
            at: now
        ) == true)
        store = nil

        let reloaded = GatherKnowledgeStore(directoryURL: dir)
        let actual = try XCTUnwrap(reloaded.position(
            region: "eldergrove",
            kind: "rock",
            keys: ["12,47", "12,46"],
            nowMS: now + 100
        ))
        XCTAssertEqual(actual.x, expected.x, accuracy: 0.000001)
        XCTAssertEqual(actual.z, expected.z, accuracy: 0.000001)
        XCTAssertEqual(actual.ry, expected.ry, accuracy: 0.000001)
    }

    func testGatherCatalogMergesPartialFootprintsAndCarriesPositionForward() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherMerge-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let now = Date().timeIntervalSince1970 * 1_000
        let store = GatherKnowledgeStore(directoryURL: dir)
        let learned = Position(x: 3.5, y: 0.25, z: 4.5, ry: 0)

        XCTAssertEqual(store.rememberResource(
            region: "eldergrove",
            kind: "tree",
            keys: ["28,29"],
            hasCoal: nil,
            source: "res_evt",
            confirmedAt: now
        ), .added)
        XCTAssertTrue(store.rememberPosition(
            region: "eldergrove",
            kind: "tree",
            keys: ["28,29"],
            position: learned,
            at: now + 1
        ))
        XCTAssertEqual(store.rememberResource(
            region: "eldergrove",
            kind: "tree",
            keys: ["28,29", "28,30"],
            hasCoal: nil,
            source: "snap_cooldown",
            confirmedAt: now + 20_000
        ), .updated)

        let entries = store.catalogEntries(region: "eldergrove", kind: "tree", nowMS: now + 20_100)
        XCTAssertEqual(entries.count, 1)
        XCTAssertEqual(entries.first?.resourceKeys, ["28,29", "28,30"])
        let migrated = try XCTUnwrap(store.position(
            region: "eldergrove",
            kind: "tree",
            keys: ["28,30", "28,29"],
            nowMS: now + 20_100
        ))
        XCTAssertEqual(migrated.x, learned.x, accuracy: 0.000001)
        XCTAssertEqual(migrated.z, learned.z, accuracy: 0.000001)
    }


    func testActivityRateMatchesNodeSuccessesPerElapsedMinute() {
        let start = Date(timeIntervalSince1970: 1_000)
        let now = start.addingTimeInterval(134)
        let rate = ActivityRateMeter.perMinute(successes: 15, startedAt: start, now: now)
        XCTAssertEqual(rate, 15.0 / (134.0 / 60.0), accuracy: 0.000001)
    }

    func testActivityRateIgnoresAttemptsAndFailuresByUsingOnlySuccesses() {
        let start = Date(timeIntervalSince1970: 2_000)
        let now = start.addingTimeInterval(120)
        XCTAssertEqual(ActivityRateMeter.perMinute(successes: 5, startedAt: start, now: now), 2.5, accuracy: 0.000001)
    }

    func testActivityRateUsesNodeMinimumElapsedWindowAndFormatsPerMinute() {
        let start = Date(timeIntervalSince1970: 3_000)
        let now = start.addingTimeInterval(0.1)
        XCTAssertEqual(ActivityRateMeter.perMinute(successes: 1, startedAt: start, now: now), 100.0, accuracy: 0.000001)
        XCTAssertEqual(ActivityRateMeter.formatted(successes: 0, startedAt: start, now: now), "0.00/min")
    }


    func testActivityToolPolicyMapsOnlyGatherAndFishingTools() {
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .tree), "tool_axe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .stone), "tool_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .coal), "tool_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .fishing), "tool_fishing_rod")
        XCTAssertNil(ActivityToolPolicy.requiredTool(for: .chicken))
        XCTAssertNil(ActivityToolPolicy.requiredTool(for: .zombie))
        XCTAssertNil(ActivityToolPolicy.requiredTool(for: .dragon))
    }

    func testSessionRateStillUsesOnlyAuthoritativeSuccesses() {
        let start = Date(timeIntervalSince1970: 1_000)
        let now = start.addingTimeInterval(120)
        XCTAssertEqual(ActivityRateMeter.perMinute(successes: 3, startedAt: start, now: now), 1.5, accuracy: 0.0001)
    }


    func testLoadoutAllocatorRestoresFishingRodFromBankIntoHotbar() throws {
        let rod: [String: Any] = ["t": "tool_fishing_rod", "n": 1, "durability": 71]
        var hotbar: [Any] = [NSNull(), NSNull(), NSNull(), NSNull(), NSNull(), NSNull()]
        var inventory: [Any] = Array(repeating: NSNull(), count: 24)
        var bank: [Any] = [rod, NSNull()]

        let moved = InventoryLoadoutAllocator.withdraw(
            type: "tool_fishing_rod", quantity: 1, preferHotbar: true,
            hotbar: &hotbar, inventory: &inventory, bank: &bank
        )

        XCTAssertEqual(moved, 1)
        let loaded = try XCTUnwrap(hotbar[0] as? [String: Any])
        XCTAssertEqual(loaded["t"] as? String, "tool_fishing_rod")
        XCTAssertEqual(loaded["durability"] as? Int, 71)
        XCTAssertTrue(bank[0] is NSNull)
    }

    func testLoadoutAllocatorWithdrawsOnlyGoalBaitFromBank() throws {
        var hotbar: [Any] = [NSNull(), NSNull(), NSNull(), NSNull(), NSNull(), NSNull()]
        var inventory: [Any] = Array(repeating: NSNull(), count: 24)
        var bank: [Any] = [["t": "bait_feather", "n": 20], NSNull()]

        let moved = InventoryLoadoutAllocator.withdraw(
            type: "bait_feather", quantity: 3, preferHotbar: false,
            hotbar: &hotbar, inventory: &inventory, bank: &bank
        )

        XCTAssertEqual(moved, 3)
        XCTAssertEqual(InventoryLoadoutAllocator.carriedCount(type: "bait_feather", hotbar: hotbar, inventory: inventory), 3)
        XCTAssertEqual(try XCTUnwrap((bank[0] as? [String: Any])?["n"] as? Int), 17)
    }

    func testSessionErrorsAreSeparatedFromAttemptFailures() {
        var stats = ActivityStats()
        stats.attempts = 26
        stats.failures = 26
        stats.sessionErrors = 1
        XCTAssertEqual(stats.failures, stats.attempts)
        XCTAssertEqual(stats.sessionErrors, 1)
    }

    func testContinuedStatusPreservesContextualBankMovement() {
        let value = ContinuedActivityStatusFormatter.status(
            mode: .dragon,
            state: .moving,
            currentTarget: nil,
            rawStatus: "🏦 Indo ao banco • BANK-FIRST"
        )
        XCTAssertEqual(value, "🏦 Indo ao banco • BANK-FIRST")
    }

}
