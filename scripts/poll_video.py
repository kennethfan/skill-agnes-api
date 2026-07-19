"""异步视频结果轮询 + 自动保存。

使用前将 VIDEO_ID 替换为实际的 video_id。
"""

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

VIDEO_ID = "video_YOUR_VIDEO_ID"
OUTPUT_DIR = Path.home() / "agent" / "media" / "videos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if sys.platform == "win32":
    key_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    key_dir = Path.home() / ".config" / "agnes"
KEY = (key_dir / "key").read_text(encoding="utf-8").strip()

while True:
    url = f"https://apihub.agnes-ai.com/agnesapi?{urlencode({'video_id': VIDEO_ID})}"
    req = Request(url, headers={"Authorization": f"Bearer {KEY}"}, method="GET")
    with urlopen(req) as resp:
        data = json.loads(resp.read())

    status = data.get("status", "")
    print(f"Status: {status}")

    if status == "completed":
        video_url = data.get("url", "")
        print(f"Download URL: {video_url}")
        timestamp = int(time.time())
        save_path = OUTPUT_DIR / f"agnes-video-{timestamp}.mp4"
        with urlopen(video_url) as vresp:
            save_path.write_bytes(vresp.read())
        print(f"Saved to: {save_path}")
        break
    elif status == "failed":
        error = data.get("error", "unknown error")
        print(f"Error: {error}")
        break

    time.sleep(5)
