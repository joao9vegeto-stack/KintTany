import SwiftUI
import AVKit

@main
struct PandaiOSApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @State private var streamAddress = ""
    @State private var player: AVPlayer?
    @State private var message = "Aguardando análise do protocolo Panda"

    var body: some View {
        NavigationStack {
            ZStack {
                Color(red: 0.035, green: 0.045, blue: 0.075).ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        VStack(alignment: .leading, spacing: 7) {
                            Text("PANDA").font(.system(size: 34, weight: .black, design: .rounded)).tracking(3)
                            Text("CLOUD GAMING • iOS").font(.caption.weight(.bold)).tracking(2).foregroundStyle(.mint)
                        }.padding(.top, 24)

                        VStack(alignment: .leading, spacing: 10) {
                            Label("Diagnóstico de streaming", systemImage: "dot.radiowaves.left.and.right").font(.headline)
                            Text("O protocolo de sessão do APK ainda está sendo identificado. Este player é um teste isolado para streams HLS compatíveis com AVPlayer; não representa ainda a conexão real com os servidores Panda.")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }.padding(16).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

                        VStack(alignment: .leading, spacing: 12) {
                            Text("URL de teste HLS").font(.headline)
                            TextField("https://servidor/exemplo.m3u8", text: $streamAddress)
                                .textInputAutocapitalization(.never).keyboardType(.URL).autocorrectionDisabled()
                                .padding(13).background(.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 10))
                            Button(action: startTestStream) {
                                Label("Testar reprodução", systemImage: "play.fill")
                                    .frame(maxWidth: .infinity).padding(13)
                                    .background(.mint, in: RoundedRectangle(cornerRadius: 10))
                                    .foregroundStyle(.black).fontWeight(.bold)
                            }.disabled(streamAddress.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }.padding(16).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))

                        if let player {
                            VideoPlayer(player: player).frame(height: 230).clipShape(RoundedRectangle(cornerRadius: 14))
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Estado").font(.headline)
                            Text(message).font(.subheadline).foregroundStyle(.secondary)
                            Text("Build inicial • transporte Panda pendente de engenharia reversa")
                                .font(.caption2).foregroundStyle(.tertiary)
                        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                            .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))
                    }.padding(.horizontal, 18).padding(.bottom, 30)
                }
            }.preferredColorScheme(.dark).toolbar(.hidden, for: .navigationBar)
        }
    }

    private func startTestStream() {
        guard let url = URL(string: streamAddress),
              url.scheme?.lowercased() == "https",
              url.pathExtension.lowercased() == "m3u8" else {
            message = "Informe uma URL HTTPS terminada em .m3u8."
            return
        }
        let item = AVPlayerItem(url: url)
        player = AVPlayer(playerItem: item)
        player?.play()
        message = "Solicitação HLS enviada ao AVPlayer. A confirmação depende do servidor e da rede."
    }
}
