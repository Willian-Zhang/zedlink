import XCTest
@testable import ZedLink

@MainActor final class TurnNotificationReceiptsTests: XCTestCase {
    func testReplayAndReconnectUseOneReceiptPerNativeEvent() throws {
        let suite = "turn-alert-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = TurnNotificationReceipts(defaults: defaults, now: { 1000 })
        XCTAssertTrue(first.claim(scope: "gateway:target:instance:epoch:thread", sequence: 12, reason: "completed"))
        XCTAssertFalse(first.claim(scope: "gateway:target:instance:epoch:thread", sequence: 12, reason: "completed"))
        let restored = TurnNotificationReceipts(defaults: defaults, now: { 1001 })
        XCTAssertFalse(restored.claim(scope: "gateway:target:instance:epoch:thread", sequence: 12, reason: "completed"))
        XCTAssertTrue(restored.claim(scope: "gateway:target:instance:new-epoch:thread", sequence: 12, reason: "completed"))
        XCTAssertFalse(restored.claim(scope: "gateway:target:instance:epoch:thread", sequence: 13, reason: "error"))
        XCTAssertFalse(restored.claim(scope: "gateway:target:instance:epoch:thread", sequence: 0, reason: "cancelled"))
    }

    func testPendingInputIsNotRepeatedAndReceiptsAreBounded() throws {
        let suite = "turn-alert-test-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let receipts = TurnNotificationReceipts(defaults: defaults, now: { 1000 })
        XCTAssertTrue(receipts.claim(scope: "a", inputID: "input-1"))
        XCTAssertFalse(receipts.claim(scope: "a", inputID: "input-1"))
        XCTAssertFalse(receipts.claim(scope: "a", inputID: ""))
        for index in 0..<140 { XCTAssertTrue(receipts.claim(scope: "a", sequence: index + 1, reason: "cancelled")) }
        let saved = try XCTUnwrap(defaults.dictionary(forKey: "zedlink.turnNotificationReceipts"))
        XCTAssertLessThanOrEqual(saved.count, 128)
    }
}
