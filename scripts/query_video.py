"""按 task_id 查询视频任务状态（备用方式）— 使用 AgnesClient。

使用前将 TASK_ID 替换为实际的 task_id。
"""

import json
from client import AgnesClient

TASK_ID = "<TASK_ID>"

client = AgnesClient()
data = client.get(f"/v1/videos/{TASK_ID}")
print(json.dumps(data, indent=2))
