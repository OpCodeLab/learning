package com.opcodelabs.learn.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.opcodelabs.learn.data.Api
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request

private val imageCache = HashMap<String, ImageBitmap>()

/** Course cover: fetched with the sign-in token (covers are not public), cached in memory. */
@Composable
fun Cover(api: Api, slug: String, coverId: String?, title: String, modifier: Modifier = Modifier) {
    val url = coverId?.let { api.mediaUrl(slug, it) }
    val bmp by produceState(url?.let { imageCache[it] }, url) {
        if (url != null && value == null) {
            value = withContext(Dispatchers.IO) {
                runCatching {
                    api.http.newCall(Request.Builder().url(url).build()).execute().use { r ->
                        r.body?.bytes()?.let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
                    }
                }.getOrNull()
            }?.also { imageCache[url] = it }
        }
    }
    Box(modifier.background(Chrome), contentAlignment = Alignment.Center) {
        val b = bmp
        if (b != null) Image(b, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else Text(title.take(1).uppercase(), color = Gold, fontSize = 48.sp, fontWeight = FontWeight.Bold)
    }
}

/** Lesson length like Udemy: "9 min". */
fun lessonLength(seconds: Double?): String? =
    seconds?.takeIf { it > 0 }?.let { "${maxOf(1, Math.round(it / 60).toInt())} min" }

/** "21 h 12 min", "45 min". */
fun totalLength(seconds: Double): String? {
    if (seconds <= 0) return null
    val m = maxOf(1, Math.round(seconds / 60).toInt())
    return if (m >= 60) "${m / 60} h ${m % 60} min" else "$m min"
}

@Composable
fun Loading() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
fun ErrorState(message: String, onRetry: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(32.dp), verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text(message, textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Button(onRetry, Modifier.padding(top = 16.dp)) { Text("Try again") }
    }
}

fun formatSize(n: Long): String = when {
    n < 1024 -> "$n B"
    n < 1024 * 1024 -> "%.0f KB".format(n / 1024.0)
    else -> "%.1f MB".format(n / 1024.0 / 1024.0)
}
