"""AGNES API 共享工具函数。"""

import json
import os
import sys
import base64
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode

OUTPUT_DIR_IMAGES = Path.home() / "agent" / "media" / "images"
OUTPUT_DIR_VIDEOS = Path.home() / "agent" / "media" / "videos"
BASE_URL = "https://apihub.agnes-ai.com"


def _config_dir() -> Path:
    """返回平台适配的配置文件目录。"""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
    return Path.home() / ".config" / "agnes"


def get_api_key() -> str:
    """从文件或环境变量读取 API key。"""
    key_file = _config_dir() / "key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return os.environ.get("AGNES_API_KEY", "")


def api_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def api_post(path: str, body: dict) -> dict:
    """发起 POST 请求并返回解析后的 JSON。"""
    req = Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        headers=api_headers(),
        method="POST",
    )
    with urlopen(req) as resp:
        return json.loads(resp.read())


def api_get(path: str) -> dict:
    """发起 GET 请求并返回解析后的 JSON。"""
    req = Request(f"{BASE_URL}{path}", headers=api_headers(), method="GET")
    with urlopen(req) as resp:
        return json.loads(resp.read())


def download_file(url: str, save_path: Path):
    """下载文件到本地路径。"""
    with urlopen(url) as resp:
        save_path.write_bytes(resp.read())


def ensure_dirs():
    """确保输出目录存在。"""
    OUTPUT_DIR_IMAGES.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR_VIDEOS.mkdir(parents=True, exist_ok=True)
