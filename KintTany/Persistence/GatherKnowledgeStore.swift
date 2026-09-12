import Foundation
import Dispatch

struct GatherCatalogRecord: Codable, Equatable {
    let region: String
    let kind: String
    let resourceKeys: [String]
    let hasCoal: Bool?
    let hasMetal: Bool?
    let lastConfirmedAt: Double
    let source: String

    var signature: String {
        GatherKnowledgeStore.signature(kind: kind, keys: resourceKeys)
    }
}

struct GatherPositionRecord: Codable, Equatable {
    let region: String
    let kind: String
    let resourceKeys: [String]
    let x: Double
    let z: Double
    let ry: Double
    let at: Double

    var signature: String {
        GatherKnowledgeStore.signature(kind: kind, keys: resourceKeys)
    }
}

enum GatherKnowledgeChange: Equatable {
    case none
    case added
    case updated
    case refreshed
}

/// Persistent gathering knowledge modeled after the Node v5.2/v7.7
/// `resource-catalog.json` + `gather-position-memory.json` behavior.
///
/// Only STATIC metadata is persisted here: region/kind/footprint/rock subtype
/// and a proven interaction position/yaw. Never persist action proofs, wear,
/// h/hm, busy state or cooldown as if they were valid in a later session.
final class GatherKnowledgeStore {
    private struct CatalogDocument: Codable {
        var version = 1
        var entries: [String: GatherCatalogRecord] = [:]
    }

    private struct PositionDocument: Codable {
        var version = 1
        var entries: [String: GatherPositionRecord] = [:]
    }

    private let catalogURL: URL
    private let positionURL: URL
    private let maxCatalogEntries: Int
    private let maxPositionEntries: Int
    private let catalogMaxAgeMS: Double
    private let positionMaxAgeMS: Double
    private let confirmationRefreshMS: Double

    private var catalog = CatalogDocument()
    private var positions = PositionDocument()

    // RC3.5: mutations stay synchronous/in-memory, but JSON encoding + atomic
    // writes are debounced off the realtime hot path. A final synchronous flush
    // happens when the gather session/store ends so cross-session persistence is
    // preserved without blocking every FELLED/position update.
    private let ioQueue = DispatchQueue(label: "com.joaopedro.kinttany.gather-knowledge-io", qos: .utility)
    private var pendingFlush: DispatchWorkItem?

    init(
        directoryURL: URL? = nil,
        maxCatalogEntries: Int = 4_096,
        maxPositionEntries: Int = 256,
        catalogMaxAgeMS: Double = 90 * 24 * 60 * 60 * 1_000,
        positionMaxAgeMS: Double = 30 * 24 * 60 * 60 * 1_000,
        confirmationRefreshMS: Double = 15 * 60 * 1_000
    ) {
        let directory = directoryURL ?? Self.defaultDirectoryURL()
        self.catalogURL = directory.appendingPathComponent("resource-catalog.json", isDirectory: false)
        self.positionURL = directory.appendingPathComponent("gather-position-memory.json", isDirectory: false)
        self.maxCatalogEntries = max(64, maxCatalogEntries)
        self.maxPositionEntries = max(32, maxPositionEntries)
        self.catalogMaxAgeMS = max(24 * 60 * 60 * 1_000, catalogMaxAgeMS)
        self.positionMaxAgeMS = max(24 * 60 * 60 * 1_000, positionMaxAgeMS)
        self.confirmationRefreshMS = max(10_000, confirmationRefreshMS)

        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        load()
        prune(save: false)
    }

    deinit {
        flush()
    }

