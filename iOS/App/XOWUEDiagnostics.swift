import Foundation
import UIKit

enum XOWUEDiagnostics {
    private static let lock = NSRecursiveLock()
    private static var started = false
    private static var buildNumber: String {
        let value = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        return value?.isEmpty == false ? value! : "unknown"
    }
    static var diagnosticFilename: String { "diagnostico-build-\(buildNumber).txt" }
    static var crashFilename: String { "crash-build-\(buildNumber).txt" }

    static func startup() {
        lock.lock()
        defer { lock.unlock() }
        guard !started else { return }
        started = true
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }

        let diagnosticURL = documents.appendingPathComponent(diagnosticFilename)
        let crashURL = documents.appendingPathComponent(crashFilename)
        ensureFile(diagnosticURL)

        // A previous incomplete boot is not proof of a crash: iOS may suspend
        // or terminate the process, and users may force-close the app.
        let previous = (try? String(contentsOf: diagnosticURL, encoding: .utf8)) ?? ""
        let previousStart = previous.range(of: "BOOT_STARTED", options: .backwards)?.lowerBound
        let previousFinish = previous.range(of: "BOOT_FINISHED", options: .backwards)?.lowerBound
        if let previousStart, previousFinish.map({ previousStart > $0 }) ?? true {
            appendLocked("RECOVERY previous boot did not finish; crash not established", to: diagnosticURL)
        }
        // Native crash reports are created only by the fatal signal handler.
        crashURL.path.withCString { XOWUECrashRecorderInstall($0) }

        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        appendLocked("APP_LAUNCH build=\(build) title_id=41560816 documents=\(documents.path)", to: diagnosticURL)
        appendLocked("APP_ENV device=\(UIDevice.current.model) os=\(UIDevice.current.systemVersion) bundle=\(Bundle.main.bundleIdentifier ?? "unknown") arch=arm64", to: diagnosticURL)
        NSSetUncaughtExceptionHandler { exception in
            let stack = exception.callStackSymbols.prefix(24).joined(separator: " | ")
            XOWUEDiagnostics.recordCrash("UNCAUGHT_NS_EXCEPTION name=\(exception.name.rawValue) reason=\(exception.reason ?? "none") stack=\(stack)")
        }
    }

    static func fileURL(named name: String) -> URL? {
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return nil }
        return documents.appendingPathComponent(name)
    }

    static func existingCrashFileURL() -> URL? {
        guard let url = fileURL(named: crashFilename),
              FileManager.default.fileExists(atPath: url.path),
              let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = attrs[.size] as? NSNumber,
              size.intValue > 0 else { return nil }
        // A controlled Xbox firmware return is recorded in the diagnostic,
        // not fabricated as an iOS crash. Hide the empty native crash file.
        return url
    }

    static func log(_ message: String) {
        lock.lock()
        defer { lock.unlock() }
        guard let url = fileURL(named: diagnosticFilename) else { return }
        appendLocked(message, to: url)
        let summaryPrefixes = ["CODE_AUDIT", "AOT_PROGRESS", "HOT_FN_CODE", "THREAD_DUMP",
                               "XENOS_", "PM4_", "SWAP_", "WAIT_", "VBLANK", "GRAPHICS_INTERRUPT"]
        if summaryPrefixes.contains(where: { message.contains($0) }) {
            refreshCompactSummaryLocked(diagnosticURL: url)
        }
    }

    private static func refreshCompactSummaryLocked(diagnosticURL: URL) {
        guard let source = try? String(contentsOf: diagnosticURL, encoding: .utf8) else { return }
        let lines = source.split(whereSeparator: \.isNewline).map(String.init)
        var audits = lines.filter { $0.contains("CODE_AUDIT") }
        var progress = Array(lines.filter { $0.contains("AOT_PROGRESS") }.suffix(4))
        var hot = Array(lines.filter { $0.contains("HOT_FN_CODE") }.suffix(6))
        var threads = lines.filter { $0.contains("THREAD_DUMP") }
        var gpu = Array(lines.filter { line in
            ["XENOS_", "PM4_", "SWAP_", "WAIT_", "VBLANK", "GRAPHICS_INTERRUPT"].contains(where: { line.contains($0) })
        }.suffix(15))
        func assembled() -> [String] { audits + progress + hot + threads + gpu }
        while assembled().joined(separator: "\n").utf8.count > 4000 {
            if !gpu.isEmpty { gpu.removeFirst() }
            else if !threads.isEmpty { threads.removeFirst() }
            else if !hot.isEmpty { hot.removeFirst() }
            else if !progress.isEmpty { progress.removeFirst() }
            else if !audits.isEmpty { audits.removeLast() }
            else { break }
        }
        let summary = assembled().joined(separator: "\n") + "\n"
        let summaryURL = diagnosticURL.deletingLastPathComponent().appendingPathComponent("resumo-b62.txt")
        try? summary.write(to: summaryURL, atomically: true, encoding: .utf8)
    }

    static func bootStarted(path: String, build: String) {
        lock.lock()
        defer { lock.unlock() }
        if let url = fileURL(named: diagnosticFilename) {
            appendLocked("BOOT_STARTED build=\(build) title_id=41560816 xex=\(path)", to: url)
        }
    }

    static func bootFinished(code: Int32, text: String) {
        lock.lock()
        defer { lock.unlock() }
        let result = "BOOT_FINISHED code=\(code)\n\(text)"
        if let url = fileURL(named: diagnosticFilename) {
            appendLocked(result, to: url)
        }
    }

    static func bootFailed(_ message: String) {
        log("BOOT_FAILED \(message)")
    }

    static func recordCrash(_ message: String) {
        lock.lock()
        defer { lock.unlock() }
        if let url = fileURL(named: diagnosticFilename) {
            appendLocked("CRASH \(message)", to: url)
        }
        if let url = fileURL(named: crashFilename) {
            appendLocked("CRASH \(message)", to: url)
        }
    }

    private static func ensureFile(_ url: URL) {
        guard !FileManager.default.fileExists(atPath: url.path) else { return }
        FileManager.default.createFile(atPath: url.path, contents: Data())
    }

    private static func appendLocked(_ message: String, to url: URL) {
        ensureFile(url)
        let timestamp = ISO8601DateFormatter().string(from: Date())
        guard let data = "\(timestamp) \(message)\n".data(using: .utf8) else { return }

        guard let file = try? FileHandle(forWritingTo: url) else { return }
        defer { try? file.close() }
        _ = try? file.seekToEnd()
        try? file.write(contentsOf: data)
    }
}

