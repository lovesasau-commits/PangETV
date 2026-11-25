package com.sasau.pangetv.player

import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource

/** 播放器工厂：统一 UA / Referer / DNS 策略。 */
@UnstableApi
object PlayerFactory {

    /** 用浏览器 UA：相当一部分源站会拒绝 ExoPlayer 默认 UA。 */
    const val UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"

    fun httpFactory(referer: String?): DefaultHttpDataSource.Factory {
        val factory = DefaultHttpDataSource.Factory()
            .setAllowCrossProtocolRedirects(true)
            .setUserAgent(UA)
            .setConnectTimeoutMs(15000)
            .setReadTimeoutMs(20000)
            .setDns(MiguDns())
        val props = HashMap<String, String>()
        props["User-Agent"] = UA
        props["Accept"] = "*/*"
        if (!referer.isNullOrBlank()) props["Referer"] = referer
        factory.setDefaultRequestProperties(props)
        return factory
    }

    fun mediaSource(url: String, referer: String?): MediaSource {
        val factory = httpFactory(referer)
        val item = MediaItem.fromUri(url)
        return if (url.contains(".m3u8", ignoreCase = true)) {
            HlsMediaSource.Factory(factory)
                .setAllowChunklessPreparation(true)
                .setAllowChunklessPlayback(true)
                .createMediaSource(item)
        } else {
            ProgressiveMediaSource.Factory(factory).createMediaSource(item)
        }
    }
}
