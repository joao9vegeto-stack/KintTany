import Foundation

enum PS4ELFInspectorError: LocalizedError {
    case truncatedHeader, notELF, not64Bit, notLittleEndian
    case unsupportedMachine(UInt16), unsupportedELFType(UInt16)
    case invalidProgramHeaderTable, invalidLoadSegment, invalidSELFHeader, selfWithoutEmbeddedELF

    var errorDescription: String? {
        switch self {
        case .truncatedHeader: return "eboot.bin é menor que o cabeçalho ELF mínimo."
        case .notELF: return "eboot.bin não contém ELF nem um contêiner SELF PS4 reconhecível."
        case .not64Bit: return "O executável não usa ELF de 64 bits."
        case .notLittleEndian: return "O ELF não está em little-endian."
        case .unsupportedMachine(let machine):
            return String(format: "Arquitetura ELF não suportada (e_machine=0x%04x); esperado x86-64.", machine)
        case .unsupportedELFType(let type):
            return String(format: "Tipo ELF não suportado (e_type=0x%04x).", type)
        case .invalidProgramHeaderTable:
            return "A tabela de segmentos ELF está ausente, malformada ou fora do arquivo."
        case .invalidLoadSegment:
            return "Um segmento ELF possui tamanhos ou offsets inconsistentes."
        case .invalidSELFHeader:
            return "O cabeçalho ou a tabela de segmentos SELF possui tamanhos/offsets inválidos."
        case .selfWithoutEmbeddedELF:
            return "Contêiner SELF PS4 reconhecido, mas não foi encontrado um ELF interno íntegro. O conteúdo pode estar criptografado, compactado ou usar outro layout."
        }
    }
}

/// Structural inspection only. It does not decrypt SELF, relocate segments,
/// resolve PS4 imports, generate ARM64 code, or execute the game.
enum PS4ELFInspector {
    private static let elfMagic: [UInt8] = [0x7f, 0x45, 0x4c, 0x46]
    private static let ps4SelfMagic: [UInt8] = [0x4f, 0x15, 0x3d, 0x1d]
    private static let sceSelfMagic: [UInt8] = [0x53, 0x43, 0x45, 0x00]
    private static let selfHeaderSize = 0x20
    private static let selfEntrySize = 0x20
    private static let maxSelfMetadataEntries = 1024
    private static let maxEmbeddedELFSearch = 0x10000

    private struct SELFEntry {
        let properties: UInt64
        let offset: UInt64
        let storedSize: UInt64
        let unpackedSize: UInt64
        var isEncrypted: Bool { (properties & (1 << 1)) != 0 }
        var isSigned: Bool { (properties & (1 << 2)) != 0 }
        var isCompressed: Bool { (properties & (1 << 3)) != 0 }
        var hasBlocks: Bool { (properties & (1 << 11)) != 0 }
    }

