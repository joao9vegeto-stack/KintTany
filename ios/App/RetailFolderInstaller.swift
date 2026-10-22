import Foundation
import CryptoKit

/// A retail install is accepted only after every required file is present,
/// the *original* 4,603,904-byte XBE matches the pinned rePOP retail build,
/// and the complete directory has been copied into the app sandbox.
struct RetailFolderInstaller {
    static let expectedSHA256 = "753C58B191279BF4D1A8B28A936DF36AA222ED566487AB1FBDFCD090E91EE379"
    static let retailXBEBytes: UInt64 = 4_603_904
    static let requiredFiles = ["default.xbe", "prince.bf", "shaders.bin"]
    static let requiredFolders = ["VIDEO", "SOUND", "MEDIA", "POP1", "POP2"]

    enum InstallError: LocalizedError {
        case incorrectFolder(String)
        case unsupportedXBE(String)
        case missing([String])
        case inaccessible(String)
        case unsafeItem(String)
        case coordination(String)
        var errorDescription: String? {
            switch self {
            case .incorrectFolder(let why): return "Pasta retail inválida: \(why)"
            case .unsupportedXBE(let sha): return "Esse default.xbe não corresponde à retail NTSC suportada (SHA-256 \(sha))."
            case .missing(let names):
                return "A extração está incompleta. Faltam: \(names.joined(separator: ", ")). O rePOP precisa desses arquivos na mesma pasta do default.xbe."
            case .inaccessible(let why): return "O app Arquivos não liberou a pasta: \(why). Use 'No Meu iPhone > PoPTST' como alternativa."
            case .unsafeItem(let why): return "Cópia bloqueada por arquivo não seguro: \(why)."
            case .coordination(let why): return "Falha ao receber a pasta do app Arquivos: \(why)"
            }
        }
    }
    struct Inventory {
        let installURL: URL
        let sha256: String
        let installedAt: Date
    }

