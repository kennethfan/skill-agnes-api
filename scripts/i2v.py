"""图生视频 (Image-to-Video) — 使用 VideoClient (Video 2.5 Flash)"""

from client import VideoClient

client = VideoClient()
task_id = client.create({
    "prompt": "The woman slowly turns around and looks back at the camera, natural facial expression, cinematic camera movement",
    "mode": "reference",
    "size": "720P",
    "aspect_ratio": "16:9",
    "seconds": "5",
    "images": ["https://example.com/image.png"],
})
print(f"Task ID: {task_id}")
