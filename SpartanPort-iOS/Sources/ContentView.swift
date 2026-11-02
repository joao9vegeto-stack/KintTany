import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var gameFolder = GameFolderStore()
    @State private var showingFolderPicker = false
    @State private var kosmicKrispProbe = "Aguardando verificação"

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.025, green: 0.035, blue: 0.055), Color(red: 0.055, green: 0.085, blue: 0.13), .black],
                           startPoint: .topLeading, endPoint: .bottomTrailing).ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    payloadCard
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Label("Superfície gráfica", systemImage: "cube.transparent").font(.headline)
                            Spacer()
                            Text("METAL").font(.caption2.weight(.black)).tracking(1.5).foregroundStyle(.cyan)
                        }
                        MetalClearView().frame(height: 180).clipShape(RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.12)))
                        Text("Teste de clear Metal; ainda não é o renderer de comandos gráficos do PS4.")
                            .font(.caption).foregroundStyle(.secondary)
                    }.padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Estado técnico", systemImage: "wrench.and.screwdriver").font(.headline)
                        statusRow("Launcher iOS", state: "Implementado", good: true)
                        statusRow("Detecção", state: "\(gameFolder.availableGames.count) instalação(ões)", good: !gameFolder.availableGames.isEmpty)
                        statusRow("Persistência", state: gameFolder.selectedRelativePath == nil ? "Aguardando jogo" : "Ativa", good: gameFolder.selectedRelativePath != nil)
                        statusRow("param.sfo", state: gameFolder.titleID ?? "Não lido", good: gameFolder.titleID != nil)
                        statusRow("eboot.bin", state: gameFolder.executableValidated ? "ELF64 x86-64" : "Não validado", good: gameFolder.executableValidated)
                        statusRow("KosmicKrisp ICD", state: kosmicKrispProbe, good: kosmicKrispProbe.hasPrefix("ICD loaded"))
                        statusRow("Runtime PS4 ARM64", state: "Não integrado", good: false)
                        statusRow("AOT x86-64 → ARM64", state: "Não integrado", good: false)
                        Text("Iniciar só será habilitado quando existir runtime PS4 real. Esta versão não executa eboot.bin.")
                            .font(.caption).foregroundStyle(.secondary).padding(.top, 4)
                        Text("Diagnóstico: Documents/diagnostico.txt").font(.caption2.monospaced()).foregroundStyle(.secondary)
                    }.padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
                }.padding(18).frame(maxWidth: 760).frame(maxWidth: .infinity)
            }
        }
        .onAppear {
            gameFolder.refresh()
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
            Text(gameFolder.gameTitle ?? "Launcher nativo para iPhone e iPad").font(.subheadline).foregroundStyle(.secondary)
            if let id = gameFolder.titleID {
                Text("\(id) • \(gameFolder.contentVersion ?? "versão desconhecida")").font(.caption.monospaced()).foregroundStyle(.cyan)
            }
        }.padding(.vertical, 8)
    }

    private var payloadCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Biblioteca de jogos", systemImage: "folder.badge.plus").font(.headline)
            Text(gameFolder.folderName ?? "Nenhuma instalação selecionada")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(gameFolder.folderName == nil ? Color.secondary : Color.white).lineLimit(1)
            HStack(spacing: 10) {
                Button { showingFolderPicker = true } label: {
                    Label("Importar pasta PS4", systemImage: "folder").frame(maxWidth: .infinity).padding(.vertical, 11)
                }.buttonStyle(.borderedProminent).tint(.orange).disabled(gameFolder.isImporting)
                Button { gameFolder.refresh() } label: {
                    Image(systemName: "arrow.clockwise").frame(width: 44, height: 44)
                }.buttonStyle(.bordered).disabled(gameFolder.isImporting).accessibilityLabel("Redetectar jogos")
            }
            if gameFolder.isImporting { ProgressView("Importando dump…").font(.caption).tint(.orange) }
            if !gameFolder.availableGames.isEmpty {
                Divider().overlay(.white.opacity(0.1))
                Label("Instalações detectadas", systemImage: "checkmark.folder").font(.subheadline.weight(.semibold))
                ForEach(gameFolder.availableGames) { game in
                    Button { gameFolder.selectDetectedGame(relativePath: game.relativePath) } label: {
                        HStack(spacing: 10) {
                            Image(systemName: gameFolder.selectedRelativePath == game.relativePath ? "checkmark.circle.fill" : "folder")
                                .foregroundStyle(gameFolder.selectedRelativePath == game.relativePath ? .green : .secondary)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(game.title ?? game.folderName).font(.subheadline.weight(.semibold)).foregroundStyle(.primary).lineLimit(1)
                                Text("\(game.titleID ?? "Title ID não lido") • \(game.relativePath)")
                                    .font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(2)
                            }
                            Spacer(minLength: 0)
                        }.padding(9).background(.white.opacity(gameFolder.selectedRelativePath == game.relativePath ? 0.10 : 0.035), in: RoundedRectangle(cornerRadius: 10))
                    }.buttonStyle(.plain)
                }
            } else {
                Text("Busca automática em Documents e subpastas. Pasta padrão: Documents/SpartanPort/Jogos.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !gameFolder.details.isEmpty {
                Divider().overlay(.white.opacity(0.1))
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(gameFolder.details, id: \.self) { item in
                        Text(item).font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                }
            }
            Text(gameFolder.message).font(.caption).foregroundStyle(gameFolder.executableValidated ? Color.green : Color.secondary)
            Button {} label: {
                Label("Iniciar jogo", systemImage: "play.fill").frame(maxWidth: .infinity).padding(.vertical, 11)
            }.buttonStyle(.bordered).disabled(true)
                .accessibilityHint("Indisponível: runtime PS4 ARM64 e carregador AOT ainda não integrados.")
        }.padding(16).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 20))
    }

    private func statusRow(_ title: String, state: String, good: Bool) -> some View {
        HStack {
            Text(title).font(.subheadline)
            Spacer()
            Text(state).font(.caption.weight(.semibold)).foregroundStyle(good ? .green : .orange).multilineTextAlignment(.trailing)
        }.padding(.vertical, 3)
    }
}