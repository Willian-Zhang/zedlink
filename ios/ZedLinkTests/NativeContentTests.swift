import XCTest
import UIKit
import SwiftUI
@testable import ZedLink

final class NativeContentTests: XCTestCase {
    @MainActor
    func testProfileStoreKeepsIdentityForTheSameGatewayAddress() {
        let original = ConnectionProfile(name: "Zed", route: .tailscale,
            endpoint: "https://old.example", gatewayID: "FIXTURE-GATEWAY")
        let updated = ProfileStore.profileForSave(ConnectionProfile(name: "Zed renamed", route: .tailscale,
            endpoint: "https://old.example/", gatewayID: "fixture-gateway"),
            among: [original])
        XCTAssertEqual(updated.id, original.id)
        XCTAssertEqual(updated.name, "Zed renamed")
    }

    @MainActor
    func testProfileStoreKeepsAnotherRouteToTheSameGateway() {
        let original = ConnectionProfile(name: "Tailscale", route: .tailscale,
            endpoint: "https://zed.tailnet.example", gatewayID: "FIXTURE-GATEWAY")
        let alternate = ConnectionProfile(name: "Local", route: .local,
            endpoint: "https://zed.lan.example", gatewayID: "fixture-gateway")
        let saved = ProfileStore.profileForSave(alternate, among: [original])
        XCTAssertNotEqual(saved.id, original.id)
        XCTAssertEqual(saved.endpoint, alternate.endpoint)
    }

    func testAssistantSeparatesPublishedReasoningFromAnswer() {
        let entry = NativeEntryPresentation("""
        ## Assistant

        <thinking>
        Inspecting the native thread
        </thinking>

        The answer is ready.
        """, index: 3)

        XCTAssertEqual(entry.kind, .assistant)
        XCTAssertEqual(entry.reasoning, ["Inspecting the native thread"])
        XCTAssertEqual(entry.body, "The answer is ready.")
    }

    func testStreamingReasoningWithoutClosingTagIsVisible() {
        let entry = NativeEntryPresentation("## Assistant\n\n<thinking>\nStill working", index: 0)
        XCTAssertEqual(entry.reasoning, ["Still working"])
        XCTAssertTrue(entry.body.isEmpty)
    }

    func testToolMetadataUsesNativeProjection() {
        let entry = NativeEntryPresentation("""
        **Tool Call: Run tests**
        Status: InProgress

        Terminal:
        ```
        cargo test
        ```
        """, index: 1)

        XCTAssertEqual(entry.kind, .tool)
        XCTAssertEqual(entry.toolName, "Run tests")
        XCTAssertEqual(entry.toolStatus, "InProgress")
    }
}

final class MobileReviewTests: XCTestCase {
    func testUnifiedDiffSeparatesFileHeadersFromChanges() {
        let lines = ReviewLine.lines("diff --git a/demo.rs b/demo.rs\n--- a/demo.rs\n+++ b/demo.rs\n@@ -1 +1 @@\n-old\n+new\n unchanged")
        XCTAssertEqual(lines.map(\.id), Array(1...7))
        XCTAssertTrue(lines.prefix(4).allSatisfy { $0.kind == .header })
        XCTAssertEqual(lines[4].kind, .removed)
        XCTAssertEqual(lines[5].kind, .added)
        XCTAssertEqual(lines[6].kind, .plain)
    }

