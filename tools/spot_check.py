#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""胖鹅TV · 抽样复测（交付前的现场自检）

按应用内**完全相同**的规则去探活：
  1. 普通源：直连 GET（带浏览器 UA），跟随 302
  2. 咪咕源：先取 302 的签名地址，再把 cache.ott.fifalive.itv.cmvideo.cn
     钉到真实 CDN IP 上取流（等价于应用里的 OkHttp 自定义 Dns）

与 check_streams.py 的区别：这里每组只抽 N 条，用来快速确认
「交付这一刻这些源还活着」。

用法:
    python tools/spot_check.py                 # 每组抽 3 条
    python tools/spot_check.py --per-group 5
"""
import argparse
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_streams as cs  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEFAULT_PLAYLIST = os.path.join(
    ROOT, "app", "src", "main", "assets", "playlist.m3u")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", default=DEFAULT_PLAYLIST)
    ap.add_argument("--per-group", type=int, default=3)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    channels = cs.parse_playlist(args.playlist)
    groups = {}
    for ch in channels:
        groups.setdefault(ch["group"], []).append(ch)

    sample = []
    for g, lst in groups.items():
        step = max(1, len(lst) // args.per_group)
        picked = lst[::step][:args.per_group]
        sample.extend(picked)
        print("抽样：%s -> %d/%d 条" % (g, len(picked), len(lst)), flush=True)
    print("")

    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(cs.check_channel, sample):
            results.append(r)

    ok = 0
    print("%-14s %-24s %-6s %-7s %s" % ("分组", "台名", "状态", "可用", "说明"))
    print("-" * 92)
    for r in sorted(results, key=lambda x: (x["group"], x["name"])):
        good = r.get("ok")
        ok += 1 if good else 0
        atts = r.get("attempts") or [{}]
        first = atts[0]
        status = first.get("status", "-")
        head = first.get("head", "") or ""
        print("%-14s %-24s %-6s %-7s %s" % (
            r["group"][:13], r["name"][:23], status,
            "是" if good else "否", head[:44]))

    print("\n==== 抽样通过 %d / %d ====" % (ok, len(results)))

    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("证据已写入: %s" % args.json)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
