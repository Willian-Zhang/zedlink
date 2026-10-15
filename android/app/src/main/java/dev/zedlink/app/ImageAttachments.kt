package dev.zedlink.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas as AndroidCanvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import java.io.ByteArrayOutputStream
import kotlin.math.max
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal suspend fun loadPromptBitmap(context: Context, uri: Uri): Bitmap? = withContext(Dispatchers.IO) {
    val decoded = context.contentResolver.openInputStream(uri)?.use(BitmapFactory::decodeStream) ?: return@withContext null
    val scale = minOf(1f, 1600f / max(decoded.width, decoded.height).coerceAtLeast(1))
    if (scale >= 1f) decoded else Bitmap.createScaledBitmap(decoded, (decoded.width * scale).toInt(), (decoded.height * scale).toInt(), true)
}

internal fun promptJpeg(bitmap: Bitmap, strokes: List<List<Offset>> = emptyList()): ByteArray? {
    val result = bitmap.copy(Bitmap.Config.ARGB_8888, true)
    if (strokes.isNotEmpty()) {
        val canvas = AndroidCanvas(result)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = AndroidColor.rgb(255, 93, 104)
            style = Paint.Style.STROKE
            strokeCap = Paint.Cap.ROUND
            strokeJoin = Paint.Join.ROUND
            strokeWidth = max(4f, result.width / 120f)
        }
        strokes.forEach { points ->
            points.zipWithNext().forEach { (from, to) ->
                canvas.drawLine(from.x * result.width, from.y * result.height, to.x * result.width, to.y * result.height, paint)
            }
        }
    }
    for (quality in listOf(88, 78, 68, 58, 48)) {
        val output = ByteArrayOutputStream()
        result.compress(Bitmap.CompressFormat.JPEG, quality, output)
        if (output.size() <= 1024 * 1024) return output.toByteArray()
    }
    return null
}

@Composable
internal fun ImageAnnotationDialog(bitmap: Bitmap, close: () -> Unit, attach: (ByteArray) -> Unit) {
    val strokes = remember(bitmap) { mutableStateListOf<List<Offset>>() }
    var active by remember(bitmap) { mutableStateOf<List<Offset>>(emptyList()) }
    AlertDialog(
        onDismissRequest = close,
        title = { Text("Review image") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Draw to mark an area, or attach the image as it is.", color = Muted, style = MaterialTheme.typography.bodySmall)
                Box(Modifier.fillMaxWidth().aspectRatio(bitmap.width.toFloat() / bitmap.height.coerceAtLeast(1)).background(Color.Black)) {
                    Image(bitmap.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.FillBounds)
                    Canvas(Modifier.fillMaxSize().pointerInput(bitmap, strokes.size) {
                        detectDragGestures(
                            onDragStart = { point -> active = listOf(Offset(point.x / size.width, point.y / size.height)) },
                            onDrag = { change, _ ->
                                change.consume()
                                active = active + Offset(change.position.x / size.width, change.position.y / size.height)
                            },
                            onDragEnd = { if (active.size > 1) strokes += active; active = emptyList() },
                            onDragCancel = { active = emptyList() },
                        )
                    }) {
                        (strokes.toList() + listOf(active)).filter { it.size > 1 }.forEach { points ->
                            points.zipWithNext().forEach { (from, to) ->
                                drawLine(Color(0xffff5d68), Offset(from.x * size.width, from.y * size.height),
                                    Offset(to.x * size.width, to.y * size.height), strokeWidth = 4.dp.toPx())
                            }
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { if (strokes.isNotEmpty()) strokes.removeAt(strokes.lastIndex) }, enabled = strokes.isNotEmpty()) { Text("Undo") }
                    TextButton(onClick = { strokes.clear(); active = emptyList() }, enabled = strokes.isNotEmpty() || active.isNotEmpty()) { Text("Clear") }
                }
            }
        },
        confirmButton = {
            Button(onClick = { promptJpeg(bitmap, strokes)?.let(attach) }, shape = androidx.compose.ui.graphics.RectangleShape) { Text("ATTACH") }
        },
        dismissButton = { TextButton(onClick = close) { Text("CANCEL") } },
        containerColor = Surface,
    )
}
