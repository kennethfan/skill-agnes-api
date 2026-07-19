"""图生视频 (Image-to-Video)"""

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

if sys.platform == "win32":
    key_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    key_dir = Path.home() / ".config" / "agnes"
KEY = (key_dir / "key").read_text(encoding="utf-8").strip()

body = {
    "model": "agnes-video-v2.0",
    "prompt": "The woman slowly turns around and looks back at the camera, natural facial expression, cinematic camera movement",
    "image": "https://example.com/image.png",
    "num_frames": 121,
    "frame_rate": 24,
}

req = Request(
    "https://apihub.agnes-ai.com/v1/videos",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    method="POST",
)

with urlopen(req) as resp:
    result = json.loads(resp.read())
print(json.dumps(result, indent=2))
