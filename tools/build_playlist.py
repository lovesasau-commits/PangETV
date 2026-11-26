#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""胖鹅TV · 内置播放列表合成器（v4）

v4 的关键改动（都来自实测证据，不是拍脑袋）：

1. **弃用 fmml 源里指向咪咕 CDN 的央视/卫视地址**。
   实测：这些地址第一跳 302 正常，第二跳跳到
   `cache.ott.wasulive/bestlive/ystenlive.itv.cmvideo.cn`，
   整个 39.135.122.0/24 全部返回 403 —— 版权内容在咪咕 CDN 上拿不到。
   央视/卫视改走 fanmingming + CCSH 的直连地址。

2. **咪咕 CDN 只保留「咪咕自有内容」**（Contentid 以 3 开头 + channel-id=FifastbLive），
   并把 `stbId=3` 改成有效值 `YanG-1989`。
   实测：stbId=3 → 403；stbId=YanG-1989 → 200 + HLS。
   （`tools/migu_probe/probe_matrix.py` 是这套结论的复现脚本）

3. **咪咕特色台（五星体育/劲爆体育/魅力足球/游戏风云/睛彩…）改走 CCSH**，
   每台有多路镜像，实测能挑出活的。

4. **实测可用镜像前置**：`--rank-from` 传入上次实测 JSON，
   把真正出流的那一路挪到第一位，App 打开即命中，不用挨个试。

5. **--prune-from**：整台全挂的直接剔除。

用法:
    # 第一遍：全量候选
    python tools/build_playlist.py --cache-dir ../_tmp --out ../app/src/main/assets/playlist.m3u --offline
    # 实测
    python tools/check_streams.py --playlist ... --json stream-check-v6.json --csv stream-check-v6.csv --jobs 12
    # 第二遍：剔除死台 + 可用镜像前置
    python tools/build_playlist.py --prune-from stream-check-v6.json --rank-from stream-check-v6.json --selftest
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "app", "src", "main", "assets", "playlist.m3u")
ATTR_RE = re.compile(r'([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"')

# ── 上游源 ───────────────────────────────────────────────────────────
SOURCES = {
    # 咪咕 CDN · 带真实台名（只取咪咕自有内容，见下方说明）
    "fmml": "https://m3u.ibert.me/fmml_itv.m3u",
    # 咪咕 CDN · 匿名编号赛事台（这份是好的，stbId 已带对）
    "migu": "https://raw.githubusercontent.com/YanG-1989/m3u/main/Migu.m3u",
    # 央视 / 卫视（直连，多镜像）
    "cn": "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/index.m3u",
    "ccsh": "https://raw.githubusercontent.com/CCSH/IPTV/main/live_lite.m3u",
    # 韩国电视 / 韩国电台
    "kr": "https://raw.githubusercontent.com/wujinfeng009/iptv/main/Korean.m3u",
    "kro": "https://iptv-org.github.io/iptv/countries/kr.m3u",
    "radio": "https://raw.githubusercontent.com/junguler/m3u-radio-music-playlists/main/allradio.net/Korea.m3u",
    # 只取免费「央视频道」里的 CCTV-5 / CCTV-5+，付费分组一律不碰
    "guovin": "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
}

CACHE_NAME = {
    "kro": "kr_iptvorg.m3u",
    "guovin": "guovin_result.m3u",
}

# 镜像上限：候选多、实测挑出活的那一路再前置，所以可以放宽
MAX_MIRRORS = 16

# 咪咕取流必须带这个 stbId，否则 CDN 返回 403（实测结论）
MIGU_STBID = "YanG-1989"

# ── 栏目定义（顺序即 App 顶部 tab 顺序）─────────────────────────────
G_FAV = "常用"
G_MIGU = "咪咕体育"
G_EVENT = "赛事"
G_CN = "中国新闻"
G_KR = "韩国新闻"
G_RADIO = "韩国电台"
GROUP_ORDER = [G_FAV, G_MIGU, G_EVENT, G_CN, G_KR, G_RADIO]

