package com.sasau.pangetv

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import com.sasau.pangetv.databinding.ActivityPlayerBinding
import com.sasau.pangetv.model.Channel
import com.sasau.pangetv.player.PlayerFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/** 播放页：主源失败自动换备用源。 */
@UnstableApi
class PlayerActivity : AppCompatActivity() {

    private lateinit var binding: ActivityPlayerBinding
    private var player: ExoPlayer? = null

    private var urls: List<String> = emptyList()
    private var index = 0
    private var referer: String? = null
    private var channelName = ""
    private var channelGroup = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityPlayerBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        channelName = intent.getStringExtra(EXTRA_NAME).orEmpty()
        channelGroup = intent.getStringExtra(EXTRA_GROUP).orEmpty()
        referer = intent.getStringExtra(EXTRA_REFERER)
        @Suppress("UNCHECKED_CAST")
        val list = intent.getStringArrayListExtra(EXTRA_URLS) ?: arrayListOf<String>()
        urls = list

        binding.tvTitle.text = channelName
        binding.tvSubtitle.text = channelGroup

        player = ExoPlayer.Builder(this).build().also { binding.playerView.player = it }
        player?.addListener(errorListener)

        binding.btnRetry.setOnClickListener { playCurrent() }
        binding.btnNext.setOnClickListener {
            if (index + 1 < urls.size) {
                index++
                playCurrent()
            } else {
                showError("已经是最后一个源了")
            }
        }

        playCurrent()
    }

    private val errorListener = object : Player.Listener {
        override fun onPlayerError(error: PlaybackException) {
            if (index + 1 < urls.size) {
                index++
                playCurrent()
            } else {
                showError("所有源都打不开（${error.errorCodeName}）")
            }
        }
    }

    private fun playCurrent() {
        val raw = urls.getOrNull(index)
        if (raw.isNullOrBlank()) {
            showError("没有可用的播放地址")
            return
        }
        binding.tvError.visibility = View.GONE
        binding.actionBar.visibility = View.GONE
        binding.tvSubtitle.text = "$channelGroup · 源 ${index + 1}/${urls.size}"

        lifecycleScope.launch {
            val url = withContext(Dispatchers.IO) { resolvePls(raw) }
            val p = player ?: return@launch
            try {
                p.setMediaSource(PlayerFactory.mediaSource(url, referer))
                p.prepare()
                p.playWhenReady = true
            } catch (e: Exception) {
                showError("无法准备播放：${e.message}")
            }
        }
    }

    /** .pls 是 Shoutcast 播放列表，需要先解析出真实流地址。 */
    private fun resolvePls(url: String): String {
        val lower = url.substringBefore('?').lowercase()
        if (!lower.endsWith(".pls")) return url
        return try {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 12000
            conn.readTimeout = 12000
            conn.setRequestProperty("User-Agent", PlayerFactory.UA)
            try {
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                Regex("(?im)^File\\d*=(.+)$").find(text)?.groupValues?.get(1)?.trim()
                    ?: text.lineSequence().firstOrNull { it.trim().startsWith("http") }?.trim()
                    ?: url
            } finally {
                conn.disconnect()
            }
        } catch (_: Exception) {
            url
        }
    }

    private fun showError(message: String) {
        binding.tvError.text = message
        binding.tvError.visibility = View.VISIBLE
        binding.actionBar.visibility = View.VISIBLE
    }

    @Deprecated("兼容旧版 onBackPressed")
    override fun onBackPressed() {
        if (binding.playerView.isControllerFullyVisible) {
            binding.playerView.hideController()
        } else {
            super.onBackPressed()
        }
    }

    override fun onStop() {
        super.onStop()
        player?.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }

    companion object {
        private const val EXTRA_NAME = "name"
        private const val EXTRA_GROUP = "group"
        private const val EXTRA_URLS = "urls"
        private const val EXTRA_REFERER = "referer"

        fun start(context: Context, channel: Channel) {
            val intent = Intent(context, PlayerActivity::class.java).apply {
                putExtra(EXTRA_NAME, channel.name)
                putExtra(EXTRA_GROUP, channel.group)
                putExtra(EXTRA_URLS, ArrayList(channel.urls))
                putExtra(EXTRA_REFERER, channel.referer)
            }
            context.startActivity(intent)
        }
    }
}
