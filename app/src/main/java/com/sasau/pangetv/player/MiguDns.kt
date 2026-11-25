package com.sasau.pangetv.player

import androidx.media3.datasource.Dns
import java.net.InetAddress
import java.net.UnknownHostException

/**
 * 自定义 DNS：绕开运营商对咪咕 CDN 域名的污染解析。
 *
 * 背景：`cache.ott.fifalive.itv.cmvideo.cn` 在部分国内网络被解析到
 * 1.1.1.1 之类的假地址，直连必然 403；而它真实的后端是
 * `base-v4v6-cm-miguvideo.e.cdn.chinamobile.com`。
 * 这里只替换「解析结果」，Host 头 / SNI 仍保持原域名，所以签名 URL 依然有效。
 */
class MiguDns(private val delegate: Dns = Dns.DEFAULT) : Dns {

    override fun lookup(hostname: String): List<InetAddress> {
        val alias = ALIASES[hostname.lowercase()] ?: return delegate.lookup(hostname)
        return try {
            delegate.lookup(alias)
        } catch (e: UnknownHostException) {
            delegate.lookup(hostname)
        }
    }

    companion object {
        private val ALIASES = mapOf(
            "cache.ott.fifalive.itv.cmvideo.cn" to "base-v4v6-cm-miguvideo.e.cdn.chinamobile.com"
        )
    }
}