# ── 台名归一化 ───────────────────────────────────────────────────────
CODEC_SUFFIX_RE = re.compile(
    r"\s+(?:50\s*FPS|FPS|HEVC|H\.?265|H\.?264|4K\s*HEVC|4K)$", re.I)

CCTV_STD = {
    "1": "CCTV-1 综合", "2": "CCTV-2 财经", "3": "CCTV-3 综艺",
    "4": "CCTV-4 中文国际", "5": "CCTV-5 体育", "5+": "CCTV-5+ 体育赛事",
    "6": "CCTV-6 电影", "7": "CCTV-7 国防军事", "8": "CCTV-8 电视剧",
    "9": "CCTV-9 纪录", "10": "CCTV-10 科教", "11": "CCTV-11 戏曲",
    "12": "CCTV-12 社会与法", "13": "CCTV-13 新闻", "14": "CCTV-14 少儿",
    "15": "CCTV-15 音乐", "16": "CCTV-16 奥林匹克", "17": "CCTV-17 农业农村",
}

# 央视的体育/赛事台归到「赛事」栏，不留在「中国新闻」
CN_SPORT_CHANNELS = {"CCTV-5 体育", "CCTV-5+ 体育赛事", "CCTV-16 奥林匹克"}

# CCSH 的咪咕特色台 → 统一成「咪咕 XXX」，与咪咕源重名时能合并
CCSH_MIGU_NAMES = {
    "咪咕体育": "咪咕 体育",
    "足球频道": "咪咕 足球频道",
    "五星体育": "咪咕 五星体育",
    "劲爆体育": "咪咕 劲爆体育",
    "魅力足球": "咪咕 魅力足球",
    "睛彩竞技": "咪咕 睛彩竞技",
    "睛彩篮球": "咪咕 睛彩篮球",
    "游戏风云": "咪咕 游戏风云",
    "精品体育": "咪咕 精品体育",
    "超级体育": "咪咕 超级体育",
    "哒啵赛事": "咪咕 哒啵赛事",
    "武搏世界": "咪咕 武搏世界",
    "中国功夫": "咪咕 中国功夫",
}


def canon_cn(name):
    """把各源写法不同的央视/卫视台名统一成一种。"""
    n = CODEC_SUFFIX_RE.sub("", name.strip())
    n = re.sub(r"\s+", " ", n)
    m = re.match(r"^CCTV[\s\-]*(\d{1,2})(\+)?$", n, re.I)
    if m:
        key = m.group(1) + ("+" if m.group(2) else "")
        return CCTV_STD.get(key, n)
    if re.match(r"^CCTV[\s\-]*4K$", n, re.I):
        return "CCTV-4K 超高清"
    if re.match(r"^CCTV[\s\-]*8K$", n, re.I):
        return "CCTV-8K 超高清"
    m = re.match(r"^CETV[\s\-]*(\d)$", n, re.I)
    if m:
        return "CETV-%s" % m.group(1)
    m = re.match(r"^咪咕4K[\s\-]*(\d)$", n)
    if m:
        return "咪咕 4K 台 %s" % m.group(1)
    return n


def norm_name(name):
    """去掉上游挂在台名后的画质/状态后缀，用来对齐同一个台。"""
    n = re.sub(r"\s*\(\d{3,4}p\)", "", name)
    n = re.sub(r"\s*\[.*?\]", "", n)
    return n.strip()


# ── 咪咕匿名台改名 ───────────────────────────────────────────────────
DIGIT_MAP = {}
for _src in ("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟙",
             "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
             "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟸𝟹"):
    for _i, _ch in enumerate(_src):
        DIGIT_MAP[_ch] = str(_i)
DIGIT_MAP["𝕂"] = "K"

MIGU_NUM_RE = re.compile(r"咪咕直播\s*(\d+)(K)?-?(\d*)")
JUNK_NAME_RE = re.compile(r"使用说明|Github|GitHub", re.I)


