import Foundation

enum RealtimeEvent {
    case queueReady
    case queuePosition(Int)
    case queueEvicted(String)
    case regionAck(String)
    case snapshot([String: Any])
    case resourceEvent([String: Any])
    case actionProof([String: Any])
    case harvestHit([String: Any])
    case fishEvent([String: Any])
    case mobEvent([String: Any])
    case unknown(String)
}

enum RealtimeProtocol {
    static func packet(_ data: Data) -> [String: Any]? {
        try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }

    static func decode(_ data: Data) -> RealtimeEvent? {
        guard let object = packet(data), let type = object["t"] as? String else { return nil }
        switch type {
        case "queue_ready":
            return .queueReady
        case "queue_pos":
            return .queuePosition(int(object["pos"]) ?? int(object["p"]) ?? int(object["ahead"]) ?? 0)
        case "queue_evicted":
            return .queueEvicted((object["reason"] as? String) ?? "unknown")
        case "region_ack":
            return .regionAck((object["region"] as? String) ?? "")
        case "snap":
            return .snapshot(object)
        case "res_evt", "res_snap":
            return .resourceEvent(object)
        case "action_proof":
            return .actionProof(object)
        case "harv_hit", "harv_full":
            return .harvestHit(object)
        case "fish_spots", "fish_spot_moved", "fish_bite":
            return .fishEvent(object)
        case "wm_ev", "am_ev", "wild_mb_ack", "pvit":
            return .mobEvent(object)
        default:
            return .unknown(type)
        }
    }

    static func json(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [])
    }

    static func queuePing() throws -> Data {
        try json(["t": "q_ping"])
    }

    static func position(
        region: String,
        position: Position,
        lifeEpoch: Int,
        moving: Bool,
        full: Bool = false,
        action: [String: Any] = [:]
    ) throws -> Data {
        var payload: [String: Any] = [
            "t": "pos",
            "region": region,
            "x": position.x,
            "y": position.y,
            "z": position.z,
            "ry": position.ry,
            "mov": moving,
            "le": max(1, lifeEpoch),
            "tut": -1,
            "rft": 0,
            "sms": 0,
            "ocm": 0,
            "trx": 0
        ]

        if full {
            payload["outfit"] = [
                "outfitSchema": 15,
                "hat": 0,
                "top": 0,
                "pants": 0,
                "shoe": 0,
                "skinTone": 1
            ]
        }

        for (key, value) in action {
            payload[key] = value
        }
        return try json(payload)
    }

    static func harvest(region: String, kind: String, keys: [String], hasCoal: Bool) throws -> Data {
        try json([
            "t": "harv",
            "region": region,
            "k": kind,
            "keys": unique(keys),
            "hasCoal": kind == "rock" && hasCoal
        ])
    }

    static func harvestHit(
        region: String,
        kind: String,
        keys: [String],
        hasCoal: Bool,
        hasMetal: Bool = false,
        proof: String?
    ) throws -> Data {
        var payload: [String: Any] = [
            "t": "harv_hit",
            "region": region,
            "k": kind,
            "keys": unique(keys),
            "hasCoal": kind == "rock" && hasCoal,
            "hasMetal": hasMetal
        ]
        if let proof, !proof.isEmpty {
            payload["actionProof"] = proof
        }
        return try json(payload)
    }

    static func ambientHit(region: String, index: Int, lifeEpoch: Int, position: Position) throws -> Data {
        try json([
            "t": "am_ev",
            "region": region,
            "a": "hit",
            "i": index,
            "le": max(1, lifeEpoch),
            "px": position.x,
            "pz": position.z
        ])
    }

    static func wildHit(region: String, index: Int, lifeEpoch: Int, position: Position, multiplier: Int = 1) throws -> Data {
        var payload: [String: Any] = [
            "t": "wm_ev",
            "region": region,
            "a": "hit",
            "i": index,
            "le": max(1, lifeEpoch),
            "px": position.x,
            "pz": position.z
        ]
        if multiplier > 1 { payload["n"] = multiplier }
        return try json(payload)
    }

    static func int(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String, let number = Double(value) { return Int(number) }
        return nil
    }

    static func double(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? NSNumber { return value.doubleValue }
        if let value = value as? String { return Double(value) }
        return nil
    }

    static func bool(_ value: Any?) -> Bool? {
        if let value = value as? Bool { return value }
        if let value = value as? NSNumber { return value.boolValue }
        if let value = value as? String {
            switch value.lowercased() {
            case "1", "true", "yes", "on": return true
            case "0", "false", "no", "off": return false
            default: return nil
            }
        }
        return nil
    }

    private static func unique(_ values: [String]) -> [String] {
        var seen = Set<String>()
        return values.filter { seen.insert($0).inserted }
    }
}
