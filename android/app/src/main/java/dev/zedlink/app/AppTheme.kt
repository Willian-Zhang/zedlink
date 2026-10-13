package dev.zedlink.app

import androidx.activity.compose.LocalActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.SideEffect
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

private data class Palette(
    val background: Color, val surface: Color, val raised: Color, val line: Color,
    val ink: Color, val muted: Color, val blue: Color, val green: Color, val warning: Color,
)
private val dark = Palette(Color.Black, Color(0xFF0D0E10), Color(0xFF151719), Color(0xFF2B2D30),
    Color(0xFFF3F3F1), Color(0xFFA2A5AA), Color(0xFFD5E7FF), Color(0xFF79C79B), Color(0xFFE2BC80))
private val light = Palette(Color.White, Color(0xFFF2F2F6), Color(0xFFE8E9EE), Color(0xFFCACCD2),
    Color(0xFF17191D), Color(0xFF5B6068), Color(0xFF234D9C), Color(0xFF196C40), Color(0xFF805212))
private val LocalPalette = staticCompositionLocalOf { dark }
internal val Black: Color @Composable get() = LocalPalette.current.background
internal val Surface: Color @Composable get() = LocalPalette.current.surface
internal val Raised: Color @Composable get() = LocalPalette.current.raised
internal val Line: Color @Composable get() = LocalPalette.current.line
internal val Ink: Color @Composable get() = LocalPalette.current.ink
internal val Muted: Color @Composable get() = LocalPalette.current.muted
internal val Subtle: Color @Composable get() = LocalPalette.current.muted
internal val Blue: Color @Composable get() = LocalPalette.current.blue
internal val Green: Color @Composable get() = LocalPalette.current.green
internal val Warning: Color @Composable get() = LocalPalette.current.warning

@Composable internal fun ZedLinkTheme(appearance: String, content: @Composable () -> Unit) {
    val useDark = appearance == "dark" || appearance == "system" && isSystemInDarkTheme()
    val palette = if (useDark) dark else light
    val activity = LocalActivity.current as? MainActivity
    SideEffect {
        val bars = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT) { useDark }
        activity?.enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
    }
    val scheme = if (useDark) darkColorScheme(primary = palette.ink, onPrimary = palette.background,
        background = palette.background, onBackground = palette.ink, surface = palette.surface,
        onSurface = palette.ink, outline = palette.line, secondary = palette.blue)
    else lightColorScheme(primary = palette.ink, onPrimary = palette.background,
        background = palette.background, onBackground = palette.ink, surface = palette.surface,
        onSurface = palette.ink, outline = palette.line, secondary = palette.blue)
    CompositionLocalProvider(LocalPalette provides palette) { MaterialTheme(colorScheme = scheme, typography = Typography(), content = content) }
}
