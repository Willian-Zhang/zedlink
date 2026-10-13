import XCTest

/// Isolated presentation fixture, never evidence of native agent integration.
final class SessionsPreviewUITests: XCTestCase {
    func testFiltersPinsAndDemoIdentity() {
        let app = XCUIApplication()
        app.launchArguments = ["--zedlink-demo", "-zedlink.appearance", "dark"]
        app.launch()
        XCTAssertTrue(app.staticTexts["DEMO PREVIEW · Sample sessions, no live connection"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Review deployment changes"].exists)
        app.buttons["session-filter-Running"].tap()
        XCTAssertTrue(app.staticTexts["Improve project navigation"].exists)
        XCTAssertFalse(app.staticTexts["Review deployment changes"].exists)
        app.buttons["pin-demo-nav"].tap()
        app.buttons["session-filter-Pinned"].tap()
        XCTAssertTrue(app.staticTexts["Improve project navigation"].exists)
        app.buttons["pin-demo-nav"].tap()
        XCTAssertTrue(app.staticTexts["No matching sessions"].exists)
        app.buttons["session-filter-All"].tap()
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = "Sessions-demo-dark"; image.lifetime = .keepAlways; add(image)
    }
}
