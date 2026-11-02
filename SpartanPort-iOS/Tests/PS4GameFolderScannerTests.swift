import Foundation
import XCTest
@testable import SpartanPort

final class PS4GameFolderScannerTests: XCTestCase {
    func testFindsDirectAndNestedGameFolders() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let direct = root.appendingPathComponent("Direct", isDirectory: true)
        let nested = root.appendingPathComponent("Downloads/GoWIII", isDirectory: true)
        try makeGameFolder(direct)
        try makeGameFolder(nested)
        let found = PS4GameFolderScanner.findGameFolders(in: root, maxDepth: 3)
        XCTAssertEqual(Set(found.map(\.lastPathComponent)), Set(["Direct", "GoWIII"]))
    }

    func testRejectsFolderMissingParamSFO() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(at: root.appendingPathComponent("sce_sys", isDirectory: true), withIntermediateDirectories: true)
        try Data([1, 2, 3]).write(to: root.appendingPathComponent("eboot.bin"))
        XCTAssertFalse(PS4GameFolderScanner.isGameFolder(root))
    }

    private func makeGameFolder(_ folder: URL) throws {
        try FileManager.default.createDirectory(at: folder.appendingPathComponent("sce_sys", isDirectory: true), withIntermediateDirectories: true)
        try Data([1, 2, 3]).write(to: folder.appendingPathComponent("eboot.bin"))
        try Data([0, 0x50, 0x53, 0x46]).write(to: folder.appendingPathComponent("sce_sys/param.sfo"))
    }
}