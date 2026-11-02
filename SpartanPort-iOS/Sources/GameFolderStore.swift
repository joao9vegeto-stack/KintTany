import Foundation
import SwiftUI

struct PS4GameInstall: Identifiable, Equatable {
    let relativePath: String
    let folderName: String
    let title: String?
    let titleID: String?
    var id: String { relativePath }
}

private enum PS4GameImportError: LocalizedError {
    case noGameFound, copyIncomplete
    var errorDescription: String? {
        switch self {
        case .noGameFound: return "Pasta sem eboot.bin e sce_sys/param.sfo. Selecione a raiz do dump PS4."
        case .copyIncomplete: return "A cópia do dump não terminou corretamente."
        }
    }
}

@MainActor
final class GameFolderStore: ObservableObject {
    @Published private(set) var folderName: String?
    @Published private(set) var isValidPayload = false
    @Published private(set) var executableValidated = false
    @Published private(set) var gameTitle: String?
    @Published private(set) var titleID: String?
    @Published private(set) var contentVersion: String?
    @Published private(set) var message = "Procurando instalações do jogo…"
    @Published private(set) var details: [String] = []
    @Published private(set) var availableGames: [PS4GameInstall] = []
    @Published private(set) var isImporting = false
    @Published private(set) var diagnosticsPath = ""
    @Published private(set) var selectedRelativePath: String?

    private let defaultsKey = "SpartanPort.SelectedGameRelativePath"
    private let fm = FileManager.default
    private var documents: URL { fm.urls(for: .documentDirectory, in: .userDomainMask)[0] }
    private var gamesDirectory: URL {
        documents.appendingPathComponent("SpartanPort", isDirectory: true).appendingPathComponent("Jogos", isDirectory: true)
    }

    init() { refresh() }

    func refresh(selecting preferredURL: URL? = nil) {
        do { try fm.createDirectory(at: gamesDirectory, withIntermediateDirectories: true) }
        catch {
            message = "Falha ao criar a pasta de jogos: \(error.localizedDescription)"
            writeDiagnostics(error: error)
            return
        }
        diagnosticsPath = documents.appendingPathComponent("diagnostico.txt").path
        let candidates = PS4GameFolderScanner.findGameFolders(in: documents, maxDepth: 4)
        availableGames = candidates.map { url in
            let sfo = try? PS4ParamSFO.load(from: url.appendingPathComponent("sce_sys/param.sfo"))
            return PS4GameInstall(relativePath: relativePath(url), folderName: url.lastPathComponent, title: sfo?.title, titleID: sfo?.titleID)
        }
        let saved = preferredURL.map { relativePath($0) } ?? UserDefaults.standard.string(forKey: defaultsKey)
        if let url = candidates.first(where: { relativePath($0) == saved }) ?? candidates.first {
            applySelection(url)
        } else {
            clearSelection("Nenhum dump encontrado. Use Documents/SpartanPort/Jogos ou importe a pasta.")
        }
        writeDiagnostics()
    }

