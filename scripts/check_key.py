"""验证 AGNES API key 是否可用。"""

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    key_file = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes" / "key"
else:
    key_file = Path.home() / ".config" / "agnes" / "key"

if key_file.exists():
    print("key file found")
else:
    print("key file missing")

if os.environ.get("AGNES_API_KEY"):
    print("env var found")
else:
    print("env var missing")
