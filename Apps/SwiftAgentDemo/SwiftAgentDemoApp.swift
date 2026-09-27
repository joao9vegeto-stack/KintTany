import SwiftUI
import SwiftAgent
import FoundationModels

@main
struct SwiftAgentDemoApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 64))
            Text("SwiftAgent 2.0.1")
                .font(.largeTitle.bold())
            Text("FoundationModels • iOS 26+")
                .foregroundStyle(.secondary)
            Text("SwiftAgent integrado com sucesso.")
        }
        .padding()
    }
}
