package com.opcodelabs.learn.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Download
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.opcodelabs.learn.data.Api
import com.opcodelabs.learn.data.ApiException
import com.opcodelabs.learn.data.Attachment
import kotlinx.coroutines.launch

/** Downloads a lesson file into the app cache, then opens it with a viewer app (PDF reader...). */
@Composable
fun AttachmentList(api: Api, slug: String, files: List<Attachment>, title: String) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val busy = remember { mutableStateMapOf<String, Boolean>() }
    Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
        Text(title, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        files.forEach { f ->
            Row(Modifier.fillMaxWidth().clickable(enabled = busy[f.id] != true) {
                busy[f.id] = true
                scope.launch {
                    try {
                        val file = api.download(slug, f, ctx.cacheDir)
                        val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", file)
                        val type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase())
                            ?: "application/octet-stream"
                        val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, type)
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        try {
                            ctx.startActivity(Intent.createChooser(view, f.name))
                        } catch (e: ActivityNotFoundException) {
                            Toast.makeText(ctx, "No app on this phone opens ${file.extension} files", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: ApiException) {
                        Toast.makeText(ctx, e.message, Toast.LENGTH_LONG).show()
                    } finally {
                        busy[f.id] = false
                    }
                }
            }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.Description, null, tint = MaterialTheme.colorScheme.tertiary)
                Spacer(Modifier.width(12.dp))
                Text(f.name, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(formatSize(f.size), style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = 8.dp))
                if (busy[f.id] == true) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else Icon(Icons.Default.Download, "Open", tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
