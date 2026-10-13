"""文生视频 (Text-to-Video) — 使用 VideoClient (Video 2.5 Flash)"""

from client import VideoClient

client = VideoClient()
task_id = client.create({
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion",
    "mode": "text",
    "size": "720P",
    "aspect_ratio": "16:9",
    "seconds": "5",
})
print(f"Task ID: {task_id}")