def translit_digits(s):
    for k, v in DIGIT_MAP.items():
        s = s.replace(k, v)
    return s


def migu_rename(name):
    """把「咪咕直播 𝟙「移动」」这类匿名台名改成能看懂的；说明条目返回空串。"""
    if JUNK_NAME_RE.search(name):
        return ""
    n = translit_digits(name)
    m = MIGU_NUM_RE.search(n)
    if m:
        if m.group(2):      # 咪咕直播 4K-1 / 4K-2
            return "咪咕 4K 台 %s" % (m.group(3) or "1")
        return "咪咕赛事台 %02d（赛事轮播）" % int(m.group(1))
    n = n.replace("「移动」", "").strip()
    if n.startswith("睛彩"):
        return "咪咕 " + n
    return n


def fix_migu_url(url):
    """咪咕取流必须带有效 stbId，否则 CDN 403（实测结论）。"""
    if "cmvideo.cn" not in url:
        return url
    if "stbId=" in url:
        return re.sub(r"stbId=[^&]*", "stbId=" + MIGU_STBID, url)
    sep = "&" if "?" in url else "?"
    return url + sep + "stbId=" + MIGU_STBID


def is_migu_own_content(url):
    """咪咕自有内容：Contentid 以 3 开头且 channel-id=FifastbLive。

    其它（央视/卫视版权，Contentid 5/6/1/7 开头）实测全部 403，不要。
    """
    return bool(re.search(r"Contentid=3\d+", url)) and "channel-id=FifastbLive" in url


# ── 韩国电视台白名单（全国性频道，去掉地区台与重复台）───────────────
KR_TV_KEEP = {
    "KBS1", "KBS 1 UHD", "KBS2", "KBS News D", "KBS LiveCam DokDo",
    "KBS Drama", "KBS Joy", "KBS Life", "KBS Story", "KBS Kids", "KBS World",
    "MBC Andong (안동 MBC)", "MBC Chungbuk (MBC 충북)", "MBC Drama", "MBC Net",
    "SBS JTV", "SBS CJB",
    "EBS 1", "EBS 2", "EBS E", "EBS kids", "EBS+ 1", "EBS+ 2",
    "EBS TV-1", "EBS TV-2", "EBS TV-e", "EBS TV-i", "EBS TV-Kids", "EBS TV-Plus 2",
    "Arirang TV", "Arirang TV UN", "Arirang TV HD",
    "TV Chosun", "TV Chosun 2",
    "TBS Seoul", "TBS TV", "GCN24 Korean", "GCN", "CGNTV",
    "RUTC TV", "OUN", "BTN TV", "FGTV", "NHTV",
    "BBS Buddhist Broadcasting", "BBS TV", "Buddhist Broadcasting System TV",
    "Buddhist True Network TV", "National Assembly TV",
    "NBS Korea Agricultural Broadcasting", "NBS",
    "YTN", "Channel A", "CJ OnStyle", "CJ OnStyle Plus", "OCN",
    "KTV", "MTN", "RTV", "STB", "GoodTV", "Korea TV",
    "CTS기독교TV", "Job Plus TV (한국직업방송)", "WBC TV", "WBS TV",
    "CPBC TV", "Korea Work TV", "MNB World",
    "SPOTV", "SPOTV2", "tvN Asia (Indonesian Subtitle)", "tvN Movies (Indonesian Subtitle)",
}

