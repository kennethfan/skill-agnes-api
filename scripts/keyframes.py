"""关键帧动画 (Keyframe Animation)"""

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
    "prompt": "Generate a smooth cinematic transition between the keyframes, maintaining visual consistency and natural camera movement",
    "extra_body": {
        "image": [
            "https://example.com/keyframe1.png",
            "https://example.com/keyframe2.png",
        ],
        "mode": "keyframes",
    },
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
