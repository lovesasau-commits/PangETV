#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地 PangETV 工程打包成 push_files 工具需要的 JSON 参数（支持分片）。"""
import json
import math
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EXCLUDE_DIRS = {".gradle", "build", ".idea", ".git", "__pycache__", ".cache"}
EXCLUDE_NAMES = {".DS_Store"}


def collect():
    files = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            if n in EXCLUDE_NAMES or n.endswith(".apk") or n == "_push_args.json":
                continue
            full = os.path.join(base, n)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            try:
                with open(full, "rb") as f:
                    raw = f.read()
                content = raw.decode("utf-8")
            except Exception as e:  # noqa: BLE001
                print("skip %s: %s" % (rel, e), file=sys.stderr)
                continue
            files.append({"path": rel, "content": content})
    return files


def main():
    out = sys.argv[1]
    chunk = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    chunks = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    files = collect()
    # 大文件单独成片，避免单次请求过大
    files.sort(key=lambda f: (len(f["content"]) > 20000, f["path"]))
    per = max(1, math.ceil(len(files) / chunks))
    part = files[(chunk - 1) * per: chunk * per]
    args = {
        "owner": "lovesasau-commits",
        "repo": "PangETV",
        "branch": "main",
        "message": "feat: 胖鹅TV v1.0.0 — 米咕体育 / 央视卫视 / 韩国新闻 / 韩国电台 (%d/%d)" % (chunk, chunks),
        "files": part,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(args, f, ensure_ascii=False)
    print("chunk %d/%d: files=%d bytes=%d -> %s" % (
        chunk, chunks, len(part), sum(len(x["content"]) for x in part), os.path.abspath(out)))


if __name__ == "__main__":
    main()
