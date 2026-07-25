# ADR 0005: 将视频管线 skills 合并到 agnes-api

## 状态

已采纳

## 上下文

视频生成能力最初分裂为四个独立的 skill：

| Skill | 职责 |
|-------|------|
| `agnes-api` | AGNES HTTP 客户端层 + 基础能力（t2i/i2i/t2v/refine/comic） |
| `today-in-history` | "历史上的今天"日更视频管线 |
| `story-video` | 儿童故事动画视频管线 |
| `poem-video` | 古诗朗诵竖屏视频管线 |

这种分裂导致以下问题：

1. **重复的前置声明**：三个管线 skill 各自声明"前置技能: agnes-api"，但用户必须先发现 agnes-api → 再发现独立 skill → 分别加载
2. **发现断裂**：在 `skill` 列表或 `/ask-matt` 中，用户看不到 agnes-api 能力全景——不知道 agnes-api 还能做"历史上的今天"
3. **文档膨胀**：底座能力（refine、comic）和平线能力（视频管线）分属不同目录，但都引用同一个 AGNES API
4. **脚本归属混乱**：核心函数（`poem_video.py`、`story_video.py`）在 agnes-api/scripts/ 下，但编排脚本（`poem-pipeline.py`、`story-pipeline.py`）在 `~/agent/media/scripts/` 下——跨仓库维护

## 决策

### 1. 物理合并

将所有能力合并到 `agnes-api` skill 目录下，使用分层文档结构：

```
agnes-api/
├── SKILL.md              ← 精简能力总览 + 索引
├── CONTEXT.md            ← 领域词汇表
├── docs/
│   ├── refine.md         ← 精修能力详情
│   ├── comic.md          ← 漫画能力详情
│   └── pipelines/
│       ├── today-in-history.md
│       ├── story-video.md
│       └── poem-video.md
├── scripts/
│   └── pipelines/
│       ├── today-in-history-pipeline.py
│       ├── story-pipeline.py
│       └── poem-pipeline.py
```

- `SKILL.md` 只保留能力概览（一段描述 + 链接到子文档），不再包含 CLI 用法等细节
- 精修（refine）和漫画（comic）从 SKILL.md 拆出独立文档
- 三个管线从独立 skill 迁入 `docs/pipelines/`
- 三个编排脚本从 `~/agent/media/scripts/` 迁入 `scripts/pipelines/`

### 2. 管线脚本参数化

三个管线脚本原硬编码 `BASE_DIR = Path.home() / "agent" / "media"`。迁移时增加 `--work-dir` 参数（默认 `~/agent/media/`），使管线可作为可复用的 skill 组件在任何工作目录下运行。

### 3. 删除独立 skill 目录

`poem-video/`、`story-video/`、`today-in-history/` 三个目录被删除，其 `description` 更新到 agnes-api/SKILL.md 的 YAML frontmatter 中。

## 影响

- **正面**：用户一次加载 `agnes-api` skill 即可看到所有能力全景；发现路径从 4 步缩短为 1 步
- **正面**：脚本和文档归属一致，降低维护成本
- **负面**：`SKILL.md` 篇幅增长（~200 行 vs 之前 359 行），但通过分层拆分保持可读性
- **负面**：已有 agent 如果显式加载 `story-video` skill 会失败（404），需更新 prompt 改为加载 `agnes-api`
