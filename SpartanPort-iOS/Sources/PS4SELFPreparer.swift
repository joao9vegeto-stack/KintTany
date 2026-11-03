import Foundation

enum PS4SELFPreparerError: LocalizedError {
    case unsupportedEncryptedOrCompressedSegments
    case invalidSELFEntryTable
    case embeddedELFNotFound
    case invalidProgramHeaderTable
    case outputTooLarge
    case ambiguousSegmentMapping(UInt64)
    case missingSegmentData(UInt64)

    var errorDescription: String? {
        switch self {
        case .unsupportedEncryptedOrCompressedSegments:
            return "O SELF contém segmentos criptografados ou compactados; esta preparação não tenta descriptografá-los."
        case .invalidSELFEntryTable:
            return "A tabela SELF não pode ser usada para reconstruir o ELF."
        case .embeddedELFNotFound:
            return "O ELF interno não foi localizado dentro do contêiner SELF."
        case .invalidProgramHeaderTable:
            return "A tabela de program headers não é válida para reconstrução."
        case .outputTooLarge:
            return "O tamanho de ELF reconstruído excede o limite de segurança de 512 MiB."
        case .ambiguousSegmentMapping(let size):
            return String(format: "Mais de uma entrada SELF corresponde ao segmento de tamanho 0x%llx.", size)
        case .missingSegmentData(let size):
            return String(format: "Não há entrada SELF para reconstruir o segmento de tamanho 0x%llx.", size)
        }
    }
}

/// Rebuilds an ordinary ELF file from plaintext PS4 SELF segment entries.
/// This is preparation only: the result remains x86-64 and is not executable
/// on iOS until a real AOT translator and PS4 runtime are integrated.
enum PS4SELFPreparer {
    private static let elfMagic: [UInt8] = [0x7f, 0x45, 0x4c, 0x46]
    private static let ps4SelfMagic: [UInt8] = [0x4f, 0x15, 0x3d, 0x1d]
    private static let sceSelfMagic: [UInt8] = [0x53, 0x43, 0x45, 0x00]
    private static let maxOutputSize: UInt64 = 512 * 1024 * 1024
    private static let selfHeaderSize = 0x20
    private static let selfEntrySize = 0x20

    private struct SELFEntry {
        let index: Int
        let properties: UInt64
        let offset: UInt64
        let storedSize: UInt64
        let unpackedSize: UInt64
        var encrypted: Bool { (properties & (1 << 1)) != 0 }
        var compressed: Bool { (properties & (1 << 3)) != 0 }
        // SELF entry properties encode the PT_LOAD program-header index in bits 20...35.
        // Bit 11 marks an entry that carries blocks for that segment (PS4Recomp elfloader contract).
        var hasBlocks: Bool { (properties & (1 << 11)) != 0 }
        var segmentIndex: Int { Int((properties >> 20) & 0xffff) }
    }

    private struct ProgramHeader {
        let index: Int
        let type: UInt32
        let offset: UInt64
        let fileSize: UInt64
        let memorySize: UInt64
    }

