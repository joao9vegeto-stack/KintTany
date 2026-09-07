import SwiftUI

struct RootView: View {
    @EnvironmentObject var app: AppStore
    @State private var showLogin = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    HStack { Label("KintTany", systemImage: "bolt.shield.fill").font(.title2.bold()); Spacer(); Button("Sessão") { showLogin = true }.buttonStyle(.bordered); Circle().fill(app.connected ? .green : .gray).frame(width: 10) }
                    statusCard
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) { ForEach(ActivityMode.allCases) { mode in activityCard(mode) } }
                    logCard
                }.padding()
            }.navigationTitle("Dashboard").sheet(isPresented: $showLogin) { LoginWebView { cookie in app.saveCookie(cookie); showLogin = false }.ignoresSafeArea() }
        }
    }
    var statusCard: some View { VStack(alignment: .leading, spacing: 8) { Text(app.activity?.title ?? "Nenhuma atividade").font(.headline); Text(app.state.rawValue); ProgressView(value: Double(app.stats.successes), total: Double(max(app.goal, 1))); HStack { Text("Sucessos: \(app.stats.successes)"); Spacer(); Text("Falhas: \(app.stats.failures)") }; Button("STOP", role: .destructive) { app.stop() }.buttonStyle(.borderedProminent) }.padding().background(.thinMaterial).clipShape(RoundedRectangle(cornerRadius: 16)) }
    func activityCard(_ mode: ActivityMode) -> some View { Button { app.start(mode) } label: { VStack(alignment: .leading, spacing: 8) { Label(mode.title, systemImage: mode.icon).font(.headline); Text("Meta \(app.goal)").font(.caption).foregroundStyle(.secondary) } .frame(maxWidth: .infinity, alignment: .leading).padding().background(Color.blue.opacity(0.10)).clipShape(RoundedRectangle(cornerRadius: 14)) }.buttonStyle(.plain) }
    var logCard: some View { VStack(alignment: .leading) { Text("Logs").font(.headline); ForEach(Array(app.logs.suffix(5).enumerated()), id: \.offset) { Text($0.element).font(.caption.monospaced()).frame(maxWidth: .infinity, alignment: .leading) } }.frame(maxWidth: .infinity, alignment: .leading).padding().background(.thinMaterial).clipShape(RoundedRectangle(cornerRadius: 16)) }
}