    /// Imports external Files/iCloud folders into Documents so access survives picker closure.
    func select(folder url: URL) {
        guard !isImporting else { return }
        isImporting = true
        message = "Importando dump para o armazenamento do aplicativo…"
        let documentsURL = documents
        let destinationRoot = gamesDirectory
        let fileManager = fm
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            let result: Result<URL, Error>
            do {
                guard let candidate = PS4GameFolderScanner.findGameFolders(in: url, maxDepth: 2).first else {
                    throw PS4GameImportError.noGameFound
                }
                if candidate.standardizedFileURL.path.hasPrefix(documentsURL.standardizedFileURL.path + "/") {
                    result = .success(candidate)
                } else {
                    try fileManager.createDirectory(at: destinationRoot, withIntermediateDirectories: true)
                    var destination = destinationRoot.appendingPathComponent(candidate.lastPathComponent, isDirectory: true)
                    var suffix = 2
                    while fileManager.fileExists(atPath: destination.path) {
                        destination = destinationRoot.appendingPathComponent("\(candidate.lastPathComponent)-\(suffix)", isDirectory: true)
                        suffix += 1
                    }
                    let coordinator = NSFileCoordinator(filePresenter: nil)
                    var coordinationError: NSError?
                    var copyError: Error?
                    coordinator.coordinate(readingItemAt: candidate, options: [], error: &coordinationError) { coordinatedURL in
                        do { try fileManager.copyItem(at: coordinatedURL, to: destination) }
                        catch { copyError = error }
                    }
                    if let coordinationError { throw coordinationError }
                    if let copyError { throw copyError }
                    guard PS4GameFolderScanner.isGameFolder(destination) else { throw PS4GameImportError.copyIncomplete }
                    result = .success(destination)
                }
            } catch { result = .failure(error) }
            DispatchQueue.main.async {
                guard let self else { return }
                self.isImporting = false
                switch result {
                case .success(let selected):
                    self.refresh(selecting: selected)
                    self.message = "Dump importado e detectado. O runtime PS4 ainda não está disponível."
                case .failure(let error):
                    self.message = error.localizedDescription
                    self.writeDiagnostics(error: error)
                }
                self.writeDiagnostics()
            }
        }
    }

    func selectDetectedGame(relativePath: String) {
        let url = documents.appendingPathComponent(relativePath).standardizedFileURL
        guard PS4GameFolderScanner.isGameFolder(url) else { refresh(); return }
        applySelection(url)
        writeDiagnostics()
    }

    func reportPickerError(_ error: Error) {
        message = "Erro ao selecionar pasta: \(error.localizedDescription)"
        writeDiagnostics(error: error)
    }

    private func applySelection(_ url: URL) {
        folderName = url.lastPathComponent
        selectedRelativePath = relativePath(url)
        UserDefaults.standard.set(selectedRelativePath, forKey: defaultsKey)
        let eboot = url.appendingPathComponent("eboot.bin")
        let param = url.appendingPathComponent("sce_sys/param.sfo")
        let hasEboot = fm.fileExists(atPath: eboot.path)
        let hasParam = fm.fileExists(atPath: param.path)
        let hasModules = fm.fileExists(atPath: url.appendingPathComponent("sce_module").path)
        var checks = ["\(hasEboot ? "✓" : "✕") eboot.bin", "\(hasParam ? "✓" : "✕") sce_sys/param.sfo",
                      "\(hasModules ? "✓" : "–") sce_module/ (opcional)"]
        gameTitle = nil; titleID = nil; contentVersion = nil
        var metadataValid = false
        if hasParam {
            do {
                let sfo = try PS4ParamSFO.load(from: param)
                gameTitle = sfo.title; titleID = sfo.titleID; contentVersion = sfo.contentVersion
                metadataValid = sfo.title != nil && sfo.titleID != nil
                checks.append("✓ param.sfo válido")
                if let title = sfo.title { checks.append("Título: \(title)") }
                if let id = sfo.titleID { checks.append("Title ID: \(id)") }
                if let version = sfo.contentVersion { checks.append("Versão: \(version)") }
            } catch { checks.append("⚠ param.sfo: \(error.localizedDescription)") }
        }
        executableValidated = false
        if hasEboot {
            do {
                checks.append(contentsOf: try PS4ELFInspector.inspect(eboot))
                executableValidated = true
            } catch { checks.append("⚠ eboot.bin: \(error.localizedDescription)") }
        }
        details = checks
        isValidPayload = hasEboot && hasParam && metadataValid
        message = isValidPayload && executableValidated
            ? "Dump detectado; metadados e cabeçalho ELF64 x86-64 validados. O jogo ainda não é executado."
            : (isValidPayload ? "Metadados válidos; eboot.bin não passou na inspeção ELF decifrado." : "Dump incompleto ou param.sfo inválido.")
    }

    private func clearSelection(_ text: String) {
        folderName = nil; isValidPayload = false; executableValidated = false
        gameTitle = nil; titleID = nil; contentVersion = nil
        selectedRelativePath = nil; details = []; message = text
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private func relativePath(_ url: URL) -> String {
        let prefix = documents.standardizedFileURL.path + "/"
        let path = url.standardizedFileURL.path
        return path.hasPrefix(prefix) ? String(path.dropFirst(prefix.count)) : path
    }

    private func writeDiagnostics(error: Error? = nil) {
        diagnosticsPath = documents.appendingPathComponent("diagnostico.txt").path
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var lines = ["SPARTANPORT_DIAGNOSTICS", "timestamp=\(timestamp)",
                     "selected=\(selectedRelativePath ?? "none")", "folder=\(folderName ?? "none")",
                     "title=\(gameTitle ?? "unknown")", "title_id=\(titleID ?? "unknown")",
                     "payload_valid=\(isValidPayload)", "elf64_x86_64_valid=\(executableValidated)",
                     "runtime_ps4=unavailable", "message=\(message)"]
        lines.append(contentsOf: details)
        if let error { lines.append("error=\(error.localizedDescription)") }
        try? (lines.joined(separator: "\n") + "\n").write(to: URL(fileURLWithPath: diagnosticsPath), atomically: true, encoding: .utf8)
        if let error {
            let crash = "SPARTANPORT_ERROR \(timestamp)\n\(error.localizedDescription)\n"
            try? crash.write(to: documents.appendingPathComponent("crash.txt"), atomically: true, encoding: .utf8)
        }
    }
}