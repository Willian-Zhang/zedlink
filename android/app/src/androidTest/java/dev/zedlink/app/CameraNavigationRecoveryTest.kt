package dev.zedlink.app

import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Rule
import org.junit.Test

/** Run in a disposable emulator/app installation. No pairing secret or real gateway is used. */
class CameraNavigationRecoveryTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun addConnectionSurvivesActivityRecreation() {
        rule.onNodeWithText("Connections").performClick()
        rule.onNodeWithText("Add").performClick()
        rule.onNodeWithText("Scan workstation QR").assertExists()
        rule.activityRule.scenario.recreate()
        rule.waitForIdle()
        rule.onNodeWithText("Scan workstation QR").assertExists()
        rule.onNodeWithText("Test HTTPS endpoint").assertExists()
    }
    @Test fun decodedQrResultAfterRecreationOpensPairingDraftWithoutConnecting() {
        rule.activityRule.scenario.recreate()
        val link = "https://fixture.invalid#v=1&gateway=00000000-0000-0000-0000-000000000001&pair=1234567890"
        val result = com.journeyapps.barcodescanner.ScanContract().parseResult(android.app.Activity.RESULT_OK,
            android.content.Intent().putExtra(com.google.zxing.client.android.Intents.Scan.RESULT, link))
        rule.runOnUiThread { rule.activity.acceptPairingScanResult(result) }
        rule.waitForIdle()
        rule.onNodeWithText("https://fixture.invalid").assertExists()
        rule.onNodeWithText("Test HTTPS endpoint").assertExists()
        rule.onNodeWithText("Pair and save").assertIsNotEnabled()
    }

    @Test fun cancelledQrReturnsToPairingWithVisibleExplanation() {
        val result = com.journeyapps.barcodescanner.ScanContract().parseResult(android.app.Activity.RESULT_CANCELED, null)
        rule.runOnUiThread { rule.activity.acceptPairingScanResult(result) }
        rule.waitForIdle()
        rule.onNodeWithText("No QR was received. Scan again or paste the workstation pairing link.").assertExists()
        rule.onNodeWithText("Scan workstation QR").assertExists()
    }

}
