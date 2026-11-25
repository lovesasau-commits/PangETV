# 胖鹅TV · 免费高清直播（Android / Android TV）

一个可侧载安装到安卓手机与安卓电视盒子的直播客户端，内置四组公开免费直播源：

| 分组 | 内容 | 说明 |
|---|---|---|
| **咪咕体育** | 咪咕直播 1–36、咪咕 4K-1 / 4K-2、睛彩系列 | 走中国移动 CDN，**国内可直连**（应用内置 DNS 别名绕开运营商污染解析） |
| **央视新闻 / 卫视高清** | 央视各频道 + 主要卫视 | 源站会失效，内置多镜像自动换源 |
| **韩国新闻** | KBS1/KBS2/KBS World、MBC、SBS、YTN、JTBC、Channel A、TV Chosun、EBS、Arirang TV、SPOTV 等 | 境外源，部分受地区限制 |
| **韩国电台** | KBS/MBC/SBS/CBS/EBS/TBS/TBN 国台民台 FM 直播 | 纯音频也能正常播放 |

应用本身不内置任何转码服务，也不收集任何数据——它只是把公开直播地址交给系统播放器去拉流。

## 功能

- **分组浏览 + 搜索**（按台名 / 分组 / tvg-id 搜）
- **主源失败自动换源**：同一频道配多路镜像，逐个试，失败自动切下一个
- **节目单（EPG）**：拉取 iptv-org 的韩国 XMLTV 源，频道列表直接显示「正在播出」
- **自定义播放列表**：菜单 →「源设置」，可粘贴任意 M3U 地址替换内置列表；拉取失败自动回落内置
- **电视遥控器友好**：支持 LEANBACK 启动器，D-pad 上下左右 + OK 键操作
- **米咕 DNS 别名**：见下文「咪咕为什么能播」

## 咪咕为什么能播

咪咕的直播 CDN 域名 `cache.ott.fifalive.itv.cmvideo.cn` 在部分国内网络被污染成
`1.1.1.1` 之类的假地址，直连必然 403。

应用的做法（`player/MiguDns.kt`）：

1. 播放时先请求 `gslbserv.itv.cmvideo.cn/index.m3u8?...`，拿到 302 里的带签名地址；
2. 自定义 `Dns` 把 `cache.ott.fifalive.itv.cmvideo.cn` 解析到
   `base-v4v6-cm-miguvideo.e.cdn.chinamobile.com` 的真实 IP；
3. **只换解析结果，Host 头 / SNI 保持原域名**，所以签名依然有效。

实测：302 → 200，拿到 1500 kbps 的 HLS 高清流。

## 构建

需要 JDK 17 与 Android SDK（compileSdk 34）。有 Gradle 8.9+ 即可：

```bash
gradle :app:assembleRelease
# 产物: app/build/outputs/apk/release/app-release.apk
```

或者直接用仓库自带的 GitHub Actions（推 tag 即出包）：

```bash
git tag v1.0.0 && git push origin v1.0.0
```

## 安装

```bash
adb install -r PangETV-v1.0.0.apk
```

或者把 APK 传到电视盒子/手机，用文件管理器点击安装（需允许「未知来源」）。

## 目录结构

```
app/src/main/
  assets/playlist.m3u          内置播放列表（带分组与多镜像）
  java/com/sasau/pangetv/
    MainActivity.kt            分组 / 搜索 / 源设置
    PlayerActivity.kt          播放与自动换源
    model/Channel.kt
    playlist/M3uParser.kt      M3U 解析（支持多镜像 / EXTGRP / referer）
    playlist/PlaylistRepository.kt  远程列表 + 缓存 + 内置回落
    playlist/EpgRepository.kt   XMLTV 节目单
    player/MiguDns.kt          咪咕 DNS 别名
    player/PlayerFactory.kt    ExoPlayer 工厂（UA / Referer / DNS）
tools/
  build_playlist.py            合成内置播放列表（多上游合并 + 镜像归并）
  check_streams.py             逐条实测播放列表，产出 JSON/CSV 证据
```

## 播放列表维护

```bash
# 重新合成内置列表（联网拉上游）
python tools/build_playlist.py

# 实测所有频道并留证
python tools/check_streams.py \
    --playlist app/src/main/assets/playlist.m3u \
    --json evidence.json --csv evidence.csv
```

`check_streams.py` 复刻了应用内完全相同的「302 取签名 + DNS 别名」逻辑，
所以它的通过率就是应用内的预期通过率。

## 声明

- 全部为公开可访问的免费直播地址，本项目不提供、不存储、不转发任何付费频道。
- 源站归属各 broadcasters 与运营商，本项目与任何一方无隶属关系。
- 公共 IPTV 源变动频繁，**请以实测结果为准**，必要时在「源设置」里换成你自己的列表。
