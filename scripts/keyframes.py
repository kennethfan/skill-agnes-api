"""关键帧动画 (Keyframe Animation) — 使用 VideoClient (Video 2.5 Flash)"""

from client import VideoClient

client = VideoClient()
task_id = client.create({
    "prompt": "Generate a smooth cinematic transition between the keyframes, maintaining visual consistency and natural camera movement",
    "mode": "keyframe",
    "size": "720P",
    "aspect_ratio": "16:9",
    "seconds": "5",
    "first_frame": "https://example.com/keyframe1.png",
    "last_frame": "https://example.com/keyframe2.png",
})
print(f"Task ID: {task_id}")
