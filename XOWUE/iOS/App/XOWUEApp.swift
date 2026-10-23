import SwiftUI
import UniformTypeIdentifiers
import Foundation
import Combine
import UIKit

@main
struct XOWUEApp: App {
    init() { XOWUEDiagnostics.startup() }

    var body: some Scene {
        WindowGroup {
            XOWUERootView()
        }
    }
}

private enum XOWUEBuild {
    static var number: String {
        let value = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        return value?.isEmpty == false ? value! : "1"
    }
}

private enum XOWUEFileType {
    static let xex = UTType("com.xowue.xex") ?? UTType(filenameExtension: "xex", conformingTo: .data) ?? .data
    static let importerTypes: [UTType] = [.folder, xex]
}

private struct XOWUEDocumentPicker: UIViewControllerRepresentable {
    @Binding var isPresented: Bool
    let completion: (Result<[URL], Error>) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(isPresented: $isPresented, completion: completion)
    }

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes: [.folder, XOWUEFileType.xex],
            asCopy: false
        )
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIDocumentPickerViewController, context: Context) {}

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        private let isPresented: Binding<Bool>
        private let completion: (Result<[URL], Error>) -> Void

        init(isPresented: Binding<Bool>, completion: @escaping (Result<[URL], Error>) -> Void) {
            self.isPresented = isPresented
            self.completion = completion
        }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            XOWUEDiagnostics.log("picker.selected count=\(urls.count) url=\(urls.first?.path ?? "none")")
            isPresented.wrappedValue = false
            completion(.success(urls))
        }

        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            XOWUEDiagnostics.log("picker.cancelled")
            isPresented.wrappedValue = false
            completion(.failure(CancellationError()))
        }
    }
}

private struct XOWUEVulkanSurface: UIViewRepresentable {
    func makeUIView(context: Context) -> XOWUEVulkanView {
        XOWUEVulkanView(frame: .zero)
    }

    func updateUIView(_ view: XOWUEVulkanView, context: Context) {}
}

@MainActor
private struct XOWUEGameSurfaceScreen: View {
    @ObservedObject var library: XOWUEGameLibrary
    @StateObject private var touchController = XOWUETouchController()
    @State private var showBootHint = true

    private var bootSummary: String {
        library.bootOutput.components(separatedBy: .newlines).first(where: { !$0.isEmpty }) ?? ""
    }

    private var showsBootFailure: Bool {
        library.phase == .failed || library.phase == .stopped
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            XOWUEVulkanSurface().ignoresSafeArea()
            XOWUETouchControllerHUD(input: touchController)

            VStack(spacing: 0) {
                HStack {
                    Button {
                        library.gameSurfacePresented = false
                    } label: {
                        Label("BIBLIOTECA", systemImage: "chevron.left")
                            .font(.system(size: 11, weight: .heavy, design: .rounded))
                            .tracking(0.6)
                            .padding(.horizontal, 13)
                            .padding(.vertical, 10)
                            .background(.black.opacity(0.72), in: Capsule())
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    Text("X-MEN ORIGINS · KOSMICKRISP")
                        .font(.system(size: 9, weight: .heavy, design: .monospaced))
                        .tracking(0.7)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 10)
                        .background(.black.opacity(0.72), in: Capsule())
                }

                Spacer()

                if showsBootFailure {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(library.status)
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                        Text(library.detail)
                            .font(.system(size: 12))
                            .foregroundStyle(.white.opacity(0.78))
                        if !bootSummary.isEmpty {
                            Text(bootSummary)
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundStyle(.white.opacity(0.78))
                                .lineLimit(4)
                                .textSelection(.enabled)
                        }
                        Button("VOLTAR À BIBLIOTECA") {
                            library.gameSurfacePresented = false
                        }
                        .font(.system(size: 11, weight: .heavy, design: .rounded))
                        .padding(.top, 4)
                    }
                    .foregroundStyle(.white)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.black.opacity(0.88), in: RoundedRectangle(cornerRadius: 16))
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.12), lineWidth: 1))
                } else if library.phase == .booting && showBootHint {
                    Text(library.status)
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(.white.opacity(0.8))
                        .padding(.horizontal, 13)
                        .padding(.vertical, 9)
                        .background(.black.opacity(0.72), in: Capsule())
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, showsBootFailure ? 218 : 22)
        }
        .background(.black)
        .preferredColorScheme(.dark)
        .statusBarHidden(true)
        .onDisappear { touchController.releaseAll() }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                withAnimation(.easeOut(duration: 0.2)) { self.showBootHint = false }
            }
        }
    }
}

@MainActor
private final class XOWUETouchController: ObservableObject {
    @Published private(set) var buttons: UInt32 = 0
    private var leftTrigger: UInt8 = 0
    private var rightTrigger: UInt8 = 0
    private var leftX: Int16 = 0
    private var leftY: Int16 = 0
    private var rightX: Int16 = 0
    private var rightY: Int16 = 0

    func setButton(_ mask: UInt32, pressed: Bool) {
        let next = pressed ? (buttons | mask) : (buttons & ~mask)
        guard next != buttons else { return }
        buttons = next
        send()
    }

    func setTrigger(left: Bool, pressed: Bool) {
        let value: UInt8 = pressed ? 255 : 0
        if left {
            guard leftTrigger != value else { return }
            leftTrigger = value
        } else {
            guard rightTrigger != value else { return }
            rightTrigger = value
        }
        send()
    }

    func setStick(left: Bool, x: CGFloat, y: CGFloat) {
        let nextX = Int16((min(1, max(-1, x)) * 32767).rounded())
        let nextY = Int16((min(1, max(-1, y)) * 32767).rounded())
        if left {
            guard leftX != nextX || leftY != nextY else { return }
            leftX = nextX
            leftY = nextY
        } else {
            guard rightX != nextX || rightY != nextY else { return }
            rightX = nextX
            rightY = nextY
        }
        send()
    }

    func releaseAll() {
        buttons = 0
        leftTrigger = 0
        rightTrigger = 0
        leftX = 0
        leftY = 0
        rightX = 0
        rightY = 0
        send()
    }

    private func send() {
        xowue_set_touch_controller_state(
            buttons,
            leftTrigger,
            rightTrigger,
            leftX,
            leftY,
            rightX,
            rightY
        )
    }
}

