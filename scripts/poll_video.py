"""异步视频结果轮询 + 自动保存。

使用前将 VIDEO_ID 替换为实际的 video_id。
"""

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from utils import get_default_dir, get_api_key

VIDEO_ID = "video_YOUR_VIDEO_ID"
OUTPUT_DIR = get_default_dir()

while True:
    url = f"https://apihub.agnes-ai.com/agnesapi?{urlencode({'video_id': VIDEO_ID})}"
    req = Request(url, headers={"Authorization": f"Bearer {get_api_key()}"}, method="GET")
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
