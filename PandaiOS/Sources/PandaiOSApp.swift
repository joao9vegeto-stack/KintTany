import SwiftUI
import AVKit

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
                    VStack(alignment: .leading, spacing: 24) {
                        header
                        statusCard
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Sessão de streaming")
                                .font(.title3.bold())
                            Text("A reprodução direta é uma ferramenta de diagnóstico. A autenticação e o protocolo proprietário do Panda ainda precisam ser integrados a partir da análise do APK original.")
                                .font(.subheadline)
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
                                    .padding(.vertical, 14)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.purple)
                            .disabled(streamURL == nil)
                        }
                        .padding(18)
                        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
                        VStack(alignment: .leading, spacing: 8) {
                            Label("Integração Panda", systemImage: "wrench.and.screwdriver")
                                .font(.headline)
                            Text("A camada de login, descoberta de servidores, negociação de sessão, decodificação e envio de controles será ligada após identificar as APIs e o transporte usados pelo aplicativo Android. Não há endpoint inventado nesta versão.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        .padding(18)
                        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
                    }
                    .padding(20)
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
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "cloud.fill")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(.purple)
                Text("PANDA CLOUD")
                    .font(.system(size: 20, weight: .black, design: .rounded))
                    .tracking(2)
                Spacer()
                Text("iOS")
                    .font(.caption.bold())
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(.purple.opacity(0.22), in: Capsule())
            }
            Text("Cloud gaming, reconstruído para iPhone.")
                .font(.title2.bold())
            Text("Base nativa • Apple Silicon • AVFoundation")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var statusCard: some View {
        HStack(spacing: 12) {
            Image(systemName: "info.circle.fill")
                .font(.title2)
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 4) {
                Text("Base iOS em desenvolvimento")
                    .font(.headline)
                Text("O serviço Panda ainda não está conectado. Este build não simula uma sessão autenticada.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.09), in: RoundedRectangle(cornerRadius: 16))
    }

    private func startDirectPlayback() {
        guard let url = streamURL else {
            errorMessage = "Informe uma URL HTTPS HLS (.m3u8) ou MP4 válida."
            return
        }
        let item = AVPlayerItem(url: url)
        let newPlayer = AVPlayer(playerItem: item)
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
