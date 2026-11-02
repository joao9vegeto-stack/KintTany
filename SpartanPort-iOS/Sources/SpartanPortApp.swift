import SwiftUI

@main
struct SpartanPortApp: App {
    init() {
        // Install before SwiftUI creates the first scene so startup failures leave a breadcrumb.
        StartupDiagnostics.install()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
    }
}
