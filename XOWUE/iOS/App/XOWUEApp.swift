import SwiftUI
import UniformTypeIdentifiers

@main
struct XOWUEApp: App {
    var body: some Scene {
        WindowGroup {
            XOWUERootView()
        }
    }
}

private struct XOWUERootView: View {
    @State private var showingImporter = false
    @State private var selectedXEX: URL?
    @State private var status = "Selecione seu default.xex para validar o loader."
    @State private var isRunning = false

    private let allowedTypes: [UTType] = [.data, .folder]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("X-Men Origins: Wolverine")
                        .font(.largeTitle.bold())
                    Text("Xbox 360 · Title ID 41560816")
                        .font(.headline)
                        .foregroundStyle(.secondary)

                    GroupBox("Estado do projeto") {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Recompilação AOT: 345 unidades", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                            Label("Loader XEX e mapa PPC: integrado", systemImage: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                            Label("Kernel/XAM, Xenos e XMA: em desenvolvimento", systemImage: "exclamationmark.triangle.fill")
                                .foregroundStyle(.orange)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        showingImporter = true
                    } label: {
                        Label(selectedXEX == nil ? "Selecionar default.xex" : "Selecionar outro XEX", systemImage: "doc.badge.plus")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    if let selectedXEX {
                        Text(selectedXEX.lastPathComponent)
                            .font(.footnote.monospaced())
                            .foregroundStyle(.secondary)
                    }

                    Button {
                        runBoot()
                    } label: {
                        HStack {
                            if isRunning { ProgressView().tint(.white) }
                            Text(isRunning ? "Executando diagnóstico…" : "Validar e tentar iniciar")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .disabled(selectedXEX == nil || isRunning)

                    GroupBox("Diagnóstico") {
                        Text(status)
                            .font(.system(.footnote, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Text("Este IPA é um runner de desenvolvimento. Ele não contém o jogo nem seus assets. O boot completo depende das APIs Xbox 360 e dos subsistemas gráficos e de áudio ainda não implementados.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .navigationTitle("XOWUE")
            .navigationBarTitleDisplayMode(.inline)
            .fileImporter(
                isPresented: $showingImporter,
                allowedContentTypes: allowedTypes,
                allowsMultipleSelection: false,
                onCompletion: importSelection
            )
        }
    }

    private func importSelection(_ result: Result<[URL], Error>) {
        do {
            guard let source = try result.get().first else { return }
            let hasScope = source.startAccessingSecurityScopedResource()
            defer { if hasScope { source.stopAccessingSecurityScopedResource() } }

            let xexURL: URL
            if source.hasDirectoryPath {
                guard let found = FileManager.default.enumerator(at: source, includingPropertiesForKeys: nil)?
                    .compactMap({ $0 as? URL })
                    .first(where: { $0.lastPathComponent.lowercased() == "default.xex" }) else {
                    status = "A pasta selecionada não contém default.xex."
                    return
                }
                xexURL = found
            } else {
                guard source.pathExtension.lowercased() == "xex" else {
                    status = "Selecione default.xex ou uma pasta que o contenha."
                    return
                }
                xexURL = source
            }

            let support = try FileManager.default.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true
            )
            let destination = support.appendingPathComponent("default-\(UUID().uuidString).xex")
            try FileManager.default.copyItem(at: xexURL, to: destination)
            selectedXEX = destination
            status = "XEX copiado para o sandbox. Pronto para validar e tentar iniciar."
        } catch {
            status = "Falha ao importar: \(error.localizedDescription)"
        }
    }

    private func runBoot() {
        guard let path = selectedXEX?.path else { return }
        isRunning = true
        status = "Analisando XEX e iniciando o entry point…"
        DispatchQueue.global(qos: .userInitiated).async {
            var buffer = [CChar](repeating: 0, count: 4096)
            let result = path.withCString { cPath in
                buffer.withUnsafeMutableBufferPointer { output in
                    xowue_boot_xex(cPath, output.baseAddress, output.count)
                }
            }
            let message = String(cString: buffer)
            DispatchQueue.main.async {
                status = "Código \(result)\n\(message)"
                isRunning = false
            }
        }
    }
}
