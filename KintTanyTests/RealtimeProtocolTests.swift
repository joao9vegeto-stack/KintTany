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
}
