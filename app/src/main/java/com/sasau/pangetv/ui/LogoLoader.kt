package com.sasau.pangetv.ui

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.widget.ImageView
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** 极简台标加载器（内存缓存 + 线程池），避免为此引入图片库。 */
object LogoLoader {

    private const val UA = "Mozilla/5.0 (Linux; Android 13; PangETV) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"

    private val cache = object : LruCache<String, Bitmap>(96) {}
    private val pool = Executors.newFixedThreadPool(4) { r ->
        Thread(r, "logo-loader").apply { isDaemon = true }
    }

    fun load(url: String?, target: ImageView, placeholder: Int) {
        target.tag = url
        if (url.isNullOrBlank()) {
            target.setImageResource(placeholder)
            return
        }
        cache.get(url)?.let {
            target.setImageBitmap(it)
            return
        }
        target.setImageResource(placeholder)
        pool.execute {
            try {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.connectTimeout = 8000
                conn.readTimeout = 8000
                conn.setRequestProperty("User-Agent", UA)
                val bitmap = try {
                    conn.inputStream.use { BitmapFactory.decodeStream(it) }
                } finally {
                    conn.disconnect()
                }
                if (bitmap != null) {
                    cache.put(url, bitmap)
                    target.post {
                        if (target.tag == url) target.setImageBitmap(bitmap)
                    }
                }
            } catch (_: Exception) {
                // 台标拉不到就用占位图
            }
        }
    }
}
