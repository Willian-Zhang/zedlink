import XCTest
@testable import ZedLink

@MainActor final class NotificationResponseQueueTests: XCTestCase {
    private func fields(created: String? = "1000") -> [String: String] {
        var data = ["gateway": "gateway", "target": "target", "instance": "instance", "epoch": "epoch",
                    "thread": "thread", "turn": "1", "approval": "approval", "child": ""]
        data["created"] = created
        return data
    }
    func testRelaunchRestoresResponseAndClaimsItOnce() throws {
        let suite = "notification-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let queue = NotificationResponseQueue(defaults: defaults, now: { 1000 })
        queue.enqueue(id: "request", data: fields(), action: "approve")
        queue.enqueue(id: "request", data: fields(), action: "deny")
        let restored = NotificationResponseQueue(defaults: defaults, now: { 1001 })
        XCTAssertEqual(restored.claim()?.action, "approve")
        XCTAssertNil(restored.claim())
        let reopened = NotificationResponseQueue(defaults: defaults, now: { 1002 })
        reopened.enqueue(id: "request", data: fields(), action: "approve")
        XCTAssertNil(reopened.claim())
    }
    func testExpiredFutureAndIncompleteResponsesAreRejected() throws {
        let suite = "notification-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let queue = NotificationResponseQueue(defaults: defaults, now: { 100000 })
        queue.enqueue(id: "expired", data: fields(), action: "approve")
        queue.enqueue(id: "future", data: fields(created: "100001"), action: "approve")
        queue.enqueue(id: "incomplete", data: ["created": "100000"], action: "approve")
        XCTAssertNil(queue.claim())
    }
    func testLegacyAlertsOnlyOpenReviewAndQueueIsBounded() throws {
        let suite = "notification-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let queue = NotificationResponseQueue(defaults: defaults, now: { 1000 })
        for index in 0..<40 { queue.enqueue(id: "request-\(index)", data: fields(created: nil), action: "approve") }
        var count = 0
        while let response = queue.claim() { XCTAssertEqual(response.action, "review"); count += 1 }
        XCTAssertEqual(count, 16)
    }
}
