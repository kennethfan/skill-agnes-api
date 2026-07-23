"""关键帧动画 (Keyframe Animation) — 使用 VideoClient"""

from client import VideoClient

client = VideoClient()
task_id = client.create({
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
})
print(f"Task ID: {task_id}")
