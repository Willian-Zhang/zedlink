import Foundation
import CryptoKit

/// Display-only transcript pages. Cached state never authorizes a native operation.
struct CachedConversation: Codable, Identifiable {
    let gatewayID: String
    let targetID: String
    let threadID: String
    let title: String
    let entries: [String]
    let entryStartIndex: Int
    let totalEntries: Int
    let updatedAt: Date

    var id: String { [gatewayID, targetID, threadID].joined(separator: "\n") }

    init?(gatewayID: String, targetID: String, snapshot: ThreadSnapshot) {
        // Keep a contiguous suffix of the visible page. Earlier entries remain on the gateway.
        var suffix: [String] = []
        var bytes = 0
        for entry in snapshot.entries.suffix(128).reversed() {
            let size = entry.utf8.count
            if bytes + size > 512 * 1024 { break }
            suffix.append(entry)
            bytes += size
        }
        guard !suffix.isEmpty else { return nil }
        self.gatewayID = gatewayID.lowercased()
        self.targetID = targetID
        self.threadID = snapshot.threadID
        self.title = snapshot.title
        self.entries = Array(suffix.reversed())
        self.entryStartIndex = snapshot.entryStartIndex + snapshot.entries.count - suffix.count
        self.totalEntries = snapshot.totalEntries
        self.updatedAt = Date()
    }

    var displaySnapshot: ThreadSnapshot {
        ThreadSnapshot(threadID: threadID, title: title, status: "Saved copy", currentTurnID: nil,
                       instanceID: "", epoch: "", lastSequence: 0, entries: entries,
                       entryStartIndex: entryStartIndex, totalEntries: totalEntries,
                       hasOlderEntries: entryStartIndex > 0, activityEntries: [], truncated: entryStartIndex > 0,
                       activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
    }
}

actor ConversationCache {
    static let shared = ConversationCache()
    private var records: [CachedConversation]?
    private let lifetime: TimeInterval = 30 * 24 * 60 * 60
    private let maxRecords = 12
    private let legacyURL: URL?
    private let directoryURL: URL?

    init(storageURL: URL? = nil) {
        let legacyURL = storageURL ?? Self.defaultStorageURL()
        self.legacyURL = legacyURL
        directoryURL = legacyURL?.deletingLastPathComponent().appendingPathComponent("conversations-v2", isDirectory: true)
    }

    private static func defaultStorageURL() -> URL? {
        guard let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        return directory.appendingPathComponent("ZedLink", isDirectory: true)
            .appendingPathComponent("conversations-v1.json")
    }

    private func current() -> [CachedConversation] {
        if let records { return records }
        let files: [URL]
        if let directoryURL {
            files = (try? FileManager.default.contentsOfDirectory(at: directoryURL, includingPropertiesForKeys: nil)) ?? []
        } else { files = [] }
        var decoded = files.filter { $0.pathExtension == "json" }.compactMap {
            (try? Data(contentsOf: $0)).flatMap { try? JSONDecoder().decode(CachedConversation.self, from: $0) }
        }
        let legacyRecords = legacyURL.flatMap { try? Data(contentsOf: $0) }
            .flatMap { try? JSONDecoder().decode([CachedConversation].self, from: $0) }
        decoded += legacyRecords ?? []
        var seen = Set<String>()
        let valid = Array(decoded.filter { Date().timeIntervalSince($0.updatedAt) < lifetime }
            .sorted { $0.updatedAt > $1.updatedAt }
            .filter { seen.insert($0.id).inserted }.prefix(maxRecords))
        records = valid
        if legacyRecords != nil {
            let migrated = valid.allSatisfy(writeRecord)
            if migrated, let legacyURL { try? FileManager.default.removeItem(at: legacyURL) }
        }
        removeFiles(except: Set(valid.map(\.id)))
        return valid
    }

    func list(gatewayID: String, targetID: String) -> [CachedConversation] {
        current().filter { $0.gatewayID == gatewayID.lowercased() && $0.targetID == targetID }
    }

    func read(gatewayID: String, targetID: String, threadID: String) -> CachedConversation? {
        list(gatewayID: gatewayID, targetID: targetID).first { $0.threadID == threadID }
    }

    func save(_ conversation: CachedConversation) {
        var next = current()
        if let previous = next.first(where: { $0.id == conversation.id }),
           previous.title == conversation.title,
           previous.entryStartIndex == conversation.entryStartIndex,
           previous.totalEntries == conversation.totalEntries,
           previous.entries == conversation.entries { return }
        next.removeAll { $0.id == conversation.id }
        next.insert(conversation, at: 0)
        guard writeRecord(conversation) else { return }
        records = Array(next.prefix(maxRecords))
        removeFiles(except: Set(records?.map(\.id) ?? []))
    }

    func remove(gatewayID: String) {
        records = current().filter { $0.gatewayID != gatewayID.lowercased() }
        removeFiles(except: Set(records?.map(\.id) ?? []))
    }

    func remove(gatewayID: String, targetID: String, threadID: String) {
        records = current().filter {
            $0.gatewayID != gatewayID.lowercased() || $0.targetID != targetID || $0.threadID != threadID
        }
        removeFiles(except: Set(records?.map(\.id) ?? []))
    }

    private func recordURL(_ id: String) -> URL? {
        guard let directoryURL else { return nil }
        let digest = SHA256.hash(data: Data(id.utf8)).map { String(format: "%02x", $0) }.joined()
        return directoryURL.appendingPathComponent(digest).appendingPathExtension("json")
    }

    @discardableResult private func writeRecord(_ record: CachedConversation) -> Bool {
        guard let fileURL = recordURL(record.id), let data = try? JSONEncoder().encode(record) else { return false }
        do {
            try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: fileURL, options: .atomic)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: fileURL.path)
            var excluded = fileURL
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            try excluded.setResourceValues(values)
            return true
        } catch {
            // Cache failure must not affect the native session or expose transcript text in logs.
            return false
        }
    }

    private func removeFiles(except retained: Set<String>) {
        guard let directoryURL,
              let files = try? FileManager.default.contentsOfDirectory(at: directoryURL, includingPropertiesForKeys: nil) else { return }
        let names = Set(retained.compactMap { recordURL($0)?.lastPathComponent })
        for file in files where file.pathExtension == "json" && !names.contains(file.lastPathComponent) {
            try? FileManager.default.removeItem(at: file)
        }
    }
}
