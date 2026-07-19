"""文生图 — Base64 输出 (不需要 URL 时)"""

import json
import os
import sys
import time
import base64
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
    "prompt": "A clean product photo of a glass cube on a white studio background, soft shadows, high detail",
    "size": "1024x768",
    "return_base64": True,
}

req = Request(
    "https://apihub.agnes-ai.com/v1/images/generations",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    method="POST",
)

with urlopen(req) as resp:
    data = json.loads(resp.read())

b64_data = data["data"][0]["b64_json"]
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-base64-{timestamp}.png"
save_path.write_bytes(base64.b64decode(b64_data))
print(f"Saved to: {save_path}")
