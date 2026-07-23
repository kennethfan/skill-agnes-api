---
name: agnes-api
description: Use when the user wants to generate images or videos via the AGNES API. Covers text-to-image, image-to-image (editing/composition), image refine, comic generation, text-to-video, image-to-video, keyframe animation, poem recitation video, children's story video, and "today in history" video. Does NOT cover chat/completion endpoints.
allowed-tools: Bash, Read, Write, Edit
---

# AGNES API 技能

通过 [AGNES API](https://agnes-ai.com)（Sapiens AI）生成图片和视频。

## 前置条件

- API keys: 在 `~/.config/agnes/paths.yaml` 中配置 `agnes_api_keys`，取值为一个或多个 key 文件路径列表
- 验证 key: `@scripts/check_key.py`
- 工具函数: `@scripts/utils.py`

## 输出目录

| 类型 | 目录 |
|------|------|
| 图片 | `~/agent/media/images/` |
| 视频 | `~/agent/media/videos/` |

文件名格式: `agnes-<类型>-<时间戳>.<扩展名>`

## API 基础

| 项目 | 值 |
|------|-----|
| Base URL | `https://apihub.agnes-ai.com` |
| Auth | `Authorization: Bearer <API_KEY>` |

---

## 统一客户端 (Client)

| 脚本 | 用途 |
|------|------|
| `@scripts/client.py` | 三层客户端：`AgnesClient`(HTTP 传输 + key rotation) → `ImageClient`(t2i/i2i) / `VideoClient`(create/poll) |

所有脚本均通过 client.py 访问 API，自动处理 key 轮转和限流重试。

```python
from client import ImageClient, VideoClient

img = ImageClient()
url = img.t2i("a cat", size="1024x768")
data = img.download(url)

vid = VideoClient()
task_id = vid.create({"prompt": "...", ...})
result = vid.poll(task_id)
```

---

## 能力总览

### 图片生成

**端点**: `POST /v1/images/generations` | **模型**: `agnes-image-2.1-flash`

| 脚本 | 用途 |
|------|------|
| `@scripts/t2i.py` | 文生图 |
| `@scripts/t2i_base64.py` | 文生图（Base64 输出） |
| `@scripts/i2i.py` | 图生图 / 图片编辑 |
| `@scripts/compose.py` | 多图合成 |

**尺寸参考**:

| ratio | 1K | 2K | 3K | 4K |
|-------|-----|-----|-----|-----|
| `1:1` | 1024×1024 | 2048×2048 | 3072×3072 | 4096×4096 |
| `16:9` | 1312×736 | 2624×1472 | 3936×2208 | 5248×2944 |
| `9:16` | 736×1312 | 1472×2624 | 2208×3936 | 2944×5248 |
| `3:4` | 864×1152 | 1728×2304 | 2592×3456 | 3456×4608 |
| `4:3` | 1152×864 | 2304×1728 | 3456×2592 | 4608×3456 |

也支持传统精确尺寸如 `1024x768`。

### 图片精修 (Refine)

基于 i2i 的图片精修，支持画质增强、局部修改、风格迁移。
→ 详见 [`docs/refine.md`](docs/refine.md)

### 漫画创作 (Comic)

基于 t2i + i2i 的漫画生成，支持逐格/角色锚定/对话框/拼页。
→ 详见 [`docs/comic.md`](docs/comic.md)

### 古诗朗诵视频 (Poem Video)

9:16 竖屏，水墨国风，统一小书童角色，edge-tts 童声朗诵，ffmpeg drawtext 字幕。
→ 详见 [`docs/pipelines/poem-video.md`](docs/pipelines/poem-video.md)

### 故事视频 (Story Video)

多角色动画故事，自动角色语音映射，i2i 角色锚定，checkpoint 断点续传。
→ 详见 [`docs/pipelines/story-video.md`](docs/pipelines/story-video.md)

### 历史上的今天 (Today in History)

每日历史短视频，3 阶段管线，checkpoint 断点续传。
→ 详见 [`docs/pipelines/today-in-history.md`](docs/pipelines/today-in-history.md)

### 视频生成 (Video)

**端点**: `POST /v1/videos` | **模型**: `agnes-video-v2.0`
**注意**: 异步 — 创建任务 → 轮询结果

| 脚本 | 用途 |
|------|------|
| `@scripts/t2v.py` | 文生视频 |
| `@scripts/i2v.py` | 图生视频 |
| `@scripts/keyframes.py` | 关键帧动画 |
| `@scripts/poll_video.py` | 轮询结果 + 自动保存 |
| `@scripts/query_video.py` | 按 task_id 查询 |

**视频参数**:

| 参数 | 说明 |
|------|------|
| `num_frames` | 总帧数，≤ 441，必须满足 `8n + 1` 规则 |
| `frame_rate` | 帧率，1-60 |
| `height` / `width` | 会被归一化到 480p/720p/1080p 档位 |
| `seed` | 固定随机种子，可复现结果 |
| `negative_prompt` | 负面提示词 |

**常用时长**:

| 目标时长 | num_frames | frame_rate |
|----------|------------|------------|
| ~3秒 | 81 | 24 |
| ~5秒 | 121 | 24 |
| ~10秒 | 241 | 24 |
| ~18秒 | 441 | 24 |

---

## 错误码

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | API key 无效 |
| 404 | 任务/视频不存在 |
| 500 | 服务器错误 |
| 503 | 服务繁忙，稍后重试 |
