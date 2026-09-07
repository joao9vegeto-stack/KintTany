import SwiftUI

@main
struct KintTanyApp: App {
    @StateObject private var app = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
        }
    }
}
