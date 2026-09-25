import Foundation
import UIKit
import CryptoKit

/// Exact immutable capture of the Kintara cosmetic assets collected on 2026-09-25.
///
/// Build 116 intentionally keeps these bytes inside the IPA and loads them into
/// the KintTany process. This is NOT a web renderer and does not re-download
/// cosmetics at runtime. The native SceneKit avatar can request the exact
/// captured PNG/GLB bytes by their original Kintara path.
final class OfficialCosmeticPack {
    static let shared = OfficialCosmeticPack()

    struct Entry: Decodable {
        let path: String
        let mime: String
        let sha256: String
        let offset: Int
        let length: Int
    }

    private struct Index: Decodable {
        let schema: Int
        let capturedAt: String
        let count: Int
        let entries: [Entry]
    }

    private struct Loaded {
        let data: Data
        let payloadBase: Int
        let index: Index
        let byPath: [String: Entry]
    }

    private static let expectedPackSHA256 =
        "778a423b59d9e5d6b098ceebb076355f4d03ab1638e14f12be3776cc7e58c8c5"
    private static let partCount = 6

    private let loaded: Loaded?

    private init() {
        loaded = Self.load()
    }

    /// Forces the complete 5.7 MB capture into the process memory.
    func preload() {
        _ = loaded?.data.count
    }

    var assetCount: Int { loaded?.index.count ?? 0 }
    var capturedAt: String? { loaded?.index.capturedAt }

    func contains(_ originalPath: String) -> Bool {
        loaded?.byPath[originalPath] != nil
    }

    func data(forPath originalPath: String) -> Data? {
        guard let loaded, let entry = loaded.byPath[originalPath] else { return nil }
        let start = loaded.payloadBase + entry.offset
        let end = start + entry.length
        guard start >= 0, end <= loaded.data.count, start < end else { return nil }
        return Data(loaded.data[start..<end])
    }

    func image(forPath originalPath: String) -> UIImage? {
        guard let data = data(forPath: originalPath) else { return nil }
        return UIImage(data: data)
    }

    /// Materializes one exact captured model/texture when a native loader needs a URL.
    /// The written bytes are content-addressed by the captured SHA-256.
    func localURL(forPath originalPath: String) -> URL? {
        guard let loaded, let entry = loaded.byPath[originalPath],
              let bytes = data(forPath: originalPath)
        else { return nil }

        let ext = (originalPath as NSString).pathExtension
        let base = String(entry.sha256.prefix(24))
        let name = ext.isEmpty ? base : base + "." + ext

        do {
            let root = try FileManager.default.url(
                for: .cachesDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true
            ).appendingPathComponent("KintTanyOfficialCosmetics", isDirectory: true)
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            let url = root.appendingPathComponent(name)
            if !FileManager.default.fileExists(atPath: url.path) {
                try bytes.write(to: url, options: .atomic)
            }
            return url
        } catch {
            return nil
        }
    }

    private static func load() -> Loaded? {
        var joined = Data()
        for number in 1...partCount {
            let ext = String(format: "part%02d", number)
            guard let url = Bundle.main.url(
                forResource: "KintaraOfficialCosmetics.pack",
                withExtension: ext
            ),
            let part = try? Data(contentsOf: url, options: [.mappedIfSafe])
            else { return nil }
            joined.append(part)
        }

        let digest = SHA256.hash(data: joined)
            .map { String(format: "%02x", $0) }
            .joined()
        guard digest == expectedPackSHA256 else { return nil }

        let magic = Data("KTCOS1\n".utf8)
        guard joined.count >= 11, joined.prefix(magic.count) == magic else { return nil }

        let lengthBytes = joined[7..<11]
        var indexLength = 0
        for byte in lengthBytes { indexLength = (indexLength << 8) | Int(byte) }

        let indexStart = 11
        let indexEnd = indexStart + indexLength
        guard indexLength > 0, indexEnd <= joined.count else { return nil }

        let indexData = Data(joined[indexStart..<indexEnd])
        guard let index = try? JSONDecoder().decode(Index.self, from: indexData),
              index.schema == 1,
              index.count == index.entries.count,
              index.count == 156
        else { return nil }

        var map: [String: Entry] = [:]
        map.reserveCapacity(index.entries.count)
        for entry in index.entries {
            map[entry.path] = entry
        }

        return Loaded(
            data: joined,
            payloadBase: indexEnd,
            index: index,
            byPath: map
        )
    }
}
