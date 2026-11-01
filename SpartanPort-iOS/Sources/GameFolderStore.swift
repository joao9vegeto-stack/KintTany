import Foundation
import SwiftUI

@MainActor
final class GameFolderStore: ObservableObject {
    @Published private(set) var folderName: String?
    @Published private(set) var isValidPayload = false
    @Published private(set) var message = "Selecione a pasta do jogo PS4."
    @Published private(set) var details: [String] = []

    private var scopedFolder: URL?

    func select(folder url: URL) {
        let didStartAccess = url.startAccessingSecurityScopedResource()
        guard didStartAccess else {
            message = "O iOS não concedeu acesso à pasta selecionada."
            details = ["Escolha novamente a pasta pelo seletor de Arquivos."]
            isValidPayload = false
            return
        }

        if let previous = scopedFolder {
            previous.stopAccessingSecurityScopedResource()
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

        var checks: [String] = [
            "\(hasEboot ? "✓" : "✕") eboot.bin",
            "\(hasParam ? "✓" : "✕") sce_sys/param.sfo",
            "\(hasModules ? "✓" : "–") sce_module/ (opcional nesta validação)"
        ]
        details = checks
        isValidPayload = hasEboot && hasParam

        if isValidPayload {
            message = "Estrutura básica do dump identificada. Isso não significa que o jogo já seja compatível."
        } else {
            message = "A pasta selecionada não contém a estrutura mínima esperada."
        }
    }

    deinit {
        scopedFolder?.stopAccessingSecurityScopedResource()
    }
}
