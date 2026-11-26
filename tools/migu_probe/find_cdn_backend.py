#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找 cache.ott.<x>.itv.cmvideo.cn 的真实 CDN 后端域名。

已知：cache.ott.fifalive.itv.cmvideo.cn → base-v4v6-cm-miguvideo.e.cdn.chinamobile.com
推测：cache.ott.<x>.  → base-v4v6-cm-<x>.e.cdn.chinamobile.com
判据：解析结果不能是 1.1.1.1（污染）。
"""
import socket
import sys

sys.stdout.reconfigure(encoding="utf-8")

GROUPS = ["wasulive", "bestlive", "ystenlive", "fifalive", "miguvideo"]
PREFIXES = ["base-v4v6-cm-", "base-v4v6-cm2-", "base-v4v6-", "base-cm-", "base-"]
SUFFIXES = [".e.cdn.chinamobile.com", ".cdn.chinamobile.com", ".e.cdn.chinamobile.com."]

for g in GROUPS:
    for pre in PREFIXES:
        for suf in SUFFIXES:
            host = "%s%s%s" % (pre, g, suf)
            try:
                ips = sorted({i[4][0] for i in socket.getaddrinfo(host, None, socket.AF_INET)})
            except Exception:
                continue
            bad = all(ip.startswith("1.1.1.") or ip.startswith("0.0.0.") for ip in ips)
            if not bad:
                print("✔ %-56s -> %s" % (host, ips))

print("\n--- 参考：已知的 miguvideo 后端 ---")
for host in ["base-v4v6-cm-miguvideo.e.cdn.chinamobile.com"]:
    try:
        print(host, "->", sorted({i[4][0] for i in socket.getaddrinfo(host, None, socket.AF_INET)}))
    except Exception as e:
        print(host, "失败", e)
