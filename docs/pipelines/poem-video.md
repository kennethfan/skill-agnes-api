# 古诗朗诵 — 视频流水线

古诗朗诵短视频：AGNES 生成场景图 + edge-tts 朗诵 + Pillow 字幕 + ffmpeg 合成 9:16 竖屏视频。

**前置**: 需加载 `agnes-api` skill（AGNES 图片生成 API）。

## 流水线概览

统一管线 `poem-pipeline.py`，一键执行三阶段：

```
YAML 诗稿
  │
  ├─ Stage 1: 场景图片生成  (AGNES t2i, 并行 3 worker, 重试 3 次)
  ├─ Stage 2: 素材准备      (Pillow 字幕帧 + edge-tts 朗诵音频)
  └─ Stage 3: 视频合成      (ffmpeg concat → 9:16 竖屏 MP4)
```

每阶段自动跳过已完成的工作，支持 `--force-stage` 强制重跑 / `--skip-stage` 跳过。

---

## Step 1 — 编写 YAML 诗稿

为古诗编写一个 YAML 文件，结构如下：

```yaml
title: "咏鹅"
author: "骆宾王"
grade: "一年级上册"
voice: "zh-CN-YunxiaNeural"        # 可选，默认童声
scenes:
  - description: >-
      A flock of geese swimming in a green pond, white feathers floating on
      emerald water, red feet paddling, children's book illustration style
    dialogues:
      - text: "鹅，鹅，鹅，曲项向天歌。"
      - text: "白毛浮绿水，红掌拨清波。"

  - description: >-
      Two geese calling to the sky, ripples on the pond surface, warm sunlight,
      children's book illustration style
    dialogues:
      - text: "鹅，鹅，鹅，曲项向天歌。"
```

### 字段说明

| 字段 | 要求 |
|------|------|
| `title` | 诗题，显示在片头卡上 |
| `author` | 作者名，片头卡副标题 |
| `grade` | 年级（如"一年级上册"），片头卡底部标注 |
| `voice` | 可选。edge-tts 语音名称，默认 `zh-CN-YunxiaNeural` |
| `scenes[].description` | **英文**场景描述，作为 AGNES t2i 的 prompt。自动追加 `children's book illustration style` 风格后缀 |
| `scenes[].dialogues[].text` | 诗句文本。每句单独一条，字幕居中显示（无角色前缀） |

**兼容旧格式**：如果 YAML 使用 `lines` 字段（旧格式），管线会自动转换为 `scenes→dialogues` 格式。

**完成标志**: YAML 文件保存到项目目录。

---

## Step 2 — 运行统一管线

```bash
python3 scripts/pipelines/poem-pipeline.py --yaml poem-咏鹅.yaml
```

### 三阶段流程

```
Stage 1 — 场景图片生成
  调用 AGNES t2i 为 YAML 中每个 scene 的 description 生成图片。
  - 并行 3 个 worker（诗篇较短，降低并发避免超额），失败自动重试 3 次（2^n 退避）
  - 已存在的 scene 自动跳过（按文件名匹配）
  - prompt 自动追加 children's book illustration style 风格后缀
  - 图片尺寸 2K, 9:16 竖屏比例
  - 输出: images/poem-{yaml_stem}-s{NN}-{ts}.png

Stage 2 — 素材准备
  对每句诗生成字幕帧和朗诵音频。
  - 字幕帧: 场景图缩放至 720×1280 (9:16 竖屏) → 底部半透明黑条 + 白色诗句文字
  - 字号 42px，自动中文换行（按像素宽度断行）
  - 片头卡: 大标题（64px）+ 作者名（30px）+ 年级标注（26px）
  - 朗诵: edge-tts, 语速 --rate=-30%, 默认童声 zh-CN-YunxiaNeural
  - 已存在的帧/音频文件自动跳过
  - 输出: tmp/pipeline_poem-{stem}/ → frame_*.png + audio_*.mp3

Stage 3 — 视频合成
  ffmpeg concat 将全部音频段拼接为最终竖屏视频。
  - 片头卡: 第一张场景图做背景 + 半透明遮罩，叠加诗题 + 作者 + "部编版·{grade}·古诗朗诵"
  - N 段 [循环帧 + 音频] → concat=n=N:v=1:a=1
  - libx264 + aac, 24fps, 720×1280 (9:16 竖屏), yuv420p
  - 输出: videos/诗歌朗诵/{title}.mp4
```

### 管线参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--yaml` | 是 | YAML 诗稿路径（绝对或相对于 work-dir） |
| `--output` | 否 | 自定义输出视频路径 |
| `--work-dir` | 否 | 工作目录（默认 `~/agent/media/`） |
| `--clean` | 否 | 成功后清理 `tmp/` 临时文件 |
| `--force-stage` | 否 | 强制重跑某阶段，值 1/2/3 |
| `--skip-stage` | 否 | 跳过某阶段，值 1/2 |

### Checkpoint 断点续传

管线使用 `.pipeline_state.json` 追踪每首诗的阶段完成状态：

- 每完成一个 stage 自动写入 checkpoint（key: YAML 文件名 stem）
- 重复运行自动跳过已完成的阶段
- 配合 `--force-stage N` 重新生成某阶段、`--skip-stage N` 跳过某阶段

**完成标志**: MP4 文件生成，ffprobe 校验时长正确，文件大小合理。

---

## 参考实现

管线脚本位于 `scripts/pipelines/`：

| 脚本 | 用途 |
|------|------|
| `poem-pipeline.py` | 统一三阶段管线（推荐） |

该管线通过 `agnes-api` skill 提供的 AGNES API（`agnes-image-2.1-flash` 模型）完成图片生成。

## 依赖

| 工具 | 用途 | 验证 |
|------|------|------|
| AGNES API (`agnes-image-2.1-flash`) | 图片生成 | `agnes-api` skill |
| `edge-tts` | 中文语音朗诵 | `pip3 install edge-tts` |
| `Pillow` | 字幕渲染 | `pip3 install Pillow` |
| `ffmpeg` (含 libx264 + aac) | 视频合成 | `ffmpeg -version` |
| `PingFang.ttc` | 中文字体 | macOS 系统自带 `/System/Library/Fonts/PingFang.ttc` |
