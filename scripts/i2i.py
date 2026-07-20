"""图生图 / 图片编辑 (Image-to-Image)"""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from utils import get_default_dir, get_api_key

OUTPUT_DIR = get_default_dir()

body = {
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform the scene into a rain-soaked cyberpunk night with neon reflections while preserving the original composition",
    "size": "1024x768",
    "extra_body": {
        "image": ["https://example.com/input-image.png"],
        "response_format": "url",
    },
}

req = Request(
    "https://apihub.agnes-ai.com/v1/images/generations",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {get_api_key()}", "Content-Type": "application/json"},
    method="POST",
)

with urlopen(req) as resp:
    data = json.loads(resp.read())

image_url = data["data"][0]["url"]
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-i2i-{timestamp}.png"

with urlopen(image_url) as img_resp:
    save_path.write_bytes(img_resp.read())
print(f"Saved to: {save_path}")
