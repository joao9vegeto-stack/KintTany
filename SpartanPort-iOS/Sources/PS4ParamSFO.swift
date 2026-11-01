import Foundation

struct PS4ParamSFO {
    let title: String?
    let titleID: String?
    let contentVersion: String?
    let category: String?

    enum ParseError: LocalizedError {
        case invalidHeader, invalidTable, invalidString
        var errorDescription: String? {
            switch self {
            case .invalidHeader: return "param.sfo não possui cabeçalho PSF válido."
            case .invalidTable: return "A tabela de entradas do param.sfo está fora dos limites."
            case .invalidString: return "Uma string do param.sfo não está em UTF-8 válido."
            }
        }
    }

    static func load(from url: URL) throws -> PS4ParamSFO {
        let data = try Data(contentsOf: url, options: [.mappedIfSafe])
        let bytes = [UInt8](data)
        guard bytes.count >= 20,
              Array(bytes[0..<4]) == [0x00, 0x50, 0x53, 0x46],
              read32(bytes, 4) == 0x00000101 else { throw ParseError.invalidHeader }

        let keyOffset = Int(read32(bytes, 8))
        let dataOffset = Int(read32(bytes, 12))
        let count = Int(read32(bytes, 16))
        let (tableSize, overflow) = count.multipliedReportingOverflow(by: 16)
        let (tableEnd, addOverflow) = 20.addingReportingOverflow(tableSize)
        guard !overflow, !addOverflow, count <= 4096, tableEnd <= bytes.count,
              keyOffset >= tableEnd, dataOffset >= keyOffset,
              keyOffset <= bytes.count, dataOffset <= bytes.count else {
            throw ParseError.invalidTable
        }

        var values: [String: String] = [:]
        for index in 0..<count {
            let entry = 20 + index * 16
            let keyIndex = Int(read16(bytes, entry))
            let format = read16(bytes, entry + 2)
            let length = Int(read32(bytes, entry + 4))
            let maximum = Int(read32(bytes, entry + 8))
            let valueOffset = Int(read32(bytes, entry + 12))
            guard length <= maximum, keyIndex < dataOffset - keyOffset,
                  valueOffset <= bytes.count - dataOffset,
                  length <= bytes.count - dataOffset - valueOffset else { throw ParseError.invalidTable }

            let keyStart = keyOffset + keyIndex
            guard keyStart < dataOffset,
                  let keyEnd = bytes[keyStart..<dataOffset].firstIndex(of: 0),
                  let key = String(bytes: bytes[keyStart..<keyEnd], encoding: .utf8) else {
                throw ParseError.invalidString
            }
            guard format == 0x0204 || format == 0x0004 else { continue }
            let valueStart = dataOffset + valueOffset
            let valueBytes = bytes[valueStart..<(valueStart + length)].prefix { $0 != 0 }
            guard let value = String(bytes: valueBytes, encoding: .utf8) else {
                throw ParseError.invalidString
            }
            values[key] = value
        }

        return PS4ParamSFO(
            title: values["TITLE"],
            titleID: values["TITLE_ID"],
            contentVersion: values["APP_VER"],
            category: values["CATEGORY"]
        )
    }

    private static func read16(_ b: [UInt8], _ i: Int) -> UInt16 {
        UInt16(b[i]) | (UInt16(b[i + 1]) << 8)
    }
    private static func read32(_ b: [UInt8], _ i: Int) -> UInt32 {
        UInt32(b[i]) | (UInt32(b[i + 1]) << 8) | (UInt32(b[i + 2]) << 16) | (UInt32(b[i + 3]) << 24)
    }
}