private enum XOWUEGamepadButton {
    static let up: UInt32 = 0x0001
    static let down: UInt32 = 0x0002
    static let left: UInt32 = 0x0004
    static let right: UInt32 = 0x0008
    static let start: UInt32 = 0x0010
    static let back: UInt32 = 0x0020
    static let leftThumb: UInt32 = 0x0040
    static let rightThumb: UInt32 = 0x0080
    static let leftShoulder: UInt32 = 0x0100
    static let rightShoulder: UInt32 = 0x0200
    static let a: UInt32 = 0x1000
    static let b: UInt32 = 0x2000
    static let x: UInt32 = 0x4000
    static let y: UInt32 = 0x8000
}

private struct XOWUETouchControllerHUD: View {
    @ObservedObject var input: XOWUETouchController
    @State private var controlsVisible = true

    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 0) {
                HStack {
                    Spacer()
                    Button {
                        controlsVisible.toggle()
                        if !controlsVisible { input.releaseAll() }
                    } label: {
                        Image(systemName: controlsVisible ? "gamecontroller.fill" : "gamecontroller")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(XOWUEPalette.yellow)
                            .frame(width: 42, height: 34)
                            .background(.black.opacity(0.56), in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(controlsVisible ? "Ocultar controles" : "Mostrar controles")
                }

                Spacer(minLength: 0)

                if controlsVisible {
                    HStack(alignment: .bottom, spacing: 8) {
                        VStack(spacing: 8) {
                            HStack(spacing: 6) {
                                XOWUETouchButton(title: "L1", mask: XOWUEGamepadButton.leftShoulder, input: input, size: 39)
                                XOWUETouchTrigger(title: "L2", left: true, input: input)
                            }
                            XOWUETouchStick(left: true, input: input, size: 100)
                            XOWUETouchDPad(input: input)
                            XOWUETouchButton(title: "L3", mask: XOWUEGamepadButton.leftThumb, input: input, size: 39)
                        }

                        Spacer(minLength: 0)

                        VStack(spacing: 10) {
                            HStack(spacing: 6) {
                                XOWUETouchButton(title: "BACK", mask: XOWUEGamepadButton.back, input: input, size: 38, compact: true)
                                XOWUETouchButton(title: "START", mask: XOWUEGamepadButton.start, input: input, size: 38, compact: true)
                            }
                            XOWUETouchABXY(input: input)
                        }

                        Spacer(minLength: 0)

                        VStack(spacing: 8) {
                            HStack(spacing: 6) {
                                XOWUETouchTrigger(title: "R2", left: false, input: input)
                                XOWUETouchButton(title: "R1", mask: XOWUEGamepadButton.rightShoulder, input: input, size: 39)
                            }
                            XOWUETouchStick(left: false, input: input, size: 84)
                            XOWUETouchButton(title: "R3", mask: XOWUEGamepadButton.rightThumb, input: input, size: 39)
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.bottom, max(18, geometry.safeAreaInsets.bottom + 10))
                    .transition(.opacity)
                }
            }
            .padding(.horizontal, 9)
            .padding(.top, max(32, geometry.safeAreaInsets.top + 12))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .ignoresSafeArea()
        .animation(.easeOut(duration: 0.18), value: controlsVisible)
    }
}

private struct XOWUETouchButton: View {
    let title: String
    let mask: UInt32
    @ObservedObject var input: XOWUETouchController
    var size: CGFloat = 48
    var compact = false

    private var isPressed: Bool { input.buttons & mask != 0 }

    var body: some View {
        Text(title)
            .font(.system(size: compact ? 8 : 13, weight: .black, design: .rounded))
            .tracking(compact ? 0.2 : 0.4)
            .foregroundStyle(isPressed ? Color.black : Color.white)
            .frame(width: size, height: size)
            .background(isPressed ? XOWUEPalette.yellow : Color.white.opacity(0.2), in: Circle())
            .overlay(Circle().stroke(.white.opacity(0.58), lineWidth: 1.2))
            .shadow(color: .black.opacity(0.3), radius: 5, y: 2)
            .contentShape(Circle())
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { _ in input.setButton(mask, pressed: true) }
                .onEnded { _ in input.setButton(mask, pressed: false) })
            .accessibilityLabel(title)
    }
}

private struct XOWUETouchTrigger: View {
    let title: String
    let left: Bool
    @ObservedObject var input: XOWUETouchController

    var body: some View {
        Text(title)
            .font(.system(size: 10, weight: .black, design: .rounded))
            .foregroundStyle(.white)
            .frame(width: 44, height: 34)
            .background(.white.opacity(0.2), in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11).stroke(.white.opacity(0.56), lineWidth: 1))
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { _ in input.setTrigger(left: left, pressed: true) }
                .onEnded { _ in input.setTrigger(left: left, pressed: false) })
            .accessibilityLabel(title == "L2" ? "Gatilho esquerdo" : "Gatilho direito")
    }
}

private struct XOWUETouchStick: View {
    let left: Bool
    @ObservedObject var input: XOWUETouchController
    let size: CGFloat
    @State private var offset = CGSize.zero

    var body: some View {
        let radius = size * 0.34
        ZStack {
            Circle().fill(.white.opacity(0.16))
            Circle().stroke(.white.opacity(0.58), lineWidth: 1.3)
            Circle()
                .fill(.white.opacity(0.34))
                .overlay(Circle().stroke(.white.opacity(0.7), lineWidth: 1))
                .frame(width: size * 0.43, height: size * 0.43)
                .offset(offset)
        }
        .frame(width: size, height: size)
        .shadow(color: .black.opacity(0.3), radius: 5, y: 2)
        .contentShape(Circle())
        .gesture(DragGesture(minimumDistance: 0)
            .onChanged { value in
                let dx = min(radius, max(-radius, value.translation.width))
                let dy = min(radius, max(-radius, value.translation.height))
                offset = CGSize(width: dx, height: dy)
                input.setStick(left: left, x: dx / radius, y: -dy / radius)
            }
            .onEnded { _ in
                offset = .zero
                input.setStick(left: left, x: 0, y: 0)
            })
            .accessibilityLabel(left ? "Alavanca esquerda" : "Alavanca direita")
    }
}

private struct XOWUETouchDPad: View {
    @ObservedObject var input: XOWUETouchController

