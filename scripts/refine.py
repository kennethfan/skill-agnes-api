"""图片精修核心模块 — 基于 AGNES i2i

两种使用方式：
1. AI 驱动模式：被 agent 调用，传入自然语言指令
2. 工具模式：通过 refine-cli.py CLI 调用

用法示例（AI 驱动）：
    from refine import refine_image
    path = refine_image("photo.jpg", "去噪并调亮")
    path = refine_image("https://example.com/photo.jpg", "变成宫崎骏风格")
"""

import base64
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# --- 路径配置 ---

if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    CONFIG_DIR = Path.home() / ".config" / "agnes"

KEY_PATH = CONFIG_DIR / "key"
PRESETS_PATH = CONFIG_DIR / "refine-presets.yaml"
OUTPUT_DIR = Path.home() / "agent" / "media" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"


def _get_key() -> str:
    return (KEY_PATH).read_text(encoding="utf-8").strip()


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


def _resolve_image(image: str) -> str:
    """将图片输入转为 AGNES 可用的 URL 或 Data URI"""
    from urllib.parse import urlparse
    parsed = urlparse(image)
    if parsed.scheme in ("http", "https"):
        return image
    import base64
    path = Path(image).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image}")
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


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
    import json
    import time
    from urllib.request import Request, urlopen

    # 构建 prompt
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

    # 处理输入图片
    image_ref = _resolve_image(image)

    body = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "size": size,
        "ratio": ratio,
        "extra_body": {
            "image": [image_ref],
            "response_format": "url",
        },
    }

    req = Request(
        "https://apihub.agnes-ai.com/v1/images/generations",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req) as resp:
        data = json.loads(resp.read())

    image_url = data["data"][0]["url"]
    timestamp = int(time.time())
    save_path = OUTPUT_DIR / f"agnes-refine-{timestamp}.png"

    with urlopen(image_url) as img_resp:
        save_path.write_bytes(img_resp.read())

    return str(save_path)
