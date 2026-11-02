import Foundation
import UIKit

/// Writes a startup breadcrumb before SwiftUI constructs the first screen.
enum StartupDiagnostics {
    private static let lock = NSLock()
    private static var installed = false

    static func install() {
        guard !installed else { return }
        installed = true
        let handler: @convention(c) (NSException) -> Void = { exception in
            StartupDiagnostics.record("uncaught_exception=\(exception.name.rawValue) reason=\(exception.reason ?? "unknown")")
        }
        NSSetUncaughtExceptionHandler(handler)
        record("event=process_start")
        record("bundle_id=\(Bundle.main.bundleIdentifier ?? "unknown")")
        record("os=\(ProcessInfo.processInfo.operatingSystemVersionString)")
        record("device=\(UIDevice.current.model)")
        record("runtime_ps4=not_integrated")
        record("aot_x86_64_arm64=not_integrated")
    }

    static func record(_ message: String) {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let file = documents.appendingPathComponent("startup.log")
        let line = "\(ISO8601DateFormatter().string(from: Date())) \(message)\n"
        lock.lock()
        defer { lock.unlock() }
        if !FileManager.default.fileExists(atPath: file.path) {
            _ = FileManager.default.createFile(atPath: file.path, contents: Data())
        }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        do {
            try handle.seekToEnd()
            try handle.write(contentsOf: Data(line.utf8))
        } catch {
            // Diagnostics must never prevent application startup.
        }
    }
}
