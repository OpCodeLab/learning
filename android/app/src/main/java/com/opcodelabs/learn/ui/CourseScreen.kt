package com.opcodelabs.learn.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.opcodelabs.learn.data.Api
import com.opcodelabs.learn.data.ApiException
import com.opcodelabs.learn.data.Course
import com.opcodelabs.learn.data.Lesson

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CourseScreen(api: Api, slug: String, onBack: () -> Unit, onPlay: (String) -> Unit,
                 onSignedOut: (String?) -> Unit) {
    var course by remember { mutableStateOf<Course?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val collapsed = remember { mutableStateMapOf<Int, Boolean>() }

    LaunchedEffect(reload) {   // also re-runs when coming back from the player: fresh ticks and %
        try {
            course = api.course(slug); error = null
        } catch (e: ApiException) {
            if (e.kind == ApiException.Kind.SIGNED_OUT) onSignedOut("You were signed out.") else error = e.message
        }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text(course?.title ?: "", maxLines = 1, overflow = TextOverflow.Ellipsis) },
            navigationIcon = { IconButton(onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            colors = brandBarColors())
    }) { pad ->
        val c = course
        when {
            c == null && error != null -> ErrorState(error!!) { reload++ }
            c == null -> Loading()
            else -> LazyColumn(Modifier.padding(pad), contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item { Header(api, c, onPlay) }
                c.sections.forEachIndexed { si, s ->
                    val closed = collapsed[si] ?: false
                    item(key = "s$si") {
                        Surface(shape = RoundedCornerShape(4.dp), color = MaterialTheme.colorScheme.surface,
                            tonalElevation = 1.dp, modifier = Modifier.fillMaxWidth()) {
                            Column {
                                Row(Modifier.fillMaxWidth().clickable { collapsed[si] = !closed }.padding(16.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f)) {
                                        Text(s.title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                                        val done = s.lessons.count { it.completed }
                                        Text("$done / ${s.lessons.size} lessons", style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    }
                                    Icon(if (closed) Icons.Default.ExpandMore else Icons.Default.ExpandLess, null)
                                }
                                if (!closed) {
                                    s.lessons.forEach { l -> LessonRow(l, current = false) { onPlay(l.id) } }
                                    if (s.resources.isNotEmpty()) AttachmentList(api, c.slug, s.resources, "Resources")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Header(api: Api, c: Course, onPlay: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Cover(api, c.slug, c.cover, c.title,
            Modifier.widthIn(max = 640.dp).fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(4.dp)))
        Text(c.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.SemiBold)
        if (c.description.isNotBlank()) Text(c.description.trim(), style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        LinearProgressIndicator({ c.pct / 100f }, Modifier.fillMaxWidth(), drawStopIndicator = {})
        Text("${c.done} / ${c.lessons} lessons done · ${c.pct}%", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        val resume = c.allLessons.firstOrNull { it.id == c.resume }
        if (resume != null) Button({ onPlay(resume.id) }, Modifier.fillMaxWidth(), shape = RoundedCornerShape(2.dp)) {
            Icon(Icons.Default.PlayArrow, null)
            Spacer(Modifier.width(8.dp))
            Text((if (c.done > 0) "Continue: " else "Start: ") + resume.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
fun LessonRow(l: Lesson, current: Boolean, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick = onClick)
        .background(if (current) MaterialTheme.colorScheme.primaryContainer else Color.Transparent)
        .padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        if (l.completed) Icon(Icons.Default.CheckCircle, "Done", tint = Ok, modifier = Modifier.size(22.dp))
        else Icon(Icons.Outlined.Circle, null, tint = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Text(l.title, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (current) FontWeight.SemiBold else FontWeight.Normal,
            color = if (current) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.onSurface)
        if (l.attachments.isNotEmpty()) Icon(Icons.Default.AttachFile, "Files", Modifier.size(18.dp),
            tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