    func testRestoredUnknownSendContainsIdentityButNoReplayPayload() throws {
        var pending = PendingSend(id: "fixture-request", instanceID: "fixture-instance", epoch: "fixture-epoch", threadID: "fixture-thread", text: "draft")
        pending.contextPaths = ["src/demo.rs"]
        pending.attachments = [PromptAttachment(name: "image.jpg", mimeType: "image/jpeg", data: Data([1, 2, 3]))]
        let saved = try JSONEncoder().encode(pending)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: saved) as? [String: Any])
        XCTAssertEqual(Set(object.keys), Set(["id", "instanceID", "epoch", "threadID"]))
        let restored = try JSONDecoder().decode(PendingSend.self, from: saved)
        XCTAssertEqual(restored.id, pending.id)
        XCTAssertNil(restored.text)
        XCTAssertTrue(restored.attachments.isEmpty)
        XCTAssertTrue(restored.contextPaths.isEmpty)
    }

    @MainActor
    func testImagePreparationCreatesBoundedJPEG() throws {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 2400, height: 1200), format: format)
        let image = renderer.image { context in
            UIColor.blue.setFill(); context.fill(CGRect(x: 0, y: 0, width: 2400, height: 1200))
        }
        let data = try XCTUnwrap(promptJPEG(image))
        XCTAssertLessThanOrEqual(data.count, 1024 * 1024)
        let decoded = try XCTUnwrap(UIImage(data: data))
        XCTAssertLessThanOrEqual(max(decoded.size.width, decoded.size.height), 1600)
        XCTAssertEqual(Array(data.prefix(2)), [0xff, 0xd8])
    }

    func testTextOnlySubmissionDoesNotRequestAttachmentCapability() {
        let pending = PendingSend(id: "fixture-request", instanceID: "fixture-instance", epoch: "fixture-epoch", threadID: "fixture-thread", text: "draft")
        XCTAssertNil(pending.submissionParams["uploads"])
        XCTAssertNil(pending.submissionParams["context_paths"])
        XCTAssertEqual(pending.submissionParams["text"] as? String, "draft")
    }

    func testPendingPayloadDoesNotChangeWhenDraftAttachmentsChange() {
        let image = PromptAttachment(name: "image.jpg", mimeType: "image/jpeg", data: Data([1, 2]))
        var draft = [image]
        let pending = PendingSend(id: "fixture-request", instanceID: "fixture-instance", epoch: "fixture-epoch", threadID: "fixture-thread", text: "draft", contextPaths: ["src/demo.rs"], attachments: draft)
        draft.removeAll()
        XCTAssertEqual(pending.attachments, [image])
        XCTAssertEqual(pending.attachments[0].payload["data"] as? String, "AQI=")
    }
}

final class MarkdownRenderingTests: XCTestCase {
    @MainActor
    func testLightThemeTextAndAccentContrast() {
        let traits = UITraitCollection(userInterfaceStyle: .light)
        func luminance(_ color: Color) -> Double {
            var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
            XCTAssertTrue(UIColor(color).resolvedColor(with: traits).getRed(&red, green: &green, blue: &blue, alpha: &alpha))
            func linear(_ component: CGFloat) -> Double {
                let value = Double(component)
                return value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
            }
            return 0.2126 * linear(red * alpha + 1 - alpha) + 0.7152 * linear(green * alpha + 1 - alpha) + 0.0722 * linear(blue * alpha + 1 - alpha)
        }
        for color in [ZLTheme.ink, ZLTheme.muted, ZLTheme.focus, ZLTheme.healthy, ZLTheme.warning, ZLTheme.danger] {
            XCTAssertGreaterThanOrEqual(1.05 / (luminance(color) + 0.05), 4.5)
        }
    }

    func testParagraphsAndNestedListMarkersRemainSeparate() {
        XCTAssertEqual(MarkdownDocument.parse("Intro\ncontinued\n\n## List\n- **Bold**\n  - Nested `code`\n1. First\n\nFinal paragraph"), [
            .paragraph("Intro\ncontinued"), .heading(2, "List"), .item("•", 0, "**Bold**"),
            .item("•", 2, "Nested `code`"), .item("1.", 0, "First"), .paragraph("Final paragraph")
        ])
    }
    func testAlignedTablePreservesEmptyAndEscapedCells() {
        XCTAssertEqual(MarkdownDocument.parse("| Feature | Status | Notes |\n| :--- | :---: | ---: |\n| Bullets | ✅ | a\\|b |\n| Files | | `x|y` |"), [
            .table(["Feature", "Status", "Notes"], [["Bullets", "✅", "a|b"], ["Files", "", "`x|y`"]], [.leading, .center, .trailing])
        ])
    }
    func testStreamingFencedCodeStaysLiteral() {
        XCTAssertEqual(MarkdownDocument.parse("```rust\n- literal\n| not a table |"), [.code("rust", "- literal\n| not a table |")])
        XCTAssertEqual(MarkdownDocument.parse("~~~\nhello\n~~~\nAfter"), [.code("", "hello"), .paragraph("After")])
    }
    func testListContinuationAndMalformedTableRemainReadable() {
        XCTAssertEqual(MarkdownDocument.parse("a | b\n-- | nope"), [.paragraph("a | b\n-- | nope")])
        XCTAssertEqual(MarkdownDocument.parse("- long\n  continued\n- next"), [.item("•", 0, "long\ncontinued"), .item("•", 0, "next")])
    }
}
