"""验证 AGNES API key 是否可用。

检查逻辑: 读取 ~/.config/agnes/paths.yaml → agnes_api_keys 列表，
遍历其中的 key 文件路径，验证文件存在且非空。
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    config_dir = Path(__file__).resolve().parent
else:
    config_dir = Path.home() / ".config" / "agnes"

config_path = config_dir / "paths.yaml"

if not config_path.exists():
    print("paths.yaml missing — create ~/.config/agnes/paths.yaml with `agnes_api_keys`")
    sys.exit(1)

import yaml

with open(config_path, encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}

keys = cfg.get("agnes_api_keys", [])
if not keys:
    print("agnes_api_keys not set in paths.yaml — add a list of key file paths")
    sys.exit(1)

for fp in keys:
    path = Path(fp).expanduser()
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            print(f"  ✅ {fp} ({len(content)} chars)")
        else:
            print(f"  ⚠️  {fp} — empty file")
    else:
        print(f"  ❌ {fp} — file not found")
