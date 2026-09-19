import Foundation
import XCTest
@testable import KintTany

final class RealtimeProtocolTests: XCTestCase {
    func testDashboardActivityButtonsKeepExactVisualAndFunctionalOrder() {
        XCTAssertEqual(
            ActivityMode.dashboardOrder,
            [.tree, .stone, .coal, .iron, .silver, .cacti, .fishing, .chicken, .zombie, .dragon]
        )
        XCTAssertEqual(Set(ActivityMode.dashboardOrder), Set(ActivityMode.allCases))
    }

    func testEveryActivityButtonUsesItsOwnIconAsset() {
        let iconNames = ActivityMode.dashboardOrder.map(\.selectorIconName)
        XCTAssertEqual(Set(iconNames).count, ActivityMode.allCases.count)
        XCTAssertEqual(iconNames[0], "ActivityIconWood")
        XCTAssertEqual(iconNames[1], "ActivityIconStone")
        XCTAssertEqual(iconNames[2], "ActivityIconCoal")
        XCTAssertEqual(iconNames[7], "ActivityIconChicken")
        XCTAssertEqual(iconNames[9], "ActivityIconDragon")
    }

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
        XCTAssertEqual(stone["hasMetal"] as? Bool, false)
        XCTAssertEqual(coal["k"] as? String, "rock")
        XCTAssertEqual(coal["hasCoal"] as? Bool, true)
        XCTAssertEqual(coal["hasMetal"] as? Bool, false)
    }

    func testIronOreUsesRockWireKindWithMetalOnlyInFrostmere() throws {
        let data = try RealtimeProtocol.harvestHit(
            region: "frostmere",
            kind: "rock",
            keys: ["38,34"],
            hasCoal: false,
            hasMetal: true,
            proof: "iron-proof"
        )
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["region"] as? String, "frostmere")
        XCTAssertEqual(object["k"] as? String, "rock")
        XCTAssertEqual(object["hasCoal"] as? Bool, false)
        XCTAssertEqual(object["hasMetal"] as? Bool, true)
        XCTAssertEqual(object["actionProof"] as? String, "iron-proof")
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

    func testEveryGatherModeIsClassified() {
        XCTAssertTrue(ActivityMode.tree.isGathering)
        XCTAssertTrue(ActivityMode.stone.isGathering)
        XCTAssertTrue(ActivityMode.coal.isGathering)
        XCTAssertTrue(ActivityMode.iron.isGathering)
        XCTAssertTrue(ActivityMode.silver.isGathering)
        XCTAssertTrue(ActivityMode.cacti.isGathering)
        XCTAssertTrue(ActivityMode.silver.isDunesGathering)
        XCTAssertTrue(ActivityMode.silver.requiresSafeExit)
        XCTAssertTrue(ActivityMode.cacti.requiresSafeExit)
        XCTAssertFalse(ActivityMode.fishing.isGathering)
        XCTAssertFalse(ActivityMode.chicken.isGathering)
        XCTAssertFalse(ActivityMode.zombie.isGathering)
        XCTAssertFalse(ActivityMode.dragon.isGathering)
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
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "wild_sword_l2", slot: ["t": "wild_sword_l2", "n": 1, "durability": 91]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "mount_dragon", slot: ["t": "mount_dragon", "n": 1]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "item_scroll_x", slot: ["t": "item_scroll_x", "n": 1]))
        XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: "quest_item", slot: ["t": "quest_item", "n": 1, "soulbound": true]))
    }

    func testBankShopProtocolMatchesManualCaptureCoordinates() {
        XCTAssertEqual(BankShopProtocolPolicy.worldEntranceX, -21.5, accuracy: 0.0001)
        XCTAssertEqual(BankShopProtocolPolicy.worldEntranceZ, -17.5, accuracy: 0.0001)
        XCTAssertEqual(BankShopProtocolPolicy.interiorX, 2.5, accuracy: 0.0001)
        XCTAssertEqual(BankShopProtocolPolicy.interiorZ, -0.5, accuracy: 0.0001)
        XCTAssertEqual(BankShopProtocolPolicy.region, "bank_shop")
    }

    func testBankShopTransitionRequiresServerAdvancedSequence() {
        XCTAssertEqual(BankShopProtocolPolicy.acceptedTransitionSequence(baseSeq: 67647, responseSeq: 67648), 67648)
        XCTAssertNil(BankShopProtocolPolicy.acceptedTransitionSequence(baseSeq: 67647, responseSeq: 67647))
        XCTAssertNil(BankShopProtocolPolicy.acceptedTransitionSequence(baseSeq: 67647, responseSeq: 67649))
        XCTAssertNil(BankShopProtocolPolicy.acceptedTransitionSequence(baseSeq: 67647, responseSeq: nil))
    }


    func testSaveBackpackConflictEvidenceSeparatesSequenceRaceFromPayloadMismatch() throws {
        let nested: [String: Any] = [
            "error": "stale_save",
            "authoritative": ["currentStateSeq": 88]
        ]
        XCTAssertEqual(SaveBackpackConflictPolicy.authoritativeSequence(from: nested), 88)
        XCTAssertEqual(
            SaveBackpackConflictPolicy.classify(sentSeq: 87, responseSeq: 88, freshSeq: 88),
            .sequenceAdvanced
        )
        XCTAssertEqual(
            SaveBackpackConflictPolicy.classify(sentSeq: 88, responseSeq: nil, freshSeq: 88),
            .sameSequenceRejected
        )
        XCTAssertEqual(
            SaveBackpackConflictPolicy.classify(sentSeq: 88, responseSeq: nil, freshSeq: nil),
            .sequenceUnavailable
        )
        XCTAssertEqual(SaveBackpackConflictPolicy.safeTopLevelKeys(from: nested), ["authoritative", "error"])
    }

    func testSaveBackpackConflictDiagnosticFindsTieredEquipmentInstanceAndStructuralGap() throws {
        let item: [String: Any] = ["t": "silver_pickaxe", "iid": "iid-77", "d": 91, "n": 1]
        let before: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()], "bankSlots": [item]
        ]
        let sent: [String: Any] = [
            "hotbar": [item], "invSlots": [NSNull()], "bankSlots": [NSNull()]
        ]
        let authoritative: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()], "bankSlots": [item],
            "armorSlots": [["t": "armor_test", "n": 1]], "bankPages": 3
        ]
        let response: [String: Any] = [
            "error": "stale_save", "reason": "instance_location_rejected",
            "stateSeq": 67614, "backpack": authoritative
        ]

        XCTAssertEqual(SaveBackpackConflictPolicy.safeReason(from: response), "instance_location_rejected")
        XCTAssertEqual(SaveBackpackConflictPolicy.equipmentLabel(type: "silver_pickaxe"), "pickaxe:T4:silver_pickaxe")
        XCTAssertEqual(SaveBackpackConflictPolicy.itemLocation(type: "silver_pickaxe", iid: "iid-77", in: before), "bankSlots[0]")
        XCTAssertEqual(SaveBackpackConflictPolicy.itemLocation(type: "silver_pickaxe", iid: "iid-77", in: sent), "hotbar[0]")
        XCTAssertEqual(SaveBackpackConflictPolicy.itemLocation(type: "silver_pickaxe", iid: "iid-77", in: authoritative), "bankSlots[0]")
        XCTAssertEqual(SaveBackpackConflictPolicy.itemKeys(type: "silver_pickaxe", iid: "iid-77", in: before), ["d", "iid", "n", "t"])
        XCTAssertEqual(SaveBackpackConflictPolicy.itemKeys(type: "silver_pickaxe", iid: "iid-77", in: sent), ["d", "iid", "n", "t"])
        XCTAssertEqual(SaveBackpackConflictPolicy.itemKeys(type: "silver_pickaxe", iid: "iid-77", in: authoritative), ["d", "iid", "n", "t"])
        XCTAssertEqual(SaveBackpackConflictPolicy.unrepresentedAuthoritativeBackpackKeys(authoritative), ["armorSlots", "bankPages"])

        for type in ["tool_axe", "copper_axe", "iron_axe", "tool_axe_l2", "silver_axe",
                     "tool_pickaxe", "copper_pickaxe", "iron_pickaxe", "tool_pickaxe_l2", "silver_pickaxe",
                     "wild_sword", "copper_sword", "iron_sword", "wild_sword_l2", "silver_sword"] {
            XCTAssertNotEqual(SaveBackpackConflictPolicy.equipmentLabel(type: type), "other:T0:\(type)")
        }
    }

    func testSaveBackpackPayloadCarriesActiveSessionMetadataFromManualCapture() throws {
        let backpack: [String: Any] = [
            "wood": 10, "stone": 4, "potion_health": 2,
            "potion_health_l2": 9, "silver_ore": 7, "cacti": 3,
            "invSlots": [NSNull()], "hotbar": [NSNull()],
            "armorSlots": [["t": "armor_test", "n": 1]],
            "mountSlots": [NSNull()], "cosmeticSlots": [NSNull()],
            "petSlots": [NSNull()], "furnitureSlots": [NSNull()], "bankSlots": [NSNull()],
            "equippedHotbar": 0, "mountDragonRiding": true
        ]
        let body = BackpackSavePayloadPolicy.makeBody(
            backpack: backpack, baseSeq: 67647, fleet: "us", shardID: 2
        )
        XCTAssertEqual(RealtimeProtocol.int(body["baseSeq"]), 67647)
        XCTAssertEqual(body["fleet"] as? String, "us")
        XCTAssertEqual(RealtimeProtocol.int(body["shardId"]), 2)
        XCTAssertNotNil(body["intentionalRemovals"] as? [Any])
        XCTAssertNotNil(body["intentionalRelicRemovals"] as? [Any])
        XCTAssertNil(body["armorSlots"])
        XCTAssertEqual(RealtimeProtocol.bool(body["mountDragonRiding"]), true)
        let resources = try XCTUnwrap(body["resources"] as? [String: Any])
        XCTAssertEqual(RealtimeProtocol.int(resources["wood"]), 10)
        XCTAssertEqual(RealtimeProtocol.int(resources["potion_health_l2"]), 9)
    }

    func testInstancedEquipmentSelectionUsesExactHighestDurabilityBankSlot() throws {
        let bank: [Any] = [
            ["t": "tool_axe_l2", "n": 1, "d": 719, "iid": "low"],
            NSNull(),
            ["t": "tool_axe_l2", "n": 1, "d": 3974, "iid": "high"],
            ["t": "tool_axe", "n": 1]
        ]
        let index = try XCTUnwrap(BankItemSelectionPolicy.preferredBankSlotIndex(type: "tool_axe_l2", bank: bank))
        XCTAssertEqual(index, 2)
        let selected = try XCTUnwrap(bank[index] as? [String: Any])
        XCTAssertEqual(selected["iid"] as? String, "high")
        XCTAssertEqual(RealtimeProtocol.int(selected["d"]), 3974)
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

    func testDragonSafetyThresholdsPreserveNodeV521Baseline() {
        let dragon = WildCombatSafetyPolicy.policy(for: .dragon)
        XCTAssertEqual(dragon.emergencyEffectiveHP, 160)
        XCTAssertEqual(dragon.finisherEffectiveHP, 175)
        XCTAssertEqual(dragon.postKillSafeHP, 95)
        XCTAssertEqual(dragon.postKillSafeShield, 90)
        XCTAssertEqual(dragon.postKillDamageQuietMS, 1_400)
        XCTAssertEqual(dragon.quickPostEffective, 185)
    }

    func testDragonPostKillObservationCoversKnownDelayedBurst() {
        XCTAssertGreaterThanOrEqual(WildCombatSafetyPolicy.dragonMinimumPostKillObservationMS, 6_000)
        XCTAssertGreaterThan(WildCombatSafetyPolicy.dragonMinimumPostKillObservationMS, 4_000)
        XCTAssertEqual(WildCombatSafetyPolicy.dragonRequiredDamageQuietMS, 3_000)
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

    func testGatherResourceCatalogPersistsIronSubtypeInFrostmere() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherIron-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }

        let now = Date().timeIntervalSince1970 * 1_000
        var store: GatherKnowledgeStore? = GatherKnowledgeStore(directoryURL: dir)
        XCTAssertEqual(
            store?.rememberResource(
                region: "frostmere",
                kind: "rock",
                keys: ["38,34"],
                hasCoal: false,
                hasMetal: true,
                source: "self_felled",
                confirmedAt: now
            ),
            .added
        )
        store = nil

        let reloaded = GatherKnowledgeStore(directoryURL: dir)
        let entry = try XCTUnwrap(reloaded.catalogEntries(region: "frostmere", kind: "rock", nowMS: now + 100).first)
        XCTAssertEqual(entry.hasCoal, false)
        XCTAssertEqual(entry.hasMetal, true)
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


    func testActivityToolPolicyRecognizesAndPrefersEquipmentTiers() throws {
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .tree), "tool_axe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .stone), "tool_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .coal), "tool_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.acceptedTools(for: .tree), ["silver_axe", "tool_axe_l2", "tool_axe"])
        XCTAssertEqual(ActivityToolPolicy.acceptedTools(for: .silver), ["silver_pickaxe", "tool_pickaxe_l2", "copper_pickaxe"])
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .silver), "copper_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.acceptedTools(for: .cacti), ["silver_axe", "tool_axe_l2"])
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .fishing), "tool_fishing_rod")
        XCTAssertNil(ActivityToolPolicy.requiredTool(for: .chicken))

        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "copper_axe", with: .tree))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "iron_axe", with: .tree))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "silver_axe", with: .tree))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "copper_pickaxe", with: .iron))
        XCTAssertFalse(ActivityToolPolicy.isCompatible(type: "tool_pickaxe", with: .tree))
        XCTAssertFalse(ActivityToolPolicy.isCompatible(type: "tool_pickaxe", with: .silver))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "copper_pickaxe", with: .silver))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "tool_pickaxe_l2", with: .silver))
        XCTAssertTrue(ActivityToolPolicy.isCompatible(type: "silver_pickaxe", with: .silver))
        XCTAssertFalse(ActivityToolPolicy.isCompatible(type: "tool_axe", with: .cacti))

        let backpack: [String: Any] = [
            "hotbar": [["t": "tool_axe", "n": 1], ["t": "copper_pickaxe", "n": 1]],
            "invSlots": [["t": "iron_axe", "n": 1]],
            "bankSlots": [["t": "silver_axe", "n": 1], ["t": "silver_pickaxe", "n": 1]]
        ]
        let tree = try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .tree))
        XCTAssertEqual(tree.type, "silver_axe")
        XCTAssertEqual(tree.carried, 0)
        XCTAssertEqual(tree.bank, 1)

        let stone = try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .stone))
        XCTAssertEqual(stone.type, "silver_pickaxe")
        XCTAssertEqual(stone.bank, 1)
    }

    func testCombatBankFirstProtectsEverySwordTierAndBestSwordSelection() throws {
        for sword in ["wild_sword", "wild_sword_l2", "copper_sword", "iron_sword", "silver_sword"] {
            XCTAssertTrue(CombatBankFirstPolicy.isCombatRequiredType(sword))
            XCTAssertFalse(CombatBankFirstPolicy.shouldBankFirst(type: sword, slot: ["t": sword, "n": 1]))
        }
        XCTAssertFalse(CombatBankFirstPolicy.isCombatRequiredType("silver_axe"))

        let backpack: [String: Any] = [
            "hotbar": [["t": "wild_sword", "n": 1]],
            "invSlots": [["t": "iron_sword", "n": 1]],
            "bankSlots": [["t": "silver_sword", "n": 1]]
        ]
        let best = try XCTUnwrap(EquipmentTierPolicy.bestSelection(in: backpack, family: .sword, minimumTier: 1))
        XCTAssertEqual(best.type, "silver_sword")
        XCTAssertEqual(best.bank, 1)
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

    func testFishingCellHealthBlocksAfterTwoFailures() {
        XCTAssertEqual(FishingRecoveryPolicy.maxFailuresPerCell, 2)
    }

    func testCombatAckCircuitBreakerThresholdIsFour() {
        XCTAssertEqual(CombatAckCadence.circuitBreakerThreshold, 4)
    }

    func testWorldExitUsesThreeProbeCyclesBeforeAuthoritativeReconnect() {
        XCTAssertEqual(WorldExitPolicy.probeCycles, 3)
    }

    func testGatherRequiredToolsRemainMappedForPreflight() {
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .tree), "tool_axe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .stone), "tool_pickaxe")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .coal), "tool_pickaxe")
    }

    func testGatherPresenceHandoffRequiresFreshActivityPresenceOnlyAfterWorldBankPreflight() {
        XCTAssertFalse(GatherPresenceHandoffPolicy.requiresFreshActivityPresence(after: .ready))
        XCTAssertTrue(GatherPresenceHandoffPolicy.requiresFreshActivityPresence(after: .needsWorld(tool: "tool_axe_l2")))
        XCTAssertFalse(GatherPresenceHandoffPolicy.requiresFreshActivityPresence(after: .missing(tool: "tool_axe_l2")))
    }

    func testBuild75DunesTransportRecoveryOnlyClaimsShoresAfterFullLootEntryBegins() {
        XCTAssertFalse(DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: .silver, phase: .preflightSafe))
        XCTAssertFalse(DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: .cacti, phase: .preflightSafe))
        XCTAssertTrue(DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: .silver, phase: .fullLootOrEntering))
        XCTAssertTrue(DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: .cacti, phase: .fullLootOrEntering))
        XCTAssertFalse(DunesPresenceSafetyPolicy.requiresShoresRecovery(mode: .stone, phase: .fullLootOrEntering))
    }

    func testBuild76DunesToolInstanceChoosesLowestPositiveDurabilityAmongCarriedCopies() throws {
        let backpack: [String: Any] = [
            "hotbar": [
                ["t": "copper_pickaxe", "n": 1, "d": 2_200, "iid": "copper-high"],
                ["t": "copper_pickaxe", "n": 1, "d": 800, "iid": "copper-low"],
                ["t": "copper_pickaxe", "n": 1, "d": 0, "iid": "copper-broken"]
            ],
            "invSlots": [
                ["t": "copper_pickaxe", "n": 1, "d": 1_400, "iid": "copper-mid"]
            ],
            "bankSlots": [
                ["t": "copper_pickaxe", "n": 1, "d": 300, "iid": "copper-bank"]
            ]
        ]

        let selected = try XCTUnwrap(DunesToolInstancePolicy.preferredInstance(in: backpack, type: "copper_pickaxe"))
        XCTAssertTrue(selected.isCarried)
        XCTAssertEqual(selected.iid, "copper-low")
        XCTAssertEqual(selected.durability, 800)
        XCTAssertEqual(selected.sourceKey, "hotbar")
        XCTAssertEqual(selected.sourceIndex, 1)
        XCTAssertNil(selected.bankIndex)
    }

    func testBuild76DunesToolInstanceUsesLowestPositiveDurabilityBankCopyWhenNoneCarried() throws {
        let backpack: [String: Any] = [
            "hotbar": [NSNull()],
            "invSlots": [NSNull()],
            "bankSlots": [
                ["t": "copper_pickaxe", "n": 1, "d": 1_800, "iid": "bank-high"],
                ["t": "copper_pickaxe", "n": 1, "d": 640, "iid": "bank-low"],
                ["t": "copper_pickaxe", "n": 1, "d": 0, "iid": "bank-broken"]
            ]
        ]

        let selected = try XCTUnwrap(DunesToolInstancePolicy.preferredInstance(in: backpack, type: "copper_pickaxe"))
        XCTAssertFalse(selected.isCarried)
        XCTAssertEqual(selected.iid, "bank-low")
        XCTAssertEqual(selected.durability, 640)
        XCTAssertEqual(selected.bankIndex, 1)
    }

    func testBuild76BankDepositPreservesOnlySelectedToolIID() {
        let selected = DunesToolInstanceIdentity(type: "copper_pickaxe", iid: "keep-me", durability: 800)
        XCTAssertTrue(BankDepositPreservationPolicy.matchesSelectedTool(
            ["t": "copper_pickaxe", "n": 1, "d": 800, "iid": "keep-me"],
            selected: selected
        ))
        XCTAssertFalse(BankDepositPreservationPolicy.matchesSelectedTool(
            ["t": "copper_pickaxe", "n": 1, "d": 1_400, "iid": "bank-me"],
            selected: selected
        ))
        XCTAssertFalse(BankDepositPreservationPolicy.matchesSelectedTool(
            ["t": "tool_axe_l2", "n": 1, "d": 800, "iid": "keep-me"],
            selected: selected
        ))
    }

    func testGatherToolPreflightIsReadyWhenRequiredToolIsCarried() {
        XCTAssertEqual(
            GatherToolPreflightPolicy.disposition(tool: "tool_pickaxe", carried: 1, bank: 4),
            .ready
        )
    }

    func testGatherToolPreflightUsesWorldWhenToolExistsOnlyInBank() {
        XCTAssertEqual(
            GatherToolPreflightPolicy.disposition(tool: "tool_pickaxe", carried: 0, bank: 1),
            .needsWorld(tool: "tool_pickaxe")
        )
    }

    func testGatherToolPreflightFailsClosedWhenToolIsAbsentEverywhere() {
        XCTAssertEqual(
            GatherToolPreflightPolicy.disposition(tool: "tool_axe", carried: 0, bank: 0),
            .missing(tool: "tool_axe")
        )
    }

    func testTreeTierLadderAlwaysChoosesHighestAvailableTool() throws {
        func best(_ bankSlots: [Any]) throws -> EquipmentSelection {
            let backpack: [String: Any] = [
                "hotbar": [NSNull()],
                "invSlots": [NSNull()],
                "bankSlots": bankSlots
            ]
            return try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .tree))
        }

        XCTAssertEqual(try best([
            ["t": "tool_axe", "n": 1],
            ["t": "copper_axe", "n": 1],
            ["t": "iron_axe", "n": 1],
            ["t": "silver_axe", "n": 1]
        ]).type, "silver_axe")

        XCTAssertEqual(try best([
            ["t": "tool_axe", "n": 1],
            ["t": "copper_axe", "n": 1],
            ["t": "iron_axe", "n": 1]
        ]).type, "iron_axe")

        XCTAssertEqual(try best([
            ["t": "tool_axe", "n": 1],
            ["t": "copper_axe", "n": 1]
        ]).type, "copper_axe")

        XCTAssertEqual(try best([
            ["t": "tool_axe", "n": 1]
        ]).type, "tool_axe")
    }

    func testTreePrefersHistoricalIronAxeL2IDOverStarterAxe() throws {
        let backpack: [String: Any] = [
            "hotbar": [NSNull()],
            "invSlots": [NSNull()],
            "bankSlots": [["t": "tool_axe", "n": 1], ["t": "tool_axe_l2", "n": 1]]
        ]
        let best = try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .tree))
        XCTAssertEqual(best.type, "tool_axe_l2")
        XCTAssertEqual(best.tier, 3)
        XCTAssertEqual(best.bank, 1)
    }

    func testBankOnlyIronAxePreservesBestTierInWorldDisposition() throws {
        let backpack: [String: Any] = [
            "hotbar": [NSNull()],
            "invSlots": [NSNull()],
            "bankSlots": [["t": "iron_axe", "n": 1], ["t": "tool_axe", "n": 1]]
        ]
        let best = try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .tree))
        XCTAssertEqual(best.type, "iron_axe")
        XCTAssertEqual(
            GatherToolPreflightPolicy.disposition(tool: best.type, carried: best.carried, bank: best.bank),
            .needsWorld(tool: "iron_axe")
        )
    }

    func testPickaxeTierLadderPrefersBankedHigherTierOverCarriedStarter() throws {
        let backpack: [String: Any] = [
            "hotbar": [["t": "tool_pickaxe", "n": 1]],
            "invSlots": [NSNull()],
            "bankSlots": [
                ["t": "copper_pickaxe", "n": 1],
                ["t": "tool_pickaxe_l2", "n": 1],
                ["t": "silver_pickaxe", "n": 1]
            ]
        ]
        let best = try XCTUnwrap(ActivityToolPolicy.bestSelection(in: backpack, for: .stone))
        XCTAssertEqual(best.type, "silver_pickaxe")
        XCTAssertEqual(best.tier, 4)
        XCTAssertEqual(best.carried, 0)
        XCTAssertEqual(best.bank, 1)
    }


    func testCombatStateConfirmationRequiresFreshSnapshotAndHPDrop() {
        XCTAssertTrue(CombatStateConfirmationPolicy.isStateCorrelatedHit(
            beforeHP: 75, afterHP: 60, snapshotAdvanced: true
        ))
        XCTAssertFalse(CombatStateConfirmationPolicy.isStateCorrelatedHit(
            beforeHP: 75, afterHP: 75, snapshotAdvanced: true
        ))
        XCTAssertFalse(CombatStateConfirmationPolicy.isStateCorrelatedHit(
            beforeHP: 75, afterHP: 60, snapshotAdvanced: false
        ))
        XCTAssertFalse(CombatStateConfirmationPolicy.isStateCorrelatedHit(
            beforeHP: nil, afterHP: 60, snapshotAdvanced: true
        ))
    }

    func testGatherTimingPolicyPreservesRelativeSpacingInBackground() {
        XCTAssertEqual(GatherTimingPolicy.treeFrameGapMS(frameCount: 12), 46)
        XCTAssertEqual(GatherTimingPolicy.treeFrameGapMS(frameCount: 7), 84)
        XCTAssertEqual(GatherTimingPolicy.mineFrameGapMS, 65)
        XCTAssertEqual(GatherTimingPolicy.delayedFrameDiagnosticThresholdMS, 220)
        XCTAssertEqual(GatherTimingPolicy.eventGraceMS, 420)
    }

    func testMovementBudgetDependsOnEmittedFramesNotWallClock() {
        XCTAssertEqual(MovementProgressPolicy.frameBudget(maxSeconds: 30), 200)
        XCTAssertFalse(MovementProgressPolicy.exhausted(sentFrames: 199, maxSeconds: 30))
        XCTAssertTrue(MovementProgressPolicy.exhausted(sentFrames: 200, maxSeconds: 30))
    }

    @MainActor
    func testGatherPreflightBootstrapsWorldWhenBestTierToolIsBankOnly() {
        let bootstrap = AutomationEngine.bootstrapForRun(
            for: .tree,
            gatherDisposition: .needsWorld(tool: "iron_axe")
        )
        XCTAssertEqual(bootstrap.region, "world")
        XCTAssertEqual(bootstrap.position.x, 22.5, accuracy: 0.001)
        XCTAssertEqual(bootstrap.position.z, -3.5, accuracy: 0.001)
    }

    @MainActor
    func testGatherPreflightConnectsDirectlyToElderGroveWhenToolIsCarried() {
        let bootstrap = AutomationEngine.bootstrapForRun(
            for: .stone,
            gatherDisposition: .ready
        )
        XCTAssertEqual(bootstrap.region, "eldergrove")
    }

    @MainActor
    func testIronPreflightConnectsDirectlyToFrostmereWhenPickaxeIsCarried() {
        let bootstrap = AutomationEngine.bootstrapForRun(
            for: .iron,
            gatherDisposition: .ready
        )
        XCTAssertEqual(bootstrap.region, "frostmere")
        XCTAssertEqual(ActivityToolPolicy.requiredTool(for: .iron), "tool_pickaxe")
        XCTAssertTrue(ActivityMode.iron.isGathering)
    }

    func testStoneCoalAndIronResourceClassificationsNeverOverlap() {
        XCTAssertTrue(GatherResourcePolicy.matches(mode: .stone, kind: "rock", hasCoal: false, hasMetal: false))
        XCTAssertFalse(GatherResourcePolicy.matches(mode: .stone, kind: "rock", hasCoal: false, hasMetal: true))
        XCTAssertTrue(GatherResourcePolicy.matches(mode: .coal, kind: "rock", hasCoal: true, hasMetal: false))
        XCTAssertFalse(GatherResourcePolicy.matches(mode: .coal, kind: "rock", hasCoal: true, hasMetal: true))
        XCTAssertTrue(GatherResourcePolicy.matches(mode: .iron, kind: "rock", hasCoal: false, hasMetal: true))
        XCTAssertFalse(GatherResourcePolicy.matches(mode: .iron, kind: "rock", hasCoal: false, hasMetal: false))
        XCTAssertEqual(GatherRegionPolicy.region(for: .iron), "frostmere")
        XCTAssertEqual(GatherRegionPolicy.gridOffset(for: "frostmere"), 19.5)
        XCTAssertEqual(GatherRegionPolicy.gridOffset(for: "eldergrove"), 24.5)
    }

    @MainActor
    func testDunesBootstrapRequiresSafeExit() {
        let silver = AutomationEngine.bootstrapForRun(for: .silver, gatherDisposition: .ready)
        let cacti = AutomationEngine.bootstrapForRun(for: .cacti, gatherDisposition: .ready)
        XCTAssertEqual(silver.region, "desert")
        XCTAssertEqual(cacti.region, "desert")
        XCTAssertEqual(silver.position, Position(x: -9.5, z: -18.5))
        XCTAssertEqual(GatherRegionPolicy.dunesExitPosition, Position(x: -9.5, z: -19.5, ry: .pi))
        XCTAssertEqual(GatherRegionPolicy.shoresArrivalPosition, Position(x: -9.5, z: 18.5, ry: .pi))
        XCTAssertTrue(ActivityMode.silver.requiresSafeExit)
        XCTAssertTrue(ActivityMode.cacti.requiresSafeExit)
    }

    func testItemConservationDetectsMissingToolAndAllowsBankMove() {
        let before: [String: Any] = [
            "hotbar": [["t": "tool_pickaxe", "durability": 91]],
            "invSlots": [NSNull()], "bankSlots": [NSNull()]
        ]
        let moved: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()],
            "bankSlots": [["t": "tool_pickaxe", "durability": 91]]
        ]
        let missing: [String: Any] = [
            "hotbar": [NSNull()], "invSlots": [NSNull()], "bankSlots": [NSNull()]
        ]
        XCTAssertTrue(ItemConservationPolicy.isConserved(type: "tool_pickaxe", before: before, after: moved))
        XCTAssertFalse(ItemConservationPolicy.isConserved(type: "tool_pickaxe", before: before, after: missing))
        XCTAssertEqual(ItemConservationPolicy.total(type: "tool_pickaxe", in: before), 1)
    }

    func testDunesSuspiciousSnapshotHPRequiresAuthoritativeHTTPConfirmation() {
        XCTAssertTrue(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 20, conservativeHP: 99, region: "desert"
        ))
        XCTAssertFalse(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 96, conservativeHP: 99, region: "desert"
        ))
        XCTAssertFalse(DunesSnapshotHPPolicy.requiresHTTPConfirmation(
            currentHP: 100, snapshotHP: 20, conservativeHP: 99, region: "eldergrove"
        ))
    }

    func testDunesHeatSafetyUsesThirtyHPThresholdOnlyForDunes() {
        XCTAssertFalse(DunesHeatSafetyPolicy.requiresRecovery(hp: 31, mode: .silver))
        XCTAssertTrue(DunesHeatSafetyPolicy.requiresRecovery(hp: 30, mode: .silver))
        XCTAssertTrue(DunesHeatSafetyPolicy.requiresRecovery(hp: 13, mode: .cacti))
        XCTAssertFalse(DunesHeatSafetyPolicy.requiresRecovery(hp: 13, mode: .iron))
        XCTAssertEqual(DunesHeatSafetyPolicy.minimumSafeHP, 30)
        XCTAssertEqual(DunesHeatSafetyPolicy.recoveryGoalHP, 90)
        XCTAssertEqual(DunesHeatSafetyPolicy.carriedHealthPotionPlusTarget, 6)
    }

    func testDunesHeatEstimateHasNoArtificialGracePeriod() {
        XCTAssertEqual(DunesHeatSafetyPolicy.estimatedHP(baselineHP: 70, elapsedMS: 0), 70)
        XCTAssertEqual(DunesHeatSafetyPolicy.estimatedHP(baselineHP: 70, elapsedMS: 9_999), 70)
        XCTAssertEqual(DunesHeatSafetyPolicy.estimatedHP(baselineHP: 70, elapsedMS: 10_000), 69)
        XCTAssertEqual(DunesHeatSafetyPolicy.estimatedHP(baselineHP: 70, elapsedMS: 42_000), 66)
    }

    func testPvitRequiresExplicitOwnPlayerIdentity() {
        XCTAssertFalse(OwnVitalsPolicy.shouldApplyPvit(packetPlayerID: nil, playerID: 41106))
        XCTAssertFalse(OwnVitalsPolicy.shouldApplyPvit(packetPlayerID: 999, playerID: 41106))
        XCTAssertFalse(OwnVitalsPolicy.shouldApplyPvit(packetPlayerID: 41106, playerID: nil))
        XCTAssertTrue(OwnVitalsPolicy.shouldApplyPvit(packetPlayerID: 41106, playerID: 41106))
    }

    func testServerGateExplicitDenialSkipsCandidateButNilRemainsAttemptable() {
        XCTAssertFalse(ServerGatePolicy.shouldAttempt(gate: false))
        XCTAssertTrue(ServerGatePolicy.shouldAttempt(gate: true))
        XCTAssertTrue(ServerGatePolicy.shouldAttempt(gate: nil))
    }

    func testGatherResourceMarkerUsesOnlyAuthoritativeBalanceDelta() {
        XCTAssertEqual(GatherLootMarkerPolicy.resource(for: .silver), "silver_ore")
        XCTAssertEqual(GatherLootMarkerPolicy.resource(for: .cacti), "cacti")
        XCTAssertEqual(GatherLootMarkerPolicy.confirmedDelta(previous: 8, current: 10), 2)
        XCTAssertNil(GatherLootMarkerPolicy.confirmedDelta(previous: nil, current: 10))
        XCTAssertEqual(
            GatherLootMarkerPolicy.label(item: "silver_ore", previous: 8, current: 10),
            "silver_ore=10 • saldo 8→10 • variação acumulada +2"
        )
        XCTAssertEqual(
            GatherLootMarkerPolicy.label(item: "coal", previous: 10, current: 10),
            "coal=10 • saldo 10→10 • sem variação nova"
        )
    }

    func testHealthPotionWithoutAuthoritativeHPGainBlocksAnotherDose() {
        XCTAssertEqual(
            HealthPotionEffectPolicy.result(before: 66, after: 66, interrupted: false),
            .noAuthoritativeGain
        )
        XCTAssertEqual(
            HealthPotionEffectPolicy.result(before: 66, after: 76, interrupted: false),
            .confirmed
        )
        XCTAssertEqual(
            HealthPotionEffectPolicy.result(before: 66, after: 66, interrupted: true),
            .interrupted
        )
    }

    func testDunesResourceClassificationUsesRegionRatherThanLegacyRockFlags() {
        XCTAssertTrue(GatherResourcePolicy.matches(mode: .silver, region: "desert", kind: "rock", hasCoal: false, hasMetal: false))
        XCTAssertFalse(GatherResourcePolicy.matches(mode: .silver, region: "frostmere", kind: "rock", hasCoal: false, hasMetal: true))
        XCTAssertTrue(GatherResourcePolicy.matches(mode: .cacti, region: "desert", kind: "tree", hasCoal: false, hasMetal: false))
        XCTAssertFalse(GatherResourcePolicy.matches(mode: .tree, region: "desert", kind: "tree", hasCoal: false, hasMetal: false))
        XCTAssertEqual(GatherRegionPolicy.gridOffset(for: "desert"), 19.5)
    }

    func testDunesDiscoveryKeepsLegacyRockWireKindForSilver() {
        let observation = DunesResourceDiscovery.observe([
            "kind": "rock",
            "keys": ["10,11", "10,12"],
            "hasMetal": true
        ])
        XCTAssertEqual(observation.mode, .silver)
        XCTAssertEqual(observation.wireKind, "rock")
        XCTAssertEqual(observation.keys, ["10,11", "10,12"])
        XCTAssertEqual(observation.hasMetal, true)
    }

    func testDunesDiscoveryUnderstandsCactusAliasAndNestedNodes() {
        let observation = DunesResourceDiscovery.observe([
            "resourceType": "cactus",
            "nodes": [
                ["key": "4,7"],
                ["c": 5, "r": 7]
            ]
        ])
        XCTAssertEqual(observation.mode, .cacti)
        XCTAssertEqual(observation.wireKind, "tree")
        XCTAssertEqual(Set(observation.keys), Set(["4,7", "5,7"]))
    }

    func testDunesDiscoveryUnderstandsSilverAliasWithoutInventingProofData() {
        let observation = DunesResourceDiscovery.observe([
            "nodeType": "silver_ore",
            "tiles": ["21,9"],
            "actionProof": "SHOULD_NOT_APPEAR",
            "loot": "silver_ore"
        ])
        XCTAssertEqual(observation.mode, .silver)
        XCTAssertEqual(observation.wireKind, "rock")
        XCTAssertEqual(observation.keys, ["21,9"])
        XCTAssertFalse(observation.fieldNames.contains("actionProof"))
        XCTAssertFalse(DunesResourceDiscovery.diagnosticSummary(observation).contains("SHOULD_NOT_APPEAR"))
    }

    func testGatherKnowledgeExplicitFlushPersistsDebouncedChanges() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("KintTanyGatherFlush-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let now = Date().timeIntervalSince1970 * 1_000
        let store = GatherKnowledgeStore(directoryURL: dir)
        _ = store.rememberResource(
            region: "eldergrove",
            kind: "tree",
            keys: ["17,4"],
            hasCoal: nil,
            source: "self_felled",
            confirmedAt: now
        )
        XCTAssertTrue(store.rememberPosition(
            region: "eldergrove",
            kind: "tree",
            keys: ["17,4"],
            position: Position(x: 17.5, y: 0.25, z: 4.5, ry: 0),
            at: now
        ))

        store.flush()

        let reloaded = GatherKnowledgeStore(directoryURL: dir)
        XCTAssertEqual(reloaded.catalogEntries(region: "eldergrove", kind: "tree", nowMS: now + 100).count, 1)
        XCTAssertNotNil(reloaded.position(region: "eldergrove", kind: "tree", keys: ["17,4"], nowMS: now + 100))
    }


    func testBuild74DunesAlwaysUsesWorldBankServiceBeforeDesertPresence() {
        XCTAssertTrue(DunesWorldPreflightPolicy.requiresWorldBankService(for: .silver))
        XCTAssertTrue(DunesWorldPreflightPolicy.requiresWorldBankService(for: .cacti))
        XCTAssertFalse(DunesWorldPreflightPolicy.requiresWorldBankService(for: .iron))
        XCTAssertEqual(DunesWorldPreflightPolicy.bankBootstrap.region, "world")
        XCTAssertEqual(
            AutomationEngine.bootstrapForRun(for: .silver, gatherDisposition: .needsWorld(tool: "tool_pickaxe")).region,
            "world"
        )
        XCTAssertEqual(AutomationEngine.bootstrap(for: .silver).region, "desert")
        XCTAssertEqual(AutomationEngine.bootstrap(for: .cacti).region, "desert")
    }

    func testBuild74MobTelemetryCountsOnlyAliveEntries() {
        XCTAssertEqual(MobTelemetryPolicy.visibleCount(chickenAlive: 0, wildAlive: 6), 6)
        XCTAssertEqual(MobTelemetryPolicy.visibleCount(chickenAlive: 3, wildAlive: 0), 3)
        XCTAssertEqual(MobTelemetryPolicy.visibleCount(chickenAlive: 2, wildAlive: 5), 5)
        XCTAssertEqual(MobTelemetryPolicy.visibleCount(chickenAlive: -1, wildAlive: -2), 0)
    }

    func testBuild74GroundBagPolicySelectsOnlyNewOwnNearbyBag() {
        let bags: [[String: Any]] = [
            ["id": "old", "ownerId": 41106, "x": 10.0, "z": 20.0],
            ["id": "mine-near", "ownerId": 41106, "x": 11.0, "z": 21.0],
            ["id": "other-near", "ownerId": 999, "x": 10.5, "z": 20.5],
            ["id": "mine-far", "ownerId": 41106, "x": 30.0, "z": 30.0]
        ]
        XCTAssertEqual(
            WildGroundBagPolicy.candidateIDs(
                bags: bags,
                excluding: Set(["old"]),
                ownerID: 41106,
                killX: 10.0,
                killZ: 20.0
            ),
            ["mine-near"]
        )
    }

}
