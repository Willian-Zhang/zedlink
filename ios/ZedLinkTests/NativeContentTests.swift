import XCTest
@testable import ZedLink

final class NativeContentTests: XCTestCase {
    @MainActor
    func testProfileStoreKeepsIdentityForTheSameGatewayAddress() {
        let original = ConnectionProfile(name: "Zed", route: .tailscale,
            endpoint: "https://old.example", gatewayID: "A415D217-C1C0-42DA-9CC8-887D4305A73E")
        let updated = ProfileStore.profileForSave(ConnectionProfile(name: "Zed renamed", route: .tailscale,
            endpoint: "https://old.example/", gatewayID: "a415d217-c1c0-42da-9cc8-887d4305a73e"),
            among: [original])
        XCTAssertEqual(updated.id, original.id)
        XCTAssertEqual(updated.name, "Zed renamed")
    }

    @MainActor
    func testProfileStoreKeepsAnotherRouteToTheSameGateway() {
        let original = ConnectionProfile(name: "Tailscale", route: .tailscale,
            endpoint: "https://zed.tailnet.example", gatewayID: "A415D217-C1C0-42DA-9CC8-887D4305A73E")
        let alternate = ConnectionProfile(name: "Local", route: .local,
            endpoint: "https://zed.lan.example", gatewayID: "a415d217-c1c0-42da-9cc8-887d4305a73e")
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
