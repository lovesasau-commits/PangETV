package com.sasau.pangetv.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.sasau.pangetv.R
import com.sasau.pangetv.model.Channel
import com.sasau.pangetv.model.Programme

/** 列表行：分组标题 + 频道 */
sealed class Row {
    data class Header(val group: String, val count: Int) : Row()
    data class Item(val channel: Channel, val now: Programme?) : Row()
}

class ChannelAdapter(
    private val onClick: (Channel) -> Unit
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    private val rows = ArrayList<Row>()

    fun submit(newRows: List<Row>) {
        rows.clear()
        rows.addAll(newRows)
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = rows.size

    override fun getItemViewType(position: Int): Int =
        if (rows[position] is Row.Header) TYPE_HEADER else TYPE_ITEM

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        return if (viewType == TYPE_HEADER) {
            HeaderHolder(inflater.inflate(R.layout.row_header, parent, false))
        } else {
            ItemHolder(inflater.inflate(R.layout.row_channel, parent, false))
        }
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        when (val row = rows[position]) {
            is Row.Header -> (holder as HeaderHolder).bind(row)
            is Row.Item -> (holder as ItemHolder).bind(row)
        }
    }

    inner class HeaderHolder(view: View) : RecyclerView.ViewHolder(view) {
        private val title: TextView = view.findViewById(R.id.tvGroup)
        private val count: TextView = view.findViewById(R.id.tvCount)

        fun bind(row: Row.Header) {
            title.text = row.group
            count.text = "${row.count} 个"
        }
    }

    inner class ItemHolder(view: View) : RecyclerView.ViewHolder(view) {
        private val logo = view.findViewById<android.widget.ImageView>(R.id.ivLogo)
        private val name = view.findViewById<TextView>(R.id.tvName)
        private val now = view.findViewById<TextView>(R.id.tvNow)
        private val badge = view.findViewById<TextView>(R.id.tvBadge)

        fun bind(row: Row.Item) {
            val ch = row.channel
            name.text = ch.name
            LogoLoader.load(ch.logo, logo, R.drawable.ic_launcher)
            if (row.now != null) {
                now.visibility = View.VISIBLE
                now.text = "正在播出：${row.now.title}"
            } else {
                now.visibility = View.GONE
            }
            badge.text = if (ch.isAudio) "电台" else "直播"
            itemView.setOnClickListener { onClick(ch) }
        }
    }

    companion object {
        private const val TYPE_HEADER = 0
        private const val TYPE_ITEM = 1
    }
}
