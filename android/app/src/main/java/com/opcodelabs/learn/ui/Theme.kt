package com.opcodelabs.learn.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Same palette as the website (style.css).
val Accent = Color(0xFF0F6CBD)
val AccentDark = Color(0xFF479EF5)
val Ok = Color(0xFF107C10)
val Amber = Color(0xFFFFB900)

private val Light = lightColorScheme(
    primary = Accent, onPrimary = Color.White, primaryContainer = Color(0xFFEBF3FC), onPrimaryContainer = Accent,
    background = Color(0xFFF7F9FC), surface = Color.White, onSurface = Color(0xFF1B1F24),
    surfaceVariant = Color(0xFFF0F3F8), onSurfaceVariant = Color(0xFF5F6B7A), outlineVariant = Color(0xFFE3E8EF),
)
private val Dark = darkColorScheme(
    primary = AccentDark, onPrimary = Color(0xFF0B1A2A), primaryContainer = Color(0xFF10263D), onPrimaryContainer = AccentDark,
    background = Color(0xFF121417), surface = Color(0xFF1B1E23), onSurface = Color(0xFFE6E9EE),
    surfaceVariant = Color(0xFF22262C), onSurfaceVariant = Color(0xFF9AA5B4), outlineVariant = Color(0xFF2B3038),
)

@Composable
fun LearnTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, content = content)
}
