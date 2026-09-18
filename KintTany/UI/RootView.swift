import SwiftUI

struct RootView: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showLogin = false
    @State private var showFullLog = false

    var body: some View {
        KintTanyDashboard(
            onOpenSession: { showLogin = true },
            onOpenFullLog: { showFullLog = true }
        )
        .sheet(isPresented: $showLogin) {
            LoginWebView(
                onCookie: { cookie in
                    app.saveCookie(cookie)
                    showLogin = false
                },
                onDiagnostic: { line in
                    app.diagnostic(line)
                }
            )
            .preferredColorScheme(.dark)
        }
        .sheet(isPresented: $showFullLog) {
            EventLogSheet()
                .environmentObject(app)
                .preferredColorScheme(.dark)
        }
        .onChange(of: scenePhase) { _, newPhase in
            app.handleScenePhase(newPhase)
        }
    }
}
