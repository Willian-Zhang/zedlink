import XCTest

final class OnboardingUITests: XCTestCase {
    func testFirstUseReachesPairingControls() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["Choose a connection"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Connections"].tap()
        XCTAssertTrue(app.staticTexts["No connections"].waitForExistence(timeout: 5))
        app.buttons["add-connection"].tap()

        XCTAssertTrue(app.textFields["gateway-endpoint"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["test-connection"].exists)
        XCTAssertTrue(app.textFields["expected-gateway-id"].exists)
        XCTAssertTrue(app.secureTextFields["pairing-code"].exists)
        XCTAssertTrue(app.buttons["pair-and-save"].exists)
    }
}
