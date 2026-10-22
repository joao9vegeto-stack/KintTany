import SwiftUI
import UniformTypeIdentifiers
import Foundation

@_silgen_name("poptst_engine_start") private func engineStart(_ game: UnsafePointer<CChar>, _ data: UnsafePointer<CChar>) -> Int32
@_silgen_name("poptst_engine_pump") private func enginePump()
@_silgen_name("poptst_engine_status") private func engineStatus() -> UnsafePointer<CChar>?
@_silgen_name("poptst_engine_can_start") private func engineCanStart() -> Int32
@_silgen_name("poptst_engine_set_trace_path") private func engineSetTracePath(_ path: UnsafePointer<CChar>)

private enum BuildInfo {
    /* The bundle build number is the source of truth, so future builds
       update both the on-screen title and the diagnostic filename. */
    static var number: String {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String) ?? "27"
    }
    static var version: String {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "2.7"
    }
    static var title: String { "PoPTST · BUILD \(number)" }
}

private enum SandStyle {
    static let night = Color(red: 0.035, green: 0.055, blue: 0.10)
    static let panel = Color(red: 0.079, green: 0.102, blue: 0.16)
    static let gold = Color(red: 0.93, green: 0.72, blue: 0.41)
    static let pale = Color(red: 0.97, green: 0.91, blue: 0.80)
    static let muted = Color(red: 0.66, green: 0.70, blue: 0.75)
    static let red = Color(red: 0.98, green: 0.48, blue: 0.41)
}

private enum DiagnosticLog {
    static var nativeTraceURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            .appendingPathComponent("PoPTST-Crash-Build-\(BuildInfo.number).txt")
    }
    static var url: URL {
        let doc = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        return doc.appendingPathComponent("PoPTST-Diagnostico-Build-\(BuildInfo.number).txt")
    }
    static func append(_ text: String) {
        let f = url
        let time = ISO8601DateFormatter().string(from: Date())
        let row = "[\(time)] \(text.replacingOccurrences(of: "\n", with: " "))\n"
        if !FileManager.default.fileExists(atPath: f.path) {
            try? "PoPTST Retail iOS — BUILD \(BuildInfo.number) · v\(BuildInfo.version) — diagnóstico de inicialização\n".write(to: f, atomically: true, encoding: .utf8)
        }
        if let handle = try? FileHandle(forWritingTo: f) {
            defer { try? handle.close() }
            try? handle.seekToEnd()
            handle.write(Data(row.utf8))
        }
    }
}

@MainActor final class GameLibrary: ObservableObject {
    enum Phase { case empty, importing, ready, launching, playing, suspended, failed }
    @Published var phase: Phase = .empty
    @Published var message = "Selecione a pasta extraída da sua retail original."
    @Published var detail = "Apenas a versão Xbox NTSC compatível com o rePOP."
    @Published var progress: Double = 0
    @Published var installPath: String?
    @Published var lastError: String?
    private var timer: Timer?
    private var latestNativeStatus = ""

    var hasGame: Bool { installPath != nil }
    var busy: Bool { phase == .importing || phase == .launching }
    var canPlay: Bool { hasGame && (phase == .ready || phase == .failed) && engineCanStart() != 0 }