KR_RADIO_KEEP = {
    "Arirang FM", "Arirang Radio",
    "GugakFM", "gukak", "TBN 교통방송", "TBN 울산교통방송",
    "MBC FM", "MBC FM4U", "MBC충북 FM4U", "MBC충북 표준FM",
    "마포FM", "안동MBC AM", "befm",
    "CBS Music FM", "cbs music", "CBS Music FM Radio", "CBS 표쥰 FM 98.1MHz",
    "JTV 매직FM", "KBS Classic FM", "KBS Cool FM", "KBS 1Radio", "KBS 1R",
    "SBS 러브 FM-SBS 라디오", "SBS Love FM", "SBS Power FM",
    "eTBS", "FM 95.1 TBS fm", "EBS FM Radio", "EBS i Radio", "ebs tune in",
    "YTN 라디오", "WBS 원음방송", "TJB 파워 FM (POWER FM)", "KNN부산 Power FM",
    "Radio Seoul", "TBC Dream FM", "Happyday Newage Radio EZ",
    "Big B Radio - Kpop", "BOX : K-POP 케이팝",
    "Listen.moe (K-Pop)", "Listen.moe Kpop",
    "Gwangju Foreign Language Network 98.7 - English",
    "명품", "황금", "Fred Film Radio(한국어)", "Oldpop Cafe",
}

# ── 「常用」栏规则 ───────────────────────────────────────────────────
FAVORITES = [
    # —— 中国新闻 ——
    "CCTV-1 综合", "CCTV-13 新闻", "CCTV-4 中文国际", "CCTV-2 财经",
    "CGTN", "CGTN记录",
    "湖南卫视", "浙江卫视", "东方卫视", "江苏卫视", "北京卫视",
    "广东卫视", "深圳卫视", "山东卫视", "四川卫视",
    # —— 咪咕体育 / 赛事 ——
    "咪咕 4K 台 1", "咪咕 4K 台 2",
    "咪咕赛事台 01（赛事轮播）", "咪咕赛事台 02（赛事轮播）",
    "咪咕赛事台 03（赛事轮播）",
    "咪咕 五星体育", "咪咕 劲爆体育", "咪咕 魅力足球", "咪咕 全民热练",
    "咪咕 睛彩竞技", "咪咕 睛彩篮球", "咪咕 游戏风云",
    "CCTV-5 体育", "CCTV-5+ 体育赛事", "CCTV-16 奥林匹克",
    # —— 韩国新闻 ——
    "Arirang TV", "TV Chosun", "TV Chosun 2",
    "TBS Seoul", "GCN24 Korean", "RUTC TV", "OUN", "BTN TV", "FGTV", "NHTV",
    "SBS JTV", "SBS CJB", "BBS Buddhist Broadcasting",
    "KBS LiveCam DokDo", "National Assembly TV",
    "NBS Korea Agricultural Broadcasting",
    "MBC Andong (안동 MBC)", "MBC Chungbuk (MBC 충북)",
    # —— 韩国电台 ——
    "Arirang FM", "GugakFM", "TBN 교통방송", "TBN 울산교통방송",
    "MBC충북 FM4U", "MBC충북 표준FM", "마포FM", "안동MBC AM",
    "befm", "CBS Music FM", "JTV 매직FM",
]


def fav_match(rule, name):
    if rule.endswith("*"):
        return name.startswith(rule[:-1])
    return name == rule


