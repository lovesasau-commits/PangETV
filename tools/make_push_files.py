#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地 PangETV 工程拆成 create_or_update_file 需要的逐文件参数。"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_pushfiles")
EXCLUDE_DIRS = {".gradle", "build", ".idea", ".git", "__pycache__", ".cache", "_pushfiles"}
EXCLUDE_NAMES = {".DS_Store"}

# 已存在的文件需要带 blob SHA
KNOWN_SHA = {
    ".gitignore": "59fe915280e0589ca598f8f94937f05dd092e13a",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    files = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            if n in EXCLUDE_NAMES or n.endswith(".apk") or n.startswith("_push"):
                continue
            full = os.path.join(base, n)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            try:
                content = open(full, "rb").read().decode("utf-8")
            except Exception as e:  # noqa: BLE001
                print("skip %s: %s" % (rel, e), file=sys.stderr)
                continue
            files.append((rel, content))

    files.sort()
    for i, (rel, content) in enumerate(files, 1):
        args = {
            "owner": "lovesasau-commits",
            "repo": "PangETV",
            "path": rel,
            "branch": "main",
            "message": "feat: 胖鹅TV v1.0.0 (%d/%d) %s" % (i, len(files), rel),
            "content": content,
        }
        if rel in KNOWN_SHA:
            args["sha"] = KNOWN_SHA[rel]
        with open(os.path.join(OUT, "%02d.json" % i), "w", encoding="utf-8") as f:
            json.dump(args, f, ensure_ascii=False)
    print("generated %d args files in %s" % (len(files), os.path.abspath(OUT)))


if __name__ == "__main__":
    main()
