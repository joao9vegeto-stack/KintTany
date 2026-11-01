import Foundation

enum PS4ELFInspectorError: LocalizedError {
    case truncatedHeader, notELF, not64Bit, notLittleEndian
    case unsupportedMachine(UInt16)
    case invalidProgramHeaderTable

    var errorDescription: String? {
        switch self {
        case .truncatedHeader: return "eboot.bin é menor que um cabeçalho ELF64."
        case .notELF: return "eboot.bin não é um ELF decifrado; pode ser um SELF criptografado ou um arquivo inválido."
        case .not64Bit: return "O executável não usa o formato ELF de 64 bits."
        case .notLittleEndian: return "O executável ELF não está em little-endian."
        case .unsupportedMachine(let machine):
            return String(format: "Arquitetura ELF não suportada (e_machine=0x%04x); esperado x86-64.", machine)
        case .invalidProgramHeaderTable:
            return "A tabela de segmentos ELF está ausente, malformada ou fora do arquivo."
        }
    }
}

/// Inspeciona somente o cabeçalho ELF e os limites da tabela de segmentos.
/// Não descriptografa SELF, mapeia segmentos ou executa código.
enum PS4ELFInspector {
    static func inspect(_ executableURL: URL) throws -> [String] {
        let handle = try FileHandle(forReadingFrom: executableURL)
        defer { try? handle.close() }
        let header = try handle.read(upToCount: 64) ?? Data()
        guard header.count == 64 else { throw PS4ELFInspectorError.truncatedHeader }
        let bytes = Array(header)

        guard bytes[0] == 0x7f, bytes[1] == 0x45, bytes[2] == 0x4c, bytes[3] == 0x46 else {
            throw PS4ELFInspectorError.notELF
        }
        guard bytes[4] == 2 else { throw PS4ELFInspectorError.not64Bit }
        guard bytes[5] == 1 else { throw PS4ELFInspectorError.notLittleEndian }
        guard bytes[6] == 1 else { throw PS4ELFInspectorError.notELF }

        let machine = read16(bytes, at: 18)
        guard machine == 0x003e else { throw PS4ELFInspectorError.unsupportedMachine(machine) }

        let entry = read64(bytes, at: 24)
        let programHeaderOffset = read64(bytes, at: 32)
        let headerSize = read16(bytes, at: 52)
        let programHeaderEntrySize = read16(bytes, at: 54)
        let programHeaderCount = read16(bytes, at: 56)
        let attributes = try FileManager.default.attributesOfItem(atPath: executableURL.path)
        let fileSize = (attributes[.size] as? NSNumber)?.uint64Value ?? 0

        guard headerSize >= 64, programHeaderCount > 0, programHeaderEntrySize >= 56 else {
            throw PS4ELFInspectorError.invalidProgramHeaderTable
        }
        let (tableBytes, multiplyOverflow) = UInt64(programHeaderEntrySize)
            .multipliedReportingOverflow(by: UInt64(programHeaderCount))
        let (tableEnd, addOverflow) = programHeaderOffset.addingReportingOverflow(tableBytes)
        guard !multiplyOverflow, !addOverflow, tableEnd <= fileSize else {
            throw PS4ELFInspectorError.invalidProgramHeaderTable
        }

        return [
            "✓ ELF64 little-endian",
            "✓ Arquitetura x86-64 (EM_X86_64)",
            String(format: "Entry point: 0x%016llx", entry),
            "Segmentos: \(programHeaderCount) • tabela dentro do arquivo"
        ]
    }

    private static func read16(_ bytes: [UInt8], at offset: Int) -> UInt16 {
        UInt16(bytes[offset]) | (UInt16(bytes[offset + 1]) << 8)
    }

    private static func read64(_ bytes: [UInt8], at offset: Int) -> UInt64 {
        var value: UInt64 = 0
        for index in 0..<8 { value |= UInt64(bytes[offset + index]) << (index * 8) }
        return value
    }
}
