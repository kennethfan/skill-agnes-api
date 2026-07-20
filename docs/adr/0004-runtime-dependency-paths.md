# 4. Runtime Dependency Paths — Toolchain & Font Paths in Central Config

**Date**: 2026-07-20

## Context

File organization (ADR 0003) 把输出路径纳入了 `paths.yaml` 集中管理，但运行时工具链路径仍是硬编码：

- **ffmpeg 二进制**：`poem_video.py` 中硬编码了 conda 环境下的绝对路径 `/Users/kenneth/anaconda3/envs/python3.12/.../ffmpeg`，其余脚本走 PATH 上的系统 ffmpeg
- **ffprobe 二进制**：同上，只在 `poem_video.py` 中有显式路径
- **中文字体路径**：4 个脚本（`poem_video.py`、`story_video.py`、`comic.py`、`comic-page-layout.py`）各自维护一份 macOS/Linux 回退列表，共 4 份重复

这导致三个问题：

1. **分散维护** — 换字体或换 ffmpeg 版本要改 4 个文件
2. **不一致** — 有的脚本只配了 macOS 路径（PingFang），有的配了 Linux fallback（Noto），有的没有 ffmpeg 显式路径
3. **不可迁移** — 换机器后每个脚本都要改

## Decision

将运行时工具链路径也纳入 `~/.config/agnes/paths.yaml`，与输出路径同一文件管理。

### 新增配置项

```yaml
ffmpeg_bin: /absolute/path/to/ffmpeg
ffprobe_bin: /absolute/path/to/ffprobe
font_paths:
  - /System/Library/Fonts/PingFang.ttc       # macOS 优先
  - /System/Library/Fonts/STHeiti Light.ttc  # macOS 备选
  - /usr/share/fonts/truetype/noto/...       # Linux fallback
  - /usr/share/fonts/opentype/noto/...       # Linux fallback
```

### 读取方式

- **ffmpeg_bin / ffprobe_bin** — 直接返回绝对路径，不配置时走 PATH（默认值 `"ffmpeg"` / `"ffprobe"`）
- **font_paths** — 按列表顺序遍历，返回第一个存在的路径，都不存在时返回空字符串，调用方 fallback 到 `ImageFont.load_default()`

### 改动的脚本

| 脚本 | 改动内容 |
|---|---|
| `utils.py` | 新增 `get_ffmpeg_bin()` / `get_ffprobe_bin()` / `get_font_path()` |
| `poem_video.py` | ffmpeg/ffprobe 路径、2 处字体查找 → utils |
| `story_video.py` | 2 处字体查找 → utils（ffmpeg 通过 poem_video 导入） |
| `comic.py` | 字体查找 → utils |
| `comic-page-layout.py` | 字体查找 → utils |

## Consequences

- **正面**：换 ffmpeg 版本或加新的字体路径只需改一个文件
- **正面**：macOS ↔ Linux 跨平台字体回退逻辑统一在配置层，脚本无需感知平台差异
- **正面**：新脚本调用 `get_font_path()` 一行拿到可用字体，无需自维护候选列表
- **负面**：`paths.yaml` 从"文件目录配置"变为"工具链配置"，职责略有扩大，但仍然是"路径配置"这一大类，语义未溢出
- **负面**：`ffmpeg_bin` 是用户机器特定的绝对路径，不适合团队共享——但在当前单用户场景下可接受

## Alternatives Considered

| 方案 | 理由 | 为什么没选 |
|---|---|---|
| 只改 font_paths，ffmpeg 保持 PATH 查找 | 改动最小，ffmpeg 通常已在 PATH | `poem_video.py` 依赖的 portable ffmpeg 不在 PATH 上，必须显式指定 |
| ffmpeg 沿用原始硬编码，不纳入配置 | 无需改动 | 与"集中配置"原则矛盾，换环境仍要改代码 |
| 把工具链路径放进独立 `config.yaml` | 职责分离更清晰 | 对于当前单配置文件的简单项目，拆文件增加复杂度 |
