package com.sasau.pangetv.playlist

import android.content.Context
import android.util.Xml
import com.sasau.pangetv.model.Programme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.xmlpull.v1.XmlPullParser
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * 节目单（EPG）。数据来自 iptv-org 公开的韩国 XMLTV 源。
 * 拉取失败一律降级为「无节目单」，不影响播放。
 */
object EpgRepository {

    private const val EPG_URLS = listOf(
        "https://iptv-org.github.io/epg/guides/kr/seezntv.com.epg.xml",
        "https://iptv-org.github.io/epg/guides/kr/wavve.com.epg.xml"
    )
    private const val CACHE_FILE = "epg.xml"
    private const val MAX_AGE_MS = 6 * 60 * 60 * 1000L
    private const val UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"

    /** key 统一归一化，播放列表里用 tvg-id 或频道名都能查到。 */
    fun normalize(s: String): String =
        s.lowercase(Locale.US).replace(Regex("[\\s\\-_()\\[\\].·、,，]"), "")

    suspend fun load(context: Context): Map<String, List<Programme>> = withContext(Dispatchers.IO) {
        val cache = File(context.filesDir, CACHE_FILE)
        if (cache.exists() && System.currentTimeMillis() - cache.lastModified() < MAX_AGE_MS) {
            parse(cache.readText(Charsets.UTF_8))?.let { return@withContext it }
        }
        try {
            val sb = StringBuilder()
            for (u in EPG_URLS) {
                sb.append(fetch(u)).append('\n')
            }
            val text = sb.toString()
            if (text.contains("<tv")) {
                cache.writeText(text, Charsets.UTF_8)
                parse(text)?.let { return@withContext it }
            }
        } catch (_: Exception) {
            // 忽略，走缓存
        }
        try {
            if (cache.exists()) parse(cache.readText(Charsets.UTF_8)) ?: emptyMap() else emptyMap()
        } catch (_: Exception) {
            emptyMap()
        }
    }

    private fun fetch(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 20000
        conn.setRequestProperty("User-Agent", UA)
        try {
            if (conn.responseCode !in 200..299) return ""
            return conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun parse(xml: String): Map<String, List<Programme>>? {
        if (!xml.contains("<tv")) return null
        return try {
            val parser = Xml.newPullParser()
            parser.setInput(xml.reader())

            val idToName = HashMap<String, String>()
            val byId = HashMap<String, MutableList<Programme>>()

            var event = parser.eventType
            while (event != XmlPullParser.END_DOCUMENT) {
                if (event == XmlPullParser.START_TAG) {
                    when (parser.name) {
                        "channel" -> {
                            val id = parser.getAttributeValue(null, "id") ?: ""
                            val display = readText(parser, "display-name")
                            if (id.isNotEmpty() && display.isNotEmpty()) idToName[id] = display
                        }
                        "programme" -> {
                            val ch = parser.getAttributeValue(null, "channel") ?: ""
                            val start = parseTime(parser.getAttributeValue(null, "start"))
                            val stop = parseTime(parser.getAttributeValue(null, "stop"))
                            val title = readText(parser, "title")
                            if (ch.isNotEmpty() && start != null && stop != null && title.isNotEmpty()) {
                                byId.getOrPut(ch) { mutableListOf() }.add(Programme(title, start, stop))
                            }
                        }
                    }
                }
                event = parser.next()
            }

            val result = HashMap<String, List<Programme>>()
            for ((id, list) in byId) {
                result[normalize(id)] = list
                idToName[id]?.let { name ->
                    val key = normalize(name)
                    result[key] = (result[key] ?: emptyList()) + list
                }
            }
            result
        } catch (_: Exception) {
            null
        }
    }

    /** 读取当前开始标签下某个子标签的文本。 */
    private fun readText(parser: XmlPullParser, tag: String): String {
        var depth = 0
        while (depth < 64) {
            val ev = parser.next()
            when (ev) {
                XmlPullParser.START_TAG -> {
                    depth++
                    if (parser.name == tag) return parser.nextText().trim()
                }
                XmlPullParser.END_TAG -> {
                    if (depth == 0) return ""
                    depth--
                }
                XmlPullParser.END_DOCUMENT -> return ""
            }
        }
        return ""
    }

    private fun parseTime(raw: String?): Long? {
        if (raw.isNullOrBlank()) return null
        return try {
            val fmt = SimpleDateFormat("yyyyMMddHHmmss Z", Locale.US)
            fmt.isLenient = false
            fmt.parse(raw.trim()).time
        } catch (_: Exception) {
            null
        }
    }

    /** 取某频道当前正在播的节目。 */
    fun now(map: Map<String, List<Programme>>, channel: com.sasau.pangetv.model.Channel): Programme? {
        if (map.isEmpty()) return null
        val keys = listOfNotNull(
            channel.tvgId?.let { normalize(it) },
            normalize(channel.name)
        )
        val now = System.currentTimeMillis()
        for (k in keys) {
            val list = map[k] ?: continue
            list.firstOrNull { it.startMs <= now && now < it.stopMs }?.let { return it }
        }
        return null
    }
}
