#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""胖鹅TV · 内置播放列表合成器

把多个上游公开直播源合并成一份带分组的 M3U，并按「频道名」把不同镜像
合并成同一个频道的多条备用地址（应用里会自动换源）。

用法:
    python tools/build_playlist.py [--cache-dir DIR] [--out FILE] [--offline]
"""
import argparse
import os
import re
import sys
import urllib.request
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "app", "src", "main", "assets", "playlist.m3u")

SOURCES = {
    # 咪咕（运营商 CDN，国内可直连，靠应用内的 DNS 别名绕污染）
    "migu": "https://raw.githubusercontent.com/YanG-1989/m3u/main/Migu.m3u",
    # 央视 / 卫视（含备用镜像）
    "cn": "https://raw.githubusercontent.com/fanmingming/live/main/tv/m3u/index.m3u",
    # 韩国电视
    "kr": "https://raw.githubusercontent.com/wujinfeng009/iptv/main/Korean.m3u",
    # 韩国电台
    "radio": "https://raw.githubusercontent.com/junguler/m3u-radio-music-playlists/main/allradio.net/Korea.m3u",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

ATTR_RE = re.compile(r'([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"')
EXTINF_RE = re.compile(r"^#EXTINF:\s*(?P<dur>-?\d+)\s*(?P<attrs>.*?),(?P<name>.*)$")


def fetch(url, cache_dir, offline):
    """下载并缓存上游清单。"""
    fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.rsplit("/", 1)[-1])
    path = os.path.join(cache_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace")
    if offline:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
        return data.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print("  ! 下载失败 %s: %s" % (url, e), file=sys.stderr)
        return ""


def parse_m3u(text):
    """解析 M3U -> [{group,name,attrs,urls,referer}]"""
    out = []
    attrs, name, group, referer, urls = {}, "", "其它", None, []

    def flush():
        if urls:
            out.append({
                "group": group, "name": name, "attrs": dict(attrs),
                "urls": list(urls), "referer": referer,
            })

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = EXTINF_RE.match(line)
        if m:
            flush()
            attrs = {k.lower(): v for k, v in ATTR_RE.findall(m.group("attrs"))}
            name = m.group("name").strip()
            if attrs.get("group-title"):
                group = attrs["group-title"]
            urls, referer = [], None
            continue
        if line.startswith("#EXTGRP:"):
            flush()
            group = line[len("#EXTGRP:"):].strip()
            urls, referer = [], None
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


# ── 分组筛选规则 ────────────────────────────────────────────────
KR_TV_KEEP = re.compile(
    r"(KBS\s*1|KBS1|KBS\s*2|KBS2|KBS World|KBS News|KBS Drama|KBS Joy|KBS Life|"
    r"KBS Story|KBS LiveCam|MBC($|[^A-Za-z])|MBC On|SBS($|[^A-Za-z])|YTN|YTN Korea|"
    r"JTBC|Channel A|TV Chosun|MBN|tvN|Mnet|EBS|OCN|STB|CPBC|TBS Seoul|TBC|"
    r"SPOTV|Arirang TV|KTV|GCN24|MTN|World TV|Korea Work|JCN|CGNTV|CTSTV|BBS|"
    r"BTN|GoodTV|FGTV|UN($|[^A-Za-z])|RTV|RUTC|K Shopping|KTV|NBS|NHTV)")
KR_TV_DROP = re.compile(
    r"(Shopping|홈|쇼핑|Mall|Plus|Drama|Joy|Life|Story|Kids|Youth|스타|"
    r"Geo-blocked|regional|울산|부산|대전|광주|대구|춘천|안동|여수|목포|강원|"
    r"충북|경남|제주|울|TV N|net)", re.I)
RADIO_DROP = re.compile(
    r"(Big B Radio|BOX : K-POP|Listen\.moe|Happyday|HUG|평양FM|트로트|명품|황금|"
    r"Fred Film|Radio Seoul|Gwangju Foreign|Oldpop|K-pop|Kpop)", re.I)
RADIO_TV = re.compile(r"(EBS TV|CPBC TV|TBS TV|Buddhist|KBS World TV|Gukak TV|"
                      r"Arirang TV|BTN TV|GBS)", re.I)

# 韩国新闻的额外镜像（主源挂了自动换这些）
KR_EXTRA_MIRRORS = {
    "KBS1": ["http://mytv.dothome.co.kr/ch/catv/1.php"],
    "KBS2": ["http://mytv.dothome.co.kr/ch/catv/2.php"],
    "MBC": ["http://123.254.72.24:1935/tvlive/livestream2/playlist.m3u8"],
    "YTN": ["http://202.60.106.14:21585/214/playlist.m3u8"],
    "KBS World": ["https://kbsworld-ott.akamaized.net/hls/live/2002341/kbsworld/master.m3u8"],
}


def pick(entries, group_filter, drop=None, keep=None):
    """按 group 过滤并做名称归一（去掉分辨率后缀等）。"""
    res = []
    for e in entries:
        if group_filter and not group_filter(e["group"]):
            continue
        if drop and drop.search(e["name"]):
            continue
        if keep and not keep.search(e["name"]):
            continue
        res.append(e)
    return res


def norm_name(name):
    n = re.sub(r"\s*\(\d{3,4}p\)", "", name)
    n = re.sub(r"\s*\[.*?\]", "", n)
    return n.strip()


def merge_mirrors(entries):
    """同名频道合并成一条，多个地址按出现顺序排列。"""
    order, buckets = [], {}
    for e in entries:
        key = norm_name(e["name"])
        if key not in buckets:
            buckets[key] = {
                "name": key, "group": e["group"], "attrs": dict(e["attrs"]),
                "urls": [], "referer": e["referer"],
            }
            order.append(key)
        b = buckets[key]
        for u in e["urls"]:
            if u not in b["urls"]:
                b["urls"].append(u)
        if not b["referer"]:
            b["referer"] = e["referer"]
        # 优先保留带 tvg-id / logo 的那份属性
        if e["attrs"].get("tvg-logo") and not b["attrs"].get("tvg-logo"):
            b["attrs"] = dict(e["attrs"])
    return [buckets[k] for k in order]


def build(cache_dir, offline):
    parsed = {}
    for key, url in SOURCES.items():
        print("· 拉取 %s ..." % key)
        text = fetch(url, cache_dir, offline)
        parsed[key] = parse_m3u(text)
        print("  -> %d 条" % len(parsed[key]))

    groups = []  # [(分组名, [channel])]

    # 1) 咪咕体育
    migu = [e for e in parsed["migu"]
            if e["name"].startswith("咪咕直播") or e["name"].startswith("睛彩")
            or "4K" in e["name"]]
    migu = sorted(migu, key=lambda e: (not e["name"].startswith("咪咕直播"),
                                        e["name"]))
    groups.append(("咪咕体育", merge_mirrors(migu)))

    # 2) 央视高清（主 + 备用镜像）
    cctv = [e for e in parsed["cn"] if e["group"] in ("央视高清", "央视备用")]
    cctv = [e for e in cctv if re.search(r"CCTV|CGTN", e["name"])]
    groups.append(("央视新闻", merge_mirrors(cctv)))

    # 3) 卫视高清（主 + 备用镜像）
    sats = [e for e in parsed["cn"] if e["group"] in ("卫视高清", "卫视备用")]
    groups.append(("卫视高清", merge_mirrors(sats)))

    # 4) 韩国新闻
    kr = pick(parsed["kr"], lambda g: True, KR_TV_DROP, KR_TV_KEEP)
    kr = merge_mirrors(kr)
    for ch in kr:
        for extra in KR_EXTRA_MIRRORS.get(norm_name(ch["name"]), []):
            if extra not in ch["urls"]:
                ch["urls"].append(extra)
    groups.append(("韩国新闻", kr))

    # 5) 韩国电台
    radio = pick(parsed["radio"], lambda g: True, RADIO_DROP)
    radio = [e for e in radio if not RADIO_TV.search(e["name"])]
    groups.append(("韩国电台", merge_mirrors(radio)))

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
            head = "#EXTINF:-1 %s,%s" % (" ".join(attrs), ch["name"])
            lines.append(head)
            if ch.get("referer"):
                lines.append("#EXTVLCOPT:http-referrer=%s" % ch["referer"])
            for u in ch["urls"]:
                lines.append(u)
            total += 1
        lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("\n✔ 已写出 %s" % os.path.abspath(out_path))
    print("  共 %d 个频道" % total)
    for gname, channels in groups:
        print("  - %-10s %d 个" % (gname, len(channels)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default=os.path.join(HERE, ".cache"))
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.cache_dir, exist_ok=True)
    groups = build(args.cache_dir, args.offline)
    dump(groups, args.out)


if __name__ == "__main__":
    main()
