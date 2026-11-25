package com.sasau.pangetv

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.sasau.pangetv.databinding.ActivityMainBinding
import com.sasau.pangetv.model.Channel
import com.sasau.pangetv.model.Programme
import com.sasau.pangetv.playlist.EpgRepository
import com.sasau.pangetv.playlist.PlaylistRepository
import com.sasau.pangetv.ui.ChannelAdapter
import com.sasau.pangetv.ui.Row
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val repo by lazy { PlaylistRepository(this) }
    private val adapter by lazy { ChannelAdapter { ch -> PlayerActivity.start(this, ch) } }

    private var all: List<Channel> = emptyList()
    private var epg: Map<String, List<Programme>> = emptyMap()
    private var selectedGroup: String? = null
    private var query: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.rvChannels.layoutManager = LinearLayoutManager(this)
        binding.rvChannels.adapter = adapter

        binding.etSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                query = s?.toString()?.trim().orEmpty()
                render()
            }
        })

        binding.btnMenu.setOnClickListener { showMenu(it) }

        loadChannels()
    }

    override fun onResume() {
        super.onResume()
        if (all.isNotEmpty()) render()
    }

    private fun loadChannels() {
        binding.progress.visibility = View.VISIBLE
        binding.tvEmpty.visibility = View.GONE
        lifecycleScope.launch {
            val (label, list) = repo.load()
            all = list
            binding.tvSource.text = label
            buildTabs()
            render()
            binding.progress.visibility = View.GONE

            // 节目单后台拉取，失败无所谓
            val map = EpgRepository.load(this@MainActivity)
            if (map.isNotEmpty()) {
                epg = map
                render()
            }
        }
    }

    private fun buildTabs() {
        binding.tabGroup.removeAllViews()
        val groups = listOf<String?>(null) + all.map { it.group }.distinct()
        for (g in groups) {
            val tv = TextView(this)
            tv.text = g ?: getString(com.sasau.pangetv.R.string.group_all)
            tv.setPadding(dp(14), dp(6), dp(14), dp(6))
            tv.setTextColor(if (g == selectedGroup) {
                androidx.core.content.ContextCompat.getColor(this, com.sasau.pangetv.R.color.bg)
            } else {
                androidx.core.content.ContextCompat.getColor(this, com.sasau.pangetv.R.color.fg_dim)
            })
            tv.setBackgroundResource(if (g == selectedGroup) {
                com.sasau.pangetv.R.drawable.bg_tab_selected
            } else {
                com.sasau.pangetv.R.drawable.bg_tab
            })
            tv.setOnClickListener {
                selectedGroup = g
                buildTabs()
                render()
            }
            binding.tabGroup.addView(tv)
        }
    }

    private fun render() {
        val filtered = all.filter { ch ->
            val inGroup = selectedGroup == null || ch.group == selectedGroup
            val inQuery = query.isEmpty() ||
                    ch.name.contains(query, ignoreCase = true) ||
                    ch.group.contains(query, ignoreCase = true) ||
                    (ch.tvgId?.contains(query, ignoreCase = true) == true)
            inGroup && inQuery
        }
        val rows = ArrayList<Row>()
        filtered.groupBy { it.group }.forEach { (group, channels) ->
            rows.add(Row.Header(group, channels.size))
            channels.forEach { rows.add(Row.Item(it, EpgRepository.now(epg, it))) }
        }
        adapter.submit(rows)
        binding.tvEmpty.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun showMenu(anchor: View) {
        val menu = PopupMenu(this, anchor)
        menu.menu.add(0, 1, 0, getString(com.sasau.pangetv.R.string.menu_reload))
        menu.menu.add(0, 2, 1, getString(com.sasau.pangetv.R.string.menu_source))
        menu.menu.add(0, 3, 2, getString(com.sasau.pangetv.R.string.menu_about))
        menu.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                1 -> {
                    loadChannels()
                    true
                }
                2 -> {
                    showSourceDialog()
                    true
                }
                3 -> {
                    showAbout()
                    true
                }
                else -> false
            }
        }
        menu.show()
    }

    private fun showSourceDialog() {
        val input = android.widget.EditText(this).apply {
            setText(repo.remoteUrl())
            setHint(getString(com.sasau.pangetv.R.string.dlg_source_hint))
            setPadding(dp(16), dp(12), dp(16), dp(4))
        }
        val wrap = LinearLayout(this).apply { addView(input) }
        AlertDialog.Builder(this)
            .setTitle(com.sasau.pangetv.R.string.dlg_source_title)
            .setView(wrap)
            .setPositiveButton(com.sasau.pangetv.R.string.action_save) { _, _ ->
                repo.setRemoteUrl(input.text.toString())
                loadChannels()
            }
            .setNeutralButton(com.sasau.pangetv.R.string.action_reset) { _, _ ->
                repo.setRemoteUrl("")
                loadChannels()
            }
            .setNegativeButton(com.sasau.pangetv.R.string.action_cancel, null)
            .show()
    }

    private fun showAbout() {
        val version = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "1.0.0"
        } catch (_: Exception) {
            "1.0.0"
        }
        AlertDialog.Builder(this)
            .setTitle(com.sasau.pangetv.R.string.app_name)
            .setMessage(getString(com.sasau.pangetv.R.string.about_body, version))
            .setPositiveButton(com.sasau.pangetv.R.string.action_save, null)
            .show()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
}
