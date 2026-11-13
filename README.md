# 抖音转OB（初学者适用）— 抖音视频 → Obsidian 知识库

> 一个简单的人工提供抖音链接（可通过抖音PC客户端获得），由本插件自动将视频内容转化文字记录，并自动导入到Obsidian中，适用于harness、个人知识库搭建初学者上手。也是本人使用harness完全借助deepseek创建的第一个插件，具备实验性质：-）

把抖音视频（单条分享链接或博主主页批量）下载下来，离线转写成带时间戳的中文文字稿，写成 Markdown 笔记放进本机 Obsidian Vault。

安装后左侧栏会多出一个「抖音转OB」图标：里面只有三个部分——粘贴抖音链接的录入框、**开始抓取**按钮、以及注意事项，不熟悉命令行的使用者也能直接用。

- **抓取**：Playwright 驱动本机 Edge 的持久化配置目录，先拿 `ttwid` 等 Cookie，再打开视频页，在页面自身的 `response` 回调里截获 `/aweme/v1/web/aweme/detail/` 的 `aweme_detail`（yt-dlp 对抖音已失效，见“背景”）。
- **转写**：sherpa-onnx + SenseVoice（中英日韩粤，int8 模型约 228 MiB）+ silero VAD 切段，纯本地、离线、无 API key。
- **落库**：YAML frontmatter + 视频文案 + `- \`mm:ss\` 句子` 形式的转写 + 要点区，封面存 `抖音收藏/_附件/`，去重索引 `抖音收藏/.index.json`。

## 安装

```sh
# 1. 从 GitHub 仓库（推荐）
dsh plugin add github:KunWu1980/dsh-douyin-kb

# 2. 从本地目录（开发时用，link 安装）
dsh plugin add C:\path\to\douyin-kb-plugin
```

桌面版也可以在 **设置 → 插件** 里用“安装插件”填上面同样的 spec；或让 Agent 调用 `plugin_manager install_bundle`。

> 更新已安装的 bundle 后需要重启应用，宿主才会加载新的 JS 模块代际；`application: applied` 只代表 profile 已写入。

## 运行时前置

插件本身零 npm 依赖，但它调用的 Python 脚本需要：

| 依赖 | 用途 | 安装 |
| --- | --- | --- |
| Node.js ≥ 20（含 npm） | 宿主运行插件 | 已随 DSH 提供 |
| Python 3.10+ | 执行 `assets/douyin_kb.py` | 系统 Python 或 DSH 自带运行时 |
| `playwright` | 驱动 Edge 抓取抖音页面 | `python -m pip install playwright`（用 `channel="msedge"`，无需下载 Chromium） |
| `av` (PyAV) | 无 ffmpeg 时解码音轨 | `python -m pip install av` |
| `sherpa-onnx` | 离线语音转写 + VAD | `python -m pip install sherpa-onnx` |
| `numpy` | 音频重采样 | pip |
| SenseVoice 模型 | 中文转写 | `model.int8.onnx` + `tokens.txt` 放到 `%USERPROFILE%\.dsh\douyin-kb\models\` |
| silero VAD | 语音切段 | `silero_vad.onnx` 同目录（缺失会退化为 25s 定长切块） |

模型下载（国内镜像）：

```powershell
# SenseVoice（约 228 MiB）
curl.exe -L -o "$env:USERPROFILE\.dsh\douyin-kb\models\model.int8.onnx" `
  https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/model.int8.onnx
curl.exe -L -o "$env:USERPROFILE\.dsh\douyin-kb\models\tokens.txt" `
  https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main/tokens.txt
# silero VAD（约 2.2 MiB）
curl.exe -L -o "$env:USERPROFILE\.dsh\douyin-kb\models\silero_vad.onnx" `
  https://hf-mirror.com/onnx-community/silero-vad/resolve/main/onnx/model.onnx
```

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `vault` | 自动识别（Obsidian 当前打开的库） | 也支持环境变量 `OBSIDIAN_VAULT` 或本地 `config.json` 覆盖 |
| `kbHome` | `%USERPROFILE%\.dsh\douyin-kb` | 模型、浏览器配置、下载缓存；也可用 `DOUYIN_KB_HOME` |
| `python` | 自动探测 | 指定 Python 可执行文件；也可用 `DOUYIN_KB_PYTHON` |
| `timeoutSeconds` | `900` | 单次工具调用超时 |

