package dev.zedlink.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class MobileLayoutTest {
    @get:Rule val compose = createComposeRule()

    @Test fun longSessionTitleWrapsAtLargeTextAndPinDoesNotOpenConversation() {
        val title = "Review the disposable project configuration and explain the remaining changes across mobile clients"
        var opened = 0
        var pinned = 0
        compose.setContent {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 1.5f)) {
                ZedLinkTheme("light") {
                    Surface(Modifier.width(320.dp)) {
                        Column {
                            ThreadRow(NativeThread("fixture", title, "generating", 1), true, false, true,
                                { pinned++ }, { opened++ })
                        }
                    }
                }
            }
        }
        val layouts = mutableListOf<TextLayoutResult>()
        compose.onNodeWithText(title, useUnmergedTree = true)
            .performSemanticsAction(SemanticsActions.GetTextLayoutResult) { it(layouts) }
        assertTrue(layouts.single().lineCount > 2)
        assertFalse(layouts.single().hasVisualOverflow)
        compose.onNodeWithContentDescription("Pin session").performClick()
        compose.runOnIdle { assertEquals(1, pinned); assertEquals(0, opened) }
        compose.onNodeWithText(title).performClick()
        compose.runOnIdle { assertEquals(1, opened) }
    }

    @Test fun dismissedNoticeReturnsForNewError() {
        val issue = mutableStateOf("The requested desktop action is unavailable.")
        compose.setContent { ZedLinkTheme("dark") { Surface { Notice(issue.value) } } }
        compose.onNodeWithText(issue.value).assertIsDisplayed()
        compose.onNodeWithContentDescription("Dismiss notice").performClick()
        compose.onNodeWithText(issue.value).assertDoesNotExist()
        compose.runOnIdle { issue.value = "Connection interrupted. Reconnect to continue." }
        compose.onNodeWithText(issue.value).assertIsDisplayed()
    }
}
