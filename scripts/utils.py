"""AGNES API 共享工具函数。

路径配置从 ~/.config/agnes/paths.yaml 读取，所有脚本通过此模块获取路径。
"""

import json
import os
import sys
import base64
import time
import shutil
from pathlib import Path
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


# ─── API 工具 ──────────────────────────────────────────


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
    """确保兜底目录存在（向后兼容）。"""
    get_default_dir()