    /// rePOP port/android SaveFolders.prepare parity. Never overwrite a save
    /// already present on the iPhone; preserve original source files and
    /// reject symlink traversal. Temporary copy is atomically renamed.
    static func prepareSaveFolders(gameDir: URL, dataDir: URL) throws {
        let fm = FileManager.default
        let saves = dataDir.appendingPathComponent("saves/xbox-retail", isDirectory: true)
        try fm.createDirectory(at: saves, withIntermediateDirectories: true)
        func copyMissing(from source: URL, to target: URL) throws {
            guard fm.fileExists(atPath: source.path) else { return }
            let props = try source.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey])
            if props.isSymbolicLink == true {
                throw InstallError.unsafeItem("save: \(source.lastPathComponent)")
            }
            if props.isDirectory == true {
                try fm.createDirectory(at: target, withIntermediateDirectories: true)
                for item in try fm.contentsOfDirectory(at: source,
                        includingPropertiesForKeys: [.isDirectoryKey,.isRegularFileKey,.isSymbolicLinkKey],
                        options: [.skipsHiddenFiles]) {
                    try copyMissing(from: item, to: target.appendingPathComponent(item.lastPathComponent))
                }
            } else if props.isRegularFile == true && !fm.fileExists(atPath: target.path) {
                try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                let temp = target.deletingLastPathComponent()
                    .appendingPathComponent(".poptst-save-migration-\(UUID().uuidString)")
                do {
                    try fm.copyItem(at: source, to: temp)
                    let handle = try FileHandle(forWritingTo: temp)
                    try handle.synchronize()
                    try handle.close()
                    if !fm.fileExists(atPath: target.path) {
                        try fm.moveItem(at: temp, to: target)
                    }
                } catch {
                    try? fm.removeItem(at: temp)
                    throw error
                }
                if fm.fileExists(atPath: temp.path) { try? fm.removeItem(at: temp) }
            }
        }
        try copyMissing(from: gameDir.appendingPathComponent("UDATA"),
                        to: saves.appendingPathComponent("UDATA"))
        try copyMissing(from: gameDir.appendingPathComponent("TDATA"),
                        to: saves.appendingPathComponent("TDATA"))
        try copyMissing(from: saves.appendingPathComponent("UserData"),
                        to: saves.appendingPathComponent("UDATA"))
        try copyMissing(from: saves.appendingPathComponent("TitleData"),
                        to: saves.appendingPathComponent("TDATA"))
    }

    static func applicationSupport() throws -> URL {
        let fm = FileManager.default
        guard let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            throw InstallError.inaccessible("Application Support indisponível")
        }
        let root = base.appendingPathComponent("PoPTST", isDirectory: true)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    static func documents() throws -> URL {
        guard let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            throw InstallError.inaccessible("Documents indisponível")
        }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// The app-owned Documents folder is visible in Files > On My iPhone > PoPTST.
    /// M7.39 of AscensionRecomp demonstrated this route works without a folder picker.
    /// Create only directories and instructions; never create placeholder game files.
    static func prepareVisibleGameHome() throws -> URL {
        let fm = FileManager.default
        let docs = try documents()
        let folder = docs.appendingPathComponent("xbox-retail", isDirectory: true)
        try fm.createDirectory(at: folder, withIntermediateDirectories: true)
        for name in requiredFolders {
            try fm.createDirectory(at: folder.appendingPathComponent(name, isDirectory: true),
                                   withIntermediateDirectories: true)
        }
        let note = docs.appendingPathComponent("LEIA-ME-POPTST.txt")
        if !fm.fileExists(atPath: note.path) {
            let instructions = """
            PoPTST — Prince of Persia Xbox Retail NTSC

            Copie o conteúdo da pasta extraída do seu jogo para:
            Arquivos > No Meu iPhone > PoPTST > xbox-retail

            Os arquivos default.xbe, prince.bf e shaders.bin devem estar na raiz
            de xbox-retail; VIDEO, SOUND, MEDIA, POP1 e POP2 são subpastas.
            Você também pode copiar a pasta completa pop_completo DENTRO de
            xbox-retail. O app reconhece um nível adicional automaticamente.

            Depois volte ao PoPTST e toque VERIFICAR PASTA LOCAL E JOGAR.
            Nenhum jogo é incluído no aplicativo; os saves são separados.
            """
            try instructions.write(to: note, atomically: true, encoding: .utf8)
        }
        return folder
    }

    /// Resolves ONLY the app Documents directory (plus one nested wrapper).
    /// Never follows symlinks, never traverses other apps' containers, no broad scans.
    static func localRetailCandidate() throws -> URL {
        let fm = FileManager.default
        let docs = try documents()
        let root = try prepareVisibleGameHome()
        let direct = [root, docs]
        for dir in direct where fm.fileExists(atPath: dir.appendingPathComponent("default.xbe").path) {
            return dir
        }
        let ignored = Set(["VIDEO","SOUND","MEDIA","POP1","POP2","XBOX-RETAIL.PREVIOUS"])
        for parent in direct {
            let items = try fm.contentsOfDirectory(at: parent,
                       includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
                       options: [.skipsHiddenFiles]).sorted { $0.lastPathComponent < $1.lastPathComponent }
            for item in items {
                if ignored.contains(item.lastPathComponent.uppercased()) { continue }
                let flags = try item.resourceValues(forKeys: [.isDirectoryKey,.isSymbolicLinkKey])
                if flags.isDirectory == true && flags.isSymbolicLink != true &&
                   fm.fileExists(atPath: item.appendingPathComponent("default.xbe").path) {
                    return item
                }
            }
        }
        throw InstallError.incorrectFolder("não encontrei default.xbe em Arquivos > No Meu iPhone > PoPTST > xbox-retail. Copie os 3 arquivos e as pastas VIDEO, SOUND, MEDIA, POP1 e POP2 para lá, ou coloque pop_completo dentro de xbox-retail.")
    }

    /// Validate app-owned files in place: no picker, no scope, no extra gigabytes.
    static func recognizeLocalInPlace(progress: (String, Double) -> Void) throws -> Inventory {
        progress("Procurando arquivo original na pasta local...", 0.1)
        let dir = try localRetailCandidate()
        progress("Conferindo hash da versão retail NTSC...", 0.4)
        let sha = try validate(dir)
        progress("Retail válida em No Meu iPhone; sem copiar novamente.", 1.0)
        return Inventory(installURL: dir, sha256: sha, installedAt: Date())
    }

    /// The video showed `default.xbe`, MEDIA, POP1, POP2 but not the other
    /// rePOP retail requirements. Report *all* missing files BEFORE copying.
    static func validate(_ folder: URL) throws -> String {
        let fm = FileManager.default
        var directory: ObjCBool = false
        guard fm.fileExists(atPath: folder.path, isDirectory: &directory), directory.boolValue else {
            throw InstallError.incorrectFolder("escolha a pasta que contém default.xbe")
        }
        let items = try fm.contentsOfDirectory(at: folder,
                             includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
                             options: [.skipsHiddenFiles])
        func matching(_ name: String, directory: Bool) throws -> URL? {
            let matches = items.filter { $0.lastPathComponent.caseInsensitiveCompare(name) == .orderedSame }
            if matches.count > 1 { throw InstallError.unsafeItem("nomes duplicados para \(name)") }
            guard let one = matches.first else { return nil }
            let attrs = try one.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            if attrs.isSymbolicLink == true { throw InstallError.unsafeItem(one.lastPathComponent) }
            return attrs.isDirectory == directory ? one : nil
        }
        var missing: [String] = []
        for item in requiredFiles { if try matching(item, directory: false) == nil { missing.append(item) } }
        for item in requiredFolders { if try matching(item, directory: true) == nil { missing.append(item + "/") } }
        if !missing.isEmpty { throw InstallError.missing(missing) }
        guard let xbe = try matching("default.xbe", directory: false) else {
            throw InstallError.missing(["default.xbe"])
        }
        guard let size = try xbe.resourceValues(forKeys: [.fileSizeKey]).fileSize,
              UInt64(size) >= retailXBEBytes && UInt64(size) <= 64 * 1024 * 1024 else {
            throw InstallError.incorrectFolder("default.xbe inválido: esperado o prefixo retail de 4.603.904 bytes (até 64 MiB total)")
        }
        let handle = try FileHandle(forReadingFrom: xbe)
        defer { try? handle.close() }
        var sha = SHA256()
        var remaining = retailXBEBytes
        while remaining > 0 {
            guard let chunk = try handle.read(upToCount: Int(min(remaining, 512 * 1024))), !chunk.isEmpty else {
                throw InstallError.incorrectFolder("default.xbe terminou antes do tamanho original")
            }
            sha.update(data: chunk)
            remaining -= UInt64(chunk.count)
        }
        // A Colab ISO carving may append *non-XBE ISO bytes* after the authentic
        // 4,603,904-byte XBE (verified with the user's 15-MiB padded upload).
        // Authenticate the exact retail prefix; never pass the suffix to Xbox.
        // The native boot path independently hashes the same exact prefix.
        let digest = sha.finalize().map { String(format: "%02X", $0) }.joined()
        guard digest == expectedSHA256 else { throw InstallError.unsupportedXBE(digest) }
        return digest
    }

    /// Caller receives human-readable phases and ratio (0..1). The source
    /// stays security-scoped and file-coordinated until the whole copy ends.
    static func install(_ picked: URL, progress: @escaping (String, Double) -> Void) throws -> Inventory {
        guard picked.startAccessingSecurityScopedResource() else {
            // Files inside the application's own Documents are already scoped.
            let doc = try documents().standardizedFileURL.path
            guard picked.standardizedFileURL.path.hasPrefix(doc + "/") else {
                throw InstallError.inaccessible("acesso negado a \(picked.lastPathComponent)")
            }
            return try installLocal(picked, progress: progress)
        }
        defer { picked.stopAccessingSecurityScopedResource() }
        var result: Inventory?
        var actionError: Error?
        var coordinatorError: NSError?
        progress("Obtendo acesso seguro aos arquivos…", 0.01)
        // File Provider/iCloud sources must be coordinated to avoid zero-byte
        // copies, delayed downloads and stale document-picker URLs.
        NSFileCoordinator().coordinate(readingItemAt: picked, options: [], error: &coordinatorError) { coordinated in
            do { result = try installLocal(coordinated, progress: progress) }
            catch { actionError = error }
        }
        if let error = actionError { throw error }
        if let error = coordinatorError { throw InstallError.coordination(error.localizedDescription) }
        guard let result else { throw InstallError.coordination("nenhuma pasta recebida") }
        return result
    }

    static func installFromDocuments(progress: @escaping (String, Double) -> Void) throws -> Inventory {
        try recognizeLocalInPlace(progress: progress)
    }

    private static func installLocal(_ picked: URL, progress: (String, Double) -> Void) throws -> Inventory {
        progress("Conferindo estrutura e SHA-256 antes da cópia…", 0.02)
        let digest = try validate(picked) // fail in seconds instead of copying 2.2 GB first
        let fm = FileManager.default
        let root = try applicationSupport()
        let install = root.appendingPathComponent("xbox-retail", isDirectory: true)
        let backup = root.appendingPathComponent("xbox-retail.previous", isDirectory: true)
        let staging = root.appendingPathComponent(".import-\(UUID().uuidString)", isDirectory: true)
        if picked.standardizedFileURL == install.standardizedFileURL {
            return Inventory(installURL: install, sha256: digest, installedAt: Date())
        }
        if !fm.fileExists(atPath: install.path), fm.fileExists(atPath: backup.path) {
            try fm.moveItem(at: backup, to: install)
        }
        // Enumerate once so the UI can report actual copied-file progress.
        guard let enumerator = fm.enumerator(at: picked,
                 includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey],
                 options: [.skipsHiddenFiles], errorHandler: { _, _ in false }) else {
            throw InstallError.inaccessible("não foi possível enumerar a pasta")
        }
        let urls = enumerator.allObjects.compactMap { $0 as? URL }
        if urls.isEmpty || urls.count > 250_000 { throw InstallError.incorrectFolder("quantidade de arquivos inválida") }
        for url in urls {
            let r = try url.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey])
            if r.isSymbolicLink == true || (r.isRegularFile != true && r.isDirectory != true) {
                throw InstallError.unsafeItem(url.lastPathComponent)
            }
        }
        let fileBytes = try urls.reduce(UInt64(0)) { sum, url -> UInt64 in
            let attrs = try url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            return sum + (attrs.isRegularFile == true ? UInt64(attrs.fileSize ?? 0) : 0)
        }
        guard fileBytes > 0 else { throw InstallError.incorrectFolder("nenhum arquivo legível") }
        progress("Verificação concluída · \(urls.count) itens para copiar", 0.06)
        try fm.createDirectory(at: staging, withIntermediateDirectories: true)
        do {
            var done: UInt64 = 0
            var lastReported: UInt64 = 0
            for (idx, url) in urls.enumerated() {
                let prefix = picked.standardizedFileURL.path + "/"
                let path = url.standardizedFileURL.path
                guard path.hasPrefix(prefix) else { throw InstallError.unsafeItem(url.lastPathComponent) }
                let relative = String(path.dropFirst(prefix.count))
                let dest = staging.appendingPathComponent(relative)
                let attrs = try url.resourceValues(forKeys: [.isDirectoryKey])
                if attrs.isDirectory == true {
                    try fm.createDirectory(at: dest, withIntermediateDirectories: true)
                } else {
                    try fm.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
                    guard fm.createFile(atPath: dest.path, contents: nil) else {
                        throw InstallError.inaccessible("não foi possível criar \(url.lastPathComponent)")
                    }
                    let input = try FileHandle(forReadingFrom: url)
                    let output = try FileHandle(forWritingTo: dest)
                    defer { try? input.close(); try? output.close() }
                    while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                        try output.write(contentsOf: chunk)
                        done += UInt64(chunk.count)
                        if done - lastReported >= 8 * 1024 * 1024 || idx == urls.count - 1 {
                            lastReported = done
                            let mb = Double(done) / 1_048_576
                            let totalMB = Double(fileBytes) / 1_048_576
                            progress(String(format: "Copiando %.0f / %.0f MiB · %@", mb, totalMB, url.lastPathComponent),
                                     0.06 + 0.88 * min(1, Double(done) / Double(fileBytes)))
                        }
                    }
                }
            }
            progress("Verificando a cópia…", 0.95)
            _ = try validate(staging)
            if fm.fileExists(atPath: backup.path) { try fm.removeItem(at: backup) }
            let hadInstall = fm.fileExists(atPath: install.path)
            if hadInstall { try fm.moveItem(at: install, to: backup) }
            do { try fm.moveItem(at: staging, to: install) }
            catch {
                if hadInstall && !fm.fileExists(atPath: install.path) && fm.fileExists(atPath: backup.path) {
                    try? fm.moveItem(at: backup, to: install)
                }
                throw error
            }
            if fm.fileExists(atPath: backup.path) { try? fm.removeItem(at: backup) }
            progress("Retail validada e pronta para iniciar.", 1)
            return Inventory(installURL: install, sha256: digest, installedAt: Date())
        } catch {
            try? fm.removeItem(at: staging)
            throw error
        }
    }
}
