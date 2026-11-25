package com.sasau.pangetv.playlist

import com.sasau.pangetv.model.Channel

/**
 * M3U 解析器。
 *
 * 支持标准 #EXTINF 属性（tvg-id / tvg-logo / group-title 等）、
 * #EXTGRP、#EXTVLCOPT:http-referrer，并且允许一个频道下面跟多条 URL
 * （第一条是主源，其余是备用源，应用会自动换源）。
 */
object M3uParser {

    private val ATTR = Regex("""([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"""")

    fun parse(text: String, defaultGroup: String = "其它"): List<Channel> {
        val result = ArrayList<Channel>()
        val lines = text.replace("\r\n", "\n").replace('\r', '\n').split('\n')

        var attrs: Map<String, String> = emptyMap()
        var name = ""
        var group = defaultGroup
        var referer: String? = null
        var urls = ArrayList<String>()
        var seq = 0

        fun flush() {
            val clean = urls.filter { it.isNotBlank() }
            urls = ArrayList()
            if (clean.isEmpty()) return
            result.add(
                Channel(
                    key = "$group/$name/$seq",
                    name = name.ifBlank { "未命名频道" },
                    group = group,
                    logo = attrs["tvg-logo"]?.takeIf { it.isNotBlank() },
                    tvgId = attrs["tvg-id"]?.takeIf { it.isNotBlank() },
                    urls = clean,
                    referer = referer,
                    isAudio = group.contains("电台") || group.contains("Radio")
                )
            )
            seq++
        }

        for (raw in lines) {
            val line = raw.trim()
            if (line.isEmpty()) continue
            when {
                line.startsWith("#EXTINF:") -> {
                    flush()
                    val payload = line.substringAfter("#EXTINF:")
                    val comma = payload.lastIndexOf(',')
                    if (comma >= 0) {
                        attrs = ATTR.findAll(payload.substring(0, comma))
                            .associate { it.groupValues[1].lowercase() to it.groupValues[2] }
                        name = payload.substring(comma + 1).trim()
                    } else {
                        attrs = emptyMap()
                        name = payload.trim()
                    }
                    attrs["group-title"]?.takeIf { it.isNotBlank() }?.let { group = it }
                }
                line.startsWith("#EXTGRP:") -> {
                    flush()
                    group = line.substringAfter(":").trim()
                }
                line.startsWith("#EXTVLCOPT:") -> {
                    val kv = line.substringAfter(":")
                    if (kv.startsWith("http-referrer=", ignoreCase = true)) {
                        referer = kv.substringAfter("=").trim()
                    }
                }
                line.startsWith("#") -> Unit
                else -> urls.add(line)
            }
        }
        flush()
        return result
    }
}
