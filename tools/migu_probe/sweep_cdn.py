#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫 39.135.122.0/24 段里的边缘节点，看有没有能放行央视版权流（cache.ott.wasulive）的。

fmml 源里央视/卫视的取流地址第二跳会跳到 cache.ott.wasulive.itv.cmvideo.cn，
这个域名在本地被污染成 1.1.1.1；这里试遍同一网段的真实节点。
"""
import http.client
import socket
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.stdout.reconfigure(encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
REF = "https://www.miguvideo.com/"

# 第一跳拿签名地址
FIRST = ("http://gslbserv.itv.cmvideo.cn/6000000001000029752/1.m3u8"
         "?channel-id=wasusyt&Contentid=6000000001000029752&livemode=1&stbId=YanG-1989")


def req(url, referer=None, pin=None, timeout=6):
    p = urllib.parse.urlparse(url)
    host, port = p.hostname, p.port or 80
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if referer:
        hdrs["Referer"] = referer
    try:
        s = socket.create_connection((pin or host, port), timeout)
        c = http.client.HTTPConnection(host, port, timeout=timeout)
        c.sock = s
        c.request("GET", path, headers=hdrs)
        r = c.getresponse()
        body = r.read(200).decode("utf-8", "replace")
        st = r.status
        loc = r.getheader("Location")
        c.close()
        return st, loc, body
    except Exception:
        return None, None, ""


st, loc, body = req(FIRST, referer=REF)
print("第一跳:", st, (loc or body)[:120])
if not loc:
    sys.exit(1)

IPS = ["39.135.122.%d" % i for i in range(168, 200)]


def try_ip(ip):
    st, _loc, body = req(loc, referer=REF, pin=ip)
    return ip, st, body


with ThreadPoolExecutor(max_workers=16) as p:
    for ip, st, body in p.map(try_ip, IPS):
        if st is None:
            continue
        tag = "HLS ✔" if "#EXTM3U" in body else ""
        print("%-16s %s %s %s" % (ip, st, tag, body.replace("\n", " ")[:40]))
