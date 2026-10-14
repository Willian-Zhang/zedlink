package dev.zedlink.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test

class MobileLayoutTest {
    @get:Rule val compose = createComposeRule()

    @Test fun tappingTerminalFocusesVisibleCommandField() {
        compose.setContent {
            val requester = remember { FocusRequester() }
            ZedLinkTheme("dark") {
                Surface {
                    Column(Modifier.width(320.dp).height(360.dp)) {
                        Box(Modifier.weight(1f)) {
                            TerminalOutput(AnnotatedString("Disposable terminal prompt $"), rememberScrollState(),
                                rememberScrollState(), true, true) { requester.requestFocus() }
                        }
                        TerminalKeyStrip(true) {}
                        BasicTextField("", {}, Modifier.focusRequester(requester).height(48.dp).testTag("terminal-input"))
                    }
                }
            }
        }
        compose.onNodeWithTag("terminal-input").assertIsDisplayed().assertIsNotFocused()
        compose.onNodeWithText("Disposable terminal prompt $").performClick()
        compose.onNodeWithTag("terminal-input").assertIsFocused()
    }

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

    @Test fun terminalKeysRespectInputAvailabilityAndEmitControlBytes() {
        val available = mutableStateOf(false)
        val sent = mutableListOf<String>()
        compose.setContent { ZedLinkTheme("light") { Surface { TerminalKeyStrip(available.value) { sent += it } } } }
        compose.onNodeWithText("Ctrl C").assertIsNotEnabled()
        compose.onNodeWithText("Tab").assertIsNotEnabled()
        compose.runOnIdle { assertTrue(sent.isEmpty()); available.value = true }
        compose.onNodeWithText("Ctrl C").assertIsEnabled().performClick()
        compose.onNodeWithText("Tab").performClick()
        compose.runOnIdle { assertEquals(listOf("\u0003", "\t"), sent) }
    }
}
