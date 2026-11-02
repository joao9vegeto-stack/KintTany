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
        XCTAssertTrue(report.contains(where: { $0.contains("PT_LOAD") }))
    }

    func testRecognizesPS4SELFWithEmbeddedELFAtMetadataBoundary() throws {
        let url = temporaryFile(selfContainer(elf: validELF(), entryCount: 8))
        defer { try? FileManager.default.removeItem(at: url) }
        let report = try PS4ELFInspector.inspect(url)
        XCTAssertTrue(report.contains("✓ Contêiner PS4 SELF reconhecido"))
        XCTAssertTrue(report.contains("ELF interno: offset 0x120"))
        XCTAssertTrue(report.contains(where: { $0.contains("ET_SCE_DYNEXEC") }))
        XCTAssertTrue(report.contains(where: { $0.contains("0 criptografadas • 0 compactadas") }))
        XCTAssertTrue(report.contains(where: { $0.contains("não descriptografa") }))
    }

    func testRecognizesSCESELFContainerMagic() throws {
        let magic: [UInt8] = [0x53, 0x43, 0x45, 0x00]
        let url = temporaryFile(selfContainer(elf: validELF(), entryCount: 8, magic: magic))
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertTrue(try PS4ELFInspector.inspect(url).contains("✓ Contêiner SCE SELF reconhecido"))
    }

    func testRejectsSELFWithoutEmbeddedELF() throws {
        let url = temporaryFile(selfContainer(elf: nil, entryCount: 8))
        defer { try? FileManager.default.removeItem(at: url) }
        XCTAssertThrowsError(try PS4ELFInspector.inspect(url)) { error in
            XCTAssertTrue(error.localizedDescription.contains("SELF"))
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

    func testRejectsLoadSegmentOutsideFile() throws {
        var bytes = validELF()
        write64(4096, into: &bytes, at: 64 + 8)
        write64(32, into: &bytes, at: 64 + 32)
        write64(32, into: &bytes, at: 64 + 40)
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
        write16(0xFE10, into: &bytes, at: 16)
        write16(0x003e, into: &bytes, at: 18)
        write64(0x0000000000144060, into: &bytes, at: 24)
        write64(64, into: &bytes, at: 32)
        write16(64, into: &bytes, at: 52)
        write16(56, into: &bytes, at: 54)
        write16(1, into: &bytes, at: 56)
        write32(1, into: &bytes, at: 64)
        write64(0, into: &bytes, at: 64 + 8)
        write64(0, into: &bytes, at: 64 + 32)
        write64(0, into: &bytes, at: 64 + 40)
        return bytes
    }

    private func selfContainer(elf: [UInt8]?, entryCount: UInt16, magic: [UInt8] = [0x4f, 0x15, 0x3d, 0x1d]) -> [UInt8] {
        let elfOffset = 0x20 + Int(entryCount) * 0x20
        var bytes = [UInt8](repeating: 0, count: elfOffset + (elf?.count ?? 0))
        bytes.replaceSubrange(0..<4, with: magic)
        write16(UInt16(elfOffset), into: &bytes, at: 0x0c)
        write16(UInt16(elfOffset - 0x20), into: &bytes, at: 0x0e)
        write64(UInt64(bytes.count), into: &bytes, at: 0x10)
        write16(entryCount, into: &bytes, at: 0x18)
        if let elf { bytes.replaceSubrange(elfOffset..<(elfOffset + elf.count), with: elf) }
        return bytes
    }

    private func temporaryFile(_ bytes: [UInt8]) -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try! Data(bytes).write(to: url)
        return url
    }
    private func write16(_ value: UInt16, into bytes: inout [UInt8], at offset: Int) {
        bytes[offset] = UInt8(value & 0xff); bytes[offset + 1] = UInt8((value >> 8) & 0xff)
    }
    private func write32(_ value: UInt32, into bytes: inout [UInt8], at offset: Int) {
        for index in 0..<4 { bytes[offset + index] = UInt8((value >> (index * 8)) & 0xff) }
    }
    private func write64(_ value: UInt64, into bytes: inout [UInt8], at offset: Int) {
        for index in 0..<8 { bytes[offset + index] = UInt8((value >> (index * 8)) & 0xff) }
    }
}
