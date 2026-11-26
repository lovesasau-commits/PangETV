# 胖鹅TV · 免费高清直播（Android / Android TV）

一个可侧载安装到安卓手机与安卓电视盒子的直播客户端。
**顶部一排栏目就是频道分组入口**，内置六个栏目、224 个频道。

| 栏目 | 频道数 | 内容 | 说明 |
|---|---:|---|---|
| **常用** | 54 | 最稳的一批台，跨栏目归集 | 开机默认停在这里 |
| **咪咕体育** | 15 | 咪咕 4K 台 1/2、五星体育、劲爆体育、魅力足球、全民热练、睛彩竞技/篮球、游戏风云 | 走中国移动 CDN，**国内可直连**（应用内置 DNS 别名绕开运营商污染解析） |
| **赛事** | 39 | 咪咕 01–36 号当天轮播赛事台 + CCTV-5 / CCTV-5+ / CCTV-16 | **乒乓球等直播赛事主要在这里** |
| **中国新闻** | 65 | CCTV 1-17、CGTN、CGTN记录、CETV-1/4 + 全国卫视与地方卫视 | 多镜像自动换源 |
| **韩国新闻** | 32 | 精选全国性韩台（KBS / MBC / SBS / EBS / Arirang / TV Chosun / TBS / GCN / RUTC / OUN / BTN / FGTV / NHTV 等） | 境外源，部分受地区限制 |
| **韩国电台** | 19 | 精选韩台电台（Arirang FM、GugakFM、TBN 교통/울산、MBC충북、마포FM、안동MBC AM、befm、CBS Music FM 等） | 纯音频也能正常播放 |

应用本身不内置任何转码服务，也不收集任何数据——它只是把公开直播地址交给系统播放器去拉流。

## 2026-11-26 实测可用率

从国内网络实测，**每个频道至少有一路地址可用**：

| 栏目 | 可用 | 总数 | 比例 |
|---|---:|---:|---:|
| 常用 | 54 | 54 | **100%** |
| 咪咕体育 | 15 | 15 | **100%** |
| 赛事 | 39 | 39 | **100%** |
| 中国新闻 | 65 | 65 | **100%** |
| 韩国新闻 | 32 | 32 | **100%** |
| 韩国电台 | 19 | 19 | **100%** |
| **合计** | **224** | **224** | **100%** |

> 不是「只挑能播的来报喜」：流程是
> **①先塞满候选 → ②全量实测 298 个 → ③把实测全挂的 74 个剔掉 →
> ④把实测出流的那条地址排到首位 → ⑤复测 224 个全通**。
> 逐条记录见 `evidence/stream-check-v6.csv`（298 频道 / 1571 条镜像）
> 与 `evidence/stream-check-v7.csv`（224 频道复测，224/224）。
>
> 韩国台很多只对韩国 IP 开放，**从国内服务器测不通不等于手机上打不开**；
> 本轮已把国内测不通的 66 个韩台/电台整台剔除。

## 功能

- **顶部栏目条 = 唯一的频道分组入口**（遥控器左右键切换，默认进「常用」）
- **跨栏目搜索**（按台名 / 栏目 / tvg-id 搜）
- **主源失败自动换源**：同一频道配多路镜像（最多 16 路），逐个试，失败自动切下一个；
  且**实测出流的那一路已排在第一位**
- **节目单（EPG）**：拉取 iptv-org 的韩国 XMLTV 源，频道列表直接显示「正在播出」
- **自定义播放列表**：菜单 →「源设置」，可粘贴任意 M3U 地址替换内置列表；拉取失败自动回落内置
- **电视遥控器友好**：支持 LEANBACK 启动器，D-pad 上下左右 + OK 键操作
- **咪咕 DNS 别名 + Referer 补齐**：见下文「咪咕为什么能播」

## 咪咕为什么能播

咪咕的直播 CDN 域名 `cache.ott.fifalive.itv.cmvideo.cn` 在部分国内网络被污染成
`1.1.1.1` 之类的假地址，直连必然 403。

应用的做法（`player/MiguDns.kt` + `player/PlayerFactory.kt`）：

1. 播放时先请求 `gslbserv.itv.cmvideo.cn/index.m3u8?...&stbId=...`，拿到 302 里的带签名地址；
2. HTTP 层用 **OkHttp**（不是 Media3 自带的 `DefaultHttpDataSource`），
   并挂一个自定义 `okhttp3.Dns`：把 `cache.ott.*.itv.cmvideo.cn`
   解析到 `base-v4v6-cm-miguvideo.e.cdn.chinamobile.com` 的真实 IP；
