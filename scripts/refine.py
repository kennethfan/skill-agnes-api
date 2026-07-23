"""图片精修核心模块 — 基于 AGNES i2i

两种使用方式：
1. AI 驱动模式：被 agent 调用，传入自然语言指令
2. 工具模式：通过 refine-cli.py CLI 调用

用法示例（AI 驱动）：
    from refine import refine
    path = refine("photo.jpg", "去噪并调亮")
    path = refine("https://example.com/photo.jpg", "变成宫崎骏风格")
"""

import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir

# --- 路径配置 ---

CONFIG_DIR = Path.home() / ".config" / "agnes"
PRESETS_PATH = CONFIG_DIR / "refine-presets.yaml"
OUTPUT_DIR = get_default_dir()


def _load_presets() -> dict:
    """加载预设风格配置"""
    import yaml
    if PRESETS_PATH.exists():
        with open(PRESETS_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("presets", {}) if data else {}
    return {}


def list_presets() -> list[dict]:
    """列出所有可用预设风格"""
    presets = _load_presets()
    return [{"key": k, "name": v["name"], "prompt": v["prompt"]} for k, v in presets.items()]



def refine(
    image: str,
    operation: str,
    preset: str | None = None,
    custom_prompt: str | None = None,
    size: str = "2K",
    ratio: str = "16:9",
) -> str:
    """执行一次图片精修操作。

    Args:
        image: 本地路径或 URL
        operation: 操作描述，如 "去噪并调亮"
        preset: 预设风格 key（可选）
        custom_prompt: 自定义 prompt（可选，覆盖预设）
        size: 输出尺寸
        ratio: 宽高比

    Returns:
        保存的文件路径
    """
    if custom_prompt:
        prompt = custom_prompt
    elif preset:
        presets = _load_presets()
        if preset in presets:
            prompt = presets[preset]["prompt"]
        else:
            prompt = operation
    else:
        prompt = operation

    client = ImageClient()
    image_url = client.i2i(image, prompt, size=size, ratio=ratio)
    timestamp = int(time.time())
    save_path = OUTPUT_DIR / f"agnes-refine-{timestamp}.png"
    save_path.write_bytes(client.download(image_url))
    return str(save_path)