    static func inspect(_ executableURL: URL) throws -> [String] {
        let data = try Data(contentsOf: executableURL, options: .mappedIfSafe)
        guard data.count >= 4 else { throw PS4ELFInspectorError.truncatedHeader }
        let magic = Array(data[0..<4])
        if magic == elfMagic { return try inspectELF(data, baseOffset: 0, container: nil) }
        guard magic == ps4SelfMagic || magic == sceSelfMagic else { throw PS4ELFInspectorError.notELF }
        guard data.count >= selfHeaderSize else { throw PS4ELFInspectorError.truncatedHeader }

        let headerSize = Int(read16(data, at: 0x0c))
        let metadataSize = Int(read16(data, at: 0x0e))
        let declaredFileSize = read64(data, at: 0x10)
        let entryCount = Int(read16(data, at: 0x18))
        guard entryCount > 0, entryCount <= maxSelfMetadataEntries else {
            throw PS4ELFInspectorError.invalidSELFHeader
        }
        let (tableBytes, overflow1) = entryCount.multipliedReportingOverflow(by: selfEntrySize)
        let (metadataEnd, overflow2) = selfHeaderSize.addingReportingOverflow(tableBytes)
        guard !overflow1, !overflow2, metadataEnd <= data.count,
              headerSize >= metadataEnd, headerSize <= data.count,
              metadataSize <= headerSize, declaredFileSize >= UInt64(headerSize),
              declaredFileSize <= UInt64(data.count) else {
            throw PS4ELFInspectorError.invalidSELFHeader
        }

        var selfEntries: [SELFEntry] = []
        for index in 0..<entryCount {
            let entryOffset = selfHeaderSize + index * selfEntrySize
            let entry = SELFEntry(
                properties: read64(data, at: entryOffset),
                offset: read64(data, at: entryOffset + 8),
                storedSize: read64(data, at: entryOffset + 16),
                unpackedSize: read64(data, at: entryOffset + 24)
            )
            let (entryEnd, entryOverflow) = entry.offset.addingReportingOverflow(entry.storedSize)
            guard !entryOverflow, entryEnd <= declaredFileSize else {
                throw PS4ELFInspectorError.invalidSELFHeader
            }
            selfEntries.append(entry)
        }

        let searchEnd = min(data.count - 64, max(metadataEnd, maxEmbeddedELFSearch))
        guard metadataEnd <= searchEnd else { throw PS4ELFInspectorError.selfWithoutEmbeddedELF }
        for offset in metadataEnd...searchEnd {
            guard matches(data, magic: elfMagic, at: offset) else { continue }
            if var report = try? inspectELF(data, baseOffset: offset,
                                            container: magic == ps4SelfMagic ? "PS4 SELF" : "SCE SELF") {
                let encrypted = selfEntries.filter(\.isEncrypted).count
                let compressed = selfEntries.filter(\.isCompressed).count
                let signed = selfEntries.filter(\.isSigned).count
                let blocked = selfEntries.filter(\.hasBlocks).count
                report.insert(String(format: "SELF: %d entradas • header 0x%x • metadata 0x%x",
                                     entryCount, headerSize, metadataSize), at: 1)
                report.insert("SELF flags: \(encrypted) criptografadas • \(compressed) compactadas • \(signed) assinadas • \(blocked) com blocos",
                              at: 2)
                if encrypted == 0 && compressed == 0 {
                    report.insert("✓ SELF declara segmentos sem criptografia/compactação", at: 3)
                } else {
                    report.insert("⚠ SELF requer etapa de descriptografia/descompactação", at: 3)
                }
                return report
            }
        }
        throw PS4ELFInspectorError.selfWithoutEmbeddedELF
    }