def fetch(url, cache_dir, offline):
    fname = CACHE_NAME.get(fname_key(url))
    if fname is None:
        fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.rsplit("/", 1)[-1])
    path = os.path.join(cache_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    if offline:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read().decode("utf-8", "replace")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return data
    except Exception as e:  # noqa: BLE001
        print("  ! 下载失败 %s: %s" % (url, e), file=sys.stderr)
        return ""


def fname_key(url):
    for k, v in SOURCES.items():
        if v == url:
            return k
    return url


def parse_m3u(text):
    """解析 M3U -> [{group,name,attrs,urls,referer}]（一个 EXTINF 块一条）"""
    out = []
    attrs, name, group, referer, urls = {}, "", "其它", None, []

    def flush():
        if urls:
            out.append({"group": group, "name": name, "attrs": dict(attrs),
                        "urls": list(urls), "referer": referer})

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            flush()
            payload = line[len("#EXTINF:"):]
            head, sep, tail = payload.rpartition(",")
            if sep:
                attrs = {k.lower(): v for k, v in ATTR_RE.findall(head)}
                name = tail.strip()
            else:
                attrs, name = {}, payload.strip()
            if attrs.get("group-title"):
                group = attrs["group-title"]
            urls, referer = [], None
            continue
        if line.startswith("#EXTGRP:"):
            flush()
            group = line[len("#EXTGRP:"):].strip()
            continue
        if line.startswith("#EXTVLCOPT:"):
            kv = line[len("#EXTVLCOPT:"):]
            if kv.lower().startswith("http-referrer="):
                referer = kv.split("=", 1)[1].strip()
            continue
        if line.startswith("#"):
            continue
        urls.append(line)
    flush()
    return out


def merge_mirrors(entries, cap=MAX_MIRRORS):
    """同名频道合并成一条，多路地址按出现顺序排列。"""
    order, buckets = [], {}
    for e in entries:
        key = norm_name(e["name"])
        if key not in buckets:
            buckets[key] = {"name": e["name"], "attrs": dict(e["attrs"]),
                            "urls": [], "referer": e.get("referer")}
            order.append(key)
        b = buckets[key]
        for u in e["urls"]:
            if u not in b["urls"]:
                b["urls"].append(u)
    out = []
    for k in order:
        b = buckets[k]
        b["urls"] = b["urls"][:cap]
        out.append(b)
    return out


def apply_kr_patch(channels):
    """用 tools/refresh_kr_mirrors.py 实测出来的可用地址覆盖韩台镜像。"""
    path = os.path.join(HERE, "kr_mirrors.json")
    if not os.path.exists(path):
        return channels
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        print("  ! 读取 kr_mirrors.json 失败: %s" % e, file=sys.stderr)
        return channels
    index = {norm_name(k): v for k, v in data.get("mirrors", {}).items()}
    hit = 0
    for ch in channels:
        live = index.get(norm_name(ch["name"]))
        if not live:
            continue
        merged = list(live)
        for u in ch["urls"]:
            if u not in merged:
                merged.append(u)
        ch["urls"] = merged[:MAX_MIRRORS]
        hit += 1
    print("  · 已用实测可用镜像覆盖 %d 个韩台" % hit)
    return channels


def load_prune(path):
    """读取实测 JSON，返回「实测不可用」的频道名集合。"""
    if not path:
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    bad = set()
    for r in data:
        if not r.get("ok"):
            bad.add(norm_name(r["name"]))
    print("  · 实测剔除名单：%d 个打不开的频道" % len(bad))
    return bad


def load_rank(path):
    """读取实测 JSON，返回「台名 -> 真正出流的那一路地址」。"""
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rank = {}
    for r in data:
        used = r.get("used")
        if r.get("ok") and used:
            rank.setdefault(norm_name(r["name"]), used)
    print("  · 实测可用镜像前置：%d 个频道" % len(rank))
    return rank


def build(cache_dir, offline, prune_names, rank):
    parsed = {}
    for key, url in SOURCES.items():
        print("· 拉取 %s ..." % key)
        text = fetch(url, cache_dir, offline)
        parsed[key] = parse_m3u(text) if text else []
        print("  -> %d 条" % len(parsed[key]))

    # ── 1) 中国新闻：央视 / 卫视 / CGTN / CETV ──
    cn = []
    for key in ("cn", "ccsh"):
        for e in parsed[key]:
            if e["group"].startswith("💰"):      # 付费台，不碰
                continue
            n = canon_cn(e["name"])
            if n in CN_SPORT_CHANNELS:
                continue
            if re.match(r"^(CCTV-|CGTN|CETV-\d)", n) or n.endswith("卫视"):
                cn.append(dict(e, name=n))
    cn = merge_mirrors(cn)
    print("  · 中国新闻：%d 个" % len(cn))

    # ── 2) 咪咕体育 ──
    migu_sport = []
    # 2a) 咪咕源：编号赛事台归「赛事」，睛彩台归「咪咕体育」
    for e in parsed["migu"]:
        n = migu_rename(e["name"])
        if not n:
            continue
        e = dict(e)
        e["name"] = n
        e["urls"] = [fix_migu_url(u) for u in e["urls"]]
        if n.startswith("咪咕赛事台"):
            continue
        migu_sport.append(e)
    # 2b) fmml 源：只留咪咕自有内容（Contentid 3 开头 + FifastbLive）
    for e in parsed["fmml"]:
        urls = [fix_migu_url(u) for u in e["urls"] if is_migu_own_content(u)]
        if not urls:
            continue
        n = canon_cn(e["name"])
        if n == "咪咕全民热练":
            n = "咪咕 全民热练"
        migu_sport.append(dict(e, name=n, urls=urls))
    # 2c) CCSH：咪咕特色台
    for e in parsed["ccsh"]:
        if e["group"] not in ("体育频道", "游戏频道", "NewTV"):
            continue
        n = e["name"].strip()
        if n in CCSH_MIGU_NAMES:
            n = CCSH_MIGU_NAMES[n]
        elif n in ("广东体育", "辽宁体育"):
            pass
        else:
            continue
        migu_sport.append(dict(e, name=n))
    migu_sport = merge_mirrors(migu_sport)
    print("  · 咪咕体育：%d 个" % len(migu_sport))

    # ── 3) 赛事：咪咕编号台 + 央视体育台 ──
    event = []
    for e in parsed["migu"]:
        n = migu_rename(e["name"])
        if not n.startswith("咪咕赛事台"):
            continue
        e = dict(e)
        e["name"] = n
        e["urls"] = [fix_migu_url(u) for u in e["urls"]]
        event.append(e)
    for key in ("cn", "ccsh", "guovin"):
        for e in parsed[key]:
            if e["group"].startswith("💰"):
                continue
            n = canon_cn(e["name"])
            if n in CN_SPORT_CHANNELS:
                event.append(dict(e, name=n))
    event = merge_mirrors(event)
    print("  · 赛事：%d 个" % len(event))

    # ── 4) 韩国新闻（白名单精选）──
    kr = []
    for key in ("kr", "kro", "radio"):
        for e in parsed[key]:
            n = norm_name(e["name"])
            if n in KR_TV_KEEP:
                kr.append(dict(e, name=n))
    kr = merge_mirrors(kr)
    kr = apply_kr_patch(kr)
    print("  · 韩国新闻：%d 个" % len(kr))

    # ── 5) 韩国电台（白名单精选）──
    radio = []
    for key in ("radio", "kr"):
        for e in parsed[key]:
            n = norm_name(e["name"])
            if n in KR_RADIO_KEEP:
                radio.append(dict(e, name=n))
    radio = merge_mirrors(radio)
    radio = apply_kr_patch(radio)
    print("  · 韩国电台：%d 个" % len(radio))

    pools = {G_CN: cn, G_MIGU: migu_sport, G_EVENT: event,
             G_KR: kr, G_RADIO: radio}

    # ── 6) 实测可用镜像前置 ──
    if rank:
        hit = 0
        for lst in pools.values():
            for c in lst:
                best = rank.get(norm_name(c["name"]))
                if best and best in c["urls"]:
                    c["urls"].remove(best)
                    c["urls"].insert(0, best)
                    hit += 1
        print("  · 已把实测可用镜像挪到首位：%d 个频道" % hit)

    # ── 7) 剔除实测打不开的频道 ──
    if prune_names:
        for g, lst in pools.items():
            before = len(lst)
            pools[g] = [c for c in lst if norm_name(c["name"]) not in prune_names]
            if before != len(pools[g]):
                print("  · %s：剔除 %d 个" % (g, before - len(pools[g])))

    # ── 8) 常用栏目（跨栏目挑，顺序按 FAVORITES）──
    survivors = []
    for g in (G_CN, G_MIGU, G_EVENT, G_KR, G_RADIO):
        for c in pools[g]:
            survivors.append((g, c))
    fav, seen = [], set()
    for rule in FAVORITES:
        for g, c in survivors:
            n = norm_name(c["name"])
            if n in seen:
                continue
            if fav_match(rule, n):
                seen.add(n)
                fav.append(dict(c, group=g))
    print("  · 常用：%d 个" % len(fav))

    groups = [(G_FAV, fav)]
    for g in (G_MIGU, G_EVENT, G_CN, G_KR, G_RADIO):
        groups.append((g, pools[g]))
    return groups


def dump(groups, out_path):
    lines = ["#EXTM3U x-tvg-url=\"https://iptv-org.github.io/epg/guides/kr/seezntv.com.epg.xml,https://iptv-org.github.io/epg/guides/kr/wavve.com.epg.xml\"", ""]
    total = 0
    for gname, channels in groups:
        if not channels:
            continue
        lines.append("#EXTGRP:%s" % gname)
        for ch in channels:
            attrs = []
            if ch["attrs"].get("tvg-id"):
                attrs.append('tvg-id="%s"' % ch["attrs"]["tvg-id"])
            if ch["attrs"].get("tvg-logo"):
                attrs.append('tvg-logo="%s"' % ch["attrs"]["tvg-logo"])
            attrs.append('group-title="%s"' % gname)
            lines.append("#EXTINF:-1 %s,%s" % (" ".join(attrs), ch["name"]))
            for u in ch["urls"]:
                lines.append(u)
            if ch.get("referer"):
                lines.append("#EXTVLCOPT:http-referrer=%s" % ch["referer"])
        total += len(channels)
        lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("\n✔ 已写出 %s" % os.path.abspath(out_path))
    print("  共 %d 个频道" % total)
    for gname, channels in groups:
        print("  - %-10s %d 个" % (gname, len(channels)))
    return groups


def selftest(groups):
    """内置断言：栏目顺序 / 台名不重复 / 每台至少一条地址 / 无说明条目。"""
    errors = []
    order = [g for g, _ in groups]
    if order != GROUP_ORDER:
        errors.append("栏目顺序不对：%s（期望 %s）" % (order, GROUP_ORDER))
    for gname, channels in groups:
        seen = set()
        for ch in channels:
            n = norm_name(ch["name"])
            if n in seen:
                errors.append("[%s] 台名重复：%s" % (gname, n))
            seen.add(n)
            if not ch["urls"]:
                errors.append("[%s] 没有播放地址：%s" % (gname, n))
            if JUNK_NAME_RE.search(ch["name"]):
                errors.append("[%s] 混进了说明条目：%s" % (gname, ch["name"]))
            if re.search(r"\(\d{3,4}p\)|\[(Not 24/7|Geo-blocked)\]", ch["name"]):
                errors.append("[%s] 台名还带上游后缀：%s" % (gname, ch["name"]))
            for u in ch["urls"]:
                if "cmvideo.cn" in u and "stbId=" not in u:
                    errors.append("[%s] 咪咕地址缺 stbId：%s" % (gname, n))
                    break
    if errors:
        print("\n✘ 自检未通过：")
        for e in errors[:40]:
            print("   - %s" % e)
        return False
    print("\n✔ 自检通过：栏目顺序 / 台名唯一 / 地址齐全 / 咪咕地址带 stbId")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=os.path.join(HERE, ".cache"))
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--prune-from", default="", help="上一次实测 JSON，按结果剔除打不开的频道")
    ap.add_argument("--rank-from", default="", help="上一次实测 JSON，把真正出流的那一路挪到首位")
    ap.add_argument("--selftest", action="store_true", help="写完后跑内置断言")
    args = ap.parse_args()

    os.makedirs(args.cache_dir, exist_ok=True)
    prune_names = load_prune(args.prune_from)
    rank = load_rank(args.rank_from)
    groups = build(args.cache_dir, args.offline, prune_names, rank)
    dump(groups, args.out)
    if args.selftest and not selftest(groups):
        sys.exit(1)


if __name__ == "__main__":
    main()
