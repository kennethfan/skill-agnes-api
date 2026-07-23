"""图生视频 (Image-to-Video) — 使用 VideoClient"""

from client import VideoClient

client = VideoClient()
task_id = client.create({
    "prompt": "The woman slowly turns around and looks back at the camera, natural facial expression, cinematic camera movement",
    "image": "https://example.com/image.png",
    "num_frames": 121,
    "frame_rate": 24,
})
print(f"Task ID: {task_id}")
