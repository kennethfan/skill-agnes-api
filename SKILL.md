---
name: agnes-api
description: Use when the user wants to generate images or videos via the AGNES API. Covers text-to-image, image-to-image (editing/composition), text-to-video, image-to-video, keyframe animation, image refinement (refine), comic generation, poem-to-video with TTS voiceover, and children's story video generation with multi-character TTS. Does NOT cover chat/completion endpoints.
allowed-tools: Bash, Read, Write, Edit
---

# AGNES API 技能

通过 [AGNES API](https://agnes-ai.com)（Sapiens AI）生成图片和视频。

## 前置条件

- API key: `~/.config/agnes/key` 或环境变量 `AGNES_API_KEY`
- 验证 key: `@scripts/check_key.py`
- 工具函数: `@scripts/utils.py`

## 输出目录

| 类型 | 目录 |
|---|---|
| 图片 | `~/agent/media/images/` |
| 视频 | `~/agent/media/videos/` |

文件名格式: `agnes-<类型>-<时间戳>.<扩展名>`

## API 基础

| 项目 | 值 |
|---|---|
| Base URL | `https://apihub.agnes-ai.com` |
| Auth | `Authorization: Bearer <API_KEY>` |

---

## 图片生成

**端点**: `POST /v1/images/generations` | **模型**: `agnes-image-2.1-flash`

| 脚本 | 用途 |
|---|---|
| `@scripts/t2i.py` | 文生图 |
| `@scripts/t2i_base64.py` | 文生图（Base64 输出） |
| `@scripts/i2i.py` | 图生图 / 图片编辑 |
| `@scripts/compose.py` | 多图合成 |

**size 常用组合**:

| ratio | 1K | 2K | 3K | 4K |
|---|---|---|---|---|
| `1:1` | 1024×1024 | 2048×2048 | 3072×3072 | 4096×4096 |
| `16:9` | 1312×736 | 2624×1472 | 3936×2208 | 5248×2944 |
| `9:16` | 736×1312 | 1472×2624 | 2208×3936 | 2944×5248 |
| `3:4` | 864×1152 | 1728×2304 | 2592×3456 | 3456×4608 |
| `4:3` | 1152×864 | 2304×1728 | 3456×2592 | 4608×3456 |

也支持传统精确尺寸如 `1024x768`。

## 图片精修 (Refine)

基于 i2i 的图片精修工具，支持画质增强、局部修改、风格迁移。

| 脚本 | 用途 |
|---|---|
| `@scripts/refine.py` | 核心精修函数（AI 驱动模式，被 agent 调用） |
| `@scripts/refine-cli.py` | CLI 工具模式 |

**CLI 用法**:
```
# 查看预设风格
python3 refine-cli.py --list-presets

# 按操作描述精修
python3 refine-cli.py --input photo.jpg --operation "去噪并调亮"

# 使用预设风格
python3 refine-cli.py --input photo.jpg --preset ghibli

# 自定义 prompt
python3 refine-cli.py --input photo.jpg --custom-prompt "Make it vintage"
```

**预设风格配置**: `~/.config/agnes/refine-presets.yaml`

## 漫画创作 (Comic)

基于 t2i + i2i 的漫画生成工具，支持逐格生成、角色锚定、对话框叠加、多布局拼页。

| 脚本 | 用途 |
|---|---|
| `@scripts/comic.py` | 核心漫画生成函数（AI 驱动模式，被 agent 调用） |
| `@scripts/comic-cli.py` | CLI 工具模式 |

**CLI 用法**:
```
# 查看预设风格
python3 comic-cli.py --list-presets

# 按 YAML 脚本生成漫画
python3 comic-cli.py --script my-comic.yaml

# 指定风格
python3 comic-cli.py --script my-comic.yaml --preset manga

# 自定义 prompt 覆盖
python3 comic-cli.py --script my-comic.yaml --custom-prompt "vibrant colors"
```

**预设风格**: `~/.config/agnes/comic-presets.yaml`

| 预设 | 说明 |
|---|---|
| `manga` | 黑白漫画，高对比度，日式线条 |
| `manga-color` | 彩色漫画，日式上色风格 |
| `american` | 美式漫画，粗线条，高饱和度 |
| `strip-4koma` | 四格漫画，简洁可爱 |
| `webtoon` | 条漫风格，适合手机阅读 |
| `ink-wash` | 水墨风格 |
| `retro-american` | 复古美式漫画，网点效果 |
| `minimalist` | 极简线条风格 |

**YAML 脚本格式示例** (`my-comic.yaml`):
```yaml
panels:
  - description: "A hero standing on a cliff overlooking a futuristic city"
    character_ref: ~/refs/hero.png
    speech: "The future is ours."
    speech_pos: top
  - description: "The hero jumps off the cliff, cape flowing"
    speech: "For justice!"
layout: hero  # grid | hero
```

## 诗词朗诵视频 (Poem Video)

基于 AGNES t2i + i2i + edge-tts 的诗词朗诵视频生成工具，面向 3-6 岁儿童。水墨国风，9:16 竖屏（720×1280），统一小书童角色贯穿，每句一个独立场景。字幕通过 **ffmpeg drawtext** 以纯文字形式直接叠加在画面上（白字 + 阴影，无黑底遮罩）。

| 脚本 | 用途 |
|---|---|
| `@scripts/poem_video.py` | 核心视频生成函数（AI 驱动模式，被 agent 调用） |
| `@scripts/poem-video-cli.py` | CLI 工具模式 |

**CLI 用法**:
```
# 从 YAML 脚本生成诗词朗诵视频
python3 poem-video-cli.py --script my-poem.yaml

# 指定童声
python3 poem-video-cli.py --script my-poem.yaml --voice zh-CN-YunxiaNeural

# 列出可用中文语音
python3 poem-video-cli.py --list-voices
```

**依赖**:
- `edge-tts`（朗诵音频，自动 `--rate=-30%` 慢速童声）
- **完整版 ffmpeg**（须编译支持 `drawtext` + `libfontconfig`，macOS 系统自带 ffmpeg 通常不含此组件）

**工作流**:
1. 解析 YAML 脚本 → 读取出诗句列表
2. **t2i** 生成每句对应的场景图（prompt 中包含 "little scholar" 保证角色统一）
3. **封面卡**：用 Pillow 在首张场景图上叠加诗名 + 作者
4. **edge-tts** 逐句生成朗诵音频（慢速 `--rate=-30%`，默认童声 `zh-CN-YunxiaNeural`）
5. 场景图缩放到 720×1280
6. **ffmpeg concat filter** 逐段拼接，**drawtext** 叠加字幕（白字 `fontcolor=white` + 半透明阴影 `shadowcolor=black@0.5`，居中对齐，距底部 80px），无黑底遮罩

**参数说明**:
| 参数 | 值 |
|---|---|
| 视频尺寸 | 720×1280 (9:16 竖屏) |
| 场景生成尺寸 | 736×1312 (AGNES 1K 9:16) |
| 字幕位置 | `(w-text_w)/2` 水平居中，`h-80` 距底部 80px |
| 字幕字体 | PingFang.ttc / STHeiti Light.ttc |
| 字幕样式 | 42px 白色 + 2px 半透明阴影 |
| 语音 | edge-tts —rate=-30% 慢速朗诵 |
| 默认语音 | zh-CN-YunxiaNeural 童声 |

**YAML 脚本格式示例** (`my-poem.yaml`):
```yaml
title: "静夜思"
author: "李白"
voice: "zh-CN-YunxiaNeural"  # 可选，默认童声
lines:
  - text: "床前明月光"
    description: "A little scholar in ancient Chinese clothing sits by his bed, moonlight streaming through the window onto the floor, ink-wash painting style, soft lighting"
  - text: "疑是地上霜"
    description: "The moonlight on the floor looks like frost, a little scholar gazing at it curiously, ink-wash style"
  - text: "举头望明月"
    description: "The little scholar looks up at the bright moon through the window, ink-wash painting, soft lighting"
  - text: "低头思故乡"
    description: "The little scholar lowers his head, thinking of his hometown far away, ink-wash style, nostalgic atmosphere"
```

## 故事视频 (Story Video)

面向 3-6 岁儿童的中文经典故事动画视频生成工具。基于 AGNES t2i + i2i + edge-tts + ffmpeg 管线。

网上搜索故事正文 → AI 拆分为场景 + 多角色对话 → 自动分配角色语音 → 合成视频。

| 脚本 | 用途 |
|---|---|
| `@scripts/story_video.py` | 故事文本 → YAML → 视频渲染（复用 `poem_video` 的 t2i/i2i/edge-tts/ffmpeg 函数） |
| `@scripts/story-video-cli.py` | CLI 入口 |

**CLI 用法**:
```
# 搜索故事 → 全自动生成视频
python3 story-video-cli.py --title "三只小猪"

# 指定视觉风格
python3 story-video-cli.py --title "三只小猪" --style ink-wash

# 跳过搜索，直接给文本文件
python3 story-video-cli.py --textfile my-story.txt --style american

# 指定输出路径
python3 story-video-cli.py --title "三只小猪" -o my-story.mp4
```

**依赖**:
- `edge-tts`（多角色语音，自动 `--rate=-30%` 慢速）
- 完整版 ffmpeg（须含 drawtext + libfontconfig）
- `Pillow`（标题卡制作）
- 视觉 preset 复用 `comic.py` 风格体系

**工作流**:
1. **搜索** — AI agent 通过 websearch / opencli 搜索中文儿童故事网站，获取故事正文
2. **拆文** — 当前 AI agent 将正文拆分为 `scenes`，每个 scene 包含：
   - `description` — 场景图 prompt（英文，给 AGNES t2i/i2i 用）
   - `dialogues[]` — 该场景内的多条角色对话
3. **角色语音分配** — AI 根据角色类型自动分配 edge-tts voice（可手工在 YAML 中覆盖）
4. **t2i 首张场景图** — 第一张图作为角色锚定起点
5. **i2i 后续场景** — 以首张为参考，保证角色外观一致
6. **标题卡** — Pillow 在首张图上叠加故事名
7. **edge-tts** — 逐条 dialogue 生成音频，每条使用对应角色的 voice（带自动重试，应对微软 TTS 服务偶发超时）
8. **ffmpeg 合成** — 每个 scene 中多条 dialogue 共用同一画面，音频逐条拼接 + drawtext 字幕逐条切换

**自动角色语音映射**:

| 角色倾向 | 自动分配 voice | 示例角色 |
|---|---|---|
| 旁白/叙述 | `zh-CN-YunxiaNeural` 童声 | 旁白 |
| 成年男性 | `zh-CN-YunjianNeural` 低沉 | 大灰狼、爸爸、猎人 |
| 成年女性 | `zh-CN-XiaoxiaoNeural` 温柔 | 妈妈、奶奶 |
| 小动物/幼儿 | `zh-CN-YunxiNeural` 活泼 | 小猪、小兔、小鸡 |
| 活泼女童 | `zh-CN-XiaoyiNeural` 明亮 | 小红帽、姐姐 |

可在 YAML 中用 `characters` 块手工覆盖。

**YAML 脚本格式示例** (`my-story.yaml`):
```yaml
title: "三只小猪"
source: "经典童话"
style: "american"                 # 视觉风格 preset
voice: "zh-CN-YunxiaNeural"       # 默认旁白语音
# characters:                     # 可选，手工覆盖角色语音
#   大灰狼: zh-CN-YunjianNeural
scenes:
  - description: "Three little piglets saying goodbye to their mother at a cozy cottage door, bright sunny day, children's book illustration style"
    dialogues:
      - character: "旁白"
        text: "从前有三只小猪，他们长大了要离开家去外面生活。"
  - description: "A little pig building a house made of yellow straw, green meadow, blue sky, cute cartoon style"
    dialogues:
      - character: "旁白"
        text: "第一只小猪用稻草搭了一座房子。"
      - character: "大灰狼"
        text: "小猪小猪，让我进来！"
        voice: "zh-CN-YunjianNeural"
      - character: "小猪"
        text: "不开不开就不开！"
        voice: "zh-CN-YunxiNeural"
  - description: "A big bad wolf blowing at a straw house, the straw flying everywhere, dramatic moment"
    dialogues:
      - character: "大灰狼"
        text: "那我吹一口气，就把你的房子吹倒！"
        voice: "zh-CN-YunjianNeural"
      - character: "旁白"
        text: "大灰狼深吸一口气，呼——草屋倒了。"
```

## 视频生成 (Video)

**端点**: `POST /v1/videos` | **模型**: `agnes-video-v2.0`
**注意**: 异步 — 创建任务 → 轮询结果

| 脚本 | 用途 |
|---|---|
| `@scripts/t2v.py` | 文生视频 |
| `@scripts/i2v.py` | 图生视频 |
| `@scripts/keyframes.py` | 关键帧动画 |
| `@scripts/poll_video.py` | 轮询结果 + 自动保存 |
| `@scripts/query_video.py` | 按 task_id 查询 |

**视频参数**:

| 参数 | 说明 |
|---|---|
| `num_frames` | 总帧数，≤ 441，必须满足 `8n + 1` 规则 |
| `frame_rate` | 帧率，1-60 |
| `height` / `width` | 会被归一化到 480p/720p/1080p 档位 |
| `seed` | 固定随机种子，可复现结果 |
| `negative_prompt` | 负面提示词 |

**常用时长**:

| 目标时长 | num_frames | frame_rate |
|---|---|---|
| ~3秒 | 81 | 24 |
| ~5秒 | 121 | 24 |
| ~10秒 | 241 | 24 |
| ~18秒 | 441 | 24 |

## 错误码

| 状态码 | 含义 |
|---|---|
| 400 | 请求参数错误 |
| 401 | API key 无效 |
| 404 | 任务/视频不存在 |
| 500 | 服务器错误 |
| 503 | 服务繁忙，稍后重试 |
