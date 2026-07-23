"""文生图 (Text-to-Image) — 使用 ImageClient"""

import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir

OUTPUT_DIR = get_default_dir()

client = ImageClient()
image_url = client.t2i(
    "A luminous floating city above a misty canyon at sunrise, cinematic realism, wide-angle composition",
    size="2K",
    ratio="16:9",
)
timestamp = int(time.time())
save_path = OUTPUT_DIR / f"agnes-image-t2i-{timestamp}.png"
save_path.write_bytes(client.download(image_url))
print(f"Saved to: {save_path}")
