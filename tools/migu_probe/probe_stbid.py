#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证：咪咕 CDN 是否只认 stbId。

同一个 Contentid（fmml 源给的 CCTV-1），只改 stbId，看哪些能拿到 HLS。
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

TEMPLATE = ("http://gslbserv.itv.cmvideo.cn/{cid}/1.m3u8?channel-id={ch}"
            "&Contentid={cid}&livemode=1&stbId={stb}")

CID = "6000000001000029752"   # fmml 源里 CCTV 1 的 Contentid


def cdn_ip():
    return socket.getaddrinfo(ALIAS, None, socket.AF_INET)[0][4][0]


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


ip = cdn_ip()
print("CDN IP:", ip, "\n")
for stb in ["3", "YanG-1989", "0", "test", "PangETV"]:
    for ch in ["wasusyt", "FifastbLive"]:
        u = TEMPLATE.format(cid=CID, ch=ch, stb=stb)
        st, loc, body = req(u, referer=REF)
        note = ""
        if st == 302 and loc:
            st2, loc2, body2 = req(loc, referer=REF, pin=ip)
            note = " -> %s %s" % (st2, "HLS" if "#EXTM3U" in body2 else body2.replace("\n", " ")[:36])
        else:
            note = " | " + body.replace("\n", " ")[:40]
        print("stbId=%-10s channel-id=%-12s %s%s" % (stb, ch, st, note))
    print()
