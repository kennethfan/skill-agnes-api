"""文生视频 (Text-to-Video) — 使用 VideoClient"""

import json
from client import VideoClient

client = VideoClient()
task_id = client.create({
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion",
    "height": 768,
    "width": 1152,
    "num_frames": 121,
    "frame_rate": 24,
})
print(f"Task ID: {task_id}")
