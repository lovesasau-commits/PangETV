#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MiguProbe 的编译与运行脚本（Windows / JDK 17）。

用法:
    python tools/migu_probe/run.py "<m3u8地址>" [referer]

会从 Gradle 缓存里找 okhttp / okio / kotlin-stdlib，缺哪个就提示先编译一次
（`python _tools/build_local.py` 会把这些依赖拉下来）。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 工作区根目录（工具链 _toolchain 在 PangETV 之外）
REPO = os.path.join(HERE, "..", "..", "..")

GRADLE_CACHE = os.path.join(os.path.expanduser("~"), ".gradle", "caches",
                             "modules-2", "files-2.1")
JARS = [
    ("com.squareup.okhttp3", "okhttp", "4.12.0"),
    ("com.squareup.okio", "okio-jvm", "3.6.0"),
    ("org.jetbrains.kotlin", "kotlin-stdlib", "1.9.24"),
]
TOOLCHAIN_JDK = os.path.join(REPO, "_toolchain", "jdk")


def find_jar(group, name, version):
    base = os.path.join(GRADLE_CACHE, group, name, version)
    if not os.path.isdir(base):
        return None
    for dirpath, _, filenames in os.walk(base):
        for f in filenames:
            if f.endswith(".jar") and not f.endswith("-sources.jar"):
                return os.path.join(dirpath, f)
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    url = sys.argv[1]
    referer = sys.argv[2] if len(sys.argv) > 2 else "https://www.miguvideo.com/"

    jars = []
    for group, name, version in JARS:
        p = find_jar(group, name, version)
        if not p:
            print("找不到 %s:%s:%s —— 先跑一次 `python _tools/build_local.py` 让 Gradle 拉依赖" %
                  (group, name, version))
            return 3
        jars.append(p)
    cp = ";".join(jars)

    javac = os.path.join(TOOLCHAIN_JDK, "bin", "javac.exe")
    java = os.path.join(TOOLCHAIN_JDK, "bin", "java.exe")
    if not os.path.exists(javac):
        print("找不到便携 JDK：%s" % TOOLCHAIN_JDK)
        return 3

    r = subprocess.run([javac, "-encoding", "UTF-8", "-cp", cp, "-d", HERE,
                        os.path.join(HERE, "MiguProbe.java")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        return 1

    r = subprocess.run([java, "-Dstdout.encoding=UTF-8", "-cp", HERE + ";" + cp,
                        "MiguProbe", url, referer],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout)
    if r.stderr:
        print(r.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
