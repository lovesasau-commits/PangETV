#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""胖鹅TV · 韩国频道镜像刷新

公共 IPTV 源会劣化（实测：KBS1/KBS2 的两个镜像一个 DNS 解析失败、
一个返回 200 空 body）。本脚本：

  1. 汇总候选地址 = 当前列表里的韩台地址 + 上游清单里同名/别名的地址
     + 手工补充的备用地址；
  2. 用与应用内完全相同的规则逐条实测（咪咕走 302+DNS 别名，其余直连）；
  3. 只把**实测可用**的地址写进 tools/kr_mirrors.json。

build_playlist.py 读取该文件覆盖韩台镜像列表。

用法:
    python tools/refresh_kr_mirrors.py                # 探测并写文件
    python tools/refresh_kr_mirrors.py --report       # 只看报告不写文件
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
import check_streams as cs  # noqa: E402

PLAYLIST = os.path.join(ROOT, "app", "src", "main", "assets", "playlist.m3u")
OUT_JSON = os.path.join(HERE, "kr_mirrors.json")

UPSTREAMS = [
    "https://raw.githubusercontent.com/wujinfeng009/iptv/main/Korean.m3u",
    "https://raw.githubusercontent.com/junguler/m3u-radio-music-playlists/main/allradio.net/Korea.m3u",
    "https://iptv-org.github.io/iptv/countries/kr.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/kr.m3u",
]

# 列表里的台名 -> 上游清单里可能出现的别名（归一化后比较）
ALIASES = {
    "KBS1": ["KBS1", "KBS 1", "KBS1TV", "KBS 1TV", "KBS1 TV"],
    "KBS2": ["KBS2", "KBS 2", "KBS2TV", "KBS 2TV", "KBS2 TV"],
    "MBC": ["MBC", "MBC TV", "MBC News", "MBC News TV"],
    "SBS": ["SBS", "SBS TV", "SBS News", "SBS News TV"],
    "YTN": ["YTN", "YTN TV"],
    "EBS 1": ["EBS 1", "EBS1", "EBS 1TV", "EBS1TV", "EBS 1 TV"],
    "EBS 2": ["EBS 2", "EBS2", "EBS 2TV", "EBS2TV", "EBS 2 TV"],
    "EBS E": ["EBS E", "EBS English", "EBSE"],
    "EBS+ 1": ["EBS+ 1", "EBS Plus 1", "EBSPlus1"],
    "EBS+ 2": ["EBS+ 2", "EBS Plus 2", "EBSPlus2"],
    "Arirang TV": ["Arirang TV", "Arirang TV HD"],
    "Arirang FM": ["Arirang FM", "Arirang Radio"],
    "SBS JTV": ["SBS JTV", "JTV"],
    "TV Chosun": ["TV Chosun"],
    "TV Chosun 2": ["TV Chosun 2"],
    "GoodTV": ["GoodTV", "Good TV", "Good TV (South Korea)"],
    "RTV": ["RTV", "RTV (South Korea)"],
    "MTN": ["MTN"],
    "OCN": ["OCN"],
    "MNB World": ["MNB World"],
    "Gugak FM": ["GugakFM", "gukak", "Gugak TV"],
    "CGNTV": ["CGNTV", "GCN", "GCN24 Korean", "GCN (South Korea)"],
}

# 手工补充的备用地址
EXTRA = {
    "KBS1": ["http://mytv.dothome.co.kr/ch/catv/1.php"],
    "KBS2": ["http://mytv.dothome.co.kr/ch/catv/2.php"],
    "MBC": ["http://123.254.72.24:1935/tvlive/livestream2/playlist.m3u8"],
    "SBS": ["http://123.254.72.24:1935/tvlive/livestream/playlist.m3u8"],
    "YTN": ["http://202.60.106.14:8080/214/playlist.m3u8"],
    "KBS World": ["https://kbsworld-ott.akamaized.net/hls/live/2002341/kbsworld/master.m3u8"],
}

