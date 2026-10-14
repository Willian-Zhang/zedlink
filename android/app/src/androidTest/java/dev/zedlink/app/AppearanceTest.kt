package dev.zedlink.app

import androidx.compose.material3.Surface
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsDisplayed
import org.junit.Rule
import org.junit.Test

class AppearanceTest {
    @get:Rule val compose = createComposeRule()
    @Test fun removalDialogShowsReadableActionsInLightTheme() {
        compose.setContent { ZedLinkTheme("light") { Surface { ForgetAccessDialog(ConnectionProfile("Fixture", "https://fixture.example", "fixture"), {}, {}) } } }
        compose.onNodeWithText("Remove local access?").assertIsDisplayed()
        compose.onNodeWithText("Remove").assertIsDisplayed()
        compose.onNodeWithText("Cancel").assertIsDisplayed()
    }
}
