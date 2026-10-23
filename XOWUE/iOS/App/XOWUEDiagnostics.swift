import Foundation

enum XOWUEDiagnostics {
    private static let lock = NSRecursiveLock()
    private static var started = false
    private static let maximumBytes = 2 * 1024 * 1024
    private static let diagnosticName = "diagnostico.txt"
    private static let crashName = "crash.txt"

    static func startup() {
        lock.lock()
        defer { lock.unlock() }
        guard !started else { return }
        started = true
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }

        let diagnosticURL = documents.appendingPathComponent(diagnosticName)
        let crashURL = documents.appendingPathComponent(crashName)
        ensureFile(diagnosticURL)
        ensureFile(crashURL)

        let previous = (try? String(contentsOf: crashURL, encoding: .utf8)) ?? ""
        let previousStart = previous.range(of: "BOOT_STARTED", options: .backwards)?.lowerBound
        let previousFinish = previous.range(of: "BOOT_FINISHED", options: .backwards)?.lowerBound
        let previousBootUnfinished: Bool
        if let previousStart {
            previousBootUnfinished = previousFinish.map { previousStart > $0 } ?? true
        } else {
            previousBootUnfinished = false
        }
        if previousBootUnfinished {
            appendLocked("RECOVERY previous process ended after BOOT_STARTED without BOOT_FINISHED; possible crash or force quit", to: crashURL)
        }

        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        appendLocked("APP_LAUNCH build=\(build) title_id=41560816 documents=\(documents.path)", to: diagnosticURL)
        appendLocked("APP_LAUNCH build=\(build) title_id=41560816", to: crashURL)
        NSSetUncaughtExceptionHandler { exception in
            let stack = exception.callStackSymbols.prefix(24).joined(separator: " | ")
            recordCrash("UNCAUGHT_NS_EXCEPTION name=\(exception.name.rawValue) reason=\(exception.reason ?? "none") stack=\(stack)")
        }
    }

    static func fileURL(named name: String) -> URL? {
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return nil }
        return documents.appendingPathComponent(name)
    }

    static func log(_ message: String) {
        lock.lock()
        defer { lock.unlock() }
        guard let url = fileURL(named: diagnosticName) else { return }
        appendLocked(message, to: url)
    }

    static func bootStarted(path: String, build: String) {
        lock.lock()
        defer { lock.unlock() }
        if let url = fileURL(named: diagnosticName) {
            appendLocked("BOOT_STARTED build=\(build) title_id=41560816 xex=\(path)", to: url)
        }
        if let url = fileURL(named: crashName) {
            appendLocked("BOOT_STARTED build=\(build) xex=\(path)", to: url)
        }
    }

    static func bootFinished(code: Int32, text: String) {
        lock.lock()
        defer { lock.unlock() }
        let result = "BOOT_FINISHED code=\(code)\n\(text)"
        if let url = fileURL(named: diagnosticName) {
            appendLocked(result, to: url)
        }
        if let url = fileURL(named: crashName) {
            appendLocked(result, to: url)
        }
    }

    static func bootFailed(_ message: String) {
        recordCrash("BOOT_FAILED \(message)")
    }

    static func recordCrash(_ message: String) {
        lock.lock()
        defer { lock.unlock() }
        if let url = fileURL(named: diagnosticName) {
            appendLocked("CRASH \(message)", to: url)
        }
        if let url = fileURL(named: crashName) {
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

        if let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
           let size = attributes[.size] as? NSNumber,
           size.intValue > maximumBytes,
           let existing = try? Data(contentsOf: url) {
            try? Data(existing.suffix(maximumBytes / 2)).write(to: url, options: .atomic)
        }

        guard let file = try? FileHandle(forWritingTo: url) else { return }
        defer { try? file.close() }
        try? file.seekToEnd()
        try? file.write(contentsOf: data)
    }
}
