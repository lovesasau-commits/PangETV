#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地工程可靠地上传到 GitHub（create_or_update_file 逐文件，带 SHA 与体积校验）。

用法:
    python tools/upload_to_github.py --repo PangETV --owner lovesasau-commits
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TMP = os.path.join(ROOT, "_pushfiles")
EXCLUDE_DIRS = {".gradle", "build", ".idea", ".git", "__pycache__", ".cache", "_pushfiles"}
EXCLUDE_NAMES = {".DS_Store"}
SIZE_RE = re.compile(r'"size":(\d+)')
SHA_RE = re.compile(r"\(SHA:\s*([0-9a-f]{40})\)")


def local_files():
    out = []
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for n in names:
            if n in EXCLUDE_NAMES or n.endswith(".apk") or n.startswith("_push"):
                continue
            full = os.path.join(base, n)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            out.append((rel, full))
    return sorted(out)


def find_mcode_tools():
    import glob
    env = os.environ.get("MCODE_TOOLS")
    if env and os.path.exists(env):
        return env
    which = shutil.which("mcode-tools")
    if which:
        return which
    patterns = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "..", "..", "*", "mcode-tools.cmd"),
        r"D:\minimax data\.minimax\bin\hosts\*\mcode-tools.cmd",
    ]
    for pat in patterns:
        hits = glob.glob(pat)
        if hits:
            return hits[0]
    return "mcode-tools"


MCODE = find_mcode_tools()


def run(tool, args):
    os.makedirs(TMP, exist_ok=True)
    argf = os.path.join(TMP, "_call.json")
    with io.open(argf, "w", encoding="utf-8") as f:
        json.dump(args, f, ensure_ascii=False)
    cmdline = '"%s" connector call %s --args-file "%s"' % (MCODE, tool, argf)
    p = subprocess.run(cmdline, shell=True, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def remote_sha(owner, repo, path, branch="main"):
    code, out = run("connector__github__get_file_contents",
                    {"owner": owner, "repo": repo, "path": path, "ref": branch})
    m = SHA_RE.search(out)
    return m.group(1) if m else None


def upload(owner, repo, branch, rel, full):
    with io.open(full, "rb") as f:
        raw = f.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "SKIP", "非 UTF-8 文件"
    want = len(raw)

    last = ""
    for attempt in range(1, 4):
        args = {
            "owner": owner, "repo": repo, "path": rel, "branch": branch,
            "message": "feat: 胖鹅TV v1.0.0 %s" % rel,
            "content": content,
        }
        code, out = run("connector__github__create_or_update_file", args)
        if code != 0:
            last = (out.strip().splitlines() or ["unknown"])[-1][:120]
            # GitHub 对 contents/gist 端点有次级速率限制：静默 70 秒等窗口重置
            print("   .. 触发次级速率限制，等待 70s 后重试 (%s)" % rel, flush=True)
            time.sleep(70)
            sha = remote_sha(owner, repo, rel, branch)
            if sha:
                args["sha"] = sha
                code, out = run("connector__github__create_or_update_file", args)
        m = SIZE_RE.search(out)
        if code == 0 and m:
            got = int(m.group(1))
            if got == want:
                return "OK", "%d bytes" % got
            return "BAD", "体积不符 期望%d 实得%d" % (want, got)
        time.sleep(70)
    return "FAIL", last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="lovesasau-commits")
    ap.add_argument("--repo", default="PangETV")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    files = local_files()
    if args.only:
        files = [f for f in files if args.only in f[0]]
    ok = bad = 0
    for rel, full in files:
        status, detail = upload(args.owner, args.repo, args.branch, rel, full)
        if status == "OK":
            ok += 1
        else:
            bad += 1
        print("%-4s %-58s %s" % (status, rel, detail))
        sys.stdout.flush()
        time.sleep(4)
    print("\n==== 成功 %d 失败 %d ====" % (ok, bad))


if __name__ == "__main__":
    main()
