#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""矩阵测试：咪咕 CDN 到底认什么。

变量：
  路径形式   A=/index.m3u8（migu 源）   B=/{cid}/1.m3u8（fmml 源）
  channel-id FifastbLive / wasusyt / bestzb / ystenlive
  Contentid  3000000001000005308（咪咕赛事台01，实测 200）
             6000000001000029752（fmml 的 CCTV-1）
输出：第一跳状态 + 302 目标 host + 第二跳状态 + 是否 HLS
"""
import http.client
import socket
import sys
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
REF = "https://www.miguvideo.com/"
ALIAS = "base-v4v6-cm-miguvideo.e.cdn.chinamobile.com"

CDN_IPS = sorted({i[4][0] for i in socket.getaddrinfo(ALIAS, None, socket.AF_INET)})


def req(url, referer=None, pin=None):
    p = urllib.parse.urlparse(url)
    host, port = p.hostname, p.port or 80
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if referer:
        hdrs["Referer"] = referer
    try:
        s = socket.create_connection((pin or host, port), 12)
        c = http.client.HTTPConnection(host, port, timeout=12)
        c.sock = s
        c.request("GET", path, headers=hdrs)
        r = c.getresponse()
        body = r.read(300).decode("utf-8", "replace")
        st, loc = r.status, r.getheader("Location")
        c.close()
        return st, loc, body
    except Exception as e:
        return 0, None, "%s: %s" % (type(e).__name__, e)


def run(cid, ch, path_form, stb):
    if path_form == "A":
        first = ("http://gslbserv.itv.cmvideo.cn/index.m3u8?channel-id=%s&Contentid=%s"
                 "&livemode=1&stbId=%s" % (ch, cid, stb))
    else:
        first = ("http://gslbserv.itv.cmvideo.cn/%s/1.m3u8?channel-id=%s&Contentid=%s"
                 "&livemode=1&stbId=%s" % (cid, ch, cid, stb))
    st, loc, body = req(first, referer=REF)
    if st != 302 or not loc:
        return "%s %s" % (st, body.replace("\n", " ")[:34])
    host = urllib.parse.urlparse(loc).hostname
    best = None
    for ip in CDN_IPS:
        st2, _, b2 = req(loc, referer=REF, pin=ip)
        if "#EXTM3U" in b2:
            best = "HLS(%s)" % ip
            break
        if best is None:
            best = "%s" % st2
    return "%s -> %s %s" % (st, host, best)


CASES = [
    ("咪咕赛事台01 已知可用", "3000000001000005308", "FifastbLive", "A", "YanG-1989"),
    ("咪咕赛事台01 换路径B", "3000000001000005308", "FifastbLive", "B", "YanG-1989"),
    ("咪咕赛事台01 换stbId=3", "3000000001000005308", "FifastbLive", "A", "3"),
    ("CCTV1 路径A/FifastbLive", "6000000001000029752", "FifastbLive", "A", "3"),
    ("CCTV1 路径A/wasusyt", "6000000001000029752", "wasusyt", "A", "3"),
    ("CCTV1 路径B/wasusyt", "6000000001000029752", "wasusyt", "B", "3"),
    ("CCTV1 路径B/FifastbLive", "6000000001000029752", "FifastbLive", "B", "3"),
    ("劲爆体育 路径B/bestzb", "5000000002000029972", "bestzb", "B", "3"),
    ("劲爆体育 路径A/FifastbLive", "5000000002000029972", "FifastbLive", "A", "3"),
]

for label, cid, ch, pf, stb in CASES:
    print("%-26s %s" % (label, run(cid, ch, pf, stb)))
