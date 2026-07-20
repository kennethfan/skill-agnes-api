# 3. File Organization — Role-Isolated Project Layout

**Date**: 2026-07-20

## Context

AGNES API 技能中包含 11 个 Python 脚本，每个脚本硬编码自己的输出路径：

```python
OUTPUT_DIR = Path.home() / "agent" / "media" / "images"
# 或
OUTPUT_DIR = Path.home() / "agent" / "media" / "videos"
```

在实践中暴露出四个问题：

1. **硬编码路径 × 11 份** — 修改路径需改 11 个文件，无单一信源
2. **中间产物与最终交付物混淆** — `videos/` 下同时有最终 `.mp4` 和 140+ 张诗歌场景图（中间产物），无法区分哪些可以删除
3. **无项目隔离** — 三个项目的 `comic-scene-01-*.png` 混在同一个 `images/` 目录，不同 Run 的文件互相覆盖或堆积
4. **无清理机制** — Pipeline 完成后中间帧（`*frame-*`, `*scene-*`, `*title-*`）无任何清理提示，持续堆积

## Decision

采用 **项目隔离 + 角色分层** 的文件组织方案，由 `~/.config/agnes/paths.yaml` 集中配置路径规则。

### 角色层级（Role Axes）

每个文件按其在 pipeline 中的角色归入三个目录之一：

| 角色 | 目录名 | 生命周期 | 示例 |
|---|---|---|---|
| **Asset** | `assets/` | 保留（不可再生） | 角色参考图、背景素材、角色锚定图 |
| **Intermediate** | `scenes/`, `panels/`, `bubbles/`, `frames/`, `audio/` | 可删除，完成后询问 | t2i 场景原图、逐格图、气泡、视频帧、TTS 音频段 |
| **Deliverable** | `deliverable/` | 保留（最终产出） | 拼页 PNG、最终 MP4 |

### 项目隔离（Project Isolation）

```
~/agent/media/
├── assets/                          ← 跨项目共享的输入素材
└── projects/
    └── <project-name>/
        ├── <project-name>.yaml      ← 剧本随项目存储
        ├── scenes/                  ← Intermediate: t2i 场景原图
        ├── panels/                  ← Intermediate: 漫画逐格
        ├── bubbles/                 ← Intermediate: 气泡图层
        ├── frames/                  ← Intermediate: 视频拼帧
        ├── audio/                   ← Intermediate: TTS 音频段
        └── deliverable/
            ├── comic-pages/         ← Deliverable: 拼页
            └── videos/              ← Deliverable: 最终视频
```

### 无归属文件的兜底

`~/agent/media/tmp/` — 存放临时生成的零散图片/视频。用于 `t2i.py` 单独跑一次"帮我画只猫"的场景，没有项目上下文。

### 清理机制

Pipeline 完成时，主动询问用户："已生成 47 个中间文件，是否删除？"（默认 yes）。删除范围为项目目录下的 scenes/, panels/, bubbles/, frames/, audio/ 及其内容。

### 配置入口

`~/.config/agnes/paths.yaml` 作为唯一信源，`utils.py` 从中加载全部路径，所有脚本通过 `utils.py` 获取路径，不再自行硬编码。

## Consequences

- **正面**：一个文件改路径，所有脚本生效；中间产物可安全清理；项目文件互不干扰
- **正面**：新脚本不再需要猜测路径——直接 `from utils import get_project_dir`
- **负面**：改脚本工作量较大（11 个文件），但多为机械替换
- **负面**：Pipeline 清理提示增加了交互步骤，但默认 yes 可一键跳过
- **迁移策略**：旧 `images/` 和 `videos/` 保留不动，新文件按新规则写入；3 个月后确认无引用即可删除

## Alternatives Considered

| 方案 | 理由 | 为什么没选 |
|---|---|---|
| 仅靠命名前缀区分（如 `projectA-scene-01`） | 改动最小 | 前缀不能阻止同目录堆积，也无法批量清理中间产物 |
| 仅按项目分层（不区分角色） | 结构更浅 | 无法区分"可删"和"保留"，清理时得逐文件判断 |
| 全用 tempfile 随机目录 | 天然清理 | 无法预览、无法重跑复用、调试困难 |
