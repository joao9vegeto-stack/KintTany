import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var gameFolder = GameFolderStore()
    @State private var showingFolderPicker = false
    @State private var kosmicKrispProbe = "Aguardando verificação"

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.025, green: 0.035, blue: 0.055), Color(red: 0.055, green: 0.085, blue: 0.13), .black],
                startPoint: .topLeading, endPoint: .bottomTrailing
            ).ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Renderizador Apple", systemImage: "cube.transparent").font(.headline)
                            Spacer()
                            Text("METAL").font(.caption2.weight(.black)).tracking(1.5).foregroundStyle(.cyan)
                        }
                        MetalClearView()
                            .frame(height: 210)
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.12)))
                        Text("Teste de apresentação Metal; ainda não renderiza comandos gráficos do PS4.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))

                    payloadCard

                    VStack(alignment: .leading, spacing: 8) {
                        Label("Estado da integração", systemImage: "wrench.and.screwdriver").font(.headline)
                        statusRow("Aplicativo iOS / SwiftUI", state: "Implementado", good: true)
                        statusRow("Superfície Metal", state: "Teste inicial", good: true)
                        statusRow("KosmicKrisp Vulkan ICD", state: kosmicKrispProbe, good: kosmicKrispProbe.hasPrefix("ICD loaded"))
                        statusRow("Metadados param.sfo", state: gameFolder.titleID ?? "Não lidos", good: gameFolder.titleID != nil)
                        statusRow("Inspeção do eboot.bin", state: gameFolder.executableValidated ? "ELF64 x86-64" : "Não validado", good: gameFolder.executableValidated)
                        statusRow("Runtime PS4 ARM64", state: "Pendente", good: false)
                        statusRow("AOT x86-64 → ARM64", state: "Pendente", good: false)
                        Text("Iniciar jogo permanece desativado: não existe runtime PS4 integrado nesta versão.")
                            .font(.caption).foregroundStyle(.secondary).padding(.top, 4)
                    }
                    .padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
                }
                .padding(18).frame(maxWidth: 760).frame(maxWidth: .infinity)
            }
        }
        .onAppear {
            _ = SpartanKosmicKrispProbe()
            kosmicKrispProbe = String(cString: SpartanKosmicKrispProbeMessage())
        }
        .fileImporter(isPresented: $showingFolderPicker, allowedContentTypes: [.folder], allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls): if let folder = urls.first { gameFolder.select(folder: folder) }
            case .failure(let error): gameFolder.reportPickerError(error)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Image(systemName: "gamecontroller.fill").foregroundStyle(.orange)
                Text("SPARTANPORT").font(.system(size: 13, weight: .black, design: .rounded)).tracking(2.8)
                Spacer()
                Text("iOS • ARM64").font(.caption2.weight(.bold)).foregroundStyle(.cyan)
                    .padding(.horizontal, 10).padding(.vertical, 6).background(.cyan.opacity(0.12), in: Capsule())
            }
            Text("God of War III").font(.system(size: 32, weight: .black, design: .rounded))
            Text(gameFolder.gameTitle ?? "Base nativa para iPhone e iPad").font(.subheadline).foregroundStyle(.secondary)
            if let id = gameFolder.titleID {
                Text("\(id) • \(gameFolder.contentVersion ?? "versão desconhecida")")
                    .font(.caption.monospaced()).foregroundStyle(.cyan)
            }
        }
        .padding(.vertical, 8)
    }

    private var payloadCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Arquivos do jogo", systemImage: "folder.badge.plus").font(.headline)
            Text(gameFolder.folderName ?? "Nenhuma pasta selecionada")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(gameFolder.folderName == nil ? Color.secondary : Color.white).lineLimit(1)
            Button { showingFolderPicker = true } label: {
                Label("Selecionar pasta do dump PS4", systemImage: "folder")
                    .frame(maxWidth: .infinity).padding(.vertical, 12)
            }.buttonStyle(.borderedProminent).tint(.orange)
            if !gameFolder.details.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(gameFolder.details, id: \.self) { item in
                        Text(item).font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                }
            }
            Text(gameFolder.message).font(.caption)
                .foregroundStyle(gameFolder.executableValidated ? Color.green : Color.secondary)
            Button("Iniciar jogo") {}.frame(maxWidth: .infinity).padding(.vertical, 11)
                .buttonStyle(.bordered).disabled(true)
                .accessibilityHint("Indisponível: o runtime PS4 ainda não foi integrado.")
        }
        .padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
    }

    private func statusRow(_ title: String, state: String, good: Bool) -> some View {
        HStack {
            Text(title).font(.subheadline)
            Spacer()
            Text(state).font(.caption.weight(.semibold)).foregroundStyle(good ? .green : .orange)
        }.padding(.vertical, 3)
    }
}
