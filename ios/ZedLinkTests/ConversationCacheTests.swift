import XCTest
@testable import ZedLink

final class ConversationCacheTests: XCTestCase {
    func testMigratesLegacyCacheAndSkipsUnchangedWrite() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("zedlink-cache-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent("conversations.json")
        let snapshot = ThreadSnapshot(threadID: "thread", title: "Fixture", status: "Idle", currentTurnID: nil,
                                      instanceID: "instance", epoch: "epoch", lastSequence: 1,
                                      entries: ["## Assistant\n\nHello"], entryStartIndex: 0, totalEntries: 1,
                                      hasOlderEntries: false, activityEntries: [], truncated: false,
                                      activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
        let original = try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot))
        try JSONEncoder().encode([original]).write(to: file)
        let cache = ConversationCache(storageURL: file)
        let migrated = await cache.read(gatewayID: "gateway", targetID: "project", threadID: "thread")
        XCTAssertEqual(migrated?.entries, original.entries)
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
        await cache.save(try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot)))
        let unchanged = await cache.read(gatewayID: "gateway", targetID: "project", threadID: "thread")
        XCTAssertEqual(unchanged?.updatedAt, original.updatedAt)
        let restored = await ConversationCache(storageURL: file).read(gatewayID: "gateway", targetID: "project", threadID: "thread")
        XCTAssertEqual(restored?.entries, original.entries)
    }

    func testCacheEvictsOldestConversation() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("zedlink-cache-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("conversations.json")
        let cache = ConversationCache(storageURL: file)
        for index in 0..<25 {
            let snapshot = ThreadSnapshot(threadID: "thread-\(index)", title: "Fixture \(index)", status: "Idle", currentTurnID: nil,
                                          instanceID: "instance", epoch: "epoch", lastSequence: 1,
                                          entries: ["## Assistant\n\nHello"], entryStartIndex: 0, totalEntries: 1,
                                          hasOlderEntries: false, activityEntries: [], truncated: false,
                                          activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
            let saved = try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot))
            await cache.save(saved)
        }
        let restored = await ConversationCache(storageURL: file).list(gatewayID: "gateway", targetID: "project")
        XCTAssertEqual(restored.count, 24)
        XCTAssertFalse(restored.contains { $0.threadID == "thread-0" })
        XCTAssertTrue(restored.contains { $0.threadID == "thread-24" })
    }

    func testCacheKeepsRecentConversationsWithinDiskBudget() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("zedlink-cache-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("conversations.json")
        let cache = ConversationCache(storageURL: file)
        for index in 0..<20 {
            let snapshot = ThreadSnapshot(threadID: "thread-\(index)", title: "Fixture \(index)", status: "Idle", currentTurnID: nil,
                                          instanceID: "instance", epoch: "epoch", lastSequence: 1,
                                          entries: ["## Assistant\n\n" + String(repeating: "x", count: 450_000)],
                                          entryStartIndex: 0, totalEntries: 1,
                                          hasOlderEntries: false, activityEntries: [], truncated: false,
                                          activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
            await cache.save(try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot)))
        }
        let restored = await ConversationCache(storageURL: file).list(gatewayID: "gateway", targetID: "project")
        XCTAssertLessThan(restored.count, 20)
        XCTAssertTrue(restored.contains { $0.threadID == "thread-19" })
        XCTAssertFalse(restored.contains { $0.threadID == "thread-0" })
        let totalBytes = try restored.reduce(0) { $0 + (try JSONEncoder().encode($1)).count }
        XCTAssertLessThanOrEqual(totalBytes, 8 * 1024 * 1024)
    }

    func testOlderSaveCannotReplaceNewerConversation() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("zedlink-cache-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let cache = ConversationCache(storageURL: directory.appendingPathComponent("conversations.json"))
        func snapshot(_ title: String) -> ThreadSnapshot {
            ThreadSnapshot(threadID: "thread", title: title, status: "Idle", currentTurnID: nil,
                           instanceID: "instance", epoch: "epoch", lastSequence: 1,
                           entries: ["## Assistant\n\n" + title], entryStartIndex: 0, totalEntries: 1,
                           hasOlderEntries: false, activityEntries: [], truncated: false,
                           activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
        }
        let now = Date()
        let older = try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot("Older"),
                                                       updatedAt: now.addingTimeInterval(-2)))
        let newer = try XCTUnwrap(CachedConversation(gatewayID: "gateway", targetID: "project", snapshot: snapshot("Newer"),
                                                       updatedAt: now.addingTimeInterval(-1)))
        await cache.save(newer)
        await cache.save(older)
        let saved = await cache.read(gatewayID: "gateway", targetID: "project", threadID: "thread")
        XCTAssertEqual(saved?.title, "Newer")
    }

    func testSavedPageIsBoundedScopedAndRemovedOnUnexpose() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("zedlink-cache-test-\(UUID())")
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("conversations.json")
        let cache = ConversationCache(storageURL: file)
        let entries = (0..<140).map { "## Assistant\n\nEntry \($0)" }
        let snapshot = ThreadSnapshot(threadID: "thread", title: "Fixture", status: "Idle", currentTurnID: nil,
                                      instanceID: "instance", epoch: "epoch", lastSequence: 2,
                                      entries: entries, entryStartIndex: 0, totalEntries: 140,
                                      hasOlderEntries: false, activityEntries: [], truncated: false,
                                      activityTruncated: false, pendingApprovals: [], rewindPoints: [], subagents: [])
        let saved = try XCTUnwrap(CachedConversation(gatewayID: "Gateway", targetID: "project", snapshot: snapshot))
        XCTAssertEqual(saved.entryStartIndex, 12)
        XCTAssertEqual(saved.entries.count, 128)
        XCTAssertEqual(saved.displaySnapshot.entryStartIndex, 116)
        XCTAssertEqual(saved.displaySnapshot.entries.first, entries[116])
        XCTAssertEqual(saved.displaySnapshot.entries.last, entries.last)
        XCTAssertEqual(saved.displaySnapshot(visibleCount: 128).entryStartIndex, 12)
        await cache.save(saved)
        let restored = ConversationCache(storageURL: file)
        let page = await restored.read(gatewayID: "gateway", targetID: "project", threadID: "thread")
        XCTAssertEqual(page?.entries.last, entries.last)
        let otherTarget = await restored.list(gatewayID: "gateway", targetID: "other")
        XCTAssertTrue(otherTarget.isEmpty)
        await restored.remove(gatewayID: "gateway", targetID: "project", threadID: "thread")
        let afterRemoval = await ConversationCache(storageURL: file).list(gatewayID: "gateway", targetID: "project")
        XCTAssertTrue(afterRemoval.isEmpty)
    }
}