    private static func inspectELF(_ data: Data, baseOffset: Int, container: String?) throws -> [String] {
        guard baseOffset >= 0, baseOffset <= data.count - 64 else {
            throw PS4ELFInspectorError.truncatedHeader
        }
        guard matches(data, magic: elfMagic, at: baseOffset) else { throw PS4ELFInspectorError.notELF }
        guard data[baseOffset + 4] == 2 else { throw PS4ELFInspectorError.not64Bit }
        guard data[baseOffset + 5] == 1 else { throw PS4ELFInspectorError.notLittleEndian }
        guard data[baseOffset + 6] == 1 else { throw PS4ELFInspectorError.notELF }

        let type = read16(data, at: baseOffset + 16)
        guard type == 2 || type == 0xFE00 || type == 0xFE10 || type == 0xFE18 else {
            throw PS4ELFInspectorError.unsupportedELFType(type)
        }
        let machine = read16(data, at: baseOffset + 18)
        guard machine == 0x003e else { throw PS4ELFInspectorError.unsupportedMachine(machine) }

        let entry = read64(data, at: baseOffset + 24)
        let phoff = read64(data, at: baseOffset + 32)
        let headerSize = read16(data, at: baseOffset + 52)
        let phEntrySize = read16(data, at: baseOffset + 54)
        let phCount = read16(data, at: baseOffset + 56)
        guard headerSize >= 64, phCount > 0, phCount <= 1024, phEntrySize >= 56 else {
            throw PS4ELFInspectorError.invalidProgramHeaderTable
        }

        let (tableBytes, mulOverflow) = UInt64(phEntrySize).multipliedReportingOverflow(by: UInt64(phCount))
        let (tableRelativeEnd, addOverflow) = phoff.addingReportingOverflow(tableBytes)
        let (tableAbsoluteEnd, baseOverflow) = UInt64(baseOffset).addingReportingOverflow(tableRelativeEnd)
        guard !mulOverflow, !addOverflow, !baseOverflow, tableAbsoluteEnd <= UInt64(data.count) else {
            throw PS4ELFInspectorError.invalidProgramHeaderTable
        }

        var loadSegments = 0
        for index in 0..<Int(phCount) {
            let headerOffset = baseOffset + Int(phoff) + index * Int(phEntrySize)
            let segmentType = read32(data, at: headerOffset)
            let fileOffset = read64(data, at: headerOffset + 8)
            let fileSize = read64(data, at: headerOffset + 32)
            let memorySize = read64(data, at: headerOffset + 40)
            if segmentType == 1 {
                guard fileSize <= memorySize else { throw PS4ELFInspectorError.invalidLoadSegment }
                loadSegments += 1
                // SELF p_offset addresses the reconstructed ELF, not the
                // container bytes. SELF payload ranges are checked separately.
                let (relativeEnd, overflow1) = fileOffset.addingReportingOverflow(fileSize)
                guard !overflow1 else { throw PS4ELFInspectorError.invalidLoadSegment }
                if container == nil {
                    let (absoluteEnd, overflow2) = UInt64(baseOffset).addingReportingOverflow(relativeEnd)
                    guard !overflow2, absoluteEnd <= UInt64(data.count) else {
                        throw PS4ELFInspectorError.invalidLoadSegment
                    }
                }
            }
        }
        guard loadSegments > 0 else { throw PS4ELFInspectorError.invalidProgramHeaderTable }

        var report: [String] = []
        if let container {
            report.append("✓ Contêiner \(container) reconhecido")
            report.append(String(format: "ELF interno: offset 0x%llx", UInt64(baseOffset)))
            report.append("⚠ Inspeção estrutural; não descriptografa nem extrai segmentos SELF")
        }
        report.append("✓ ELF64 little-endian")
        report.append("✓ Arquitetura x86-64 (EM_X86_64)")
        let typeName: String
        switch type {
        case 0xFE00: typeName = "ET_SCE_EXEC"
        case 0xFE10: typeName = "ET_SCE_DYNEXEC"
        case 0xFE18: typeName = "ET_SCE_DYNAMIC"
        default: typeName = "ET_EXEC"
        }
        report.append(String(format: "Tipo ELF: 0x%04x (%@)", type, typeName))
        report.append(String(format: "Entry point: 0x%016llx", entry))
        report.append("Program headers: \(phCount) • PT_LOAD: \(loadSegments) • tamanhos validados")
        return report
    }

    private static func matches(_ data: Data, magic: [UInt8], at offset: Int) -> Bool {
        guard offset >= 0, offset <= data.count - magic.count else { return false }
        for index in magic.indices where data[offset + index] != magic[index] { return false }
        return true
    }

    private static func read16(_ data: Data, at offset: Int) -> UInt16 {
        UInt16(data[offset]) | (UInt16(data[offset + 1]) << 8)
    }
    private static func read32(_ data: Data, at offset: Int) -> UInt32 {
        UInt32(data[offset]) | (UInt32(data[offset + 1]) << 8)
            | (UInt32(data[offset + 2]) << 16) | (UInt32(data[offset + 3]) << 24)
    }
    private static func read64(_ data: Data, at offset: Int) -> UInt64 {
        var value: UInt64 = 0
        for index in 0..<8 { value |= UInt64(data[offset + index]) << (index * 8) }
        return value
    }
}
