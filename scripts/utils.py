"""AGNES API 共享工具函数。

路径配置从 ~/.config/agnes/paths.yaml 读取，所有脚本通过此模块获取路径。
"""

import json
import os
import sys
import base64
import time as _time
import shutil
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

BASE_URL = "https://apihub.agnes-ai.com"

# ─── 路径配置加载 ───────────────────────────────────────

_CONFIG_CACHE: dict | None = None


def _config_dir() -> Path:
    """返回平台适配的配置文件目录。"""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
    return Path.home() / ".config" / "agnes"


def _load_config() -> dict:
    """加载 paths.yaml，缓存避免重复读取。"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    config_path = _config_dir() / "paths.yaml"
    if config_path.exists():
        import yaml
        with open(config_path, encoding="utf-8") as f:
            _CONFIG_CACHE = yaml.safe_load(f) or {}
    else:
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE


def _cfg(key: str, default=None):
    """从 paths.yaml 读取值，支持点号路径如 'project_layout.intermediates'。"""
    val = _load_config()
    for part in key.split("."):
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
    return val if val is not None else default


# ─── 基础路径 ──────────────────────────────────────────


def get_base_dir() -> Path:
    """AGNES 媒体根目录。"""
    return Path(_cfg("base_dir", "~/agent/media")).expanduser()


def get_assets_dir() -> Path:
    """跨项目共享的输入素材目录。"""
    return get_base_dir() / _cfg("assets_dir", "assets")


def get_default_dir() -> Path:
    """无项目归属的零散文件兜底目录（旧 flat 模式的等价位置）。"""
    d = get_base_dir() / _cfg("default_dir", "tmp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_projects_dir() -> Path:
    """所有项目的根目录。"""
    return get_base_dir() / _cfg("projects_dir", "projects")


# ─── 项目级路径 ────────────────────────────────────────


def get_project_dir(name: str) -> Path:
    """返回 project 根目录。"""
    return get_projects_dir() / name


def get_project_intermediate_dir(name: str, intermediate_type: str) -> Path:
    """返回 project 下的 intermediate 子目录。

    intermediate_type: scenes / panels / bubbles / frames / audio
    """
    layout = _cfg("project_layout.intermediates", {})
    subdir = layout.get(intermediate_type, intermediate_type)
    d = get_project_dir(name) / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_deliverable_dir(name: str, deliverable_type: str) -> Path:
    """返回 project 下的 deliverable 子目录。

    deliverable_type: comic_pages / videos
    """
    layout = _cfg("project_layout.deliverables", {})
    subdir = layout.get(deliverable_type, f"deliverable/{deliverable_type}")
    d = get_project_dir(name) / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_project_dirs(name: str) -> dict[str, Path]:
    """创建 project 的所有子目录，返回 {角色: 路径} 字典。"""
    project_dir = get_project_dir(name)

    inter_layout = _cfg("project_layout.intermediates", {})
    intermediates = {}
    for key, subdir in inter_layout.items():
        d = project_dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        intermediates[key] = d

    deliv_layout = _cfg("project_layout.deliverables", {})
    deliverables = {}
    for key, subdir in deliv_layout.items():
        d = project_dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        deliverables[key] = d

    return {"intermediates": intermediates, "deliverables": deliverables, "root": project_dir}


def cleanup_intermediates(name: str, quiet: bool = False) -> bool:
    """询问用户是否删除 project 的 intermediate 目录。

    Args:
        name: 项目名
        quiet: 如果 True 直接删除不询问

    Returns:
        是否执行了删除
    """
    prompt = _cfg("cleanup.prompt", True)
    default_yes = _cfg("cleanup.default_yes", True)

    inter_layout = _cfg("project_layout.intermediates", {})
    project_dir = get_project_dir(name)
    target_dirs = [project_dir / subdir for subdir in inter_layout.values()]

    # 统计文件数
    total = 0
    for d in target_dirs:
        if d.exists():
            total += sum(1 for _ in d.iterdir())

    if total == 0:
        return False

    if not quiet and prompt:
        if default_yes:
            answer = input(f"Delete {total} intermediate files in '{name}/'? [Y/n]: ").strip().lower()
            if answer == "n":
                return False
        else:
            answer = input(f"Delete {total} intermediate files in '{name}/'? [y/N]: ").strip().lower()
            if answer != "y":
                return False

    for d in target_dirs:
        if d.exists():
            shutil.rmtree(d)
            d.mkdir(parents=True, exist_ok=True)
    print(f"  Cleaned {total} intermediate files from '{name}'")
    return True


# ─── 运行时工具路径 ──────────────────────────────────────


def get_ffmpeg_bin() -> str:
    """返回 ffmpeg 二进制路径，默认走 PATH。"""
    return _cfg("ffmpeg_bin", "ffmpeg")


def get_ffprobe_bin() -> str:
    """返回 ffprobe 二进制路径，默认走 PATH。"""
    return _cfg("ffprobe_bin", "ffprobe")


def get_font_path() -> str:
    """按配置顺序遍历 font_paths，返回第一个存在的字体路径。"""
    paths = _cfg("font_paths", [])
    for fp in paths:
        if Path(fp).expanduser().exists():
            return fp
    return ""


# ─── 向后兼容 ──────────────────────────────────────────

# 旧脚本无 project 概念时使用的兜底目录
OUTPUT_DIR_IMAGES = get_default_dir()
OUTPUT_DIR_VIDEOS = get_default_dir()


# ─── Key Pool（多 key 轮转限流） ───────────────────────────

class KeyPool:
    """Round-robin API key pool with automatic cooldown on 503."""

    def __init__(self):
        self._keys: list[str] = []
        self._loaded = False
        self._index = 0
        self._cooldowns: dict[int, float] = {}

    def _ensure_loaded(self):
        if self._loaded:
            return
        backups = _cfg("agnes_api_keys", [])
        for fp in backups:
            path = Path(fp).expanduser()
            if path.exists():
                self._keys.append(path.read_text(encoding="utf-8").strip())
        if not self._keys:
            raise RuntimeError(
                "No API keys configured. Set `agnes_api_keys` in your paths.yaml file."
            )
        self._loaded = True

    def acquire(self) -> tuple[str, int]:
        """Get the next available key. Returns (key_string, key_index)."""
        self._ensure_loaded()
        now = _time.time()
        expired = [idx for idx, until in list(self._cooldowns.items()) if now >= until]
        for idx in expired:
            del self._cooldowns[idx]

        n = len(self._keys)
        for _ in range(n * 2):
            idx = self._index % n
            self._index += 1
            if idx not in self._cooldowns:
                return self._keys[idx], idx

        earliest = min(self._cooldowns.values())
        wait = max(0.1, earliest - now)
        print(f"  All {n} keys rate-limited, waiting {wait:.0f}s...")
        _time.sleep(wait)
        self._cooldowns.clear()
        idx = self._index % n
        self._index += 1
        return self._keys[idx], idx

    def report_503(self, key_index: int):
        """Mark a key as rate-limited. It enters cooldown for key_cooldown_seconds."""
        cooldown = _cfg("key_cooldown_seconds", 30)
        self._cooldowns[key_index] = _time.time() + cooldown
        available = len(self._keys) - len(self._cooldowns)
        print(f"  Key {key_index} rate-limited, cooling {cooldown}s ({available}/{len(self._keys)} keys available)")

    def key_count(self) -> int:
        self._ensure_loaded()
        return len(self._keys)


_key_pool: KeyPool | None = None


def get_key_pool() -> KeyPool:
    """Get or create the global API key pool."""
    global _key_pool
    if _key_pool is None:
        _key_pool = KeyPool()
    return _key_pool


def urlopen_with_rotation(
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    method: str = "POST",
    timeout: int = 60,
    max_retries: int | None = None,
):
    """urlopen wrapper with automatic key rotation on HTTP 503.

    On 503: rotate to next key and retry immediately (no backoff).
    On other errors: exponential backoff then retry.
    """
    pool = get_key_pool()
    if max_retries is None:
        max_retries = pool.key_count() * 3

    base_headers = {"Content-Type": "application/json", **(headers or {})}

    last_error: Exception | None = None
    for attempt in range(max_retries):
        key, key_idx = pool.acquire()
        hdrs = {**base_headers, "Authorization": f"Bearer {key}"}
        try:
            req = Request(url, data=data, headers=hdrs, method=method)
            return urlopen(req, timeout=timeout)
        except HTTPError as e:
            if e.code == 503:
                pool.report_503(key_idx)
                last_error = e
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                wait = min(2 ** attempt, 30)
                print(f"  Retry {attempt + 1}/{max_retries} after {wait}s: {e}")
                _time.sleep(wait)
                last_error = e
                continue
            raise

    raise RuntimeError(f"API request failed after {max_retries} retries") from last_error


# ─── API 工具 ──────────────────────────────────────────


def get_api_key() -> str:
    """从 paths.yaml agnes_api_keys 的第一把 key 文件读取。"""
    keys = _cfg("agnes_api_keys", [])
    if not keys:
        raise RuntimeError(
            "No API keys configured. Set `agnes_api_keys` in your paths.yaml file."
        )
    path = Path(keys[0]).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"API key file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def api_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
    }


def api_post(path: str, body: dict) -> dict:
    """发起 POST 请求并返回解析后的 JSON（带 key rotation）。"""
    resp = urlopen_with_rotation(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        method="POST",
    )
    return json.loads(resp.read())


def api_get(path: str) -> dict:
    """发起 GET 请求并返回解析后的 JSON（带 key rotation）。"""
    resp = urlopen_with_rotation(
        f"{BASE_URL}{path}",
        method="GET",
    )
    return json.loads(resp.read())


def download_file(url: str, save_path: Path):
    """下载文件到本地路径。"""
    with urlopen(url) as resp:
        save_path.write_bytes(resp.read())


def ensure_dirs():
    """确保兜底目录存在（向后兼容）。"""
    get_default_dir()
