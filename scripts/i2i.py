"""图生图 / 图片编辑 (Image-to-Image) — 使用 ImageClient"""

import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir

OUTPUT_DIR = get_default_dir()

client = ImageClient()
image_url = client.i2i(
    "https://example.com/input-image.png",
    "Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition",
    size="1024x768",
)
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-i2i-{timestamp}.png"
save_path.write_bytes(client.download(image_url))
print(f"Saved to: {save_path}")
