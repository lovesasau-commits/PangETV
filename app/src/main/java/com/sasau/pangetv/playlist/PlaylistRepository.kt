package com.sasau.pangetv.playlist

import android.content.Context
import com.sasau.pangetv.model.Channel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * 播放列表仓库：远程 M3U 优先，失败回落到缓存，再回落到内置 assets。
 */
class PlaylistRepository(private val context: Context) {

    private val prefs by lazy { context.getSharedPreferences("pangetv", Context.MODE_PRIVATE) }
    private val cacheFile by lazy { File(context.filesDir, "playlist.m3u") }

    fun remoteUrl(): String = prefs.getString(KEY_REMOTE, "") ?: ""

    fun setRemoteUrl(url: String) {
        val clean = url.trim()
        prefs.edit().putString(KEY_REMOTE, clean).apply()
        if (clean.isEmpty() && cacheFile.exists()) cacheFile.delete()
    }

    /** 返回 (来源说明, 频道列表)。任何一步失败都静默降级，不会抛异常。 */
    suspend fun load(): Pair<String, List<Channel>> = withContext(Dispatchers.IO) {
        val remote = remoteUrl()
        if (remote.isNotBlank()) {
            try {
                val text = fetch(remote)
                if (text.contains("#EXTINF", ignoreCase = true)) {
                    cacheFile.writeText(text, Charsets.UTF_8)
                    return@withContext "远程列表" to M3uParser.parse(text)
                }
            } catch (_: Exception) {
                // 落到缓存
            }
            try {
                if (cacheFile.exists()) {
                    return@withContext "缓存列表" to M3uParser.parse(cacheFile.readText(Charsets.UTF_8))
                }
            } catch (_: Exception) {
                // 落到内置
            }
        }
        val bundled = context.assets.open(BUNDLED).bufferedReader(Charsets.UTF_8).use { it.readText() }
        "内置列表" to M3uParser.parse(bundled)
    }

    private fun fetch(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 15000
        conn.instanceFollowRedirects = true
        conn.setRequestProperty("User-Agent", UA)
        conn.setRequestProperty("Accept", "*/*")
        try {
            val code = conn.responseCode
            if (code !in 200..299) throw IOException("HTTP $code")
            return conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private const val KEY_REMOTE = "remote_playlist_url"
        const val BUNDLED = "playlist.m3u"

        /** 用浏览器 UA：不少源站会拒绝 ExoPlayer 默认 UA。 */
        const val UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    }
}