    var body: some View {
        ZStack {
            XOWUETouchButton(title: "↑", mask: XOWUEGamepadButton.up, input: input, size: 27)
                .offset(y: -22)
            XOWUETouchButton(title: "↓", mask: XOWUEGamepadButton.down, input: input, size: 27)
                .offset(y: 22)
            XOWUETouchButton(title: "←", mask: XOWUEGamepadButton.left, input: input, size: 27)
                .offset(x: -22)
            XOWUETouchButton(title: "→", mask: XOWUEGamepadButton.right, input: input, size: 27)
                .offset(x: 22)
        }
        .frame(width: 76, height: 62)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Direcional")
    }
}

private struct XOWUETouchABXY: View {
    @ObservedObject var input: XOWUETouchController

    var body: some View {
        ZStack {
            XOWUETouchButton(title: "Y", mask: XOWUEGamepadButton.y, input: input).offset(y: -30)
            XOWUETouchButton(title: "A", mask: XOWUEGamepadButton.a, input: input).offset(y: 30)
            XOWUETouchButton(title: "X", mask: XOWUEGamepadButton.x, input: input).offset(x: -30)
            XOWUETouchButton(title: "B", mask: XOWUEGamepadButton.b, input: input).offset(x: 30)
        }
        .frame(width: 126, height: 126)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Botões A B X Y")
    }
}

private enum XOWUEFileStore {
    static let executableName = "default.xex"
    static let selectedGameKey = "xowue.selected-game-relative-path"

    enum StoreError: LocalizedError {
        case noDocuments
        case missingExecutable
        case ambiguousExecutable
        case invalidExecutableName
        case inaccessible(String)
        case unsafeItem(String)
        case coordination(String)
        case tooManyItems
        case emptyFolder
        case copyFailed(String)

        var errorDescription: String? {
            switch self {
            case .noDocuments:
                return "A pasta Documentos do XOWUE não está disponível."
            case .missingExecutable:
                return "Não encontrei default.xex. Coloque a pasta do jogo em Arquivos > No Meu iPhone > XOWUE > Jogos."
            case .ambiguousExecutable:
                return "Há mais de um default.xex nessa pasta. Escolha a pasta exata do jogo."
            case .invalidExecutableName:
                return "Selecione o arquivo default.xex ou a pasta que contém esse executável."
            case .inaccessible(let reason):
                return "O iOS não liberou acesso a esse item: \(reason). Copie o jogo para No Meu iPhone > XOWUE > Jogos e tente novamente."
            case .unsafeItem(let name):
                return "A importação foi interrompida porque encontrou um link ou item não suportado: \(name)."
            case .coordination(let reason):
                return "O app Arquivos não concluiu a transferência: \(reason)"
            case .tooManyItems:
                return "A pasta contém mais de 250.000 itens e não será copiada."
            case .emptyFolder:
                return "A pasta selecionada não contém arquivos."
            case .copyFailed(let reason):
                return "Falha ao copiar a pasta do jogo: \(reason)"
            }
        }
    }

