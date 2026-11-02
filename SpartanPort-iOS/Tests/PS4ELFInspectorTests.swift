import Foundation
import XCTest
@testable import SpartanPort

final class PS4ELFInspectorTests: XCTestCase {
    func testAcceptsWellFormedELF64X8664Header() throws {
        let url = temporaryFile(validELF())
        defer { try? FileManager.default.removeItem(at: url) }
        let report = try PS4ELFInspector.inspect(url)
        XCTAssertTrue(report.contains("✓ ELF64 little-endian"))
        XCTAssertTrue(report.contains("✓ Arquitetura x86-64 (EM_X86_64)"))
    }

    func testIdentifiesPS4SELFContainerWithoutClaimingToDecryptIt() throws {
        let url = temporaryFile([0x53, 0x43, 0x45, 0x00] + [UInt8](repeating: 0, count: 124))
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ELFInspector.inspect(url)) { error in
            XCTAssertTrue(error.localizedDescription.contains("SELF"))
            XCTAssertTrue(error.localizedDescription.contains("não descriptografa"))
        }
    }

    func testRejectsNonELFOrUnknownContainer() throws {
        let url = temporaryFile([UInt8](repeating: 0, count: 128))
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ELFInspector.inspect(url))
    }

    func testRejectsProgramHeaderTableOutsideFile() throws {
        var bytes = validELF()
        write64(4096, into: &bytes, at: 32)
        let url = temporaryFile(bytes)
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ELFInspector.inspect(url))
    }

    func testRejectsTruncatedELFHeader() throws {
        let url = temporaryFile([0x7f, 0x45, 0x4c, 0x46, 2, 1, 1])
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ELFInspector.inspect(url))
    }

    private func validELF() -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: 120)
        bytes.replaceSubrange(0..<4, with: [0x7f, 0x45, 0x4c, 0x46])
        bytes[4] = 2; bytes[5] = 1; bytes[6] = 1
        write16(0x003e, into: &bytes, at: 18)
        write64(0x0000000100400000, into: &bytes, at: 24)
        write64(64, into: &bytes, at: 32)
        write16(64, into: &bytes, at: 52)
        write16(56, into: &bytes, at: 54)
        write16(1, into: &bytes, at: 56)
        return bytes
    }

    private func temporaryFile(_ bytes: [UInt8]) -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try! Data(bytes).write(to: url)
        return url
    }

    private func write16(_ value: UInt16, into bytes: inout [UInt8], at offset: Int) {
        bytes[offset] = UInt8(value & 0xff)
        bytes[offset + 1] = UInt8((value >> 8) & 0xff)
    }

    private func write64(_ value: UInt64, into bytes: inout [UInt8], at offset: Int) {
        for index in 0..<8 { bytes[offset + index] = UInt8((value >> (index * 8)) & 0xff) }
    }
}