MAX_MIRRORS = 8
RES_RE = re.compile(r"\s*\(\d{3,4}p\)")
BRACKET_RE = re.compile(r"\s*\[[^\]]*\]")


def norm(s):
    s = RES_RE.sub("", s)
    s = BRACKET_RE.sub("", s)
    # 注意保留 '+'：否则 "EBS 1" 与 "EBS+ 1" 会归一成同一个键
    s = re.sub(r"[\s\-_()\[\].·、,，:：'/]", "", s)
    return s.lower()


def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": cs.UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print("  ! 下载失败 %s: %s" % (url, e), file=sys.stderr)
        return ""


def _parse_text(text):
    """复用 check_streams 的解析逻辑（内存文本）。"""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".m3u")
    os.close(fd)
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        return cs.parse_playlist(tmp)
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="只打印报告，不写文件")
    ap.add_argument("--jobs", type=int, default=12)
    args = ap.parse_args()

    # 1) 候选池：归一化名 -> {name, urls, referer}
    cands = {}

    def add(name, url, referer=None):
        if not url or not name:
            return
        key = norm(name)
        slot = cands.setdefault(key, {"name": name, "urls": [], "referer": referer})
        if url not in slot["urls"]:
            slot["urls"].append(url)

    # 别名反查表：上游归化名 -> 列表里的归化名
    alias_index = {}
    for disp, names in ALIASES.items():
        for n in names:
            alias_index.setdefault(norm(n), norm(disp))

    # 当前列表里的韩台
    cur = cs.parse_playlist(PLAYLIST)
    for ch in cur:
        if ch["group"] in ("韩国新闻", "韩国电台"):
            for u in ch["urls"]:
                add(ch["name"], u, ch.get("referer"))

    # 上游清单：按别名匹配补候选
    for up in UPSTREAMS:
        print("· 拉取 %s" % up, flush=True)
        text = fetch(up)
        if not text:
            continue
        for ch in _parse_text(text):
            key = alias_index.get(norm(ch["name"]))
            if not key or key not in cands:
                continue
            slot = cands[key]
            for u in ch["urls"]:
                if u not in slot["urls"]:
                    slot["urls"].append(u)

    # 手工补充
    for name, urls in EXTRA.items():
        for u in urls:
            add(name, u)

    # 2) 逐条实测
    jobs = []
    for key, info in cands.items():
        for u in info["urls"]:
            jobs.append((key, u, info.get("referer")))
    print("候选地址 %d 条，开始实测…" % len(jobs), flush=True)

    def probe(job):
        key, url, referer = job
        status, head, ok = cs.probe(url, referer)
        return key, url, status, head, ok

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(probe, jobs))

    # 3) 汇总
    good = {}
    for key, url, status, head, ok in results:
        if ok:
            good.setdefault(key, []).append(url)

    print("\n%-34s %-5s %-6s %s" % ("频道", "候选", "可用", "命中地址"))
    print("-" * 100)
    total_ok = 0
    for key in sorted(cands, key=lambda k: cands[k]["name"]):
        info = cands[key]
        hits = good.get(key, [])
        total_ok += 1 if hits else 0
        print("%-34s %-5d %-6s %s" % (
            info["name"][:33], len(info["urls"]), len(hits),
            (hits[0][:58] if hits else "—")))

    usable = {k: v[:MAX_MIRRORS] for k, v in good.items()}
    print("\n==== %d / %d 个韩台至少有一路可用 ====" % (total_ok, len(cands)))

    if not args.report:
        payload = {
            "generated_at": "2026-11-25",
            "note": "只保留实测可用的地址；build_playlist.py 读取本文件覆盖韩台镜像",
            "mirrors": {cands[k]["name"]: v for k, v in usable.items()},
        }
        with io.open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("已写入: %s" % OUT_JSON)


if __name__ == "__main__":
    main()