本机专属设置**不需要手动填写**：插件会读 Obsidian 自己的 `obsidian.json`，用“当前打开的那个库”作为 `vault`。只有在你想覆盖时才需要额外指定——写在插件目录之外的 `%USERPROFILE%\.dsh\douyin-kb\config.json`（该文件不在仓库里，也不会随插件发布）：

```json
{ "vault": "D:\\path\\to\\Obsidian Vault" }
```

读取优先级：插件配置 `vault` → 环境变量 `OBSIDIAN_VAULT` → `config.json` 的 `vault` → Obsidian 当前打开的库 → 默认 `%USERPROFILE%\Documents\Obsidian Vault`。

## 左侧栏面板（初学者推荐）

安装并重启 DeepSeek Harness 后，左侧栏出现「抖音转OB」图标：

1. 把抖音分享链接（或整段分享文案）粘进录入框；
2. 点 **开始抓取**，面板显示进度，抓完会给出笔记路径；
3. 首次使用会弹出浏览器窗口要求扫码登录抖音，用手机抖音扫一次即可，之后无需重复。

面板下方固定展示三条注意事项：首次扫码登录、离线语音模型偶有错字需人工校对、使用前需自行安装 Node.js / Git / Python。

## 斜杠命令

```text
/douyin https://v.douyin.com/xxxxxx/
```

与面板按钮等价（同样走 `force=true` 覆盖写），适合在会话里直接触发。

## 工具用法

Agent 侧工具名 `douyin_kb`：

```jsonc
{ "action": "ingest", "target": "7.66 12/31 ... https://v.douyin.com/xxxx/", "force": false }
{ "action": "batch",  "target": "https://www.douyin.com/user/MS4wLjABAAAA...", "limit": 5 }
{ "action": "probe",  "target": "https://www.douyin.com/video/7703889641270775066" }
{ "action": "login" }
```

命令行等价物（排错时用）：

```powershell
python assets/douyin_kb.py ingest "https://v.douyin.com/xxxx/" --vault "D:\path\to\Obsidian Vault"
python assets/douyin_kb.py probe 7703889641270775066
```

## 常见问题

- **`Fresh cookies (not necessarily logged in) are needed` / HTTP 403**：抖音风控。本插件走浏览器截获，不使用 yt-dlp；若页面出现 `data-e2e="error-page"`，先 `action=login` 扫码，或删掉 `%USERPROFILE%\.dsh\douyin-kb\browser-profile` 重来。无头模式会被判定为机器人，默认有头。
- **`aweme_detail: null` + `filter_reason: "core_dep"`**：视频区域/内容受限，换片源。
- **转写为空**：视频无语音、音量过低，或 VAD 误切；可先 `action=probe` 确认时长。
- **中文乱码**：PowerShell 里跑命令行版时先 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`。

## 目录

```
douyin-kb-plugin/
├─ index.js              # 宿主侧：注册 douyin_kb 工具与 /douyin 命令，spawn Python
├─ client.js             # 客户端：左侧栏图标 + 主面板（录入框 / 开始抓取 / 注意事项）
├─ package.json          # dsh.bundle.patch + dsh.client 清单
├─ cordis.patch.yml      # 插入插件行
├─ locale/{en,zh}.json   # 插件名与描述
├─ icon.svg
└─ assets/douyin_kb.py   # 抓取 + 下载 + 转写 + 写笔记
```

## 更新日志

- **1.2.0**（2026-11-13）— 全面梳理精简代码：宿主侧配置读取统一可选链、超时设置收敛到一处；客户端侧新增 `unwrap()` 统一解析 `remote.commands.execute` 返回值；Python 侧移除未使用的返回值与死代码、修复重复导入、收敛 argparse 公共参数。README 精简为功能介绍并新增本更新日志。
- **1.1.3**（2026-11-12）— 修复面板「开始抓取」误报「没有找到 /douyin 命令」：`remote.commands.execute` 的返回值此前少剥一层嵌套；`/douyin` 命令改为模块级注入注册。
- **1.1.1 – 1.1.2** — 调试中间版本，未单独发布。
- **1.1.0**（2026-11-10）— 初版发布。知识库路径自动识别 Obsidian 当前打开的库；README 与自动识别行为对齐。

## 背景：为什么不用 yt-dlp

yt-dlp 的抖音提取器要求站点 Cookie 里有 `s_v_web_id`，且 `/aweme/v1/web/aweme/detail/` 可直接请求；实测伪造 Cookie 无效、裸请求 403、`iesdouyin` 分享页已不含 `videoInfoRes`。唯一稳定通道是让真实浏览器自己发请求，再从响应里取数据。

## License

MIT
