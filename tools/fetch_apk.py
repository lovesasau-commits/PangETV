#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 GitHub Release 拉回胖鹅TV APK，并做完整性校验。

用法:
    python tools/fetch_apk.py --out-dir <目录>
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

OWNER = "lovesasau-commits"
REPO = "PangETV"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"


def mcode():
    import glob
    import shutil
    env = os.environ.get("MCODE_TOOLS")
    if env and os.path.exists(env):
        return env
    w = shutil.which("mcode-tools")
    if w:
        return w
    hits = glob.glob(r"D:\minimax data\.minimax\bin\hosts\*\mcode-tools.cmd")
    return hits[0] if hits else "mcode-tools"


def list_releases():
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_pushfiles", "_rel.json")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"owner": OWNER, "repo": REPO}, f)
    cmdline = '"%s" connector call connector__github__list_releases --args-file "%s"' % (mcode(), tmp)
    p = subprocess.run(cmdline, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def candidate_urls():
    urls = []
    raw = list_releases()
    print("--- list_releases 原始输出（截断） ---")
    print(raw.strip()[:1500])
    import re
    for tag in re.findall(r'"tag_name"\s*:\s*"([^"]+)"', raw):
        for name in ("PangETV-%s.apk" % tag, "app-release.apk"):
            urls.append("https://github.com/%s/%s/releases/download/%s/%s" % (OWNER, REPO, tag, name))
    for i in range(1, 15):
        tag = "v%d" % i
        urls.append("https://github.com/%s/%s/releases/download/%s/PangETV-%s.apk" % (OWNER, REPO, tag, tag))
        urls.append("https://github.com/%s/%s/releases/download/%s/app-release.apk" % (OWNER, REPO, tag))
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def verify(path):
    """校验 APK 是否像一个真的 Android 安装包。"""
    if not zipfile.is_zipfile(path):
        return False, "不是合法 zip"
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    required = ["AndroidManifest.xml", "classes.dex", "resources.arsc"]
    missing = [r for r in required if r not in names]
    if missing:
        return False, "缺少 %s" % ", ".join(missing)
    return True, "包含 %d 个条目" % len(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "胖鹅TV", "dist"))
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    urls = candidate_urls()
    print("\n尝试 %d 个候选下载地址…" % len(urls))
    got = None
    for u in urls:
        try:
            size = download(u, os.path.join(out_dir, "PangETV.apk"))
        except Exception as e:  # noqa: BLE001
            print("  失败 %s :: %s" % (u.rsplit("/", 1)[-1], type(e).__name__))
            continue
        print("  命中 %s  (%d bytes)" % (u, size))
        got = (u, os.path.join(out_dir, "PangETV.apk"))
        break

    if not got:
        print("\n没有找到可下载的 APK。")
        return 1

    url, path = got
    ok, detail = verify(path)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    size = os.path.getsize(path)
    print("\n==== 校验结果 ====")
    print("下载地址 : %s" % url)
    print("本地路径 : %s" % path)
    print("文件大小 : %d bytes (%.2f MB)" % (size, size / 1024.0 / 1024.0))
    print("SHA256   : %s" % sha)
    print("APK 结构 : %s (%s)" % ("通过" if ok else "不通过", detail))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
