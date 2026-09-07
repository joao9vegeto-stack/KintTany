import Foundation

enum RealtimeEvent {
    case queueReady, queuePosition(Int), regionAck(String), snapshot([String:Any]), resourceEvent([String:Any]), actionProof(String), harvestHit([String:Any]), mobEvent([String:Any]), unknown(String)
}

enum RealtimeProtocol {
    static func decode(_ data: Data) -> RealtimeEvent? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String:Any], let type = object["t"] as? String else { return nil }
        switch type {
        case "queue_ready": return .queueReady
        case "queue_pos": return .queuePosition(object["p"] as? Int ?? 0)
        case "region_ack": return .regionAck(object["region"] as? String ?? "")
        case "snap": return .snapshot(object)
        case "res_evt", "res_snap": return .resourceEvent(object)
        case "action_proof": return .actionProof((object["actionProof"] ?? object["proof"] ?? "") as? String ?? "")
        case "harv_hit": return .harvestHit(object)
        case "wm_ev", "am_ev", "wild_mb_ack": return .mobEvent(object)
        default: return .unknown(type)
        }
    }

    static func json(_ object: [String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject: object) }
    static func queuePing() throws -> Data { try json(["t":"q_ping"]) }
    static func position(region: String, position: Position, lifeEpoch: Int, moving: Bool, action: [String:Any] = [:]) throws -> Data {
        var p: [String:Any] = ["t":"pos", "region":region, "x":position.x, "y":position.y, "z":position.z, "ry":position.ry, "mov":moving, "le":lifeEpoch, "tut":-1, "rft":0, "sms":0, "ocm":0, "trx":0]
        action.forEach { p[$0.key] = $0.value }; return try json(p)
    }
    static func harvest(region: String, kind: String, keys: [String], hasCoal: Bool) throws -> Data { try json(["t":"harv", "region":region, "k":kind, "keys":keys, "hasCoal":hasCoal]) }
    static func harvestHit(region: String, kind: String, keys: [String], hasCoal: Bool, proof: String?) throws -> Data { var p:[String:Any] = ["t":"harv_hit", "region":region, "k":kind, "keys":keys, "hasCoal":hasCoal, "hasMetal":false]; if let proof { p["actionProof"] = proof }; return try json(p) }
    static func wildHit(region: String, index: Int, lifeEpoch: Int, position: Position, multiplier: Int = 1) throws -> Data { var p:[String:Any] = ["t":"wm_ev", "region":region, "a":"hit", "i":index, "le":lifeEpoch, "px":position.x, "pz":position.z]; if multiplier > 1 { p["n"] = multiplier }; return try json(p) }
}
