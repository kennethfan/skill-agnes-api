"""文生图 — Base64 输出 (不需要 URL 时) — 使用 ImageClient"""

import base64
import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir

OUTPUT_DIR = get_default_dir()

client = ImageClient()
data = client.post(
    "/v1/images/generations",
    {
        "model": "agnes-image-2.1-flash",
        "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
        "size": "1024x768",
        "return_base64": True,
    },
)
b64_data = data["data"][0]["b64_json"]
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-base64-{timestamp}.png"
save_path.write_bytes(base64.b64decode(b64_data))
print(f"Saved to: {save_path}")
