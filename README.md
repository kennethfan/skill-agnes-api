# AGNES API — Agent Skill

<p align="right">
  <a href="README.en.md">🇬🇧 English</a>
</p>

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> 通过 [AGNES API](https://apihub.agnes-ai.com)（Sapiens AI）生成图片和视频的 OpenCode Agent Skill。
> 设计为被 AI agent 调用，用于文生图、图生图、视频生成、漫画创作、诗词朗诵视频、故事动画视频等场景。

---

## 功能特性

- **图片生成** — 文生图 (T2I)、图生图 (I2I)、多图合成
- **图片精修** — 基于 I2I 的画质增强、风格迁移、局部修改，支持预设风格
- **漫画创作** — 从 YAML 脚本逐格生成漫画，支持对话框叠加、多布局拼页
- **诗词朗诵视频** — 诗词 → AGNES 场景图 + edge-tts 朗诵音频 + ffmpeg 合成，水墨国风竖屏
- **故事动画视频** — 面向 3-6 岁儿童的多角色配音故事动画，角色外观一致性保持，支持 checkpoint 断点续传
- **视频生成** — 文生视频 (T2V)、图生视频 (I2V)、关键帧动画，异步轮询
- **纯 Python 标准库** — 仅依赖 `urllib`，无 `requests` 库

---

## 前置条件

1. **API Key** — 从 [AGNES API](https://agnes-ai.com) 获取
2. **Python 3.10+**
3. 可选依赖（按需安装）：

```bash
pip install edge-tts          # 诗词/故事视频（TTS 配音）
pip install Pillow            # 漫画对话框 / 标题卡
pip install PyYAML            # YAML 脚本解析
# ffmpeg（完整版，需支持 drawtext + libfontconfig）— 视频合成
```

### API Key 配置

```bash
# 方式一：配置文件
echo "your-api-key" > ~/.config/agnes/key

# 方式二：环境变量
export AGNES_API_KEY="your-api-key"

# 验证
python3 scripts/check_key.py
```

### 路径配置

所有输出路径、工具路径由 `~/.config/agnes/paths.yaml` 统一管理。可配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `base_dir` | 媒体根目录 | `~/agent/media` |
| `default_dir` | 无项目兜底目录 | `tmp` |
| `projects_dir` | 项目根目录 | `projects` |
| `assets_dir` | 共享素材目录 | `assets` |
| `ffmpeg_bin` | ffmpeg 路径 | `ffmpeg`（走 PATH） |
| `ffprobe_bin` | ffprobe 路径 | `ffprobe`（走 PATH） |
| `font_paths` | 中文字体路径列表（按序查找） | `[]`（自动回退） |
| `cleanup.prompt` | 是否询问清理中间文件 | `true` |
| `cleanup.default_yes` | 清理默认回答 | `true` |

示例配置：

```yaml
# ~/.config/agnes/paths.yaml
base_dir: ~/agent/media
ffmpeg_bin: /opt/homebrew/bin/ffmpeg
font_paths:
  - /System/Library/Fonts/PingFang.ttc
  - /System/Library/Fonts/STHeiti Light.ttc
cleanup:
  prompt: true
  default_yes: true
```

不创建此文件时自动使用默认值，所有代码通过 `utils.py` 读取该配置，无需逐脚本修改。

---

## 目录结构

```
├── README.md                 # 本文档
├── README.en.md              # English version
├── AGENTS.md                 # Agent 知识库
├── SKILL.md                  # Skill 定义（agent 入口）
├── CONTEXT.md                # 领域术语表
├── docs/adr/                 # 架构决策记录
│   ├── 0001-image-refine-tool.md
│   ├── 0002-story-video-architecture.md
│   └── 0003-file-organization.md
├── scripts/                  # 所有代码（扁平结构，无包）
│   ├── utils.py              # 共享工具：API key、HTTP 辅助、输出目录
│   ├── t2i.py                # 文生图（示例脚本，运行于 import）
│   ├── i2i.py                # 图生图（示例脚本，运行于 import）
│   ├── compose.py            # 多图合成（示例脚本）
│   ├── refine.py             # 核心 — 图片精修
│   ├── refine-cli.py         # CLI 封装
│   ├── comic.py              # 核心 — 漫画生成
│   ├── comic-cli.py          # CLI 封装
│   ├── comic-page-layout.py  # 漫画拼页 + 对话框（独立工具）
│   ├── poem_video.py         # 核心 — 诗词朗诵视频
│   ├── poem-video-cli.py     # CLI 封装
│   ├── story_video.py        # 核心 — 故事视频（扩展 poem_video）
│   ├── story-video-cli.py    # CLI 封装
│   ├── t2i_base64.py         # 文生图 — Base64 输出（示例脚本）
│   ├── t2v.py                # 文生视频（示例脚本）
│   ├── i2v.py                # 图生视频（示例脚本）
│   ├── keyframes.py          # 关键帧动画（示例脚本）
│   ├── poll_video.py         # 轮询视频结果
│   └── query_video.py        # 查询任务状态
├── LICENSE                   # Apache 2.0
└── .gitignore
```

---

## 输出目录

输出路径由 `~/.config/agnes/paths.yaml` 统一管理（详见下方路径配置）。脚本通过 `utils.py` 读取，不再硬编码。

### 默认目录（无项目）

零散生成的图片/视频存放在兜底目录：

| 类型 | 路径 |
|------|------|
| 默认 | `~/agent/media/tmp/` |

文件名格式：`agnes-<类型>-<时间戳>.<扩展名>`

### 项目隔离目录（推荐）

使用 `--project` / `project=` 参数时，文件按角色分层存放：

```
~/agent/media/
├── assets/                          ← 跨项目共享输入素材
└── projects/
    └── <project-name>/
        ├── <project-name>.yaml      ← 剧本
        ├── scenes/                  ← Intermediate: t2i 场景原图
        ├── panels/                  ← Intermediate: 漫画逐格
        ├── bubbles/                 ← Intermediate: 气泡图层
        ├── frames/                  ← Intermediate: 视频帧
        ├── audio/                   ← Intermediate: TTS 音频段
        └── deliverable/
            ├── comic-pages/         ← Deliverable: 拼页 PNG
            └── videos/              ← Deliverable: 最终 MP4
```

| 角色 | 生命周期 | 说明 |
|------|---------|------|
| **Asset** | 保留 | 不可再生的输入素材（角色参考图、背景图） |
| **Intermediate** | 可删除 | Pipeline 临时产物，完成后询问用户是否清理 |
| **Deliverable** | 保留 | 最终交付物（拼页 PNG、视频 MP4） |

Pipeline 完成时会主动询问「是否删除中间文件？」（默认 yes），一键清理。也可通过 `utils.cleanup_intermediates()` 手动调用。

---

## 快速开始

### 验证 API Key

```bash
python3 scripts/check_key.py
```

### 图片生成

```bash
# 文生图
python3 scripts/t2i.py

# 图片精修
python3 scripts/refine-cli.py --input photo.jpg --operation "去噪并调亮"

# 使用预设风格精修
python3 scripts/refine-cli.py --input photo.jpg --preset ghibli
```

### 漫画创作

```bash
# 查看可用风格
python3 scripts/comic-cli.py --list-presets

# 从 YAML 脚本生成漫画
python3 scripts/comic-cli.py --script my-comic.yaml --preset manga
```

### 诗词朗诵视频

```bash
# 从 YAML 脚本生成
python3 scripts/poem-video-cli.py --script my-poem.yaml

# 指定童声
python3 scripts/poem-video-cli.py --script my-poem.yaml --voice zh-CN-YunxiaNeural
```

### 故事动画视频

```bash
# 从 YAML 脚本生成（推荐）
python3 scripts/story-video-cli.py --script my-story.yaml

# 指定视觉风格
python3 scripts/story-video-cli.py --script my-story.yaml --style ink-wash

# 指定输出路径
python3 scripts/story-video-cli.py --script my-story.yaml -o my-story.mp4

# 使用项目目录隔离中间文件（支持 checkpoint 断点续传）
python3 scripts/story-video-cli.py --script my-story.yaml --project 三只小猪
```

> ⚠️ `--title` 搜索模式和 `--textfile` 文本直出模式暂未实现，当前仅支持 `--script` 模式。需在外部准备 YAML 脚本后传入。

### 视频生成（异步）

```bash
# 文生视频
python3 scripts/t2v.py

# 轮询结果
python3 scripts/poll_video.py <task_id>
```

---

## API 基础

| 项目 | 值 |
|------|-----|
| Base URL | `https://apihub.agnes-ai.com` |
| 图片模型 | `agnes-image-2.1-flash` |
| 视频模型 | `agnes-video-v2.0` |
| Auth | `Authorization: Bearer <API_KEY>` |

### 图片参数

| ratio | 1K | 2K | 3K | 4K |
|-------|-----|-----|-----|-----|
| `1:1` | 1024×1024 | 2048×2048 | 3072×3072 | 4096×4096 |
| `16:9` | 1312×736 | 2624×1472 | 3936×2208 | 5248×2944 |
| `9:16` | 736×1312 | 1472×2624 | 2208×3936 | 2944×5248 |
| `3:4` | 864×1152 | 1728×2304 | 2592×3456 | 3456×4608 |
| `4:3` | 1152×864 | 2304×1728 | 3456×2592 | 4608×3456 |

也支持传统精确尺寸如 `1024x768`。

### 视频参数

| 参数 | 说明 |
|------|------|
| `num_frames` | 总帧数，≤ 441，必须满足 `8n + 1` |
| `frame_rate` | 帧率，1-60 |
| `height` / `width` | 会被归一化到 480p/720p/1080p 档位 |
| `seed` | 固定随机种子，可复现结果 |
| `negative_prompt` | 负面提示词 |
| 时长参考 | ~3s (81帧/24fps) / ~5s (121帧/24fps) / ~10s (241帧/24fps) / ~18s (441帧/24fps) |

---

## 高级用法

### 作为 Python 模块调用

```python
# 图片精修
from scripts.refine import refine
path = refine("photo.jpg", "变成宫崎骏风格")

# 漫画生成
from scripts.comic import create_comic
path = create_comic("my-comic.yaml", preset="manga")

# 诗词视频（默认目录）
from scripts.poem_video import create_poem_video
path = create_poem_video("my-poem.yaml")

# 诗词视频（项目隔离 — 推荐）
path = create_poem_video("my-poem.yaml", project="静夜思")

# 故事视频（项目隔离 — 推荐）
from scripts.story_video import create_story_video
path = create_story_video("my-story.yaml", project="三只小猪")
```

### YAML 脚本格式

**诗词脚本** (`my-poem.yaml`):
```yaml
title: "静夜思"
author: "李白"
voice: "zh-CN-YunxiaNeural"  # 可选
lines:
  - text: "床前明月光"
    description: "A little scholar in ancient Chinese clothing sits by his bed, moonlight streaming through the window..."
  - text: "疑是地上霜"
    description: "The moonlight on the floor looks like frost, a little scholar gazing at it curiously..."
```

**故事脚本** (`my-story.yaml`):
```yaml
title: "三只小猪"
source: "经典童话"
style: "american"
characters:                          # 可选，手工覆盖角色语音
  小猪大哥: "zh-CN-YunxiNeural"
  大灰狼: "zh-CN-YunjianNeural"
scenes:
  - description: "Three little piglets saying goodbye to their mother..."
    dialogues:
      - character: "旁白"
        text: "从前有三只小猪..."
      - character: "大灰狼"
        text: "小猪小猪，让我进来！"
        voice: "zh-CN-YunjianNeural"   # 可选，覆盖自动映射
```

> `characters` 块可在顶层手工覆盖任意角色的 edge-tts 语音，优先级高于自动映射。每条 dialogue 内的 `voice` 进一步覆盖角色级设置。

---

## 漫画预设风格

| 预设 | 说明 |
|------|------|
| `manga` | 黑白漫画，高对比度，日式线条 |
| `manga-color` | 彩色漫画，日式上色风格 |
| `american` | 美式漫画，粗线条，高饱和度 |
| `strip-4koma` | 四格漫画，简洁可爱 |
| `webtoon` | 条漫风格，适合手机阅读 |
| `ink-wash` | 水墨风格 |
| `retro-american` | 复古美式漫画，网点效果 |
| `minimalist` | 极简线条风格 |

---

## 角色语音映射

自动为故事角色分配 edge-tts 语音（可在 YAML 中覆盖）：

| 角色倾向 | 自动分配语音 | 示例角色 |
|----------|-------------|---------|
| 旁白/叙述 | `zh-CN-YunxiaNeural` 童声 | 旁白、叙述 |
| 成年男性（低沉） | `zh-CN-YunjianNeural` 低沉 | 大灰狼、灰狼、狼、狐狸、老虎、爸爸、猎人 |
| 成年女性（温柔） | `zh-CN-XiaoxiaoNeural` 温柔 | 妈妈、奶奶、外婆 |
| 小动物/幼儿（活泼） | `zh-CN-YunxiNeural` 活泼 | 小猪、小兔、小羊、小鸡、小鸭 |
| 活泼女童（明亮） | `zh-CN-XiaoyiNeural` 明亮 | 小红帽、姐姐、公主 |

---

## 错误码

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | API key 无效 |
| 404 | 任务/视频不存在 |
| 500 | 服务器错误 |
| 503 | 服务繁忙，稍后重试 |

---

## 架构决策

- [ADR 0001: 基于 AGNES i2i 的图片精修工具](docs/adr/0001-image-refine-tool.md)
- [ADR 0002: 故事视频架构](docs/adr/0002-story-video-architecture.md)
- [ADR 0003: 文件组织 — 角色隔离的项目布局](docs/adr/0003-file-organization.md)

---

## 许可证

[Apache License 2.0](LICENSE)
