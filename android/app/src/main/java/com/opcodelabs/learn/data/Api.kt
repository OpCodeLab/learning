package com.opcodelabs.learn.data

import android.content.Context
import android.os.Build
import com.opcodelabs.learn.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Why a call failed, in terms the screens can act on. */
class ApiException(val kind: Kind, message: String, val extra: String? = null) : Exception(message) {
    enum class Kind { SIGNED_OUT, CODE_REQUIRED, ELSEWHERE, OFFLINE, NOT_FOUND, OTHER }
}

/** Sign-in token, kept in app-private storage (never backed up: see the manifest). */
class Session(context: Context) {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
    var token: String?
        get() = prefs.getString("token", null)
        set(v) = prefs.edit().putString("token", v).apply()
    var email: String?
        get() = prefs.getString("email", null)
        set(v) = prefs.edit().putString("email", v).apply()
    fun clear() = prefs.edit().clear().apply()
}

class Api(private val session: Session) {
    val base = BuildConfig.BASE_URL.trimEnd('/')

    /** "OpCodeLearn/1.0.0 (Android 14; Pixel 7)": the server shows it as the device name. */
    val userAgent = "OpCodeLearn/%s (Android %s; %s)".format(
        BuildConfig.VERSION_NAME, Build.VERSION.RELEASE, Build.MODEL.take(40).replace(Regex("[()]"), ""))

    private val json = Json { ignoreUnknownKeys = true }

    /** Shared by API calls, the video player and downloads: adds the token to every request. */
    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val b = chain.request().newBuilder().header("User-Agent", userAgent)
            session.token?.let { b.header("Authorization", "Bearer $it") }
            chain.proceed(b.build())
        }
        .build()

    fun mediaUrl(slug: String, fileId: String) = "$base/media/$slug/$fileId"

    private suspend fun call(method: String, path: String, body: String? = null): String =
        withContext(Dispatchers.IO) {
            val req = Request.Builder().url(base + path).apply {
                if (method == "POST") post((body ?: "{}").toRequestBody("application/json".toMediaType()))
            }.build()
            try {
                http.newCall(req).execute().use { r ->
                    val text = r.body?.string().orEmpty()
                    if (r.isSuccessful) return@withContext text
                    val error = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull()
                    val msg = error?.get("error")?.jsonPrimitive?.content ?: "HTTP ${r.code}"
                    throw when {
                        r.code == 401 && msg == "code required" -> ApiException(ApiException.Kind.CODE_REQUIRED, msg)
                        r.code == 401 && path.startsWith("/api/v1/login") -> ApiException(ApiException.Kind.OTHER, msg)
                        r.code == 401 -> ApiException(ApiException.Kind.SIGNED_OUT, "Signed out")
                        r.code == 409 -> ApiException(ApiException.Kind.ELSEWHERE, msg,
                            error?.get("device")?.jsonPrimitive?.content)
                        r.code == 503 -> ApiException(ApiException.Kind.OFFLINE,
                            "Courses are offline for a moment. Try again in a few minutes.")
                        r.code == 404 -> ApiException(ApiException.Kind.NOT_FOUND, msg)
                        else -> ApiException(ApiException.Kind.OTHER, msg)
                    }
                }
            } catch (e: IOException) {
                throw ApiException(ApiException.Kind.OFFLINE, "No connection. Check your internet and try again.")
            }
        }

    suspend fun login(email: String, password: String, code: String?): LoginResponse {
        val body = JsonObject(buildMap {
            put("email", JsonPrimitive(email)); put("password", JsonPrimitive(password))
            if (!code.isNullOrBlank()) put("code", JsonPrimitive(code))
        })
        val r = json.decodeFromString<LoginResponse>(call("POST", "/api/v1/login", body.toString()))
        session.token = r.token
        session.email = r.user.email
        return r
    }

    suspend fun logout() {
        runCatching { call("POST", "/api/v1/logout") }
        session.clear()
    }

    suspend fun me(): Me = json.decodeFromString(call("GET", "/api/v1/me"))
    suspend fun courses(): List<CourseCard> = json.decodeFromString<CourseList>(call("GET", "/api/v1/courses")).courses
    suspend fun course(slug: String): Course = json.decodeFromString(call("GET", "/api/v1/courses/$slug"))
    suspend fun playStatus(): PlayStatus = json.decodeFromString(call("GET", "/api/play"))
    suspend fun appVersion(): AppVersion = json.decodeFromString(call("GET", "/api/v1/app"))

    /** Claim playback for this device. Throws ELSEWHERE (with the other device's name) unless takeover. */
    suspend fun play(takeover: Boolean) {
        call("POST", "/api/play", """{"takeover": $takeover}""")
    }

    /** Progress ping (every 15 s while playing, and on pause/end). Throws ELSEWHERE if another device took over. */
    suspend fun progress(slug: String, lessonId: String, position: Double, duration: Double,
                         playing: Boolean, ended: Boolean) {
        call("POST", "/api/progress",
            """{"course":"$slug","lesson":"$lessonId","position":$position,"duration":$duration,""" +
                """"playing":$playing,"ended":$ended}""")
    }

    /** Download an attachment into the app cache (opened afterwards through the FileProvider). */
    suspend fun download(slug: String, a: Attachment, dir: File): File = withContext(Dispatchers.IO) {
        val out = File(dir, "attachments").apply { mkdirs() }.resolve(a.name.replace('/', '_'))
        val req = Request.Builder().url(mediaUrl(slug, a.id)).build()
        try {
            http.newCall(req).execute().use { r ->
                if (r.code == 401) throw ApiException(ApiException.Kind.SIGNED_OUT, "Signed out")
                if (!r.isSuccessful) throw ApiException(ApiException.Kind.OTHER, "Download failed (${r.code})")
                out.outputStream().use { r.body!!.byteStream().copyTo(it) }
            }
        } catch (e: IOException) {
            throw ApiException(ApiException.Kind.OFFLINE, "Download failed. Check your connection.")
        }
        out
    }
}
