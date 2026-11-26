package com.sasau.pangetv.player

import okhttp3.Dns
import java.net.InetAddress
import java.net.UnknownHostException

/**
 * 自定义 DNS：绕开运营商对咪咕 CDN 域名的污染解析。
 *
 * 背景：`cache.ott.fifalive.itv.cmvideo.cn` 在部分国内网络被解析到
 * 1.1.1.1 之类的假地址，直连必然 403；而它真实的后端是
 * `base-v4v6-cm-miguvideo.e.cdn.chinamobile.com`。
 *
 * 这里只替换「解析结果」，URL / Host 头 / SNI 仍保持原域名，
 * 所以咪咕的签名 URL 依然有效（与 curl --resolve 的实测方案等价）。
 *
 * v1.1 改动：咪咕取流不止 fifalive 一个主机，实测还会跳到
 * `cache.ott.wasulive / bestlive / ystenlive` 等同样被污染的主机，
 * 所以改成按 `cache.ott.*.itv.cmvideo.cn` 前缀统一走后端。
 *
 * 说明：Media3 1.4.1 的 DataSource 层已经没有 Dns 抽象了
 * （那是 ExoPlayer2 时代的 API），所以这里实现的是 OkHttp 的 Dns，
 * 由 OkHttpDataSource 承担 HTTP 传输。
 */
class MiguDns(private val delegate: Dns = Dns.SYSTEM) : Dns {

    override fun lookup(hostname: String): List<InetAddress> {
        val lower = hostname.lowercase()
        val alias: String = ALIASES[lower] ?: when {
            lower.startsWith("cache.ott.") && lower.endsWith("itv.cmvideo.cn") -> BACKEND
            else -> return delegate.lookup(hostname)
        }
        return try {
            delegate.lookup(alias)
        } catch (e: UnknownHostException) {
            delegate.lookup(hostname)
        }
    }

    companion object {
        /** 咪咕 CDN 的真实后端（本地解析结果 39.135.122.x）。 */
        const val BACKEND = "base-v4v6-cm-miguvideo.e.cdn.chinamobile.com"

        private val ALIASES = mapOf(
            "cache.ott.fifalive.itv.cmvideo.cn" to BACKEND
        )
    }
}
