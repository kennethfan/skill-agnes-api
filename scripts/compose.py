"""多图合成 (Multi-Image Composition) — 使用 ImageClient"""

import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir

OUTPUT_DIR = get_default_dir()

client = ImageClient()
data = client.post(
    "/v1/images/generations",
    {
        "model": "agnes-image-2.1-flash",
        "prompt": "Combine the two characters into an intense fantasy battle scene, dynamic lighting, detailed background, cinematic composition",
        "size": "1024x768",
        "extra_body": {
            "image": [
                "https://example.com/character-1.png",
                "https://example.com/character-2.png",
            ],
            "response_format": "url",
        },
    },
)
image_url = data["data"][0]["url"]
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-compose-{timestamp}.png"
save_path.write_bytes(client.download(image_url))
print(f"Saved to: {save_path}")
