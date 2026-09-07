import Foundation
import XCTest
@testable import KintTany

final class RealtimeProtocolTests: XCTestCase {
    func testQueuePingUsesDocumentedEventName() throws {
        let data = try RealtimeProtocol.queuePing()
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["t"] as? String, "q_ping")
    }

    func testTreeHarvestIsNotCoal() throws {
        let data = try RealtimeProtocol.harvest(region: "world", kind: "tree-1", keys: ["tree"], hasCoal: false)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["k"] as? String, "tree-1")
        XCTAssertEqual(object["hasCoal"] as? Bool, false)
    }

    func testConfirmedHarvestHitDecodes() throws {
        let data = try RealtimeProtocol.harvestHit(region: "world", kind: "stone-1", keys: ["stone"], hasCoal: false, proof: "proof")
        guard case .harvestHit = RealtimeProtocol.decode(data) else {
            return XCTFail("harv_hit must be decoded as a harvest hit")
        }
    }
}
