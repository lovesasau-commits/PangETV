#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""胖鹅TV · 内置列表逐条实测

按应用内完全相同的规则去探活：
  1. 普通源：直连 GET（带浏览器 UA），跟随 302
  2. 咪咕源：先取 302 的签名地址，再把
     cache.ott.fifalive.itv.cmvideo.cn 钉到真实 CDN IP 上取流
     （等价于应用里的自定义 Dns）

用法:
    python tools/check_streams.py --playlist app/src/main/assets/playlist.m3u \
        --json out.json --csv out.csv
"""
import argparse
import csv
import http.client
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
MIGU_REFERER = "https://www.miguvideo.com/"
MIGU_CDN_HOST = "cache.ott.fifalive.itv.cmvideo.cn"
MIGU_ALIAS_HOST = "base-v4v6-cm-miguvideo.e.cdn.chinamobile.com"
TIMEOUT = 12


# ── HTTP 基础件 ─────────────────────────────────────────────────
class PinnedConnection(http.client.HTTPConnection):
    """连接时用指定 IP，但 Host/SNI 仍用原域名（等价 curl --resolve）。"""

    def __init__(self, host, port, timeout=TIMEOUT, pin_ip=None):
        super().__init__(host, port, timeout=timeout)
        self._pin_ip = pin_ip

    def connect(self):
        self.sock = socket.create_connection(
            (self._pin_ip or self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()


def http_get(url, referer=None, pin_host=None, pin_ip=None, timeout=TIMEOUT):
    """返回 (status, body_head, final_url)。只读，不跟随自动跳转。"""
    p = urllib.parse.urlparse(url)
    host = p.hostname
    if not host:
        return 0, "bad url", url
    port = p.port or (443 if p.scheme == "https" else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    headers = {"User-Agent": UA, "Accept": "*/*", "Connection": "close"}
    if referer:
        headers["Referer"] = referer
    try:
        if p.scheme == "https":
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
        else:
            conn = PinnedConnection(host, port, timeout=timeout, pin_ip=pin_ip)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read(2048)
        status = resp.status
        loc = resp.getheader("Location")
        conn.close()
        return status, (loc or body.decode("utf-8", "replace")), url
    except Exception as e:  # noqa: BLE001
        return 0, "%s: %s" % (type(e).__name__, e), url


def resolve_alias_ip():
    try:
        infos = socket.getaddrinfo(MIGU_ALIAS_HOST, None, socket.AF_INET)
        return infos[0][4][0]
    except Exception:
        return None


def probe(url, referer=None):
    """探活单条地址；咪咕走「302 + DNS 别名」两步。"""
    host = urllib.parse.urlparse(url).hostname or ""
    is_migu = "cmvideo.cn" in host

    if is_migu and MIGU_CDN_HOST not in host:
        # 第一步：拿 302 里的签名地址
        status, payload, _ = http_get(url, referer=referer or MIGU_REFERER)
        if status != 302 or not payload.startswith("http"):
            return status, (payload or "")[:120], False
        target = payload
    else:
        target = url

    pin = None
    if MIGU_CDN_HOST in (urllib.parse.urlparse(target).hostname or ""):
        pin = resolve_alias_ip()
        if not pin:
            return 0, "无法解析别名 %s" % MIGU_ALIAS_HOST, False

    status, payload, final = http_get(target, referer=referer, pin_ip=pin)
    # 咪咕签名地址可能再 302 一次，继续跟
    hops = 0
    while status in (301, 302, 303, 307, 308) and payload.startswith("http") and hops < 3:
        target = payload
        hops += 1
        status, payload, final = http_get(target, referer=referer, pin_ip=pin)

    head = payload[:160].replace("\n", " ") if payload else ""
    ok = status == 200 and ("#EXTM3U" in payload or "#EXTINF" in payload or len(payload) > 60)
    return status, head, ok


# ── 列表解析 ────────────────────────────────────────────────────
def parse_playlist(path):
    text = open(path, encoding="utf-8").read()
    channels, group, name, attrs, urls, referer = [], "其它", "", {}, [], None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            payload = line[len("#EXTINF:"):]
            i = payload.rfind(",")
            head, name = (payload[:i], payload[i + 1:].strip()) if i >= 0 else ("", payload.strip())
            attrs = {k.lower(): v for k, v in re.findall(r'([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"', head)}
            if attrs.get("group-title"):
                group = attrs["group-title"]
            urls, referer = [], None
            continue
        if line.startswith("#EXTGRP:"):
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
        channels.append({"group": group, "name": name, "attrs": attrs,
                         "referer": referer, "urls": list(urls)})
    return channels


def check_channel(ch):
    attempts = []
    for u in ch["urls"]:
        status, head, ok = probe(u, ch.get("referer"))
        attempts.append({"url": u, "status": status, "head": head, "ok": ok})
        if ok:
            break
    return {
        "group": ch["group"], "name": ch["name"],
        "tvg_id": ch["attrs"].get("tvg-id", ""),
        "ok": any(a["ok"] for a in attempts),
        "used": next((a["url"] for a in attempts if a["ok"]), ""),
        "attempts": attempts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playlist", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "app", "src", "main", "assets", "playlist.m3u"))
    ap.add_argument("--json", default="")
    ap.add_argument("--csv", default="")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()

    channels = parse_playlist(args.playlist)
    print("共 %d 个频道，开始实测（并发 %d）…" % (len(channels), args.jobs))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(check_channel, channels))

    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    print("\n==== 通过 %d / %d ====" % (len(ok), len(results)))
    by_group = {}
    for r in results:
        g = by_group.setdefault(r["group"], [0, 0])
        g[1] += 1
        if r["ok"]:
            g[0] += 1
    for g, (o, t) in by_group.items():
        print("  %-10s %d/%d" % (g, o, t))
    if bad:
        print("\n---- 未通过 ----")
        for r in bad:
            last = r["attempts"][-1] if r["attempts"] else {}
            print("  [%s] %-28s %s  %s" % (r["group"], r["name"], last.get("status"), (last.get("head") or "")[:60]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print("\nJSON -> %s" % args.json)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["分组", "频道", "tvg-id", "是否可用", "命中地址", "尝试数", "状态码", "响应摘要"])
            for r in results:
                for i, a in enumerate(r["attempts"]):
                    w.writerow([r["group"], r["name"], r["tvg_id"],
                                "是" if a["ok"] else "否",
                                a["url"] if a["ok"] else "",
                                len(r["attempts"]), a["status"], a["head"][:120]])
        print("CSV  -> %s" % args.csv)


if __name__ == "__main__":
    main()
