import XCTest

final class OnboardingUITests: XCTestCase {
    func testSessionsKeyboardDismissesWhenLeavingSearch() {
        let app = XCUIApplication()
        app.launch()

        let search = app.textFields["session-search"]
        XCTAssertTrue(search.waitForExistence(timeout: 10))
        search.tap()
        search.typeText("agent")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 3))

        let searchKey = app.keyboards.buttons["Search"]
        XCTAssertTrue(searchKey.waitForExistence(timeout: 3))
        searchKey.tap()
        XCTAssertFalse(app.keyboards.firstMatch.waitForExistence(timeout: 1))

        app.tabBars.buttons["Connections"].tap()
        XCTAssertTrue(app.staticTexts["No connections"].waitForExistence(timeout: 5))
    }

    func testFirstUseReachesPairingControls() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["Choose a connection"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Connections"].tap()
        XCTAssertTrue(app.staticTexts["No connections"].waitForExistence(timeout: 5))
        app.buttons["add-connection"].tap()

        XCTAssertTrue(app.buttons["scan-pairing-qr"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Use pairing link from clipboard"].exists)
        XCTAssertTrue(app.textFields["gateway-endpoint"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["test-connection"].exists)
        XCTAssertTrue(app.textFields["expected-gateway-id"].exists)
        for _ in 0..<4 {
            if app.buttons["pair-and-save"].exists { break }
            app.swipeUp()
        }
        XCTAssertTrue(app.secureTextFields["pairing-code"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["pair-and-save"].exists)
    }
}
