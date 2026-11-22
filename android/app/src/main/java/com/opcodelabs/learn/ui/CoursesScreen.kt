package com.opcodelabs.learn.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Language
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.opcodelabs.learn.BuildConfig
import com.opcodelabs.learn.R
import com.opcodelabs.learn.data.Api
import com.opcodelabs.learn.data.ApiException
import com.opcodelabs.learn.data.AppVersion
import com.opcodelabs.learn.data.CourseCard
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CoursesScreen(api: Api, email: String, onOpen: (String) -> Unit, onSignedOut: (String?) -> Unit) {
    var courses by remember { mutableStateOf<List<CourseCard>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    var update by remember { mutableStateOf<AppVersion?>(null) }
    var menu by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    LaunchedEffect(reload) {
        try {
            courses = api.courses(); error = null
        } catch (e: ApiException) {
            if (e.kind == ApiException.Kind.SIGNED_OUT) onSignedOut(
                "You were signed out. This happens when the account signs in on another device.")
            else error = e.message
        }
        refreshing = false
    }
    LaunchedEffect(Unit) {
        update = runCatching { api.appVersion() }.getOrNull()?.takeIf { it.version_code > BuildConfig.VERSION_CODE }
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text("My courses", fontWeight = FontWeight.Bold) }, colors = brandBarColors(),
            navigationIcon = {
                Image(painterResource(R.drawable.opcode_mark), "OpCode Labs", Modifier.padding(start = 14.dp, end = 4.dp).size(32.dp))
            }, actions = {
            IconButton({ menu = true }) { Icon(Icons.Default.AccountCircle, "Account") }
            DropdownMenu(menu, { menu = false }) {
                Text(email, Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                HorizontalDivider()
                DropdownMenuItem({ Text("Open the website") }, leadingIcon = { Icon(Icons.Default.Language, null) },
                    onClick = { menu = false; ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(api.base))) })
                DropdownMenuItem({ Text("Sign out") }, leadingIcon = { Icon(Icons.AutoMirrored.Filled.Logout, null) },
                    onClick = { menu = false; scope.launch { api.logout(); onSignedOut(null) } })
            }
        })
    }) { pad ->
        PullToRefreshBox(refreshing, { refreshing = true; reload++ }, Modifier.padding(pad).fillMaxSize()) {
            val list = courses
            when {
                list == null && error != null -> ErrorState(error!!) { reload++ }
                list == null -> Loading()
                else -> LazyVerticalGrid(GridCells.Adaptive(300.dp), contentPadding = PaddingValues(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    update?.let { v ->
                        item(span = { GridItemSpan(maxLineSpan) }) {
                            Banner("A new version (${v.version_name}) is available. Tap to download.")
                            TextButton({ ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(v.url))) },
                                colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.tertiary)) {
                                Text("Download the update")
                            }
                        }
                    }
                    if (list.isEmpty()) item(span = { GridItemSpan(maxLineSpan) }) {
                        Text("No course here yet. Once your trainer opens a course for you, it shows up here.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(16.dp))
                    }
                    items(list, key = { it.slug }) { c -> CourseCardView(api, c) { onOpen(c.slug) } }
                }
            }
        }
    }
}

@Composable
private fun CourseCardView(api: Api, c: CourseCard, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick), shape = RoundedCornerShape(4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(0.dp),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)) {
        Cover(api, c.slug, c.cover, c.title, Modifier.fillMaxWidth().aspectRatio(16f / 9f))
        Box(Modifier.fillMaxWidth().height(3.dp).background(Gold))
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(c.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            LinearProgressIndicator({ c.pct / 100f }, Modifier.fillMaxWidth(), drawStopIndicator = {})
            val until = c.expires?.let { " · until " + DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(it * 1000)) } ?: ""
            Text("${c.done} / ${c.lessons} lessons · ${c.pct}%$until", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