    static func normalizeKeys(_ values: [String]) -> [String] {
        var output: [String] = []
        var seen = Set<String>()
        for raw in values {
            let parts = raw.split(separator: ",", omittingEmptySubsequences: false)
            guard parts.count == 2,
                  let c = Int(String(parts[0]).trimmingCharacters(in: .whitespacesAndNewlines)),
                  let r = Int(String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines)) else { continue }
            let key = "\(c),\(r)"
            if seen.insert(key).inserted { output.append(key) }
        }
        return output
    }

    static func signature(kind: String, keys: [String]) -> String {
        let normalizedKind = kind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedKeys = normalizeKeys(keys).sorted()
        guard !normalizedKind.isEmpty, !normalizedKeys.isEmpty else { return "" }
        return "\(normalizedKind):\(normalizedKeys.joined(separator: "|"))"
    }

    static func entryID(region: String, kind: String, keys: [String]) -> String {
        let normalizedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let signature = signature(kind: kind, keys: keys)
        guard !normalizedRegion.isEmpty, !signature.isEmpty else { return "" }
        return "\(normalizedRegion)|\(signature)"
    }

    func catalogEntries(region: String, kind: String? = nil, nowMS: Double = GatherKnowledgeStore.nowMS) -> [GatherCatalogRecord] {
        let wantedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let wantedKind = kind?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return catalog.entries.values
            .filter { record in
                guard record.region == wantedRegion else { return false }
                if let wantedKind, !wantedKind.isEmpty, record.kind != wantedKind { return false }
                return record.lastConfirmedAt > 0 && nowMS - record.lastConfirmedAt <= catalogMaxAgeMS
            }
            .sorted { $0.lastConfirmedAt > $1.lastConfirmedAt }
    }

    func catalogCount(region: String, kind: String? = nil, nowMS: Double = GatherKnowledgeStore.nowMS) -> Int {
        catalogEntries(region: region, kind: kind, nowMS: nowMS).count
    }

    @discardableResult
    func rememberResource(
        region: String,
        kind: String,
        keys: [String],
        hasCoal incomingHasCoal: Bool?,
        hasMetal incomingHasMetal: Bool? = nil,
        source: String,
        confirmedAt nowMS: Double = GatherKnowledgeStore.nowMS
    ) -> GatherKnowledgeChange {
        let normalizedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedKind = kind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalizedRegion.isEmpty, ["tree", "rock"].contains(normalizedKind) else { return .none }

        let incomingKeys = Self.normalizeKeys(keys)
        guard !incomingKeys.isEmpty else { return .none }
        let incomingSet = Set(incomingKeys)
        let cleanSource = String(source.prefix(48))

        // A res_evt may expose only part of a multi-tile footprint. Any catalog
        // records of the same region/kind that share a tile necessarily describe
        // the same physical resource, so merge them instead of creating duplicate
        // selectable targets. This also heals older partial observations over time.
        let overlapping = catalog.entries.filter { _, record in
            record.region == normalizedRegion &&
            record.kind == normalizedKind &&
            !Set(record.resourceKeys).isDisjoint(with: incomingSet)
        }

        var mergedKeys = incomingKeys
        let oldRecords = overlapping.map(\.value)
        for record in oldRecords {
            mergedKeys.append(contentsOf: record.resourceKeys)
        }
        mergedKeys = Self.normalizeKeys(mergedKeys).sorted()
        let mergedID = Self.entryID(region: normalizedRegion, kind: normalizedKind, keys: mergedKeys)
        guard !mergedID.isEmpty else { return .none }

        let newestOld = oldRecords.max { $0.lastConfirmedAt < $1.lastConfirmedAt }
        let strongestOld = oldRecords.first(where: { $0.source == "self_felled" }) ?? newestOld
        let oldCoal = strongestOld?.hasCoal
        let oldMetal = strongestOld?.hasMetal
        let hasCoal: Bool?
        let hasMetal: Bool?
        if normalizedKind != "rock" {
            hasCoal = nil
            hasMetal = nil
        } else {
            if let incomingHasCoal {
                if let oldCoal, oldCoal != incomingHasCoal, strongestOld?.source == "self_felled", cleanSource != "self_felled" {
                    hasCoal = oldCoal
                } else {
                    hasCoal = incomingHasCoal
                }
            } else {
                hasCoal = oldCoal
            }

            if let incomingHasMetal {
                if let oldMetal, oldMetal != incomingHasMetal, strongestOld?.source == "self_felled", cleanSource != "self_felled" {
                    hasMetal = oldMetal
                } else {
                    hasMetal = incomingHasMetal
                }
            } else {
                hasMetal = oldMetal
            }
        }

        let oldKeys = newestOld?.resourceKeys.sorted() ?? []
        let metadataChanged = newestOld == nil ||
            oldKeys != mergedKeys ||
            newestOld?.hasCoal != hasCoal ||
            newestOld?.hasMetal != hasMetal
        let oldAt = newestOld?.lastConfirmedAt ?? 0

        if !metadataChanged, nowMS - oldAt < confirmationRefreshMS {
            return .none
        }

        // Remove superseded partial IDs before writing the canonical merged ID.
        for id in overlapping.keys where id != mergedID {
            catalog.entries.removeValue(forKey: id)
        }

        let record = GatherCatalogRecord(
            region: normalizedRegion,
            kind: normalizedKind,
            resourceKeys: mergedKeys,
            hasCoal: hasCoal,
            hasMetal: hasMetal,
            lastConfirmedAt: nowMS,
            source: cleanSource == "self_felled" || strongestOld?.source != "self_felled"
                ? (metadataChanged ? cleanSource : (newestOld?.source ?? cleanSource))
                : "self_felled"
        )
        catalog.entries[mergedID] = record

        // If a successful interaction position was learned while the footprint
        // was only partially known, move the newest position to the merged ID.
        let overlappingPositionIDs = positions.entries.filter { _, value in
            value.region == normalizedRegion &&
            value.kind == normalizedKind &&
            !Set(value.resourceKeys).isDisjoint(with: Set(mergedKeys))
        }
        if let newestPosition = overlappingPositionIDs.values.max(by: { $0.at < $1.at }) {
            for id in overlappingPositionIDs.keys where id != mergedID {
                positions.entries.removeValue(forKey: id)
            }
            positions.entries[mergedID] = GatherPositionRecord(
                region: normalizedRegion,
                kind: normalizedKind,
                resourceKeys: mergedKeys,
                x: newestPosition.x,
                z: newestPosition.z,
                ry: newestPosition.ry,
                at: newestPosition.at
            )
            scheduleFlush()
        }

        pruneCatalog(nowMS: nowMS)
        scheduleFlush()
        return newestOld == nil ? .added : (metadataChanged ? .updated : .refreshed)
    }

    func position(region: String, kind: String, keys: [String], nowMS: Double = GatherKnowledgeStore.nowMS) -> Position? {
        let id = Self.entryID(region: region, kind: kind, keys: keys)
        guard let record = positions.entries[id], record.at > 0, nowMS - record.at <= positionMaxAgeMS else { return nil }
        return Position(x: record.x, y: 0.25, z: record.z, ry: record.ry)
    }

    func positionSnapshot(region: String, nowMS: Double = GatherKnowledgeStore.nowMS) -> [String: Position] {
        let wantedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        var result: [String: Position] = [:]
        for record in positions.entries.values where record.region == wantedRegion {
            guard record.at > 0, nowMS - record.at <= positionMaxAgeMS else { continue }
            result[record.signature] = Position(x: record.x, y: 0.25, z: record.z, ry: record.ry)
        }
        return result
    }

    @discardableResult
    func rememberPosition(
        region: String,
        kind: String,
        keys: [String],
        position: Position,
        at nowMS: Double = GatherKnowledgeStore.nowMS
    ) -> Bool {
        guard position.x.isFinite, position.z.isFinite, position.ry.isFinite else { return false }
        let normalizedRegion = region.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedKind = kind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let normalizedKeys = Self.normalizeKeys(keys)
        let id = Self.entryID(region: normalizedRegion, kind: normalizedKind, keys: normalizedKeys)
        guard !id.isEmpty else { return false }

        let next = GatherPositionRecord(
            region: normalizedRegion,
            kind: normalizedKind,
            resourceKeys: normalizedKeys,
            x: position.x,
            z: position.z,
            ry: position.ry,
            at: nowMS
        )
        if positions.entries[id] == next { return false }
        positions.entries[id] = next
        prunePositions(nowMS: nowMS)
        scheduleFlush()
        return true
    }

    func prune(save: Bool = true, nowMS: Double = GatherKnowledgeStore.nowMS) {
        pruneCatalog(nowMS: nowMS)
        prunePositions(nowMS: nowMS)
        if save { scheduleFlush() }
    }

    private func load() {
        let decoder = JSONDecoder()
        if let data = try? Data(contentsOf: catalogURL),
           let decoded = try? decoder.decode(CatalogDocument.self, from: data) {
            catalog = decoded
        }
        if let data = try? Data(contentsOf: positionURL),
           let decoded = try? decoder.decode(PositionDocument.self, from: data) {
            positions = decoded
        }
    }

    private func pruneCatalog(nowMS: Double) {
        let survivors = catalog.entries
            .filter { _, value in value.lastConfirmedAt > 0 && nowMS - value.lastConfirmedAt <= catalogMaxAgeMS }
            .sorted { $0.value.lastConfirmedAt > $1.value.lastConfirmedAt }
            .prefix(maxCatalogEntries)
        catalog.entries = Dictionary(uniqueKeysWithValues: survivors.map { ($0.key, $0.value) })
    }

    private func prunePositions(nowMS: Double) {
        let survivors = positions.entries
            .filter { _, value in value.at > 0 && nowMS - value.at <= positionMaxAgeMS }
            .sorted { $0.value.at > $1.value.at }
            .prefix(maxPositionEntries)
        positions.entries = Dictionary(uniqueKeysWithValues: survivors.map { ($0.key, $0.value) })
    }

    func flush() {
        pendingFlush?.cancel()
        pendingFlush = nil
        let catalogSnapshot = catalog
        let positionSnapshot = positions
        let catalogURL = self.catalogURL
        let positionURL = self.positionURL
        ioQueue.sync {
            Self.saveSnapshot(catalogSnapshot, to: catalogURL)
            Self.saveSnapshot(positionSnapshot, to: positionURL)
        }
    }

    private func scheduleFlush(delay: TimeInterval = 1.5) {
        pendingFlush?.cancel()
        let catalogSnapshot = catalog
        let positionSnapshot = positions
        let catalogURL = self.catalogURL
        let positionURL = self.positionURL
        let item = DispatchWorkItem {
            Self.saveSnapshot(catalogSnapshot, to: catalogURL)
            Self.saveSnapshot(positionSnapshot, to: positionURL)
        }
        pendingFlush = item
        ioQueue.asyncAfter(deadline: .now() + delay, execute: item)
    }

    private static func saveSnapshot<T: Encodable>(_ value: T, to url: URL) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(value) else { return }
        try? data.write(to: url, options: .atomic)
    }

    private static func defaultDirectoryURL() -> URL {
        let fm = FileManager.default
        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fm.urls(for: .cachesDirectory, in: .userDomainMask).first
            ?? fm.temporaryDirectory
        return base
            .appendingPathComponent("KintTany", isDirectory: true)
            .appendingPathComponent("GatherKnowledge", isDirectory: true)
    }

    private static var nowMS: Double {
        Date().timeIntervalSince1970 * 1_000
    }
}
