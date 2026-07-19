"""多图合成 (Multi-Image Composition)"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

OUTPUT_DIR = Path.home() / "agent" / "media" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if sys.platform == "win32":
    key_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    key_dir = Path.home() / ".config" / "agnes"
KEY = (key_dir / "key").read_text(encoding="utf-8").strip()

body = {
    "model": "agnes-image-2.1-flash",
    "prompt": "Combine the two characters into an intense fantasy battle scene, dynamic lighting, detailed background, cinematic composition",
    "size": "1024x768",
    "extra_body": {
        "image": [
            "https://example.com/character-1.png",
            "https://example.com/character-2.png",
        ],
        "response_format": "url",
    },
}

req = Request(
    "https://apihub.agnes-ai.com/v1/images/generations",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    method="POST",
)

with urlopen(req) as resp:
    data = json.loads(resp.read())

image_url = data["data"][0]["url"]
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-compose-{timestamp}.png"

with urlopen(image_url) as img_resp:
    save_path.write_bytes(img_resp.read())
print(f"Saved to: {save_path}")