    static func prepare(from sourceURL: URL, to destinationURL: URL) throws -> [String] {
        let data = try Data(contentsOf: sourceURL, options: .mappedIfSafe)
        let validation = try PS4ELFInspector.inspect(sourceURL)
        guard data.count >= 4 else { throw PS4SELFPreparerError.embeddedELFNotFound }
        let magic = Array(data[0..<4])

        if magic == elfMagic {
            try FileManager.default.createDirectory(at: destinationURL.deletingLastPathComponent(),
                                                     withIntermediateDirectories: true)
            try data.write(to: destinationURL, options: .atomic)
            return validation + ["✓ ELF existente copiado para a área preparada",
                                  "Saída: \(destinationURL.lastPathComponent)"]
        }

        guard magic == ps4SelfMagic || magic == sceSelfMagic,
              data.count >= selfHeaderSize else {
            throw PS4SELFPreparerError.invalidSELFEntryTable
        }

        let headerSize = Int(read16(data, at: 0x0c))
        let declaredFileSize = read64(data, at: 0x10)
        let entryCount = Int(read16(data, at: 0x18))
        guard entryCount > 0, entryCount <= 1024 else {
            throw PS4SELFPreparerError.invalidSELFEntryTable
        }
        let (tableBytes, mulOverflow) = entryCount.multipliedReportingOverflow(by: selfEntrySize)
        let (metadataEnd, addOverflow) = selfHeaderSize.addingReportingOverflow(tableBytes)
        guard !mulOverflow, !addOverflow, metadataEnd <= data.count,
              headerSize >= metadataEnd, headerSize <= data.count,
              declaredFileSize >= UInt64(headerSize), declaredFileSize <= UInt64(data.count) else {
            throw PS4SELFPreparerError.invalidSELFEntryTable
        }

        var entries: [SELFEntry] = []
        for index in 0..<entryCount {
            let offset = selfHeaderSize + index * selfEntrySize
            let entry = SELFEntry(
                index: index,
                properties: read64(data, at: offset),
                offset: read64(data, at: offset + 8),
                storedSize: read64(data, at: offset + 16),
                unpackedSize: read64(data, at: offset + 24)
            )
            let (end, overflow) = entry.offset.addingReportingOverflow(entry.storedSize)
            guard !overflow, end <= declaredFileSize else {
                throw PS4SELFPreparerError.invalidSELFEntryTable
            }
            entries.append(entry)
        }
        guard !entries.contains(where: { $0.encrypted || $0.compressed }) else {
            throw PS4SELFPreparerError.unsupportedEncryptedOrCompressedSegments
        }

        let elfOffset = try locateEmbeddedELF(data, after: metadataEnd)
        let phoff = read64(data, at: elfOffset + 32)
        guard phoff <= UInt64(Int.max) else { throw PS4SELFPreparerError.invalidProgramHeaderTable }
        let phEntrySize = Int(read16(data, at: elfOffset + 54))
        let phCount = Int(read16(data, at: elfOffset + 56))
        guard phEntrySize >= 56, phCount > 0, phCount <= 1024 else {
            throw PS4SELFPreparerError.invalidProgramHeaderTable
        }
        let (phTableBytes, phMulOverflow) = phEntrySize.multipliedReportingOverflow(by: phCount)
        let (phTableStart, phAddOverflow) = elfOffset.addingReportingOverflow(Int(phoff))
        let (phTableEnd, phEndOverflow) = phTableStart.addingReportingOverflow(phTableBytes)
        guard !phMulOverflow, !phAddOverflow, !phEndOverflow,
              phTableEnd <= data.count else {
            throw PS4SELFPreparerError.invalidProgramHeaderTable
        }

        var programHeaders: [ProgramHeader] = []
        var outputSize = UInt64(64 + phTableBytes)
        for index in 0..<phCount {
            let offset = phTableStart + index * phEntrySize
            let type = read32(data, at: offset)
            let segmentOffset = read64(data, at: offset + 8)
            let fileSize = read64(data, at: offset + 32)
            let memorySize = read64(data, at: offset + 40)
            if type == 1 && fileSize > memorySize {
                throw PS4SELFPreparerError.invalidProgramHeaderTable
            }
            if fileSize > 0 {
                let (end, overflow) = segmentOffset.addingReportingOverflow(fileSize)
                guard !overflow, end <= maxOutputSize else { throw PS4SELFPreparerError.outputTooLarge }
                outputSize = max(outputSize, end)
            }
            programHeaders.append(ProgramHeader(index: index, type: type, offset: segmentOffset,
                                                 fileSize: fileSize, memorySize: memorySize))
        }
        guard outputSize <= maxOutputSize, outputSize <= UInt64(Int.max) else {
            throw PS4SELFPreparerError.outputTooLarge
        }

        var output = Data(repeating: 0, count: Int(outputSize))
        output.replaceSubrange(0..<64, with: data[elfOffset..<(elfOffset + 64)])
        output.replaceSubrange(64..<(64 + phTableBytes), with: data[phTableStart..<phTableEnd])

        var usedEntries = Set<Int>()
        var mappedRanges: [Range<UInt64>] = []

        func isCovered(_ header: ProgramHeader) -> Bool {
            let end = header.offset + header.fileSize
            return mappedRanges.contains { $0.lowerBound <= header.offset && $0.upperBound >= end }
        }

        func place(_ header: ProgramHeader, bytes: Data) throws {
            guard UInt64(bytes.count) == header.fileSize else {
                throw PS4SELFPreparerError.missingSegmentData(header.fileSize)
            }
            let end = header.offset + header.fileSize
            guard end <= UInt64(output.count) else { throw PS4SELFPreparerError.outputTooLarge }
            output.replaceSubrange(Int(header.offset)..<Int(end), with: bytes)
            mappedRanges.append(header.offset..<end)
        }

        func placeFromEntry(_ header: ProgramHeader, allowFooter: Bool = false) throws {
            // Never associate a SELF payload with a PT_LOAD merely because the sizes match.
            // Retail SELF files can contain several equal-sized segments; the segment index
            // encoded in properties is the authoritative mapping (same rule as upstream PS4Recomp).
            let candidates = entries.filter {
                !usedEntries.contains($0.index) &&
                $0.hasBlocks &&
                $0.segmentIndex == header.index &&
                !$0.encrypted && !$0.compressed
            }
            if candidates.count > 1 {
                throw PS4SELFPreparerError.ambiguousSegmentMapping(header.fileSize)
            }
            if let entry = candidates.first {
                guard entry.storedSize >= header.fileSize,
                      entry.unpackedSize >= header.fileSize,
                      entry.offset <= UInt64(data.count),
                      entry.storedSize <= UInt64(data.count) - entry.offset else {
                    throw PS4SELFPreparerError.missingSegmentData(header.fileSize)
                }
                let start = Int(entry.offset)
                let end = start + Int(header.fileSize)
                try place(header, bytes: data.subdata(in: start..<end))
                usedEntries.insert(entry.index)
                return
            }

            // Some non-loadable ELF views (PT_DYNAMIC / SCE metadata) are already
            // represented inside the embedded ELF. Copy only when the complete range
            // is actually present; never read past the SELF container.
            let (embeddedStart, startOverflow) = UInt64(elfOffset).addingReportingOverflow(header.offset)
            let (embeddedEnd, endOverflow) = embeddedStart.addingReportingOverflow(header.fileSize)
            if !startOverflow, !endOverflow, embeddedEnd <= UInt64(data.count) {
                let start = Int(embeddedStart)
                let end = Int(embeddedEnd)
                try place(header, bytes: data.subdata(in: start..<end))
                return
            }

            if allowFooter {
                let footerStart = Int(declaredFileSize)
                if footerStart <= data.count {
                    let footer = data.subdata(in: footerStart..<data.count)
                    if UInt64(footer.count) == header.fileSize {
                        try place(header, bytes: footer)
                        return
                    }
                }
            }
            throw PS4SELFPreparerError.missingSegmentData(header.fileSize)
        }

        // First materialize the actual loadable memory segments.
        for header in programHeaders where header.type == 1 && header.fileSize > 0 {
            try placeFromEntry(header)
        }

        // PS4-specific data outside PT_LOAD is stored in additional SELF entries
        // (dynamic-link metadata, comment and library-version records).
        let standaloneTypes: Set<UInt32> = [0x61000000, 0x6fffff00, 0x6fffff01]
        for header in programHeaders where standaloneTypes.contains(header.type) && header.fileSize > 0 {
            if !isCovered(header) {
                try placeFromEntry(header, allowFooter: header.type == 0x6fffff01)
            }
        }

        // Other program headers are often views into a PT_LOAD or SCE_DYNLIBDATA
        // range. Only copy a separate SELF entry when no mapped segment covers it.
        for header in programHeaders where header.fileSize > 0 && !isCovered(header) {
            try placeFromEntry(header, allowFooter: header.type == 0x6fffff01)
        }

        for header in programHeaders where header.fileSize > 0 && !isCovered(header) {
            throw PS4SELFPreparerError.missingSegmentData(header.fileSize)
        }

        try FileManager.default.createDirectory(at: destinationURL.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        try output.write(to: destinationURL, options: .atomic)

        let loadCount = programHeaders.filter { $0.type == 1 && $0.fileSize > 0 }.count
        let standaloneCount = programHeaders.filter { standaloneTypes.contains($0.type) && $0.fileSize > 0 }.count
        let dependencies = dynamicDependencies(in: output, programHeaders: programHeaders)
        var result = validation + [
            "✓ SELF reconstruído em ELF64 x86-64",
            "Segmentos PT_LOAD: \(loadCount) • segmentos SCE auxiliares: \(standaloneCount)",
            "Tamanho ELF preparado: \(output.count) bytes",
            "Saída: \(destinationURL.lastPathComponent)",
            "⚠ O ELF preparado ainda requer AOT x86-64 → ARM64 e runtime PS4"
        ]
        if !dependencies.isEmpty {
            result.append("Bibliotecas PS4 DT_NEEDED: \(dependencies.count)")
            result.append(contentsOf: dependencies.map { "  • \($0)" })
        }
        return result
    }

    private static func dynamicDependencies(in elf: Data, programHeaders: [ProgramHeader]) -> [String] {
        guard let dynamic = programHeaders.first(where: { $0.type == 2 && $0.fileSize >= 16 }),
              let dynlib = programHeaders.first(where: { $0.type == 0x61000000 && $0.fileSize > 0 }) else {
            return []
        }
        let dynamicEnd = dynamic.offset + dynamic.fileSize
        let dynlibEnd = dynlib.offset + dynlib.fileSize
        guard dynamicEnd <= UInt64(elf.count), dynlibEnd <= UInt64(elf.count) else { return [] }

        var stringTableOffset: UInt64?
        var neededOffsets: [UInt64] = []
        var cursor = dynamic.offset
        while cursor + 16 <= dynamicEnd {
            let tag = Int64(bitPattern: read64(elf, at: Int(cursor)))
            let value = read64(elf, at: Int(cursor + 8))
            if tag == 0 { break }
            if tag == 1 { neededOffsets.append(value) } // DT_NEEDED
            if tag == 0x61000035 { stringTableOffset = value } // DT_SCE_STRTAB
            cursor += 16
        }
        guard let stringTableOffset,
              stringTableOffset < dynlib.fileSize else { return [] }
        let stringTableStart = dynlib.offset + stringTableOffset
        var libraries: [String] = []
        for nameOffset in neededOffsets {
            let (start, overflow) = stringTableStart.addingReportingOverflow(nameOffset)
            guard !overflow, start < dynlibEnd else { continue }
            var bytes: [UInt8] = []
            var index = start
            while index < dynlibEnd {
                let byte = elf[Int(index)]
                if byte == 0 { break }
                bytes.append(byte)
                index += 1
            }
            if !bytes.isEmpty, let name = String(bytes: bytes, encoding: .utf8) {
                libraries.append(name)
            }
        }
        return libraries
    }

    private static func locateEmbeddedELF(_ data: Data, after start: Int) throws -> Int {
        let end = min(data.count - 64, max(start, 0x10000))
        guard start <= end else { throw PS4SELFPreparerError.embeddedELFNotFound }
        for offset in start...end where matches(data, magic: elfMagic, at: offset) {
            let type = read16(data, at: offset + 16)
            if data[offset + 4] == 2 && data[offset + 5] == 1 && data[offset + 6] == 1 &&
                (type == 2 || type == 0xFE00 || type == 0xFE10 || type == 0xFE18) &&
                read16(data, at: offset + 18) == 0x003e {
                let phoff = read64(data, at: offset + 32)
                let entrySize = Int(read16(data, at: offset + 54))
                let count = Int(read16(data, at: offset + 56))
                if entrySize >= 56 && count > 0 && count <= 1024 {
                    let (tableStart, overflow1) = UInt64(offset).addingReportingOverflow(phoff)
                    let (tableBytes, overflow2) = UInt64(entrySize).multipliedReportingOverflow(by: UInt64(count))
                    let (tableEnd, overflow3) = tableStart.addingReportingOverflow(tableBytes)
                    if !overflow1 && !overflow2 && !overflow3 && tableEnd <= UInt64(data.count) {
                        return offset
                    }
                }
            }
        }
        throw PS4SELFPreparerError.embeddedELFNotFound
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