    init() {
        DiagnosticLog.append("BUILD \(BuildInfo.number) / v\(BuildInfo.version) — iniciado. Preparando Documents/xbox-retail (Arquivos).")
        // Read crash breadcrumbs on next launch, even if iOS/LiveContainer never
        // generated a JetsamEvent or .ips. Kept in Files > PoPTST > Documents.
        if let existing = try? String(contentsOf: DiagnosticLog.nativeTraceURL, encoding: .utf8) {
            let lines = existing.split(separator: "\n").suffix(6).joined(separator: " | ")
            if !lines.isEmpty {
                DiagnosticLog.append("Últimas etapas nativas da sessão anterior: \(lines)")
            }
        }
        Task.detached(priority: .utility) {
            do {
                let visible = try RetailFolderInstaller.prepareVisibleGameHome()
                let old = try RetailFolderInstaller.applicationSupport().appendingPathComponent("xbox-retail",isDirectory:true)
                let fm = FileManager.default
                let candidate = (try? RetailFolderInstaller.localRetailCandidate()) ?? old
                guard fm.fileExists(atPath: candidate.appendingPathComponent("default.xbe").path) else {
                    await MainActor.run {
                        self.message = "Pasta criada em No Meu iPhone > PoPTST > xbox-retail"
                        self.detail = "Copie seus arquivos e toque VERIFICAR PASTA LOCAL E JOGAR."
                        DiagnosticLog.append("Pasta disponível: \(visible.lastPathComponent)")
                    }
                    return
                }
                let hash = try RetailFolderInstaller.validate(candidate)
                await MainActor.run {
                    self.installPath = candidate.path
                    self.phase = .ready
                    self.message = "Jogo encontrado na pasta local."
                    self.detail = "Retail verificada • \(hash.prefix(12))…"
                    DiagnosticLog.append("Instalação validada: \(candidate.lastPathComponent)")
                }
            } catch {
                await MainActor.run {
                    self.phase = .failed
                    self.lastError = error.localizedDescription
                    self.message = "Arquivos encontrados, mas há um problema"
                    self.detail = error.localizedDescription
                    DiagnosticLog.append("Pré-validação local: \(error.localizedDescription)")
                }
            }
        }
    }

    func cancelledPicker() {
        if phase == .empty { message = "Nenhuma pasta foi selecionada." }
        DiagnosticLog.append("Seletor de pasta fechado sem seleção.")
    }

    func filePickerFailed(_ error: Error) {
        failure("Não foi possível abrir a pasta", error.localizedDescription)
    }

    func importGame(_ url: URL) {
        guard !busy else { return }
        phase = .importing
        progress = 0
        lastError = nil
        message = "Pasta selecionada: \(url.lastPathComponent)"
        detail = "Primeiro, conferindo os arquivos; depois, copiando para o iPhone."
        DiagnosticLog.append("Seletor retornou pasta: \(url.lastPathComponent).")
        performImport { progress in try RetailFolderInstaller.install(url, progress: progress) }
    }

    func importFromDocuments() {
        guard !busy else { return }
        phase = .importing
        progress = 0
        message = "Verificando No Meu iPhone > PoPTST > xbox-retail"
        detail = "Leitura direta: sem seletor, sem upload, sem copiar os arquivos novamente."
        DiagnosticLog.append("Verificação local Documents/xbox-retail sem document picker.")
        performImport { progress in try RetailFolderInstaller.installFromDocuments(progress: progress) }
    }

    private func performImport(_ work: @escaping (@escaping (String, Double) -> Void) throws -> RetailFolderInstaller.Inventory) {
        Task.detached(priority: .userInitiated) {
            do {
                let result = try work { text, portion in
                    Task { @MainActor in
                        self.progress = max(0, min(1, portion))
                        self.message = text
                        if portion > 0.05 { self.detail = "Os arquivos de jogo ficam apenas no seu iPhone." }
                    }
                }
                await MainActor.run {
                    self.installPath = result.installURL.path
                    self.phase = .ready
                    self.progress = 1
                    self.message = "Retail validada com sucesso."
                    self.detail = "SHA-256: \(result.sha256.prefix(16))… • Iniciando o jogo"
                    DiagnosticLog.append("Importação concluída, SHA-256 \(result.sha256). Início automático.")
                    // Rechecking a folder must NOT attempt to restart an
                    // already-terminated Xbox VM with live NV2A worker threads.
                    if engineCanStart() != 0 {
                        self.play()
                    } else {
                        self.phase = .suspended
                        self.message = "Retail validada; sessão encerrada"
                        self.detail = "Para um novo boot, encerre e reabra o PoPTST/LiveContainer."
                        DiagnosticLog.append("Sessão anterior permanece retida no host; boot duplicado bloqueado.")
                    }
                }
            } catch {
                await MainActor.run {
                    self.failure("Não foi possível iniciar essa retail", error.localizedDescription)
                }
            }
        }
    }

