import SwiftUI
import AVKit
import GameController

@main
struct PandaiOSApp: App {
    var body: some Scene {
        WindowGroup {
            PandaHomeView()
                .preferredColorScheme(.dark)
        }
    }
}

struct PandaHomeView: View {
    @State private var streamAddress = ""
    @State private var player: AVPlayer?
    @State private var showingPlayer = false
    @State private var errorMessage: String?
    @State private var controllerCount = GCController.controllers().count

    private var streamURL: URL? {
        guard let url = URL(string: streamAddress.trimmingCharacters(in: .whitespacesAndNewlines)),
              url.scheme?.lowercased() == "https",
              ["m3u8", "mp4"].contains(url.pathExtension.lowercased()) else { return nil }
        return url
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color(red: 0.035, green: 0.045, blue: 0.075).ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        header
                        engineStatus
                        providerStatus
                        diagnosticPlayer
                    }
                    .padding(20)
                    .frame(maxWidth: 760)
                    .frame(maxWidth: .infinity)
                }
            }
            .navigationBarHidden(true)
            .fullScreenCover(isPresented: $showingPlayer) {
                if let player {
                    DirectPlayerView(player: player) {
                        player.pause()
                        self.player = nil
                        showingPlayer = false
                    }
                }
            }
            .alert("Não foi possível iniciar", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
            .onReceive(NotificationCenter.default.publisher(for: .GCControllerDidConnect)) { _ in
                controllerCount = GCController.controllers().count
            }
            .onReceive(NotificationCenter.default.publisher(for: .GCControllerDidDisconnect)) { _ in
                controllerCount = GCController.controllers().count
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "cloud.fill")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(.purple)
                Text("PANDA CLOUD")
                    .font(.system(size: 21, weight: .black, design: .rounded))
                    .tracking(2)
                Spacer()
                Text("iOS")
                    .font(.caption.bold())
                    .padding(.horizontal, 11)
                    .padding(.vertical, 6)
                    .background(.purple.opacity(0.22), in: Capsule())
            }
            Text("Seu catálogo de jogos, direto no iPhone.")
                .font(.title2.bold())
            Text("Cliente nativo • GameStream • controles iOS")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var engineStatus: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: MoonlightCore.isLinked ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                    .font(.title2)
                    .foregroundStyle(MoonlightCore.isLinked ? .green : .orange)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Motor GameStream")
                        .font(.headline)
                    Text(MoonlightCore.isLinked
                         ? "Moonlight Common C vinculado ao aplicativo iOS."
                         : "Biblioteca GameStream ainda não vinculada.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(MoonlightCore.isLinked ? "LINKED" : "PENDING")
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .tracking(1)
                    .foregroundStyle(MoonlightCore.isLinked ? .green : .orange)
            }
            Divider().overlay(.white.opacity(0.12))
            HStack {
                Label("Controle Bluetooth", systemImage: "gamecontroller.fill")
                    .font(.subheadline.weight(.medium))
                Spacer()
                Text(controllerCount == 1 ? "1 conectado" : "\(controllerCount) conectados")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(18)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
    }

    private var providerStatus: some View {
        VStack(alignment: .leading, spacing: 9) {
            Label("Serviço Panda", systemImage: "network")
                .font(.headline)
            Text("O APK confirma o uso do cliente Limelight/GameStream. O próximo adaptador precisa obter do serviço Panda o host remoto, certificado, identificador do aplicativo e parâmetros da sessão para iniciar o streaming pelo motor nativo.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Login, catálogo e alocação de máquinas ainda estão em engenharia reversa. Nenhum endpoint ou token foi inventado.")
                .font(.caption)
                .foregroundStyle(.orange)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.purple.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
    }

    private var diagnosticPlayer: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Teste de mídia independente")
                .font(.headline)
            Text("Ferramenta de diagnóstico HLS/MP4; não representa o protocolo de sessão Panda.")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("URL HTTPS HLS (.m3u8) ou MP4", text: $streamAddress)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .autocorrectionDisabled()
                .padding(14)
                .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
            Button(action: startDirectPlayback) {
                Label("Testar reprodução", systemImage: "play.fill")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 13)
            }
            .buttonStyle(.borderedProminent)
            .tint(.purple)
            .disabled(streamURL == nil)
        }
        .padding(18)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
    }

    private func startDirectPlayback() {
        guard let url = streamURL else {
            errorMessage = "Informe uma URL HTTPS HLS (.m3u8) ou MP4 válida."
            return
        }
        let newPlayer = AVPlayer(playerItem: AVPlayerItem(url: url))
        player = newPlayer
        newPlayer.play()
        showingPlayer = true
    }
}

private struct DirectPlayerView: View {
    let player: AVPlayer
    let onClose: () -> Void

    var body: some View {
        ZStack(alignment: .topLeading) {
            VideoPlayer(player: player).ignoresSafeArea()
            Button(action: onClose) {
                Label("Fechar", systemImage: "xmark")
                    .padding(12)
                    .background(.black.opacity(0.65), in: Capsule())
            }
            .padding()
        }
        .background(.black)
    }
}
