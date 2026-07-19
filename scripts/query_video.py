"""按 task_id 查询视频任务状态（备用方式）。

使用前将 TASK_ID 替换为实际的 task_id。
"""

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

TASK_ID = "<TASK_ID>"

if sys.platform == "win32":
    key_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    key_dir = Path.home() / ".config" / "agnes"
KEY = (key_dir / "key").read_text(encoding="utf-8").strip()

req = Request(
    f"https://apihub.agnes-ai.com/v1/videos/{TASK_ID}",
    headers={"Authorization": f"Bearer {KEY}"},
    method="GET",
)

with urlopen(req) as resp:
    data = json.loads(resp.read())
print(json.dumps(data, indent=2))
