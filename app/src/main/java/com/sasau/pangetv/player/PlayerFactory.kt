package com.sasau.pangetv.player

import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.HttpDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/** 播放器工厂：统一 UA / Referer / DNS 策略。 */
@UnstableApi
object PlayerFactory {

    /** 用浏览器 UA：相当一部分源站会拒绝 ExoPlayer 默认 UA。 */
    const val UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"

    /**
     * 咪咕取流必须带 Referer，缺了就一律 403（实测结论，见 tools/migu_probe/）。
     * 频道自己没声明 Referer 时，咪咕域名自动补上这个默认值。
     */
    const val MIGU_REFERER = "https://www.miguvideo.com/"

    /**
     * HTTP 数据源工厂。
     *
     * 用 OkHttp 而不是 Media3 默认的 DefaultHttpDataSource，有两个原因：
     * 1. Media3 1.4.1 的 DataSource 层已经没有 Dns 抽象，
     *    咪咕的 DNS 别名必须由 OkHttp 的 Dns 钩子来实现；
     * 2. OkHttp 默认跟随 302 跳转，咪咕的取流链路依赖这一步。
     */
    fun httpFactory(url: String?, referer: String?): HttpDataSource.Factory {
        val client = OkHttpClient.Builder()
            .dns(MiguDns())
            .followRedirects(true)
            .followSslRedirects(true)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

        val props = HashMap<String, String>()
        props["User-Agent"] = UA
        props["Accept"] = "*/*"
        val effective = effectiveReferer(url, referer)
        if (effective != null) props["Referer"] = effective

        return OkHttpDataSource.Factory(client)
            .setUserAgent(UA)
            .setDefaultRequestProperties(props)
    }

    /** 频道没给 Referer 时，咪咕域名补默认值，其它域名不给。 */
    fun effectiveReferer(url: String?, referer: String?): String? {
        referer?.takeIf { it.isNotBlank() }?.let { return it }
        if (url != null && url.contains("cmvideo.cn")) return MIGU_REFERER
        return null
    }

    fun mediaSource(url: String, referer: String?): MediaSource {
        val factory = httpFactory(url, referer)
        val item = MediaItem.fromUri(url)
        return if (url.contains(".m3u8", ignoreCase = true)) {
            HlsMediaSource.Factory(factory)
                .setAllowChunklessPreparation(true)
                .createMediaSource(item)
        } else {
            ProgressiveMediaSource.Factory(factory).createMediaSource(item)
        }
    }
}
