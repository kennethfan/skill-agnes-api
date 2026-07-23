# 漫画创作 (Comic)

基于 t2i + i2i 的漫画生成工具，支持逐格生成、角色锚定、对话框叠加、多布局拼页。

## 脚本

| 脚本 | 用途 |
|------|------|
| `@scripts/comic.py` | 核心漫画生成函数（AI 驱动模式，被 agent 调用），支持 `project` 参数进行项目隔离目录管理 |
| `@scripts/comic-cli.py` | CLI 工具模式 |
| `@scripts/comic-page-layout.py` | （历史上的今天专用）独立管线 — 读取 `today-in-history-comic.yaml`，查找最新 `comic-scene-NN` 图片，叠加对话框并排布为 2×2 网格页面 |

## CLI 用法

```bash
# 查看预设风格
python3 comic-cli.py --list-presets

# 按 YAML 脚本生成漫画
python3 comic-cli.py --script my-comic.yaml

# 指定风格
python3 comic-cli.py --script my-comic.yaml --preset manga

# 自定义 prompt 覆盖
python3 comic-cli.py --script my-comic.yaml --custom-prompt "vibrant colors"

# 指定面板尺寸
python3 comic-cli.py --script my-comic.yaml --panel-size 1024x768

# 指定输出路径
python3 comic-cli.py --script my-comic.yaml --output my-comic.png
```

## 预设风格

配置: `~/.config/agnes/comic-presets.yaml`

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

## YAML 脚本格式

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
