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

    func testContinuedStatusNeverLeaksGatherProtocolTerms() {
        let tree = ContinuedActivityStatusFormatter.status(
            mode: .tree,
            state: .waitingProof,
            currentTarget: "Madeira • 3,26",
            rawStatus: "Handshake 1/3"
        )
        let stone = ContinuedActivityStatusFormatter.status(
            mode: .stone,
            state: .waitingResult,
            currentTarget: "Pedra • 30,45",
            rawStatus: "Progresso 5/6"
        )
        XCTAssertEqual(tree, "Cortando árvore")
        XCTAssertEqual(stone, "Minerando pedra")
        XCTAssertFalse(tree.localizedCaseInsensitiveContains("handshake"))
        XCTAssertFalse(stone.localizedCaseInsensitiveContains("progresso"))
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

}