    static func documents() throws -> URL {
        guard let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            throw StoreError.noDocuments
        }
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url.standardizedFileURL
    }

    /// Visible in Files > On My iPhone > XOWUE. Users can put their own game
    /// folder here without repeatedly invoking a document picker.
    static func prepareVisibleGameHome() throws -> URL {
        let docs = try documents()
        let home = docs.appendingPathComponent("Jogos", isDirectory: true)
        try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        let readme = docs.appendingPathComponent("LEIA-ME-XOWUE.txt")
        if !FileManager.default.fileExists(atPath: readme.path) {
            let instructions = """
            XOWUE — pasta local do jogo

            Copie a pasta completa do seu jogo para:
            Arquivos > No Meu iPhone > XOWUE > Jogos

            Estruturas aceitas:
            Jogos/default.xex
            Jogos/Nome do jogo/default.xex

            Mantenha WGame, KynapseRuntimeConfig e os demais arquivos ao lado
            do default.xex. Volte ao app e toque em ATUALIZAR PASTA LOCAL.
            O app reconhece a pasta automaticamente; o jogo não vem incluído
            no IPA.
            """
            try instructions.write(to: readme, atomically: true, encoding: .utf8)
        }
        return home
    }

    static func defaultXEX(in directory: URL) throws -> URL? {
        let fm = FileManager.default
        let items = try fm.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        let matches = items.filter {
            $0.lastPathComponent.caseInsensitiveCompare(executableName) == .orderedSame
        }
        guard matches.count <= 1 else { throw StoreError.ambiguousExecutable }
        guard let match = matches.first else { return nil }
        let values = try match.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        guard values.isSymbolicLink != true, values.isRegularFile == true else {
            throw StoreError.unsafeItem(match.lastPathComponent)
        }
        return match
    }

    static func discoverLocalGames() throws -> [URL] {
        let fm = FileManager.default
        let docs = try documents()
        let home = try prepareVisibleGameHome()
        let roots = [docs, home]
        var found: [String: URL] = [:]

        for root in roots {
            if try defaultXEX(in: root) != nil {
                found[root.standardizedFileURL.path] = root
            }
            let children = try fm.contentsOfDirectory(
                at: root,
                includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
                options: [.skipsHiddenFiles]
            ).sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }

            for child in children {
                if root == docs && child.standardizedFileURL == home.standardizedFileURL { continue }
                let values = try child.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
                guard values.isDirectory == true, values.isSymbolicLink != true else { continue }
                if try defaultXEX(in: child) != nil {
                    found[child.standardizedFileURL.path] = child
                }
            }
        }
        return found.values.sorted {
            $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending
        }
    }

    static func importSelection(
        _ source: URL,
        progress: @escaping (String, Double) -> Void
    ) throws -> URL {
        try withCoordinatedRead(source) { coordinated in
            let values = try coordinated.resourceValues(forKeys: [.isDirectoryKey])
            let isDirectory = values.isDirectory ?? coordinated.hasDirectoryPath
            if isDirectory {
                let gameFolder = try findGameFolder(in: coordinated)
                let docs = try documents()
                if isInside(gameFolder, parent: docs) {
                    progress("Jogo encontrado na pasta local do XOWUE.", 1)
                    return gameFolder.standardizedFileURL
                }
                return try copyGameFolder(gameFolder, progress: progress)
            }

            guard coordinated.pathExtension.caseInsensitiveCompare("xex") == .orderedSame,
                  coordinated.lastPathComponent.caseInsensitiveCompare(executableName) == .orderedSame else {
                throw StoreError.invalidExecutableName
            }
            return try importSingleXEX(coordinated, progress: progress)
        }
    }

    private static func findGameFolder(in selected: URL) throws -> URL {
        let fm = FileManager.default
        if try defaultXEX(in: selected) != nil { return selected }

        let children = try fm.contentsOfDirectory(
            at: selected,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        var matches: [URL] = []
        for child in children {
            let values = try child.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard values.isDirectory == true, values.isSymbolicLink != true else { continue }
            if try defaultXEX(in: child) != nil { matches.append(child) }
        }
        if matches.count > 1 { throw StoreError.ambiguousExecutable }
        guard let match = matches.first else { throw StoreError.missingExecutable }
        return match
    }

    private static func withCoordinatedRead<T>(
        _ source: URL,
        operation: (URL) throws -> T
    ) throws -> T {
        let started = source.startAccessingSecurityScopedResource()
        XOWUEDiagnostics.log("security_scope.start url=\(source.path) acquired=\(started)")
        defer { if started { source.stopAccessingSecurityScopedResource(); XOWUEDiagnostics.log("security_scope.stop url=\(source.path)") } }

        let docs = try documents()
        let local = isInside(source, parent: docs)
        guard started || local else {
            throw StoreError.inaccessible(source.lastPathComponent)
        }

        var result: T?
        var operationError: Error?
        var coordinationError: NSError?
        NSFileCoordinator().coordinate(readingItemAt: source, options: [], error: &coordinationError) { coordinated in
            do { result = try operation(coordinated) }
            catch { operationError = error }
        }
        if let operationError { throw operationError }
        if let coordinationError {
            throw StoreError.coordination(coordinationError.localizedDescription)
        }
        guard let result else { throw StoreError.coordination("nenhum item foi recebido") }
        return result
    }

    private static func copyGameFolder(
        _ source: URL,
        progress: @escaping (String, Double) -> Void
    ) throws -> URL {
        let fm = FileManager.default
        let home = try prepareVisibleGameHome()
        let folderName = safeFolderName(source.lastPathComponent)
        let destination = home.appendingPathComponent(folderName, isDirectory: true)
        let staging = home.appendingPathComponent(".xowue-import-\(UUID().uuidString)", isDirectory: true)
        let backup = home.appendingPathComponent(".xowue-backup-\(UUID().uuidString)", isDirectory: true)

        guard let enumerator = fm.enumerator(
            at: source,
            includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { throw StoreError.copyFailed("não foi possível ler o conteúdo da pasta") }

        var items: [URL] = []
        var totalBytes: UInt64 = 0
        for case let item as URL in enumerator {
            if items.count >= 250_000 { throw StoreError.tooManyItems }
            let values = try item.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            if values.isSymbolicLink == true || (values.isDirectory != true && values.isRegularFile != true) {
                throw StoreError.unsafeItem(item.lastPathComponent)
            }
            if values.isRegularFile == true { totalBytes += UInt64(max(0, values.fileSize ?? 0)) }
            items.append(item)
        }
        guard !items.isEmpty, totalBytes > 0 else { throw StoreError.emptyFolder }
        progress("Importando \(items.count) itens para No Meu iPhone > XOWUE > Jogos…", 0.02)
        try fm.createDirectory(at: staging, withIntermediateDirectories: true)

        do {
            let sourcePrefix = source.standardizedFileURL.path + "/"
            var copiedBytes: UInt64 = 0
            var lastReport: UInt64 = 0

            for (index, item) in items.enumerated() {
                let path = item.standardizedFileURL.path
                guard path.hasPrefix(sourcePrefix) else { throw StoreError.unsafeItem(item.lastPathComponent) }
                let relative = String(path.dropFirst(sourcePrefix.count))
                guard !relative.isEmpty else { throw StoreError.unsafeItem(item.lastPathComponent) }
                let target = URL(fileURLWithPath: relative, relativeTo: staging).standardizedFileURL
                guard isInside(target, parent: staging) else { throw StoreError.unsafeItem(item.lastPathComponent) }

                let values = try item.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey])
                if values.isDirectory == true {
                    try fm.createDirectory(at: target, withIntermediateDirectories: true)
                } else {
                    try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                    guard fm.createFile(atPath: target.path, contents: nil) else {
                        throw StoreError.copyFailed("não foi possível criar \(relative)")
                    }
                    do {
                        let input = try FileHandle(forReadingFrom: item)
                        let output = try FileHandle(forWritingTo: target)
                        defer { try? input.close(); try? output.close() }
                        while let chunk = try input.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                            try output.write(contentsOf: chunk)
                            copiedBytes += UInt64(chunk.count)
                        }
                    }
                    if copiedBytes - lastReport >= 8 * 1024 * 1024 || index % 64 == 0 || index == items.count - 1 {
                        lastReport = copiedBytes
                        let copiedMB = Double(copiedBytes) / 1_048_576
                        let totalMB = Double(totalBytes) / 1_048_576
                        progress(String(format: "Copiando %.0f / %.0f MiB · %@", copiedMB, totalMB, item.lastPathComponent),
                                 0.03 + 0.9 * min(1, Double(copiedBytes) / Double(totalBytes)))
                    }
                }
            }

            guard try defaultXEX(in: staging) != nil else { throw StoreError.missingExecutable }
            let hadDestination = fm.fileExists(atPath: destination.path)
            if hadDestination { try fm.moveItem(at: destination, to: backup) }
            do {
                try fm.moveItem(at: staging, to: destination)
            } catch {
                if hadDestination, !fm.fileExists(atPath: destination.path), fm.fileExists(atPath: backup.path) {
                    try? fm.moveItem(at: backup, to: destination)
                }
                throw error
            }
            if hadDestination { try? fm.removeItem(at: backup) }
            progress("Pasta copiada e default.xex detectado.", 1)
            return destination
        } catch {
            try? fm.removeItem(at: staging)
            throw error
        }
    }

    private static func importSingleXEX(
        _ source: URL,
        progress: @escaping (String, Double) -> Void
    ) throws -> URL {
        let fm = FileManager.default
        let home = try prepareVisibleGameHome()
        let destination = home.appendingPathComponent("XEX importado", isDirectory: true)
        let staging = home.appendingPathComponent(".xowue-xex-\(UUID().uuidString)", isDirectory: true)
        let backup = home.appendingPathComponent(".xowue-xex-backup-\(UUID().uuidString)", isDirectory: true)

        progress("Copiando default.xex para a pasta local do app…", 0.2)
        try fm.createDirectory(at: staging, withIntermediateDirectories: true)
        do {
            try fm.copyItem(at: source, to: staging.appendingPathComponent(executableName))
            let hadDestination = fm.fileExists(atPath: destination.path)
            if hadDestination { try fm.moveItem(at: destination, to: backup) }
            do {
                try fm.moveItem(at: staging, to: destination)
            } catch {
                if hadDestination, !fm.fileExists(atPath: destination.path), fm.fileExists(atPath: backup.path) {
                    try? fm.moveItem(at: backup, to: destination)
                }
                throw error
            }
            if hadDestination { try? fm.removeItem(at: backup) }
            progress("XEX recebido. Copie também a pasta completa para incluir os assets.", 1)
            return destination
        } catch {
            try? fm.removeItem(at: staging)
            throw StoreError.copyFailed(error.localizedDescription)
        }
    }

    private static func safeFolderName(_ raw: String) -> String {
        let forbidden = CharacterSet(charactersIn: "/:\\")
            .union(.controlCharacters)
        let safe = raw.components(separatedBy: forbidden).filter { !$0.isEmpty }.joined(separator: "_")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return safe.isEmpty || safe == "." || safe == ".." ? "Jogo Xbox 360" : safe
    }

    private static func isInside(_ item: URL, parent: URL) -> Bool {
        let childPath = item.standardizedFileURL.path
        let parentPath = parent.standardizedFileURL.path
        return childPath == parentPath || childPath.hasPrefix(parentPath + "/")
    }
}

