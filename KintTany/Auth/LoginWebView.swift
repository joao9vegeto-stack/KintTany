import SwiftUI
import WebKit

struct LoginWebView: UIViewRepresentable {
    let onCookie: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(onCookie: onCookie) }
    func makeUIView(context: Context) -> WKWebView { let view = WKWebView(frame: .zero); view.navigationDelegate = context.coordinator; view.load(URLRequest(url: URL(string: "https://kintara.com")!)); return view }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
    final class Coordinator: NSObject, WKNavigationDelegate {
        let onCookie: (String) -> Void
        init(onCookie: @escaping (String) -> Void) { self.onCookie = onCookie }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { exportSession() }
        private func exportSession() {
        WKWebsiteDataStore.default().httpCookieStore.getAllCookies { cookies in
            let relevant = cookies.filter { $0.domain.contains("kintara") }
            let header = relevant.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
            if !header.isEmpty { DispatchQueue.main.async { self.onCookie(header) } }
        }
    }
    }
}