    private func failure(_ title: String, _ cause: String) {
        phase = .failed
        lastError = cause
        message = title
        detail = cause
        DiagnosticLog.append("FALHA: \(title) — \(cause)")
    }


    /* Restore an existing RETAIL save-folder backup before a new guest boot.
     * This is NOT an instantaneous savestate: the game's own Load menu then
     * reads the restored save. Never overwrite a running guest's save files. */
    func restoreNativeSaveAndPlay() {
        guard canPlay, engineCanStart() != 0 else {
            failure("Restaurar só antes do boot","Valide a pasta retail e reinicie o aplicativo caso já tenha jogado.")
            return
        }
        let fm=FileManager.default
        do {
            let data=try RetailFolderInstaller.applicationSupport().appendingPathComponent("userdata",isDirectory:true)
            let backup=data.appendingPathComponent("backups/native-save-slot",isDirectory:true)
            let destination=data.appendingPathComponent("saves/xbox-retail",isDirectory:true)
            /* B28: never restore synthetic .devices/Partition*.img from B27!
               Only the actual guest title-save folders are replaceable.
               Stage the files and back up the previous state BEFORE mutation. */
            let fmSaveFolders=["UDATA","TDATA","UserData","TitleData"]
            let available=fmSaveFolders.filter {
                fm.fileExists(atPath: backup.appendingPathComponent($0,isDirectory:true).path)
            }
            guard !available.isEmpty else {
                failure("Backup sem arquivos de save","O backup antigo contém apenas arquivos internos Xbox. Salve no jogo e faça um novo backup.")
                return
            }
            let previous=data.appendingPathComponent("backups/native-save-before-restore",isDirectory:true)
            let pending=data.appendingPathComponent("backups/native-save-restore-pending",isDirectory:true)
            try fm.createDirectory(at:destination,withIntermediateDirectories:true)
            try? fm.removeItem(at:pending)
            try? fm.removeItem(at:previous)
            try fm.createDirectory(at:pending,withIntermediateDirectories:true)
            try fm.createDirectory(at:previous,withIntermediateDirectories:true)
            for folder in available {
                try fm.copyItem(at: backup.appendingPathComponent(folder,isDirectory:true),
                                to: pending.appendingPathComponent(folder,isDirectory:true))
                let active=destination.appendingPathComponent(folder,isDirectory:true)
                if fm.fileExists(atPath:active.path) {
                    try fm.copyItem(at:active,to:previous.appendingPathComponent(folder,isDirectory:true))
                }
            }
            var installed=[String]()
            do {
                for folder in available {
                    let target=destination.appendingPathComponent(folder,isDirectory:true)
                    if fm.fileExists(atPath:target.path) { try fm.removeItem(at:target) }
                    installed.append(folder)
                    try fm.moveItem(at:pending.appendingPathComponent(folder,isDirectory:true),to:target)
                }
            } catch {
                for folder in installed {
                    let target=destination.appendingPathComponent(folder,isDirectory:true)
                    try? fm.removeItem(at:target)
                    let original=previous.appendingPathComponent(folder,isDirectory:true)
                    if fm.fileExists(atPath:original.path) { try? fm.copyItem(at:original,to:target) }
                }
                throw error
            }
            DiagnosticLog.append("SAVE B28: restored ONLY guest UDATA/TDATA titles; preserved synthetic .devices partitions")
            message="Backup restaurado • iniciar jogo"
            detail="Use Carregar/Continuar no menu do jogo para abrir seu progresso. Não é savestate instantâneo."
            play()
        } catch {
            failure("Falha ao restaurar save",error.localizedDescription)
        }
    }

