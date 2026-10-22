import XCTest

/// Opt-in against an already paired, explicitly exposed disposable test thread.
/// No test selects a user's project implicitly or performs approval/tool mutations.
final class SessionWorkspaceUITests: XCTestCase {
    private func openDisposableSession() throws -> XCUIApplication {
        let environment = ProcessInfo.processInfo.environment
        guard let thread = environment["ZEDLINK_E2E_THREAD_ID"], !thread.isEmpty else {
            throw XCTSkip("Set ZEDLINK_E2E_THREAD_ID to an exposed disposable thread, after pairing this simulator.")
        }
        let app = XCUIApplication(); app.launch()
        let row = app.buttons["thread-" + thread]
        XCTAssertTrue(row.waitForExistence(timeout: 20), "Disposable test thread is unavailable; verify pairing, route, and exposure.")
        row.tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "composer").firstMatch.waitForExistence(timeout: 15))
        XCTAssertFalse(app.tabBars.buttons["Connections"].exists)
        XCTAssertFalse(app.tabBars.buttons["Settings"].exists)
        return app
    }

    func testSessionNavigationAndWorkspaceViews() throws {
        let app = try openDisposableSession()
        app.buttons["open-workspace"].tap()
        for page in ["files", "changes", "terminal", "debug", "activity"] {
            let tab = app.buttons["workspace-" + page]
            XCTAssertTrue(tab.waitForExistence(timeout: 5)); tab.tap()
            XCTAssertTrue(app.buttons["close-workspace"].exists)
            let capture = XCTAttachment(screenshot: app.screenshot())
            capture.name = "Workspace-" + page; capture.lifetime = .keepAlways; add(capture)
        }
        app.buttons["close-workspace"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "composer").firstMatch.waitForExistence(timeout: 5))
        app.buttons["back-to-sessions"].tap()
        XCTAssertTrue(app.tabBars.buttons["Connections"].waitForExistence(timeout: 5))
    }

    func testComposerKeyboardDismissesOnWorkspaceNavigation() throws {
        let app = try openDisposableSession()
        app.descendants(matching: .any).matching(identifier: "composer").firstMatch.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(app.toolbars.buttons["Done"].exists)
        app.buttons["open-workspace"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.waitForExistence(timeout: 1))
        app.buttons["close-workspace"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists)
    }

    func testNativePromptRoundTrip() throws {
        guard ProcessInfo.processInfo.environment["ZEDLINK_E2E_ALLOW_SEND"] == "1" else {
            throw XCTSkip("Set ZEDLINK_E2E_ALLOW_SEND=1 only for the explicitly exposed disposable thread.")
        }
        let app = try openDisposableSession()
        let composer = app.descendants(matching: .any).matching(identifier: "composer").firstMatch
        composer.tap()
        composer.typeText("For this disposable test, reply exactly: ZEDLINK_IOS_ROUND_TRIP")
        app.buttons["send-prompt"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.waitForExistence(timeout: 1))
        XCTAssertTrue(app.staticTexts["ZEDLINK_IOS_ROUND_TRIP"].waitForExistence(timeout: 120), "Check the authoritative desktop thread and the configured model if the reply is missing.")
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "Native-prompt-round-trip"; capture.lifetime = .keepAlways; add(capture)
    }

    func testProjectTextSearchAndFileContents() throws {
        let app = try openDisposableSession()
        guard let query = ProcessInfo.processInfo.environment["ZEDLINK_E2E_SEARCH_TEXT"], !query.isEmpty else {
            throw XCTSkip("Set ZEDLINK_E2E_SEARCH_TEXT to a known string in the disposable project.")
        }
        app.buttons["open-workspace"].tap()
        let field = app.textFields["project-content-query"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText(query)
        app.buttons["Search"].tap()
        let result = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "project-search-result-")).firstMatch
        XCTAssertTrue(result.waitForExistence(timeout: 20)); result.tap()
        XCTAssertTrue(app.textFields["find-in-file"].waitForExistence(timeout: 10))
        app.textFields["find-in-file"].tap(); app.textFields["find-in-file"].typeText(query)
        let capture = XCTAttachment(screenshot: app.screenshot()); capture.name = "Search-file-contents"; capture.lifetime = .keepAlways; add(capture)
    }

    func testConversationSearchOpensLoadedMessage() throws {
        guard let phrase = ProcessInfo.processInfo.environment["ZEDLINK_E2E_TRANSCRIPT_TEXT"], phrase.count >= 2 else {
            throw XCTSkip("Set ZEDLINK_E2E_TRANSCRIPT_TEXT to text in the disposable thread's loaded page.")
        }
        let app = try openDisposableSession()
        app.buttons["Session actions"].tap()
        app.buttons["Find in conversation"].tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        search.tap(); search.typeText(phrase)
        let result = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "conversation-search-result-")).firstMatch
        XCTAssertTrue(result.waitForExistence(timeout: 10), "The phrase must be present in the loaded native transcript page.")
        result.tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "composer").firstMatch.waitForExistence(timeout: 5))
    }
}
