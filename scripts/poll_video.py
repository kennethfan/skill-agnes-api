"""异步视频结果轮询 + 自动保存 — 使用 AgnesClient。

使用前将 VIDEO_ID 替换为实际的 video_id。
"""

import time
from pathlib import Path
from urllib.parse import urlencode
from client import AgnesClient
from utils import get_default_dir

VIDEO_ID = "video_YOUR_VIDEO_ID"
OUTPUT_DIR = get_default_dir()

client = AgnesClient()

while True:
    data = client.get(f"/agnesapi?{urlencode({'video_id': VIDEO_ID})}")
    status = data.get("status", "")
    print(f"Status: {status}")

    if status == "completed":
        video_url = data.get("url", "")
        print(f"Download URL: {video_url}")
        timestamp = int(time.time())
        save_path = OUTPUT_DIR / f"agnes-video-{timestamp}.mp4"
        save_path.write_bytes(client.download(video_url))
        print(f"Saved to: {save_path}")
        break
    elif status == "failed":
        error = data.get("error", "unknown error")
        print(f"Error: {error}")
        break

    time.sleep(5)