    func play() {
        guard let dir = installPath, !busy else { return }
        guard engineCanStart() != 0 else {
            failure("Sessão Xbox já encerrada",
                    "A janela e os recursos nativos ficaram retidos após o boot anterior. Encerre e reabra o aplicativo para iniciar uma nova sessão.")
            return
        }
        phase = .launching
        message = "Preparando Xbox AOT + Vulkan/Metal…"
        detail = "O jogo será exibido na janela gráfica SDL3."
        lastError = nil
        DiagnosticLog.append("Solicitação de boot retail recebida.")
        do {
            let root = try RetailFolderInstaller.applicationSupport()
            let data = root.appendingPathComponent("userdata", isDirectory: true)
            try FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
            // Upstream rePOP port/android SaveFolders.prepare preserves title
            // saves from the extracted disc. Match that non-overwriting policy.
            try RetailFolderInstaller.prepareSaveFolders(gameDir: URL(fileURLWithPath: dir),
                                                         dataDir: data)
            // Main thread opens the trace before pthread_create, so even a
            // synchronous SIGBUS/SIGILL has a file descriptor to write into.
            DiagnosticLog.nativeTraceURL.path.withCString { engineSetTracePath($0) }
            DiagnosticLog.append("Trace nativo: \(DiagnosticLog.nativeTraceURL.lastPathComponent)")
            let code = dir.withCString { game in
                data.path.withCString { dest in engineStart(game, dest) }
            }
            guard code == 0 else {
                let reason = engineStatus().map { String(cString: $0) } ?? "engine_start retornou \(code)"
                failure("Falha ao criar a janela do jogo", reason)
                return
            }
            phase = .playing
            message = "Runtime nativo iniciado"
            detail = "SDL3 · Vulkan/KosmicKrisp · código retail recompilado"
            DiagnosticLog.append("engineStart retornou 0. Verificando estado do runtime.")
            timer?.invalidate()
            timer = Timer.scheduledTimer(withTimeInterval: 1.0/20.0, repeats: true) { [weak self] _ in
                guard let self else { return }
                enginePump()
                guard let ptr = engineStatus() else { return }
                let status = String(cString: ptr)
                if status != self.latestNativeStatus {
                    self.latestNativeStatus = status
                    DiagnosticLog.append("Runtime: \(status)")
                }
                if status.hasPrefix("MENU:") {
                    self.phase = .suspended
                    self.message = "Retornou ao launcher"
                    self.detail = status
                    self.timer?.invalidate()
                    self.timer = nil
                } else if status.hasPrefix("FATAL:") {
                    self.failure("O runtime encerrou a inicialização", status)
                    self.timer?.invalidate()
                    self.timer = nil
                } else if status != "Não iniciado", !status.isEmpty {
                    self.detail = status
                }
            }
        } catch { failure("Não foi possível iniciar", error.localizedDescription) }
    }
}

private struct StatusMarker: View {
    let phase: GameLibrary.Phase
    var color: Color {
        switch phase {
        case .empty: return SandStyle.muted
        case .importing, .launching: return SandStyle.gold
        case .ready, .playing: return Color(red: 0.42, green: 0.82, blue: 0.65)
        case .suspended: return SandStyle.gold
        case .failed: return SandStyle.red
        }
    }
    var caption: String {
        switch phase {
        case .empty: return "AGUARDANDO ARQUIVOS"
        case .importing: return "IMPORTANDO RETAIL"
        case .ready: return "PRONTO PARA JOGAR"
        case .launching: return "ABRINDO O JOGO"
        case .playing: return "RUNTIME ATIVO"
        case .suspended: return "MENU RESTAURADO"
        case .failed: return "ATENÇÃO NECESSÁRIA"
        }
    }
    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(caption).font(.system(size: 10, weight: .heavy, design: .rounded)).tracking(1.1)
                .foregroundStyle(color)
        }
    }
}

struct RootView: View {
    @StateObject private var library = GameLibrary()
    @State private var showFolderPicker = false

