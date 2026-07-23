# 儿童故事 — 视频流水线

儿童故事短视频：AGNES 生成场景图 + 多角色 edge-tts 旁白 + Pillow 字幕 + ffmpeg 合成。

**前置**: 需加载 `agnes-api` skill（AGNES 图片生成 API）。

## 流水线概览

统一管线 `story-pipeline.py`，一键执行三阶段：

```
YAML 剧本
  │
  ├─ Stage 1: 场景图片生成  (AGNES t2i, 并行 5 worker, 重试 3 次)
  ├─ Stage 2: 素材准备      (Pillow 字幕帧 + 多角色 edge-tts 音频)
  └─ Stage 3: 视频合成      (ffmpeg concat → MP4)
```

每阶段自动跳过已完成的工作，支持 `--force-stage` 强制重跑 / `--skip-stage` 跳过。

---

## Step 1 — 编写 YAML 剧本

为故事编写一个 YAML 文件，结构如下：

```yaml
title: "小红帽"
source: "格林童话"
characters:
  小红帽: zh-CN-XiaoyiNeural
  大灰狼: zh-CN-YunjianNeural
  奶奶: zh-CN-XiaoxiaoNeural
scenes:
  - description: >-
      A little girl in a red riding hood walking through a sunlit forest,
      picking flowers, birds singing, wide angle, storybook illustration
    dialogues:
      - character: "旁白"
        text: "从前有一个可爱的小女孩，整天戴着一顶红帽子……"
      - character: "小红帽"
        text: "奶奶生病了，我要去看她！"

  - description: >-
      A big bad wolf hiding behind a tree, eyes gleaming, talking to Little Red
      Riding Hood, dramatic lighting
    dialogues:
      - character: "大灰狼"
        text: "小姑娘，你要去哪里呀？"
```

### 字段说明

| 字段 | 要求 |
|------|------|
| `title` | 中文标题，显示在片头卡上 |
| `source` | 故事来源（如"格林童话"），显示在片头卡 |
| `characters` | 可选。角色名 → edge-tts 语音名称的映射 |
| `scenes[].description` | **英文**场景描述，作为 AGNES t2i 的 prompt。原文直传，不追加额外风格后缀 |
| `scenes[].dialogues[].character` | 角色名。`旁白` 或其他角色名 |
| `scenes[].dialogues[].text` | 对白文本 |

### 角色音色映射

**优先级**：YAML 中 `characters` 映射 > 内置角色表 > 启发式推断

内置角色表：

| 类别 | 角色 | 语音 |
|------|------|------|
| 旁白 | 旁白 / 叙述 / 叙述者 | `zh-CN-YunxiaNeural` |
| 男性 | 大灰狼、猎人、爸爸、国王、爷爷、皇帝、农夫、狮子、老虎、狐狸 | `zh-CN-YunjianNeural` |
| 女性 | 奶奶、妈妈、公主、王后、仙女、外婆、小红帽(母) | `zh-CN-XiaoxiaoNeural` |
| 小孩 | 乌龟、兔子、小猫、小狗、小鸭、小鸡、小猪 | `zh-CN-YunxiNeural` |
| 女孩 | 小红帽 | `zh-CN-XiaoyiNeural` |

启发式：以 哥/弟/爸 结尾 → 男声，以 姐/妹/妈/娘/婆 结尾 → 女声。

如不满足需求，在 YAML `characters` 中显式指定即可覆盖。

---

## Step 2 — 运行统一管线

```bash
python3 scripts/pipelines/story-pipeline.py --yaml story-小红帽.yaml
```

### 三阶段流程

```
Stage 1 — 场景图片生成
  调用 AGNES t2i 为 YAML 中每个 scene 的 description 生成图片。
  - 并行 5 个 worker，失败自动重试 3 次（2^n 退避）
  - 已存在的 scene 自动跳过（按文件名匹配）
  - description 原文直传，不追加任何风格后缀
  - 图片自动居中裁剪 (cover fit) 到 16:9
  - 输出: images/story-{yaml_stem}-s{NN}-{ts}.png

Stage 2 — 素材准备
  对每个 dialogue 生成字幕帧和角色配音音频。
  - 字幕帧: 场景图缩放至 1920×1080 → 底部半透明黑条 + 白色文字
  - 字幕格式: "角色名：对白文本"，自动中文换行
  - 配音: edge-tts，根据角色名自动匹配音色
  - 语速 --rate=-30%
  - 已存在的帧/音频文件自动跳过
  - 输出: tmp/pipeline_story-{stem}/ → frame_*.png + audio_*.mp3

Stage 3 — 视频合成
  ffmpeg concat 将全部音频段拼接为最终视频。
  - 片头卡: 第一张场景图做背景 + 半透明遮罩，叠加标题 + "改编自{source}" + "儿童故事·动画版"
  - N 段 [循环帧 + 音频] → concat=n=N:v=1:a=1
  - libx264 + aac, 24fps, 1920×1080, yuv420p
  - 输出: videos/儿童故事/{title}.mp4
```

### 管线参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--yaml` | 是 | YAML 剧本路径（绝对或相对于 work-dir） |
| `--output` | 否 | 自定义输出视频路径 |
| `--work-dir` | 否 | 工作目录（默认 `~/agent/media/`） |
| `--clean` | 否 | 成功后清理 `tmp/` 临时文件 |
| `--force-stage` | 否 | 强制重跑某阶段，值 1/2/3 |
| `--skip-stage` | 否 | 跳过某阶段，值 1/2 |

### Checkpoint 断点续传

管线使用 `.pipeline_state.json` 追踪每个故事的阶段完成状态：

- 每完成一个 stage 自动写入 checkpoint（key: `story-{stem}`）
- 重复运行自动跳过已完成的阶段
- 配合 `--force-stage N` 重新生成某阶段、`--skip-stage N` 跳过某阶段

**完成标志**: MP4 文件生成，ffprobe 校验时长正确，文件大小合理。

---

## 参考实现

管线脚本位于 `scripts/pipelines/`：

| 脚本 | 用途 |
|------|------|
| `story-pipeline.py` | 统一三阶段管线（推荐） |

该管线通过 `agnes-api` skill 提供的 AGNES API（`agnes-image-2.1-flash` 模型）完成图片生成。

## 依赖

| 工具 | 用途 | 验证 |
|------|------|------|
| AGNES API (`agnes-image-2.1-flash`) | 图片生成 | `agnes-api` skill |
| `edge-tts` | 中文语音合成（多角色） | `pip3 install edge-tts` |
| `Pillow` | 字幕渲染 | `pip3 install Pillow` |
| `ffmpeg` (含 libx264 + aac) | 视频合成 | `ffmpeg -version` |
| `PingFang.ttc` | 中文字体 | macOS 系统自带 `/System/Library/Fonts/PingFang.ttc` |
