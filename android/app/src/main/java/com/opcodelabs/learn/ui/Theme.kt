package com.opcodelabs.learn.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.TopAppBarColors
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// Same palette as the website and the lab site (lab.opcode-labs.com): black chrome like the logo,
// gold accent, square corners.
val Gold = Color(0xFFFCD23C)
val GoldDeep = Color(0xFFE0B000)
val Chrome = Color(0xFF000000)
val ChromeMuted = Color(0xFFA7ADB4)
val Accent = Gold
val Ok = Color(0xFF1E7A45)
val Amber = Gold

private val Light = lightColorScheme(
    primary = Gold, onPrimary = Color.Black, primaryContainer = Color(0xFFFFF6D1), onPrimaryContainer = Color(0xFF3D2E00),
    secondary = Color(0xFF15181C), onSecondary = Color.White,
    tertiary = Color(0xFF7A5C00), onTertiary = Color.White,  // gold-family text on light surfaces ("eyebrow")
    background = Color(0xFFF3F4F6), onBackground = Color(0xFF15181C), surface = Color.White, onSurface = Color(0xFF15181C),
    surfaceVariant = Color(0xFFF1F3F5), onSurfaceVariant = Color(0xFF5A636D),
    outline = Color(0xFFD8DCE1), outlineVariant = Color(0xFFD8DCE1), error = Color(0xFFB42318),
)
private val Dark = darkColorScheme(
    primary = Gold, onPrimary = Color.Black, primaryContainer = Color(0xFF2A2410), onPrimaryContainer = Gold,
    secondary = Color(0xFFE9ECEF), onSecondary = Color.Black,
    tertiary = Gold, onTertiary = Color.Black,
    background = Color(0xFF0A0B0D), onBackground = Color(0xFFE9ECEF), surface = Color(0xFF131518), onSurface = Color(0xFFE9ECEF),
    surfaceVariant = Color(0xFF1A1D21), onSurfaceVariant = Color(0xFF9AA3AD),
    outline = Color(0xFF5C6670), outlineVariant = Color(0xFF262A2F), error = Color(0xFFF97066),
)

private val Square = Shapes(
    extraSmall = RoundedCornerShape(2.dp), small = RoundedCornerShape(2.dp), medium = RoundedCornerShape(4.dp),
    large = RoundedCornerShape(4.dp), extraLarge = RoundedCornerShape(6.dp),
)

/** Black top bar with white text, like the website's header. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun brandBarColors(): TopAppBarColors = TopAppBarDefaults.topAppBarColors(
    containerColor = Chrome, scrolledContainerColor = Chrome, titleContentColor = Color.White,
    navigationIconContentColor = Color.White, actionIconContentColor = Color.White,
)

@Composable
fun LearnTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, shapes = Square, content = content)
}