    private var backdrop: some View {
        ZStack {
            SandStyle.night
            LinearGradient(colors: [Color(red: 0.11, green: 0.17, blue: 0.24).opacity(0.9),
                                    SandStyle.night.opacity(0.25), Color(red: 0.19, green: 0.13, blue: 0.12)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            GeometryReader { proxy in
                Circle().stroke(SandStyle.gold.opacity(0.10), lineWidth: 1)
                    .frame(width: 340, height: 340)
                    .position(x: proxy.size.width * 0.29, y: proxy.size.height * 0.69)
                Circle().stroke(SandStyle.gold.opacity(0.08), lineWidth: 28)
                    .frame(width: 255, height: 255)
                    .position(x: proxy.size.width * 0.29, y: proxy.size.height * 0.69)
                Circle().stroke(SandStyle.gold.opacity(0.09), lineWidth: 1)
                    .frame(width: 490, height: 490)
                    .position(x: proxy.size.width * 0.29, y: proxy.size.height * 0.69)
                LinearGradient(colors: [.clear, SandStyle.gold.opacity(0.075), .clear],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                    .frame(width: proxy.size.width * 0.42).rotationEffect(.degrees(-24))
                    .position(x: proxy.size.width * 0.32, y: proxy.size.height * 0.54)
            }.clipped()
        }.ignoresSafeArea()
    }

    private var identity: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "hourglass").font(.system(size: 14, weight: .bold))
                Text("PoPTST  /  NATIVE EDITION  ·  BUILD \(BuildInfo.number)")
                    .font(.system(size: 10, weight: .heavy, design: .rounded)).tracking(2.4)
            }.foregroundStyle(SandStyle.gold)
            Spacer(minLength: 8)
            Text("PRINCE OF\nPERSIA")
                .font(.system(size: 43, weight: .black, design: .serif))
                .tracking(1.8).lineSpacing(-6).minimumScaleFactor(0.7)
                .foregroundStyle(SandStyle.pale)
                .fixedSize(horizontal: false, vertical: true)
            Rectangle().fill(SandStyle.gold).frame(width: 72, height: 2)
            Text("THE SANDS OF TIME")
                .font(.system(size: 13, weight: .semibold, design: .serif)).tracking(3)
                .foregroundStyle(SandStyle.gold)
            Text("XBOX RETAIL  ·  ARM64  ·  VULKAN → METAL")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .tracking(0.8).foregroundStyle(SandStyle.muted)
            Spacer(minLength: 8)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private var actionPanel: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack {
                Text("BIBLIOTECA DO JOGO  ·  BUILD \(BuildInfo.number)")
                    .font(.system(size: 10, weight: .heavy, design: .rounded)).tracking(1.5)
                    .foregroundStyle(SandStyle.muted)
                Spacer()
                StatusMarker(phase: library.phase)
            }
            Text(library.message)
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundStyle(SandStyle.pale)
                .lineLimit(2)
                .accessibilityIdentifier("poptst-runtime-status")
            Text(library.detail)
                .font(.system(size: 12)).foregroundStyle(SandStyle.muted)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(4)
                .accessibilityIdentifier("poptst-runtime-detail")
            if library.busy || library.progress > 0 && library.phase == .importing {
                ProgressView(value: library.progress)
                    .tint(SandStyle.gold)
            }
            if library.phase == .failed, let why = library.lastError {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                    Text(why).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
                }.foregroundStyle(SandStyle.red)
                .padding(10).frame(maxWidth: .infinity, alignment: .leading)
                .background(SandStyle.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
            }
            Spacer(minLength: 2)
            Button {
                if library.canPlay { library.play() }
                else { library.importFromDocuments() }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: library.canPlay ? "play.fill" : "internaldrive.fill")
                    Text(library.canPlay ? "INICIAR JOGO" : "VERIFICAR PASTA LOCAL E JOGAR")
                    Spacer(minLength: 0)
                    Image(systemName: "arrow.up.right")
                }.font(.system(size: 12, weight: .heavy, design: .rounded))
                    .tracking(0.9).foregroundStyle(SandStyle.night)
                    .padding(.horizontal, 16).frame(height: 45)
                    .background(SandStyle.gold, in: RoundedRectangle(cornerRadius: 10))
            }.disabled(library.busy || library.phase == .playing)
            .opacity(library.busy || library.phase == .playing ? 0.5 : 1)
            .accessibilityIdentifier("poptst-primary-button")
            Button {
                library.restoreNativeSaveAndPlay()
            } label: {
                Label("RESTAURAR SAVE DO JOGO E INICIAR", systemImage: "square.and.arrow.down")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(SandStyle.gold)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(SandStyle.gold.opacity(0.40)))
            }
            .disabled(!library.canPlay || library.busy)
            .accessibilityIdentifier("poptst-restore-native-save")
            Text("Restaurar recupera saves de checkpoints do jogo. Não devolve o quadro exato: use Carregar no menu do Prince of Persia.")
                .font(.system(size: 9))
                .foregroundStyle(SandStyle.muted)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 12) {
                Button {
                    showFolderPicker = true
                } label: { Label("Selecionar pasta (alternativo)", systemImage: "folder") }
                    .disabled(library.busy)
                Button {
                    library.importFromDocuments()
                } label: { Label("Pasta local", systemImage: "internaldrive") }
                    .disabled(library.busy)
                Spacer(minLength: 0)
                ShareLink(item: DiagnosticLog.url) {
                    Label("Diagnóstico", systemImage: "square.and.arrow.up")
                }.accessibilityIdentifier("poptst-export-log")
            }.font(.system(size: 10, weight: .semibold))
             .foregroundStyle(SandStyle.gold)
            Text("Arquivos → No Meu iPhone → PoPTST → xbox-retail")
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(SandStyle.gold)
                .accessibilityIdentifier("poptst-local-path")
            Text("Copie aqui o CONTEÚDO da sua pasta completa; ou a própria pasta pop_completo dentro de xbox-retail. O app cria automaticamente VIDEO, SOUND, MEDIA, POP1 e POP2.")
                .font(.system(size: 10)).foregroundStyle(SandStyle.muted)
                .lineLimit(4).fixedSize(horizontal: false, vertical: true)
            Text("Pasta necessária: default.xbe · prince.bf · shaders.bin · VIDEO · SOUND · MEDIA · POP1 · POP2")
                .font(.system(size: 10)).foregroundStyle(SandStyle.muted.opacity(0.8))
                .lineLimit(2).fixedSize(horizontal: false, vertical: true)
        }
        .padding(22)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(SandStyle.panel.opacity(0.96), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(SandStyle.gold.opacity(0.22), lineWidth: 1))
        .shadow(color: .black.opacity(0.28), radius: 20, y: 8)
    }

    var body: some View {
        GeometryReader { proxy in
            ZStack { backdrop
                if proxy.size.width > 560 {
                    HStack(alignment: .top, spacing: 20) {
                        identity.frame(maxWidth: .infinity)
                        actionPanel.frame(width: min(455, proxy.size.width * 0.53))
                    }.padding(.horizontal, 30).padding(.vertical, 20)
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 22) {
                            identity.frame(height: 210)
                            actionPanel.frame(minHeight: 360)
                        }.padding(18)
                    }
                }
            }.preferredColorScheme(.dark)
        }
        .fileImporter(isPresented: $showFolderPicker, allowedContentTypes: [.folder],
                      allowsMultipleSelection: false) { selection in
            switch selection {
            case .success(let urls):
                guard let url = urls.first else { library.cancelledPicker(); return }
                library.importGame(url)
            case .failure(let error): library.filePickerFailed(error)
            }
        } onCancellation: {
            library.cancelledPicker()
        }
    }
}

@main struct PoPTSTApp: App {
    var body: some Scene { WindowGroup { RootView() } }
}
