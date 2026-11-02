import Foundation
import XCTest
@testable import SpartanPort

final class PS4SELFPreparerTests: XCTestCase {
    func testReconstructsPlainSELFIntoLoadableELFImage() throws {
        let source = temporaryFile(plainSELF())
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: source)
            try? FileManager.default.removeItem(at: destination)
        }

        let report = try PS4SELFPreparer.prepare(from: source, to: destination)
        let prepared = try Data(contentsOf: destination)

        XCTAssertEqual(Array(prepared[0x1000..<0x1004]), Array("GAME".utf8))
        XCTAssertTrue(report.contains(where: { $0.contains("SELF reconstruído em ELF64") }))
        XCTAssertTrue(try PS4ELFInspector.inspect(destination).contains("✓ ELF64 little-endian"))
    }

    func testRefusesEncryptedSELFEntries() throws {
        let source = temporaryFile(plainSELF(entryProperties: 1 << 1))
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: source)
            try? FileManager.default.removeItem(at: destination)
        }
        XCTAssertThrowsError(try PS4SELFPreparer.prepare(from: source, to: destination)) { error in
            XCTAssertTrue(error.localizedDescription.contains("criptografados"))
        }
    }


    func testReadsPS4DynamicLibraryDependenciesFromRebuiltImage() throws {
        let source = temporaryFile(selfWithDynamicDependency())
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer {
            try? FileManager.default.removeItem(at: source)
            try? FileManager.default.removeItem(at: destination)
        }
        let report = try PS4SELFPreparer.prepare(from: source, to: destination)
        XCTAssertTrue(report.contains("Bibliotecas PS4 DT_NEEDED: 1"))
        XCTAssertTrue(report.contains("  • libc.prx"))
    }

    private func selfWithDynamicDependency() -> [UInt8] {
        let elfOffset = 0x120
        let loadPayloadOffset = 0x220
        let dynlibPayloadOffset = 0x230
        let dynlibSize = 0x80
        let payload = Array("GAME".utf8)

        var elf = [UInt8](repeating: 0, count: 64 + 3 * 56)
        elf.replaceSubrange(0..<4, with: [0x7f, 0x45, 0x4c, 0x46])
        elf[4] = 2; elf[5] = 1; elf[6] = 1
        write16(0xFE10, into: &elf, at: 16)
        write16(0x003e, into: &elf, at: 18)
        write64(0x144060, into: &elf, at: 24)
        write64(64, into: &elf, at: 32)
        write16(64, into: &elf, at: 52)
        write16(56, into: &elf, at: 54)
        write16(3, into: &elf, at: 56)

        // PT_LOAD
        write32(1, into: &elf, at: 64)
        write64(0x1000, into: &elf, at: 64 + 8)
        write64(4, into: &elf, at: 64 + 32)
        write64(4, into: &elf, at: 64 + 40)
        // PT_DYNAMIC, covered by PT_SCE_DYNLIBDATA
        write32(2, into: &elf, at: 120)
        write64(0x3040, into: &elf, at: 120 + 8)
        write64(48, into: &elf, at: 120 + 32)
        write64(48, into: &elf, at: 120 + 40)
        // PT_SCE_DYNLIBDATA
        write32(0x61000000, into: &elf, at: 176)
        write64(0x3000, into: &elf, at: 176 + 8)
        write64(UInt64(dynlibSize), into: &elf, at: 176 + 32)
        write64(UInt64(dynlibSize), into: &elf, at: 176 + 40)

        var dynlib = [UInt8](repeating: 0, count: dynlibSize)
        let name = Array("libc.prx".utf8) + [0]
        dynlib.replaceSubrange(0x19..<(0x19 + name.count), with: name)
        write64(0x61000035, into: &dynlib, at: 0x40) // DT_SCE_STRTAB
        write64(0x18, into: &dynlib, at: 0x48)
        write64(1, into: &dynlib, at: 0x50) // DT_NEEDED
        write64(1, into: &dynlib, at: 0x58)
        write64(0, into: &dynlib, at: 0x60) // DT_NULL
        write64(0, into: &dynlib, at: 0x68)

        let fileSize = dynlibPayloadOffset + dynlibSize
        var bytes = [UInt8](repeating: 0, count: fileSize)
        bytes.replaceSubrange(0..<4, with: [0x4f, 0x15, 0x3d, 0x1d])
        bytes[4] = 0; bytes[5] = 1; bytes[6] = 1; bytes[7] = 0x12
        write32(0x101, into: &bytes, at: 8)
        write16(UInt16(elfOffset), into: &bytes, at: 0x0c)
        write16(0x100, into: &bytes, at: 0x0e)
        write64(UInt64(fileSize), into: &bytes, at: 0x10)
        write16(2, into: &bytes, at: 0x18)
        write16(0x22, into: &bytes, at: 0x1a)
        // SELF entry for PT_LOAD
        write64(1 << 2, into: &bytes, at: 0x20)
        write64(UInt64(loadPayloadOffset), into: &bytes, at: 0x28)
        write64(4, into: &bytes, at: 0x30)
        write64(4, into: &bytes, at: 0x38)
        // SELF entry for PT_SCE_DYNLIBDATA
        write64(1 << 2, into: &bytes, at: 0x40)
        write64(UInt64(dynlibPayloadOffset), into: &bytes, at: 0x48)
        write64(UInt64(dynlibSize), into: &bytes, at: 0x50)
        write64(UInt64(dynlibSize), into: &bytes, at: 0x58)
        bytes.replaceSubrange(elfOffset..<(elfOffset + elf.count), with: elf)
        bytes.replaceSubrange(loadPayloadOffset..<(loadPayloadOffset + payload.count), with: payload)
        bytes.replaceSubrange(dynlibPayloadOffset..<(dynlibPayloadOffset + dynlib.count), with: dynlib)
        return bytes
    }

    private func plainSELF(entryProperties: UInt64 = 1 << 2) -> [UInt8] {
        let elfOffset = 0x120
        let payloadOffset = 0x200
        let payload = Array("GAME".utf8)
        var elf = [UInt8](repeating: 0, count: 120)
        elf.replaceSubrange(0..<4, with: [0x7f, 0x45, 0x4c, 0x46])
        elf[4] = 2; elf[5] = 1; elf[6] = 1
        write16(0xFE10, into: &elf, at: 16)
        write16(0x003e, into: &elf, at: 18)
        write64(0x144060, into: &elf, at: 24)
        write64(64, into: &elf, at: 32)
        write16(64, into: &elf, at: 52)
        write16(56, into: &elf, at: 54)
        write16(1, into: &elf, at: 56)
        write32(1, into: &elf, at: 64) // PT_LOAD
        write64(0x1000, into: &elf, at: 64 + 8)
        write64(UInt64(payload.count), into: &elf, at: 64 + 32)
        write64(UInt64(payload.count), into: &elf, at: 64 + 40)

        var bytes = [UInt8](repeating: 0, count: payloadOffset + payload.count)
        bytes.replaceSubrange(0..<4, with: [0x4f, 0x15, 0x3d, 0x1d])
        bytes[4] = 0; bytes[5] = 1; bytes[6] = 1; bytes[7] = 0x12
        write32(0x101, into: &bytes, at: 8)
        write16(UInt16(elfOffset), into: &bytes, at: 0x0c)
        write16(0x100, into: &bytes, at: 0x0e)
        write64(UInt64(bytes.count), into: &bytes, at: 0x10)
        write16(1, into: &bytes, at: 0x18)
        write16(0x22, into: &bytes, at: 0x1a)
        write64(entryProperties, into: &bytes, at: 0x20)
        write64(UInt64(payloadOffset), into: &bytes, at: 0x28)
        write64(UInt64(payload.count), into: &bytes, at: 0x30)
        write64(UInt64(payload.count), into: &bytes, at: 0x38)
        bytes.replaceSubrange(elfOffset..<(elfOffset + elf.count), with: elf)
        bytes.replaceSubrange(payloadOffset..<(payloadOffset + payload.count), with: payload)
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
