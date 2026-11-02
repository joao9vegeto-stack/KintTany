import Foundation
enum PS4GameFolderScanner {
    static func isGameFolder(_ url: URL, fileManager: FileManager = .default) -> Bool {
        let eboot = url.appendingPathComponent("eboot.bin")
        let sfo = url.appendingPathComponent("sce_sys/param.sfo")
        var isDirectory: ObjCBool = false
        return fileManager.fileExists(atPath: eboot.path, isDirectory: &isDirectory) && !isDirectory.boolValue
            && fileManager.fileExists(atPath: sfo.path, isDirectory: &isDirectory) && !isDirectory.boolValue
    }

    static func findGameFolders(in root: URL, maxDepth: Int = 3, fileManager: FileManager = .default) -> [URL] {
        guard maxDepth >= 0 else { return [] }
        var queue: [(URL, Int)] = [(root.standardizedFileURL, 0)]
        var cursor = 0
        var visited = Set<String>()
        var matches: [URL] = []
        while cursor < queue.count {
            let (url, depth) = queue[cursor]
            cursor += 1
            guard visited.insert(url.standardizedFileURL.path).inserted else { continue }
            if isGameFolder(url, fileManager: fileManager) {
                matches.append(url)
                continue
            }
            guard depth < maxDepth,
                  let children = try? fileManager.contentsOfDirectory(at: url, includingPropertiesForKeys: [.isDirectoryKey, .isPackageKey], options: [.skipsHiddenFiles]) else { continue }
            for child in children {
                let values = try? child.resourceValues(forKeys: [.isDirectoryKey, .isPackageKey])
                if values?.isDirectory == true && values?.isPackage != true { queue.append((child, depth + 1)) }
            }
        }
        return matches.sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
    }
}