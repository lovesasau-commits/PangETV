package com.sasau.pangetv

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.View
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
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

/**
 * 首页。
 *
 * 交互约定（v1.1）：
 *  - 顶部 tab 是**唯一的频道分组入口**，默认落在「常用」；
 *  - tab 必须能被遥控器 D-pad 拿到焦点（focusable + focusableInTouchMode），
 *    左右键切栏目，上下键进列表；
 *  - 列表不再按分组重复插标题行（栏目已经在 tab 上说明了），少一层滚动；
 *  - 搜索时跨全部栏目找，清空搜索才回到当前栏目。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val repo by lazy { PlaylistRepository(this) }
    private val adapter by lazy { ChannelAdapter { ch -> PlayerActivity.start(this, ch) } }

    private var all: List<Channel> = emptyList()
    private var epg: Map<String, List<Programme>> = emptyMap()
    private var groups: List<String> = emptyList()
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
            groups = list.map { it.group }.distinct()
            selectedGroup = pickDefaultGroup()
            buildTabs()
            render()
            binding.progress.visibility = View.GONE
            focusSelectedTab()

            // 节目单后台拉取，失败无所谓
            val map = EpgRepository.load(this@MainActivity)
            if (map.isNotEmpty()) {
                epg = map
                render()
            }
        }
    }

    /** 默认进「常用」；没有就退到第一个栏目。 */
    private fun pickDefaultGroup(): String? {
        if (groups.isEmpty()) return null
        val fav = groups.firstOrNull { it.contains("常用") }
        return fav ?: groups.first()
    }

    private fun buildTabs() {
        binding.tabGroup.removeAllViews()
        for (g in groups) {
            val tv = TextView(this)
            tv.text = g
            tv.setPadding(dp(16), dp(7), dp(16), dp(7))
            tv.setTextColor(ContextCompat.getColorStateList(this, R.color.tab_text))
            tv.setBackgroundResource(R.drawable.tab_bg)
            // 遥控器 D-pad 要能走到 tab 上：之前这里漏了 focusable，顶部选项点不动
            tv.isFocusable = true
            tv.isFocusableInTouchMode = true
            tv.isSelected = g == selectedGroup
            tv.setOnClickListener { selectGroup(g) }
            tv.setOnKeyListener { _, keyCode, event ->
                if (keyCode == KeyEvent.KEYCODE_DPAD_UP && event.action == KeyEvent.ACTION_DOWN) {
                    // 上下键：从列表回到栏目条
                    tv.requestFocus()
                    true
                } else {
                    false
                }
            }
            binding.tabGroup.addView(tv)
        }
    }

    private fun selectGroup(g: String) {
        selectedGroup = g
        buildTabs()
        render()
        focusSelectedTab()
    }

    private fun focusSelectedTab() {
        val idx = groups.indexOf(selectedGroup)
        if (idx < 0) return
        binding.tabGroup.post {
            binding.tabGroup.getChildAt(idx)?.requestFocus()
        }
    }

    private fun render() {
        val filtered: List<Channel>
        if (query.isEmpty()) {
            filtered = all.filter { it.group == selectedGroup }
        } else {
            // 搜索跨全部栏目；「常用」里的台是别的栏目的副本，按台名去重免得出现两行
            val seen = HashSet<String>()
            filtered = all.filter {
                it.name.contains(query, ignoreCase = true) ||
                        it.group.contains(query, ignoreCase = true) ||
                        (it.tvgId?.contains(query, ignoreCase = true) == true)
            }.filter { seen.add(it.name) }
        }
        val rows = filtered.map { Row.Item(it, EpgRepository.now(epg, it)) }
        adapter.submit(rows)
        binding.tvEmpty.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
        binding.tvEmpty.text = getString(
            if (query.isEmpty()) R.string.empty_list else R.string.empty_search)
        binding.tvGroupInfo.text = if (query.isEmpty()) {
            getString(R.string.group_info, selectedGroup ?: "", rows.size)
        } else {
            getString(R.string.group_info_search, query, rows.size)
        }
    }

    private fun showMenu(anchor: View) {
        val menu = PopupMenu(this, anchor)
        menu.menu.add(0, 1, 0, getString(R.string.menu_reload))
        menu.menu.add(0, 2, 1, getString(R.string.menu_source))
        menu.menu.add(0, 3, 2, getString(R.string.menu_about))
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
            setHint(getString(R.string.dlg_source_hint))
            setPadding(dp(16), dp(12), dp(16), dp(4))
        }
        val wrap = LinearLayout(this).apply { addView(input) }
        AlertDialog.Builder(this)
            .setTitle(R.string.dlg_source_title)
            .setView(wrap)
            .setPositiveButton(R.string.action_save) { _, _ ->
                repo.setRemoteUrl(input.text.toString())
                loadChannels()
            }
            .setNeutralButton(R.string.action_reset) { _, _ ->
                repo.setRemoteUrl("")
                loadChannels()
            }
            .setNegativeButton(R.string.action_cancel, null)
            .show()
    }

    private fun showAbout() {
        val version = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "1.1.0"
        } catch (_: Exception) {
            "1.1.0"
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.app_name)
            .setMessage(getString(R.string.about_body, version))
            .setPositiveButton(R.string.action_ok, null)
            .show()
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
}
