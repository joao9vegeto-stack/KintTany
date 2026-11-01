import Foundation
import SwiftUI

@MainActor
final class GameFolderStore: ObservableObject {
    @Published private(set) var folderName: String?
    @Published private(set) var isValidPayload = false
    @Published private(set) var executableValidated = false
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
            message = "O iOS não concedeu acesso à pasta selecionada."
            details = ["Escolha novamente a pasta pelo seletor de Arquivos."]
            return
        }

        scopedFolder = url
        folderName = url.lastPathComponent
        let fileManager = FileManager.default
        let eboot = url.appendingPathComponent("eboot.bin", isDirectory: false)
        let param = url.appendingPathComponent("sce_sys/param.sfo", isDirectory: false)
        let modules = url.appendingPathComponent("sce_module", isDirectory: true)
        let hasEboot = fileManager.fileExists(atPath: eboot.path)
        let hasParam = fileManager.fileExists(atPath: param.path)
        let hasModules = fileManager.fileExists(atPath: modules.path)

        var checks = [
            "\(hasEboot ? "✓" : "✕") eboot.bin",
            "\(hasParam ? "✓" : "✕") sce_sys/param.sfo",
            "\(hasModules ? "✓" : "–") sce_module/ (opcional nesta validação)"
        ]
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
        isValidPayload = hasEboot && hasParam

        if isValidPayload && executableValidated {
            message = "Estrutura básica e cabeçalho ELF64 x86-64 validados. O jogo ainda não é executado pelo aplicativo."
        } else if isValidPayload {
            message = "Os arquivos básicos existem, mas eboot.bin não passou na inspeção ELF."
        } else {
            message = "A pasta selecionada não contém a estrutura mínima esperada."
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