3. **只换解析结果，Host 头 / SNI 保持原域名**，所以签名依然有效；
4. 咪咕域名**自动补 `Referer: https://www.miguvideo.com/`**——缺这个头 CDN 一律 403。

> 为什么要 OkHttp：Media3 1.4.1 的 DataSource 层已经没有 `Dns` 抽象了
> （那是 ExoPlayer2 时代的 API），只有 OkHttp 这条路还能在「不改 Host」的前提下换 IP。

实测（App 同款 HTTP 栈，`tools/migu_probe/`）：302 → 200，拿到 **1500 kbps** 的 HLS 高清流。

> 咪咕 CDN 上的**央视/卫视版权流拿不到**（扫遍 `39.135.122.0/24` 全部 403），
> 所以央视/卫视改走 fanmingming + CCSH 的直连地址；
> 咪咕只保留自有内容（`Contentid` 以 3 开头）并修正 `stbId`。

## 构建

需要 JDK 17 与 Android SDK（compileSdk 34）。有 Gradle 8.9+ 即可：

```bash
gradle :app:assembleRelease
# 产物: app/build/outputs/apk/release/app-release.apk
```

仓库自带 GitHub Actions（`.github/workflows/build-apk.yml`）：
**每次推送到 `main` 自动编译并发布 Release**，也可以在 Actions 页面手动触发。

> 用 debug keystore 签名，保证侧载装得上。正式上架请换成自己的签名。

## 安装

```bash
adb install -r PangETV-v1.1.0.apk
```

或者把 APK 传到电视盒子/手机，用文件管理器点击安装（需允许「未知来源」）。

## 目录结构

```
app/src/main/
  assets/playlist.m3u          内置播放列表（带分组与多镜像）
  java/com/sasau/pangetv/
    MainActivity.kt            栏目条 / 跨栏目搜索 / 源设置
    PlayerActivity.kt          播放与自动换源
    model/Channel.kt
    playlist/M3uParser.kt      M3U 解析（支持多镜像 / EXTGRP / referer）
    playlist/PlaylistRepository.kt  远程列表 + 缓存 + 内置回落
    playlist/EpgRepository.kt   XMLTV 节目单
    player/MiguDns.kt          咪咕 DNS 别名（实现 okhttp3.Dns）
    player/PlayerFactory.kt    播放器工厂（UA / Referer / OkHttp）
tools/
  build_playlist.py            合成内置播放列表（台名归一化 / 栏目划分 / 白名单 / 镜像前置）
  check_streams.py             逐条实测播放列表，产出 JSON/CSV 证据
  refresh_kr_mirrors.py        探测韩台候选地址，只保留实测可用的
  spot_check.py                每组抽几条快速复测
  kr_mirrors.json              上一次实测结果（build_playlist.py 读取）
  migu_probe/                  App 同款 HTTP 栈探针 + 咪咕 CDN 变量矩阵
evidence/
  stream-check-v6.csv          298 频道全量实测（剔除前的候选）
  stream-check-v7.csv          224 频道复测（224/224 通过）
```

## 播放列表维护

```bash
# 1. 重新合成内置列表（联网拉上游）
python tools/build_playlist.py

# 2. 刷新韩台镜像（逐条实测，只保留活的）
python tools/refresh_kr_mirrors.py

# 3. 全量实测并留证
python tools/check_streams.py \
    --playlist app/src/main/assets/playlist.m3u \
    --json evidence.json --csv evidence.csv

# 4. 按实测结果剔除死台 + 把可用镜像排到首位，再复测
python tools/build_playlist.py \
    --prune-from evidence.json --rank-from evidence.json --selftest
python tools/check_streams.py \
    --playlist app/src/main/assets/playlist.m3u \
    --json evidence2.json --csv evidence2.csv

# 5. 快速抽查
python tools/spot_check.py --per-group 4
```

`check_streams.py` 复刻了应用内完全相同的「302 取签名 + DNS 别名 + Referer」逻辑，
所以它的通过率就是应用内的预期通过率。

`build_playlist.py --selftest` 会跑内置断言：
栏目顺序 / 台名唯一 / 每台至少一条地址 / 咪咕地址带 stbId。

## 声明

- 全部为公开可访问的免费直播地址，本项目不提供、不存储、不转发任何付费频道
  （合成时会主动过滤上游标着「💰付费」的分组）。
- 源站归属各 broadcasters 与运营商，本项目与任何一方无隶属关系。
- 公共 IPTV 源变动频繁，**请以实测结果为准**，必要时在「源设置」里换成你自己的列表。
