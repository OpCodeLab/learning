package com.opcodelabs.learn.ui

import android.app.Activity
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import androidx.activity.compose.BackHandler
import androidx.annotation.OptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import com.opcodelabs.learn.data.Api
import com.opcodelabs.learn.data.ApiException
import com.opcodelabs.learn.data.Course
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.random.Random

/**
 * The lesson player. The whole course is one playlist, so "next" and auto-advance are native.
 * One video at a time per account: the player claims playback on the server (/api/play) and pings
 * every 15 s; if another device takes over, this one pauses and offers "Watch here instead".
 */
@OptIn(UnstableApi::class)
@Composable
fun PlayerScreen(api: Api, slug: String, startLessonId: String, onBack: () -> Unit, onInfo: () -> Unit,
                 onSignedOut: (String?) -> Unit) {
    val ctx = LocalContext.current
    val activity = ctx as Activity
    val scope = rememberCoroutineScope()
    var course by remember { mutableStateOf<Course?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var currentId by remember { mutableStateOf(startLessonId) }
    var elsewhere by remember { mutableStateOf<String?>(null) }    // other device's name while blocked
    var started by remember { mutableStateOf(false) }               // media attached to the player
    val landscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE

    val player = remember {
        ExoPlayer.Builder(ctx)
            .setMediaSourceFactory(DefaultMediaSourceFactory(OkHttpDataSource.Factory(api.http)))
            .build()
    }

    fun lessonOf(item: MediaItem?) = item?.mediaId
    fun signedOut() = onSignedOut("You were signed out. This happens when the account signs in on another device.")

    suspend fun ping(playing: Boolean, ended: Boolean = false, lessonId: String? = lessonOf(player.currentMediaItem)) {
        val id = lessonId ?: return
        val dur = player.duration.takeIf { it > 0 }?.div(1000.0) ?: return
        try {
            api.progress(slug, id, player.currentPosition / 1000.0, dur, playing, ended)
        } catch (e: ApiException) {
            when (e.kind) {
                ApiException.Kind.ELSEWHERE -> { player.pause(); elsewhere = e.extra ?: "another device" }
                ApiException.Kind.SIGNED_OUT -> signedOut()
                else -> Unit   // offline for a moment: next ping retries
            }
        }
    }

    fun attach(c: Course) {
        val lessons = c.allLessons
        val items = lessons.map { l ->
            MediaItem.Builder().setUri(api.mediaUrl(slug, l.id)).setMediaId(l.id)
                .setMediaMetadata(MediaMetadata.Builder().setTitle(l.title).build()).build()
        }
        val start = lessons.indexOfFirst { it.id == currentId }.coerceAtLeast(0)
        val pos = lessons.getOrNull(start)?.position ?: 0.0
        player.setMediaItems(items, start, (if (pos > 5) pos * 1000 else 0.0).toLong())
        player.prepare()
        player.playWhenReady = true
        started = true
    }

    fun takeOver() = scope.launch {
        try {
            api.play(takeover = true)
            elsewhere = null
            val c = course ?: return@launch
            if (!started) attach(c) else { player.prepare(); player.play() }
        } catch (e: ApiException) {
            if (e.kind == ApiException.Kind.SIGNED_OUT) signedOut() else error = e.message
        }
    }

    // Load the course, and only attach the videos once this device may play.
    LaunchedEffect(slug) {
        try {
            val c = api.course(slug)
            if (currentId == "resume") currentId = c.resume ?: c.allLessons.firstOrNull()?.id ?: ""
            course = c
            val other = api.playStatus().elsewhere
            if (other != null) elsewhere = other else attach(c)
        } catch (e: ApiException) {
            if (e.kind == ApiException.Kind.SIGNED_OUT) signedOut() else error = e.message
        }
    }

    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                scope.launch {
                    if (isPlaying) {
                        try { api.play(takeover = false) } catch (e: ApiException) {
                            if (e.kind == ApiException.Kind.ELSEWHERE) { player.pause(); elsewhere = e.extra }
                            if (e.kind == ApiException.Kind.SIGNED_OUT) signedOut()
                        }
                    } else if (player.playbackState != Player.STATE_ENDED) ping(playing = false)
                }
            }
            override fun onMediaItemTransition(item: MediaItem?, reason: Int) {
                val previous = currentId
                currentId = item?.mediaId ?: currentId
                if (reason == Player.MEDIA_ITEM_TRANSITION_REASON_AUTO) {
                    // the previous lesson played to the end
                    scope.launch {
                        try { api.progress(slug, previous, 1.0, 1.0, playing = true, ended = true) } catch (_: ApiException) {}
                    }
                }
            }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) scope.launch { ping(playing = false, ended = true) }
            }
            override fun onPlayerError(e: PlaybackException) {
                scope.launch {   // e.g. 409 because another device started meanwhile
                    val other = runCatching { api.playStatus().elsewhere }.getOrNull()
                    if (other != null) elsewhere = other
                    else error = "This video can't be played right now. Check your connection and try again."
                }
            }
        }
        player.addListener(listener)
        onDispose {
            player.removeListener(listener)
            val id = lessonOf(player.currentMediaItem)
            val pos = player.currentPosition / 1000.0
            val dur = player.duration / 1000.0
            if (id != null && dur > 0) kotlinx.coroutines.GlobalScope.launch {
                runCatching { api.progress(slug, id, pos, dur, playing = false, ended = false) }
            }
            player.release()
            activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED
            showSystemBars(activity, true)
        }
    }

    // Heartbeat while playing: keeps this device's claim alive and saves progress.
    LaunchedEffect(player) {
        while (true) {
            delay(15_000)
            if (player.isPlaying) ping(playing = true)
        }
    }

    LaunchedEffect(landscape) { showSystemBars(activity, !landscape) }
    BackHandler(landscape) { activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT }

    val c = course
    val playerBox: @Composable (Modifier) -> Unit = { mod ->
        Box(mod.background(Color.Black)) {
            AndroidView({ context ->
                PlayerView(context).apply {
                    this.player = player
                    keepScreenOn = true
                    setShowNextButton(true)
                    setShowPreviousButton(true)
                    setFullscreenButtonClickListener { full ->
                        activity.requestedOrientation = if (full) ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                        else ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT
                    }
                }
            }, Modifier.fillMaxSize(), update = { it.setFullscreenButtonState(landscape) })
            c?.watermark?.let { Watermark(it) }
            elsewhere?.let { dev -> ElsewhereOverlay(dev, ::takeOver) }
        }
    }

    when {
        c == null && error != null -> Box(Modifier.fillMaxSize()) { ErrorState(error!!, onBack) }
        landscape -> playerBox(Modifier.fillMaxSize())
        else -> Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            Spacer(Modifier.fillMaxWidth().background(Chrome).statusBarsPadding())
            Box {
                playerBox(Modifier.fillMaxWidth().aspectRatio(16f / 9f))
                IconButton(onBack, Modifier.align(Alignment.TopStart)) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = Color.White)
                }
                IconButton(onInfo, Modifier.align(Alignment.TopEnd)) {
                    Icon(Icons.Outlined.Info, "About this course", tint = Color.White)
                }
            }
            if (c == null) { Loading(); return@Column }
            val lesson = c.allLessons.firstOrNull { it.id == currentId }
            val listState = rememberLazyListState()
            LazyColumn(state = listState, modifier = Modifier.fillMaxSize()) {
                item {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(c.sectionOf(currentId)?.title ?: "", style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(lesson?.let { "${it.number ?: (it.index + 1)}. ${it.title}" } ?: "",
                            style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(c.title + (totalLength(c.length ?: 0.0)?.let { " · $it" } ?: "") + " · ${c.done} / ${c.lessons} done",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    }
                }
                if (lesson != null && lesson.attachments.isNotEmpty()) item {
                    AttachmentList(api, slug, lesson.attachments, "Files for this lesson")
                }
                item { HorizontalDivider() }
                c.sections.forEach { s ->
                    item {
                        Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant)
                            .padding(horizontal = 16.dp, vertical = 10.dp)) {
                            Text(s.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                            val len = totalLength(s.lessons.sumOf { it.length ?: 0.0 })
                            Text("${s.lessons.count { it.completed }} / ${s.lessons.size}" + (len?.let { " · $it" } ?: ""),
                                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    items(s.lessons, key = { it.id }) { l ->
                        LessonRow(l, current = l.id == currentId) {
                            val i = c.allLessons.indexOfFirst { it.id == l.id }
                            if (started && i >= 0) { player.seekTo(i, 0); player.play() }
                        }
                    }
                }
            }
        }
    }
}

/** The student's email over the video, moving every 40 s (discourages sharing recordings). */
@Composable
private fun Watermark(email: String) {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        var fx by remember { mutableFloatStateOf(0.1f) }
        var fy by remember { mutableFloatStateOf(0.15f) }
        LaunchedEffect(Unit) {
            while (true) {
                fx = 0.05f + Random.nextFloat() * 0.5f
                fy = 0.08f + Random.nextFloat() * 0.7f
                delay(40_000)
            }
        }
        Text(email, Modifier.offset(maxWidth * fx, maxHeight * fy), color = Color.White.copy(alpha = 0.28f),
            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ElsewhereOverlay(device: String, onTakeOver: () -> Unit) {
    Surface(Modifier.fillMaxSize(), color = Color(0xE60A0E14)) {
        Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text("This account is watching on another device", color = Color.White, fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center)
            Text("($device)", color = Color(0xFFC7CED8), style = MaterialTheme.typography.bodySmall)
            Text("Your access is personal: one video at a time.", color = Color.White,
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 6.dp, bottom = 12.dp))
            Button(onTakeOver) { Text("Watch here instead") }
        }
    }
}

private fun showSystemBars(activity: Activity, show: Boolean) {
    val c = WindowCompat.getInsetsController(activity.window, activity.window.decorView)
    if (show) c.show(WindowInsetsCompat.Type.systemBars())
    else {
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        c.hide(WindowInsetsCompat.Type.systemBars())
    }
}
