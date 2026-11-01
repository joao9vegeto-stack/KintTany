import Foundation
import XCTest
@testable import SpartanPort

final class PS4ParamSFOTests: XCTestCase {
    func testReadsTitleIDAndVersion() throws {
        let url = temporarySFO()
        defer { try? FileManager.default.removeItem(at: url) }
        let info = try PS4ParamSFO.load(from: url)
        XCTAssertEqual(info.title, "God of War III")
        XCTAssertEqual(info.titleID, "CUSA01715")
        XCTAssertEqual(info.contentVersion, "01.00")
    }

    func testRejectsTruncatedAndInvalidSFO() throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try Data([0, 1, 2, 3]).write(to: url)
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ParamSFO.load(from: url))
    }

    private func temporarySFO() -> URL {
        let entries: [(String, String)] = [("TITLE", "God of War III"), ("TITLE_ID", "CUSA01715"), ("APP_VER", "01.00")]
        var keys = Data()
        var values = Data()
        var records = Data()
        for (key, value) in entries {
            let keyOffset = UInt16(keys.count)
            keys.append(contentsOf: key.utf8); keys.append(0)
            let valueData = Data(value.utf8) + Data([0])
            var record = Data()
            append16(keyOffset, to: &record); append16(0x0204, to: &record)
            append32(UInt32(valueData.count), to: &record); append32(UInt32(valueData.count), to: &record)
            append32(UInt32(values.count), to: &record)
            records.append(record); values.append(valueData)
        }
        let keyTable = 20 + records.count
        let dataTable = keyTable + keys.count
        var result = Data([0x00, 0x50, 0x53, 0x46])
        append32(0x00000101, to: &result)
        append32(UInt32(keyTable), to: &result); append32(UInt32(dataTable), to: &result)
        append32(UInt32(entries.count), to: &result)
        result.append(records); result.append(keys); result.append(values)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try! result.write(to: url)
        return url
    }

    private func append16(_ value: UInt16, to data: inout Data) {
        data.append(UInt8(value & 0xff)); data.append(UInt8(value >> 8))
    }
    private func append32(_ value: UInt32, to data: inout Data) {
        for shift in stride(from: 0, through: 24, by: 8) { data.append(UInt8((value >> shift) & 0xff)) }
    }
}