private enum XOWUERuntime {
    struct Outcome {
        let code: Int32
        let text: String
    }

    enum RuntimeError: LocalizedError {
        case invalidXEX(String)
        var errorDescription: String? {
            switch self {
            case .invalidXEX(let text): return "O arquivo não passou na validação XEX2: \(text)"
            }
        }
    }

    static func inspectAndBoot(_ xex: URL) throws -> Outcome {
        XOWUEDiagnostics.log("xex.inspect.start path=\(xex.path)")
        var inspectBuffer = [CChar](repeating: 0, count: 2048)
        let inspectCode = xex.path.withCString { path in
            inspectBuffer.withUnsafeMutableBufferPointer { output in
                xowue_inspect_xex(path, output.baseAddress, output.count)
            }
        }
        guard inspectCode == 0 else {
            let message = String(cString: inspectBuffer)
            XOWUEDiagnostics.recordCrash("XEX_INSPECT_FAILED path=\(xex.path) detail=\(message)")
            throw RuntimeError.invalidXEX(message)
        }
        XOWUEDiagnostics.log("xex.inspect.ok \(String(cString: inspectBuffer))")

        var outputBuffer = [CChar](repeating: 0, count: 32768)
        let code = xex.path.withCString { path in
            outputBuffer.withUnsafeMutableBufferPointer { output in
                xowue_boot_xex(path, output.baseAddress, output.count)
            }
        }
        let text = String(cString: outputBuffer)
        XOWUEDiagnostics.log("runtime.native_return code=\(code) result=\(text.replacingOccurrences(of: "\n", with: " | "))")
        return Outcome(code: code, text: text)
    }
}

@MainActor
private final class XOWUEGameLibrary: ObservableObject {
    enum Phase: String {
        case scanning, missing, ready, importing, booting, needsChoice, stopped, failed
        var title: String {
            switch self {
            case .scanning: return "PROCURANDO O JOGO"
            case .missing: return "PASTA DO JOGO NÃO ENCONTRADA"
            case .ready: return "JOGO DETECTADO"
            case .importing: return "IMPORTANDO PASTA"
            case .booting: return "JOGO EM EXECUÇÃO"
            case .needsChoice: return "ESCOLHA A INSTALAÇÃO"
            case .stopped: return "BOOT PAROU"
            case .failed: return "AÇÃO FALHOU"
            }
        }
        var tint: Color {
            switch self {
            case .scanning, .importing, .booting: return XOWUEPalette.yellow
            case .missing, .needsChoice: return XOWUEPalette.muted
            case .ready: return XOWUEPalette.green
            case .stopped, .failed: return XOWUEPalette.red
            }
        }
    }

    @Published var phase: Phase = .scanning
    @Published var candidates: [URL] = []
    @Published var selectedGame: URL?
    @Published var status = "Preparando a pasta local do jogo…"
    @Published var detail = "O XOWUE procura default.xex ao abrir."
    @Published var progress = 0.0
    @Published var bootOutput = "Nenhum teste de boot executado."
    @Published var isBusy = false
    @Published var gameSurfacePresented = false

    var selectedLocation: String {
        guard let selectedGame, let docs = try? XOWUEFileStore.documents() else {
            return "No Meu iPhone > XOWUE > Jogos"
        }
        let path = selectedGame.standardizedFileURL.path
        let prefix = docs.path + "/"
        guard path.hasPrefix(prefix) else { return path }
        return "No Meu iPhone > XOWUE > " + String(path.dropFirst(prefix.count))
    }

    func refresh() {
        guard !isBusy else { return }
        XOWUEDiagnostics.log("scan.start roots=Documents,Documents/Jogos")
        phase = .scanning
        status = "Procurando default.xex nas pastas locais…"
        detail = "Arquivos > No Meu iPhone > XOWUE > Jogos"
        Task { @MainActor in
            do {
                let found = try await Task.detached(priority: .utility) {
                    try XOWUEFileStore.discoverLocalGames()
                }.value
                candidates = found
                XOWUEDiagnostics.log("scan.complete count=\(found.count) paths=\(found.map(\.path).joined(separator: "|"))")
                let saved = UserDefaults.standard.string(forKey: XOWUEFileStore.selectedGameKey)
                if let saved, let preferred = found.first(where: { Self.relativePath(for: $0) == saved }) {
                    selectGame(preferred)
                } else if found.count == 1, let only = found.first {
                    selectGame(only)
                } else if found.count > 1 {
                    selectedGame = nil
                    phase = .needsChoice
                    status = "Encontrei \(found.count) pastas com default.xex."
                    detail = "Escolha qual instalação quer testar."
                } else {
                    selectedGame = nil
                    phase = .missing
                    status = "Ainda não encontrei o jogo."
                    detail = "Copie a pasta completa para No Meu iPhone > XOWUE > Jogos."
                }
            } catch {
                fail(error.localizedDescription)
            }
        }
    }

