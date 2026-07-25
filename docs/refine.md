# 图片精修 (Refine)

基于 i2i 的图片精修工具，支持画质增强、局部修改、风格迁移。

## 脚本

| 脚本 | 用途 |
|------|------|
| `@scripts/refine.py` | 核心精修函数（AI 驱动模式，被 agent 调用） |
| `@scripts/refine-cli.py` | CLI 工具模式 |

## CLI 用法

```bash
# 查看预设风格
python3 refine-cli.py --list-presets

# 按操作描述精修
python3 refine-cli.py --input photo.jpg --operation "去噪并调亮"

# 使用预设风格
python3 refine-cli.py --input photo.jpg --preset ghibli

# 自定义 prompt
python3 refine-cli.py --input photo.jpg --custom-prompt "Make it vintage"

# 指定尺寸和宽高比
python3 refine-cli.py --input photo.jpg --preset cyberpunk --size 2K --ratio 16:9

# 输入为 URL
python3 refine-cli.py --input https://example.com/photo.jpg --operation "调亮+锐化"
```

## 配置

预设风格配置: `~/.config/agnes/refine-presets.yaml`
