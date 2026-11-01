import Foundation
import SwiftUI

@MainActor
final class GameFolderStore: ObservableObject {
    @Published private(set) var folderName: String?
    @Published private(set) var isValidPayload = false
    @Published private(set) var executableValidated = false
    @Published private(set) var gameTitle: String?
    @Published private(set) var titleID: String?
    @Published private(set) var contentVersion: String?
    @Published private(set) var message = "Selecione a pasta do jogo PS4."
    @Published private(set) var details: [String] = []

    private var scopedFolder: URL?

    func select(folder url: URL) {
        if let previous = scopedFolder {
            previous.stopAccessingSecurityScopedResource()
            scopedFolder = nil
        }
        guard url.startAccessingSecurityScopedResource() else {
            folderName = nil
            isValidPayload = false
            executableValidated = false
            gameTitle = nil
            titleID = nil
            contentVersion = nil
            message = "O iOS não concedeu acesso à pasta selecionada."
            details = ["Escolha novamente a pasta pelo seletor de Arquivos."]
            return
        }

        scopedFolder = url
        folderName = url.lastPathComponent
        gameTitle = nil
        titleID = nil
        contentVersion = nil
        let fm = FileManager.default
        let eboot = url.appendingPathComponent("eboot.bin")
        let param = url.appendingPathComponent("sce_sys/param.sfo")
        let modules = url.appendingPathComponent("sce_module", isDirectory: true)
        let hasEboot = fm.fileExists(atPath: eboot.path)
        let hasParam = fm.fileExists(atPath: param.path)
        let hasModules = fm.fileExists(atPath: modules.path)

        var checks = [
            "\(hasEboot ? "✓" : "✕") eboot.bin",
            "\(hasParam ? "✓" : "✕") sce_sys/param.sfo",
            "\(hasModules ? "✓" : "–") sce_module/ (opcional nesta validação)"
        ]

        if hasParam {
            do {
                let sfo = try PS4ParamSFO.load(from: param)
                gameTitle = sfo.title
                titleID = sfo.titleID
                contentVersion = sfo.contentVersion
                checks.append("✓ param.sfo: estrutura e tabela válidas")
                if let title = sfo.title { checks.append("Título: \(title)") }
                if let id = sfo.titleID { checks.append("Title ID: \(id)") }
                if let version = sfo.contentVersion { checks.append("Versão: \(version)") }
                if let category = sfo.category { checks.append("Categoria: \(category)") }
            } catch {
                checks.append("⚠ param.sfo: \(error.localizedDescription)")
            }
        }

        executableValidated = false
        if hasEboot {
            do {
                checks.append(contentsOf: try PS4ELFInspector.inspect(eboot))
                executableValidated = true
            } catch {
                checks.append("⚠ eboot.bin: \(error.localizedDescription)")
            }
        }
        details = checks
        isValidPayload = hasEboot && hasParam && gameTitle != nil && titleID != nil

        if isValidPayload && executableValidated {
            message = "Metadados PSF e cabeçalho ELF64 x86-64 validados. O jogo ainda não é executado."
        } else if isValidPayload {
            message = "Metadados do jogo válidos; eboot.bin não passou na inspeção ELF decifrado."
        } else {
            message = "Dump incompleto ou metadados param.sfo inválidos."
        }
    }

    func reportPickerError(_ error: Error) {
        message = "Não foi possível abrir o seletor: \(error.localizedDescription)"
        isValidPayload = false
        executableValidated = false
    }

    deinit {
        scopedFolder?.stopAccessingSecurityScopedResource()
    }
}