    func selectGame(_ folder: URL) {
        XOWUEDiagnostics.log("game.selected path=\(folder.path)")
        selectedGame = folder
        candidates = candidates.isEmpty ? [folder] : candidates
        if let relative = Self.relativePath(for: folder) {
            UserDefaults.standard.set(relative, forKey: XOWUEFileStore.selectedGameKey)
        }
        phase = .ready
        status = "Jogo encontrado: \(folder.lastPathComponent)"
        detail = "Toque em ABRIR JOGO para validar o XEX2 e testar o entry point."
    }

    func handlePickerResult(_ result: Result<[URL], Error>) {
        XOWUEDiagnostics.log("picker.result received")
        do {
            guard let url = try result.get().first else {
                status = "Nenhum item foi selecionado."
                return
            }
            importItem(url, startAfterImport: true)
        } catch {
            if error is CancellationError {
                XOWUEDiagnostics.log("picker.result cancellation")
                status = "Seleção cancelada. A pasta local continua disponível."
            } else {
                fail(error.localizedDescription)
            }
        }
    }

    func handleOpenURL(_ url: URL) {
        XOWUEDiagnostics.log("app.open_url path=\(url.path)")
        importItem(url, startAfterImport: true)
    }

    func importItem(_ url: URL, startAfterImport: Bool) {
        guard !isBusy else { return }
        isBusy = true
        phase = .importing
        progress = 0.01
        status = "Recebendo \(url.lastPathComponent)…"
        detail = "O app manterá a pasta na área local do XOWUE."
        XOWUEDiagnostics.log("import.start source=\(url.path)")
        Task { @MainActor in
            do {
                let folder = try await Task.detached(priority: .userInitiated) {
                    try XOWUEFileStore.importSelection(url) { text, fraction in
                        Task { @MainActor in
                            self.progress = max(0, min(1, fraction))
                            self.status = text
                            XOWUEDiagnostics.log("import.progress fraction=\(fraction) message=\(text)")
                        }
                    }
                }.value
                isBusy = false
                candidates = (try? XOWUEFileStore.discoverLocalGames()) ?? [folder]
                selectGame(folder)
                if startAfterImport { runBoot() }
            } catch {
                isBusy = false
                fail(error.localizedDescription)
            }
        }
    }

    func runBoot() {
        guard !isBusy else { return }
        guard let game = selectedGame else {
            status = "Escolha ou copie uma pasta que contenha default.xex."
            phase = .missing
            return
        }
        gameSurfacePresented = true
        isBusy = true
        phase = .booting
        progress = 0.15
        status = "Abrindo X-MEN ORIGINS: WOLVERINE…"
        detail = "Inicializando o runtime PPC, a fila Xenos e o caminho de frames no KosmicKrisp."
        bootOutput = "O jogo está sendo iniciado."
        let executablePath = game.appendingPathComponent(XOWUEFileStore.executableName).path
        XOWUEDiagnostics.bootStarted(path: executablePath, build: XOWUEBuild.number)
        Task { @MainActor in
            do {
                let executable = game.appendingPathComponent(XOWUEFileStore.executableName)
                let outcome = try await Task.detached(priority: .userInitiated) {
                    try XOWUERuntime.inspectAndBoot(executable)
                }.value
                isBusy = false
                progress = 1
                bootOutput = outcome.text
                XOWUEDiagnostics.bootFinished(code: outcome.code, text: outcome.text)
                if outcome.code == 3 {
                    phase = .stopped
                    status = "O runtime parou em um pedido de firmware."
                    detail = "O menu e o primeiro frame ainda não foram alcançados."
                } else if outcome.code == 0 {
                    phase = .stopped
                    status = "O entry point retornou; o jogo não concluiu o boot."
                    detail = "O teste confirma somente o retorno do entry point."
                } else {
                    phase = .failed
                    status = "A tentativa de boot encontrou um bloqueio."
                    detail = "O diagnóstico abaixo identifica o ponto observado."
                }
            } catch {
                isBusy = false
                phase = .failed
                status = "Não foi possível validar ou executar o XEX."
                detail = error.localizedDescription
                bootOutput = error.localizedDescription
                XOWUEDiagnostics.bootFailed(error.localizedDescription)
            }
        }
    }

    private func fail(_ message: String) {
        XOWUEDiagnostics.log("action.failed message=\(message)")
        isBusy = false
        phase = .failed
        status = "Ação não concluída."
        detail = message
        bootOutput = message
    }

    private static func relativePath(for folder: URL) -> String? {
        guard let docs = try? XOWUEFileStore.documents() else { return nil }
        let path = folder.standardizedFileURL.path
        let prefix = docs.path + "/"
        guard path.hasPrefix(prefix) else { return nil }
        return String(path.dropFirst(prefix.count))
    }
}

private enum XOWUEPalette {
    static let background = Color(rgb: 0x080B12)
    static let panel = Color(rgb: 0x151B25)
    static let panelRaised = Color(rgb: 0x202A3B)
    static let yellow = Color(rgb: 0xF5C12B)
    static let yellowLight = Color(rgb: 0xFFE18A)
    static let blue = Color(rgb: 0x163A70)
    static let blueLight = Color(rgb: 0x70B6FF)
    static let muted = Color(rgb: 0xA3A7AC)
    static let green = Color(rgb: 0x57D69A)
    static let red = Color(rgb: 0xFF5B61)
    static let white = Color(rgb: 0xF5F7FA)
}

private extension Color {
    init(rgb: UInt32) {
        self.init(
            .sRGB,
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255,
            opacity: 1
        )
    }
}

private struct XOWUEBrandMark: View {
    var body: some View {
        Image("WolverineMark")
            .resizable()
            .scaledToFit()
            .frame(width: 68, height: 68)
            .clipShape(RoundedRectangle(cornerRadius: 19))
            .overlay(RoundedRectangle(cornerRadius: 19).stroke(XOWUEPalette.blueLight.opacity(0.48), lineWidth: 1))
            .shadow(color: XOWUEPalette.yellow.opacity(0.14), radius: 10, y: 4)
            .accessibilityHidden(true)
    }
}

