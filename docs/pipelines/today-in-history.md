# 历史上的今天 — 视频流水线

每日一条"历史上的今天"短视频：AGNES 生成场景图 + edge-tts 旁白 + Pillow 字幕 + ffmpeg 合成。

**前置**: 需加载 `agnes-api` skill（AGNES 图片生成 API）。

## 流水线概览

统一管线 `today-in-history-pipeline.py`，一键执行三阶段：

```
YAML 脚本
  │
  ├─ Stage 1: 场景图片生成  (AGNES t2i, 并行 5 worker, 重试 3 次)
  ├─ Stage 2: 素材准备      (Pillow 字幕帧 + edge-tts 旁白音频)
  └─ Stage 3: 视频合成      (ffmpeg concat → MP4)
```

每阶段自动跳过已完成的工作，支持 `--force-stage` 强制重跑 / `--skip-stage` 跳过。

---

## Step 1 — 编写 YAML 脚本

为指定日期编写一个 YAML 文件，结构如下：

```yaml
title: "历史上的今天——7月19日"
source: "Wikipedia、Britannica、百度百科"
style: "illustration"                    # 视觉风格标签
voice: "zh-CN-YunxiaNeural"             # edge-tts 默认语音
scenes:
  - description: >-
      Ancient Rome engulfed in flames, buildings collapsing, citizens fleeing in panic,
      epic scale, children's book illustration style, warm dramatic colors
    dialogues:
      - character: "旁白"
        text: "公元64年7月19日，罗马陷入一片火海……"
      - character: "旁白"
        text: "大火燃烧六天，大半个罗马城化为焦土。"
```

### 字段说明

| 字段 | 要求 |
|------|------|
| `title` | 中文标题，显示在片头卡上 |
| `source` | 信息来源标注 |
| `style` | 视觉风格标签，仅用于记录 |
| `voice` | edge-tts 语音名称，默认 `zh-CN-YunxiaNeural` |
| `scenes[].description` | **英文**场景描述，作为 AGNES t2i 的 prompt。必须以 `children's book illustration style` 结尾保证风格统一 |
| `scenes[].dialogues[].character` | 角色名，`旁白` 或其他角色名 |
| `scenes[].dialogues[].text` | 对白文本 |

### 历史事件选材标准

- 选取该日期有代表性、有画面感的历史事件
- 每个事件 2-4 个 scene（呈现起因→经过→结果）
- 总 scene 数 10-20 为宜（视频总长约 5-15 分钟）
- 涵盖古今中外，避免单一地域

**完成标志**: YAML 文件保存，文件名为 `today-in-history-YYYY-MM-DD.yaml`。

---

## Step 2 — 运行统一管线

```bash
python3 scripts/pipelines/today-in-history-pipeline.py \
  --date 0723 \
  --yaml 历史上的今天/today-in-history-2026-07-23.yaml
```

### 三阶段流程

```
Stage 1 — 场景图片生成
  调用 AGNES t2i 为 YAML 中每个 scene 的 description 生成图片。
  - 并行 5 个 worker，失败自动重试 3 次（2^n 退避）
  - 已存在的 scene 自动跳过（按文件名匹配）
  - 图片自动居中裁剪 (cover fit) 到 16:9
  - 输出: images/comic-scene-{date}-{NN}-{ts}.png

Stage 2 — 素材准备
  对每个 dialogue 生成字幕帧和旁白音频。
  - 字幕帧: 场景图缩放至 1920×1080 → 底部半透明黑条 + 白色文字
  - 自动中文换行（按像素宽度断行）
  - 旁白音频: edge-tts, 语速 --rate=-30%, 默认童声 zh-CN-YunxiaNeural
  - 已存在的帧/音频文件自动跳过
  - 输出: tmp/pipeline_{date}/ → frame_*.png + audio_*.mp3

Stage 3 — 视频合成
  ffmpeg concat 将全部音频段拼接为最终视频。
  - 片头卡: 第一张场景图做背景 + 半透明遮罩，叠加标题 + 日期 + "历史上的今天" 副标题
  - N 段 [循环帧 + 音频] → concat=n=N:v=1:a=1
  - libx264 + aac, 24fps, 1920×1080, yuv420p
  - 输出: videos/历史上的今天/历史上的今天{date}.mp4
```

### 管线参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--date` | 是 | 日期 `MMdd` 格式，如 `0723` |
| `--yaml` | 是 | YAML 剧本路径（绝对或相对于 work-dir） |
| `--output` | 否 | 自定义输出视频路径 |
| `--work-dir` | 否 | 工作目录（默认 `~/agent/media/`） |
| `--clean` | 否 | 成功后清理 `tmp/` 临时文件 |
| `--force-stage` | 否 | 强制重跑某阶段，值 1/2/3 |
| `--skip-stage` | 否 | 跳过某阶段，值 1/2 |

### Checkpoint 断点续传

管线使用 `.pipeline_state.json` 追踪每个日期的阶段完成状态：

- 每完成一个 stage 自动写入 checkpoint
- 重复运行自动跳过已完成的阶段
- 配合 `--force-stage N` 重新生成某阶段、`--skip-stage N` 跳过某阶段

**完成标志**: MP4 文件生成，ffprobe 校验时长正确，文件大小合理。

---

## 参考实现

管线脚本位于 `scripts/pipelines/`：

| 脚本 | 用途 |
|------|------|
| `today-in-history-pipeline.py` | 统一三阶段管线（推荐） |

该管线通过 `agnes-api` skill 提供的 AGNES API（`agnes-image-2.1-flash` 模型）完成图片生成。

## 依赖

| 工具 | 用途 | 验证 |
|------|------|------|
| AGNES API (`agnes-image-2.1-flash`) | 图片生成 | `agnes-api` skill |
| `edge-tts` | 中文语音合成 | `pip3 install edge-tts` |
| `Pillow` | 字幕渲染 | `pip3 install Pillow` |
| `ffmpeg` (含 libx264 + aac) | 视频合成 | `ffmpeg -version` |
| `PingFang.ttc` | 中文字体 | macOS 系统自带 `/System/Library/Fonts/PingFang.ttc` |
