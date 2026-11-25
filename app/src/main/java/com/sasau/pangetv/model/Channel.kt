package com.sasau.pangetv.model

/** 一个直播频道。urls 为「主源 + 备用源」，播放失败时自动换源。 */
data class Channel(
    val key: String,
    val name: String,
    val group: String,
    val logo: String? = null,
    val tvgId: String? = null,
    val urls: List<String> = emptyList(),
    val referer: String? = null,
    val isAudio: Boolean = false
) {
    val primaryUrl: String get() = urls.firstOrNull().orEmpty()
}

/** EPG 节目单条目。 */
data class Programme(
    val title: String,
    val startMs: Long,
    val stopMs: Long
)