private struct XOWUEStatusPill: View {
    let phase: XOWUEGameLibrary.Phase
    var body: some View {
        HStack(spacing: 7) {
            Circle().fill(phase.tint).frame(width: 8, height: 8)
            Text(phase.title)
                .font(.system(size: 10, weight: .heavy, design: .rounded))
                .tracking(1)
                .foregroundStyle(phase.tint)
        }
        .padding(.horizontal, 11)
        .padding(.vertical, 8)
        .background(phase.tint.opacity(0.10), in: Capsule())
        .overlay(Capsule().stroke(phase.tint.opacity(0.25), lineWidth: 1))
    }
}

private struct XOWUERootView: View {
    @StateObject private var library = XOWUEGameLibrary()
    @State private var showingImporter = false
    @Environment(\.scenePhase) private var scenePhase

    private var buildNumber: String { XOWUEBuild.number }

    var body: some View {
        ZStack {
            XOWUEPalette.background.ignoresSafeArea()
            RadialGradient(
                colors: [Color(rgb: 0x163A70).opacity(0.30), .clear],
                center: .topTrailing, startRadius: 0, endRadius: 470
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    gameLibraryCard
                    runtimeCard
                    footer
                }
                .padding(.horizontal, 18)
                .padding(.top, 18)
                .padding(.bottom, 30)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $showingImporter) {
            XOWUEDocumentPicker(
                isPresented: $showingImporter,
                completion: library.handlePickerResult
            )
            .ignoresSafeArea()
        }
        .fullScreenCover(isPresented: $library.gameSurfacePresented) {
            XOWUEGameSurfaceScreen(library: library)
        }
        .onOpenURL { url in
            library.handleOpenURL(url)
        }
        .onAppear {
            library.refresh()
        }
        .onChange(of: scenePhase) { _, newValue in
            if newValue == .active { library.refresh() }
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            XOWUEBrandMark()
            VStack(alignment: .leading, spacing: 4) {
                Text("XOWUE")
                    .font(.system(size: 15, weight: .black, design: .rounded))
                    .tracking(2.5)
                    .foregroundStyle(XOWUEPalette.yellow)
                Text("X-MEN ORIGINS")
                    .font(.system(size: 20, weight: .black, design: .rounded))
                    .foregroundStyle(XOWUEPalette.white)
                    .minimumScaleFactor(0.75)
                    .lineLimit(1)
                Text("WOLVERINE")
                    .font(.system(size: 17, weight: .black, design: .rounded))
                    .tracking(1.1)
                    .foregroundStyle(XOWUEPalette.blueLight)
                    .lineLimit(1)
                Text("XBOX 360  ·  TITLE ID 41560816")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(XOWUEPalette.muted)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            Spacer(minLength: 2)
            VStack(spacing: 2) {
                Text("BUILD")
                    .font(.system(size: 9, weight: .heavy, design: .rounded))
                    .tracking(1.3)
                    .foregroundStyle(XOWUEPalette.yellowLight)
                Text(buildNumber)
                    .font(.system(size: 26, weight: .black, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(XOWUEPalette.white)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(XOWUEPalette.panelRaised, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(XOWUEPalette.yellow.opacity(0.35), lineWidth: 1))
            .accessibilityIdentifier("xowue-build-number")
        }
        .padding(.bottom, 2)
    }

    private var gameLibraryCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("BIBLIOTECA LOCAL", systemImage: "externaldrive.fill")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .tracking(1.2)
                    .foregroundStyle(XOWUEPalette.yellowLight)
                Spacer()
                XOWUEStatusPill(phase: library.phase)
            }

            Text(library.status)
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .foregroundStyle(XOWUEPalette.white)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("xowue-library-status")
            Text(library.detail)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(XOWUEPalette.muted)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)

            if library.isBusy {
                ProgressView(value: library.progress)
                    .tint(XOWUEPalette.yellow)
                Text(library.status)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(XOWUEPalette.muted)
                    .lineLimit(2)
            }

            if library.candidates.count > 1 {
                VStack(spacing: 8) {
                    ForEach(library.candidates, id: \.path) { folder in
                        Button {
                            library.selectGame(folder)
                        } label: {
                            HStack {
                                Image(systemName: library.selectedGame == folder ? "checkmark.circle.fill" : "folder.fill")
                                    .foregroundStyle(XOWUEPalette.yellow)
                                Text(folder.lastPathComponent)
                                    .foregroundStyle(XOWUEPalette.white)
                                    .lineLimit(1)
                                Spacer()
                                Text("default.xex")
                                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                    .foregroundStyle(XOWUEPalette.muted)
                            }
                            .padding(11)
                            .background(XOWUEPalette.panelRaised, in: RoundedRectangle(cornerRadius: 11))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if library.selectedGame != nil {
                HStack(spacing: 8) {
                    Image(systemName: "folder")
                        .foregroundStyle(XOWUEPalette.yellow)
                    Text(library.selectedLocation)
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(XOWUEPalette.muted)
                        .lineLimit(2)
                        .textSelection(.enabled)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(XOWUEPalette.background.opacity(0.8), in: RoundedRectangle(cornerRadius: 10))
            } else if library.phase == .missing {
                VStack(alignment: .leading, spacing: 6) {
                    Text("PASTA NATIVA DO APP")
                        .font(.system(size: 9, weight: .heavy, design: .rounded))
                        .tracking(1.2)
                        .foregroundStyle(XOWUEPalette.yellow)
                    Text("Arquivos  ›  No Meu iPhone  ›  XOWUE  ›  Jogos")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(XOWUEPalette.white)
                    Text("Copie a pasta completa do jogo para Jogos. O app detecta default.xex ao voltar.")
                        .font(.system(size: 11))
                        .foregroundStyle(XOWUEPalette.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(XOWUEPalette.yellow.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(XOWUEPalette.yellow.opacity(0.22), lineWidth: 1))
            }

            HStack(spacing: 10) {
                Button {
                    if library.selectedGame != nil {
                        library.runBoot()
                    } else {
                        showingImporter = true
                    }
                } label: {
                    HStack(spacing: 9) {
                        Image(systemName: library.selectedGame == nil ? "folder.badge.plus" : "play.fill")
                        Text(library.selectedGame == nil ? "IMPORTAR PASTA / XEX" : "ABRIR JOGO")
                        Spacer(minLength: 0)
                        Image(systemName: "arrow.right")
                    }
                    .font(.system(size: 12, weight: .black, design: .rounded))
                    .tracking(0.5)
                    .foregroundStyle(Color(rgb: 0x10151D))
                    .padding(.horizontal, 15)
                    .frame(height: 50)
                    .background(
                        LinearGradient(colors: [XOWUEPalette.yellowLight, XOWUEPalette.yellow],
                                       startPoint: .topLeading, endPoint: .bottomTrailing),
                        in: RoundedRectangle(cornerRadius: 14)
                    )
                }
                .buttonStyle(.plain)
                .disabled(library.isBusy)
                .accessibilityIdentifier("xowue-open-game")

                Button {
                    library.refresh()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(XOWUEPalette.white)
                        .frame(width: 50, height: 50)
                        .background(XOWUEPalette.panelRaised, in: RoundedRectangle(cornerRadius: 14))
                }
                .buttonStyle(.plain)
                .disabled(library.isBusy)
                .accessibilityLabel("Atualizar pasta local")
            }

            Button {
                showingImporter = true
            } label: {
                Label("Selecionar uma pasta ou default.xex", systemImage: "doc.badge.plus")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(XOWUEPalette.yellowLight)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .disabled(library.isBusy)
        }
        .padding(17)
        .background(XOWUEPalette.panel.opacity(0.97), in: RoundedRectangle(cornerRadius: 19))
        .overlay(RoundedRectangle(cornerRadius: 19).stroke(.white.opacity(0.08), lineWidth: 1))
    }

    private var runtimeCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("ESTADO REAL DO RUNTIME", systemImage: "cpu")
                    .font(.system(size: 11, weight: .heavy, design: .rounded))
                    .tracking(1)
                    .foregroundStyle(XOWUEPalette.yellowLight)
                Spacer()
                Text("ARM64")
                    .font(.system(size: 9, weight: .heavy, design: .monospaced))
                    .foregroundStyle(XOWUEPalette.green)
            }

            runtimeRow("Recompilação AOT", detail: "345 unidades ligadas ao runtime", icon: "checkmark.circle.fill", tint: XOWUEPalette.green)
            runtimeRow("Scheduler PPC / KTHREAD", detail: "Threads guest, espera/suspensão, TLS e encerramento pelo kernel Xbox", icon: "point.3.connected.trianglepath.dotted", tint: XOWUEPalette.yellowLight)
            runtimeRow("Memória física Xbox", detail: "Alocação, endereços físicos e mapeamento guest usados pelo XEX", icon: "point.3.connected.trianglepath.dotted", tint: XOWUEPalette.yellowLight)
            runtimeRow("Frontend Xenos / PM4", detail: "Ring buffer lido via CP_RB_WPTR; fetch de swap, draws e buffers indiretos contabilizados", icon: "point.3.connected.trianglepath.dotted", tint: XOWUEPalette.yellowLight)
            runtimeRow("KosmicKrisp · Metal WSI", detail: "Frames RGBA do frontbuffer enviados à swapchain Vulkan → Metal a 60 Hz", icon: "point.3.connected.trianglepath.dotted", tint: XOWUEPalette.blueLight)

            VStack(alignment: .leading, spacing: 6) {
                Text("KosmicKrisp permanece como backend gráfico.")
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .foregroundStyle(XOWUEPalette.white)
                Text("KosmicKrisp continua como backend gráfico. A fila Xenos acompanha submissões do XEX, processa os swaps e encaminha o frontbuffer RGBA para a superfície Vulkan → Metal. O HUD tátil injeta estados XInput no guest.")
                    .font(.system(size: 11))
                    .foregroundStyle(XOWUEPalette.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(XOWUEPalette.yellow.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(XOWUEPalette.yellow.opacity(0.2), lineWidth: 1))

            VStack(alignment: .leading, spacing: 7) {
                Text("RESULTADO DO ÚLTIMO TESTE")
                    .font(.system(size: 9, weight: .heavy, design: .rounded))
                    .tracking(1.2)
                    .foregroundStyle(XOWUEPalette.muted)
                Text(library.bootOutput)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(XOWUEPalette.white.opacity(0.88))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("xowue-boot-output")
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 12))

            HStack(spacing: 16) {
                if let url = XOWUEDiagnostics.fileURL(named: XOWUEDiagnostics.diagnosticFilename) {
                    ShareLink(item: url) {
                        Label(XOWUEDiagnostics.diagnosticFilename, systemImage: "doc.text")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(XOWUEPalette.yellowLight)
                    }
                }
                if let url = XOWUEDiagnostics.fileURL(named: XOWUEDiagnostics.crashFilename) {
                    ShareLink(item: url) {
                        Label(XOWUEDiagnostics.crashFilename, systemImage: "exclamationmark.3")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(XOWUEPalette.blueLight)
                    }
                }
            }
            Text("Logs salvos em Arquivos > No Meu iPhone > XOWUE")
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundStyle(XOWUEPalette.muted)
        }
        .padding(17)
        .background(XOWUEPalette.panel.opacity(0.94), in: RoundedRectangle(cornerRadius: 19))
        .overlay(RoundedRectangle(cornerRadius: 19).stroke(.white.opacity(0.08), lineWidth: 1))
    }

    private func runtimeRow(_ title: String, detail: String, icon: String, tint: Color) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .bold))
                .foregroundStyle(tint)
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 12, weight: .bold, design: .rounded)).foregroundStyle(XOWUEPalette.white)
                Text(detail).font(.system(size: 10)).foregroundStyle(XOWUEPalette.muted)
            }
            Spacer()
        }
    }

    private var footer: some View {
        HStack {
            Text("XOWUE  ·  BUILD \(buildNumber)")
                .font(.system(size: 9, weight: .heavy, design: .monospaced))
                .tracking(1)
                .foregroundStyle(XOWUEPalette.muted)
            Spacer()
            Text("TITLE 41560816")
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(XOWUEPalette.muted.opacity(0.8))
        }
        .padding(.horizontal, 4)
    }
}
