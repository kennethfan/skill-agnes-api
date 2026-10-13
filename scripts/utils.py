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


def get_image_model() -> str:
    """图片模型名，取 paths.yaml 的 image_model，缺省 agnes-image-2.5-flash。"""
    return _cfg("image_model", "agnes-image-2.5-flash")


def get_video_model() -> str:
    """视频模型名，取 paths.yaml 的 video_model，缺省 agnes-video-2.5-flash。"""
    return _cfg("video_model", "agnes-video-2.5-flash")


# ─── 向后兼容 ──────────────────────────────────────────

# 旧脚本无 project 概念时使用的兜底目录
OUTPUT_DIR_IMAGES = get_default_dir()
OUTPUT_DIR_VIDEOS = get_default_dir()


# ─── Key Pool（多 key 轮转限流） ───────────────────────────

# 主动限速预算默认值（每 key 每滚动 60s 窗口内的最大请求数）。
# 基于 Free 档硬限制 × 80% 余量；硬限制为 1 的档位贴上限。
# 可通过 paths.yaml 的 key_budget_<family>（如 key_budget_image_1k）覆盖。
_BUDGET_DEFAULTS: dict[str, int] = {
    "text": 8,
    "image-1k": 8,
    "image-2k": 4,
    "image-3k": 1,
    "image-4k": 1,
    "video": 1,
    "video_poll": 30,
}

_BUDGET_WINDOW_SECONDS = 60.0
_COOLDOWN_CAP_SECONDS = 300.0


class KeyPool:
    """Round-robin API key pool with escalating cooldown + proactive rate budgets.

    被动层：429/503 → 冷却（升级退避 60→120→240→300s，成功一次重置）；
    主动层：每 key 按模型族维护滚动 60s 窗口预算，接近上限时主动跳过。
    """

    def __init__(self):
        self._keys: list[str] = []
        self._loaded = False
        self._index = 0
        self._cooldowns: dict[tuple[int, str | None], float] = {}
        # 连续限流次数（升级退避用），成功一次即删除；按 (key, family) 独立计数
        self._strikes: dict[tuple[int, str | None], int] = {}
        # (key_index, family) → 最近请求时间戳列表（滚动窗口预算）
        self._budget_log: dict[tuple[int, str], list[float]] = {}

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

    @staticmethod
    def _budget_for(family: str) -> int:
        """查询某模型族的每 key 预算，paths.yaml 可覆盖。"""
        cfg_key = "key_budget_" + family.replace("-", "_")
        return int(_cfg(cfg_key, _BUDGET_DEFAULTS.get(family, 8)))

    def _has_budget(self, key_index: int, family: str, now: float) -> bool:
        """检查 key 在该模型族的滚动窗口内是否仍有预算。"""
        limit = self._budget_for(family)
        log = self._budget_log.get((key_index, family), [])
        in_window = [t for t in log if now - t < _BUDGET_WINDOW_SECONDS]
        return len(in_window) < limit

    def _record(self, key_index: int, family: str | None, now: float):
        """请求发出时记录时间戳（RPM 按服务端收到的请求计数，故在 acquire 时记账）。"""
        if family is None:
            return
        log = self._budget_log.setdefault((key_index, family), [])
        log.append(now)
        cutoff = now - _BUDGET_WINDOW_SECONDS
        self._budget_log[(key_index, family)] = [t for t in log if t >= cutoff]

    def _purge_expired(self, now: float):
        """清理已到期的冷却条目（只删过期，从不清有效冷却）。"""
        expired = [k for k, until in self._cooldowns.items() if now >= until]
        for k in expired:
            del self._cooldowns[k]

    def _cooldown_until(self, key_index: int, family: str | None, now: float) -> float:
        """某 key 对该模型族的冷却到期时刻（0 表示无有效冷却）。

        全局冷却（family=None，由 503 写入）对所有模型族生效。
        """
        latest = 0.0
        for (idx, fam), until in self._cooldowns.items():
            if idx == key_index and (fam is None or fam == family) and until > now:
                latest = max(latest, until)
        return latest

    def _budget_free_at(self, key_index: int, family: str, now: float) -> float:
        """该 key 在此模型族预算恢复的时刻（0 表示当前有预算）。"""
        window = [
            t for t in self._budget_log.get((key_index, family), [])
            if now - t < _BUDGET_WINDOW_SECONDS
        ]
        limit = self._budget_for(family)
        if len(window) < limit:
            return 0.0
        return window[len(window) - limit] + _BUDGET_WINDOW_SECONDS

    def _earliest_unblock_wait(self, family: str | None, now: float) -> float:
        """全部 key 被阻塞时，计算最早有 key 可用的等待秒数。

        每把 key 的可用时刻 = max(冷却到期, 预算窗口滑出)，取所有 key 的
        最早时刻。sleep 到该时刻后至少一把 key 可用，因此不再清空冷却——
        旧逻辑「取 min + 睡后强清」是 429 风暴（strike 虚增到 7/8）的根因。
        """
        waits = []
        for idx in range(len(self._keys)):
            usable_at = self._cooldown_until(idx, family, now)
            if family:
                usable_at = max(usable_at, self._budget_free_at(idx, family, now))
            waits.append(max(0.1, usable_at - now))
        return min(waits) if waits else 1.0

    def acquire(self, family: str | None = None) -> tuple[str, int]:
        """Get the next available key. Returns (key_string, key_index).

        family: 模型族（text / image-1k / video / video_poll 等），
        传入时启用主动预算检查；None 则只检查冷却（兼容旧行为）。
        """
        self._ensure_loaded()
        n = len(self._keys)
        # 正常情况下一次等待后必有 key 可用；60 轮是纯兜底，实际到不了
        for _ in range(60):
            now = _time.time()
            self._purge_expired(now)
            for _ in range(n * 2):
                idx = self._index % n
                self._index += 1
                if self._cooldown_until(idx, family, now) > 0:
                    continue
                if family and not self._has_budget(idx, family, now):
                    continue
                self._record(idx, family, now)
                return self._keys[idx], idx

            # 全部 key 被冷却或预算耗尽：等最早可用的 key，醒来后重扫。
            # 只清理已过期冷却，绝不清有效冷却（旧强清逻辑是 429 风暴根因）。
            wait = self._earliest_unblock_wait(family, now)
            label = f" ({family})" if family else ""
            print(f"  All {n} keys at capacity{label}, waiting {wait:.0f}s...")
            _time.sleep(wait)
        raise RuntimeError("Key pool exhausted: no key became available after waiting")

    def report_rate_limited(self, key_index: int, retry_after: str | int | None = None,
                            family: str | None = None):
        """Mark a key as rate-limited (429/503)。

        family：被限流的模型族（429 按类型池限流，只冷却该族）；
        None 表示全局冷却（503 服务繁忙，对所有族生效）。
        升级退避按 (key, family) 独立计数：base → base×2 → base×4 → 封顶 300s；
        成功一次（report_success）重置。Retry-After 头存在时优先使用其秒数。
        base = paths.yaml key_cooldown_seconds（默认 60）。
        """
        scope = (key_index, family)
        strike = self._strikes.get(scope, 0) + 1
        self._strikes[scope] = strike
        cooldown = None
        if retry_after is not None:
            try:
                cooldown = float(retry_after)
            except (TypeError, ValueError):
                cooldown = None
        if cooldown is None or cooldown < 0:
            base = float(_cfg("key_cooldown_seconds", 60))
            cooldown = min(base * (2 ** (strike - 1)), _COOLDOWN_CAP_SECONDS)
        self._cooldowns[scope] = _time.time() + cooldown
        now = _time.time()
        available = sum(
            1 for idx in range(len(self._keys))
            if self._cooldown_until(idx, family, now) <= 0
        )
        label = f" [{family}]" if family else " [global]"
        print(
            f"  Key {key_index} rate-limited{label} (strike {strike}), "
            f"cooling {cooldown:.0f}s ({available}/{len(self._keys)} keys available)"
        )

    def report_503(self, key_index: int, retry_after: str | int | None = None):
        """向后兼容别名：503 视为服务端全局繁忙，对该 key 全模型族冷却。"""
        self.report_rate_limited(key_index, retry_after=retry_after, family=None)

    def report_success(self, key_index: int, family: str | None = None):
        """请求成功：重置该 key 在此模型族及全局的升级退避计数。"""
        self._strikes.pop((key_index, family), None)
        if family is not None:
            self._strikes.pop((key_index, None), None)

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
    model_family: str = "text",
):
    """urlopen wrapper with automatic key rotation on rate-limit responses.

    On 429/503: rotate to next key and retry immediately (no backoff);
    Retry-After header, when present, sets the cooldown duration.
    On other errors: exponential backoff then retry.
    model_family: 预算模型族（text / image-1k / video / video_poll）。
    """
    pool = get_key_pool()
    if max_retries is None:
        max_retries = pool.key_count() * 3

    base_headers = {"Content-Type": "application/json", **(headers or {})}

    last_error: Exception | None = None
    for attempt in range(max_retries):
        key, key_idx = pool.acquire(family=model_family)
        hdrs = {**base_headers, "Authorization": f"Bearer {key}"}
        try:
            req = Request(url, data=data, headers=hdrs, method=method)
            resp = urlopen(req, timeout=timeout)
            pool.report_success(key_idx, family=model_family)
            return resp
        except HTTPError as e:
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if e.code == 429:
                # 429 按类型池限流：只冷却本次请求的模型族，不影响同 key 其他族
                pool.report_rate_limited(key_idx, retry_after=retry_after,
                                         family=model_family)
            elif e.code == 503:
                # 503 服务端繁忙：全局冷却该 key
                pool.report_503(key_idx, retry_after=retry_after)
            else:
                raise
            last_error = e
            continue
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


def api_post(path: str, body: dict, model_family: str = "text") -> dict:
    """发起 POST 请求并返回解析后的 JSON（带 key rotation）。"""
    resp = urlopen_with_rotation(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        model_family=model_family,
    )
    return json.loads(resp.read())


def api_get(path: str, model_family: str = "text") -> dict:
    """发起 GET 请求并返回解析后的 JSON（带 key rotation）。"""
    resp = urlopen_with_rotation(
        f"{BASE_URL}{path}",
        method="GET",
        model_family=model_family,
    )
    return json.loads(resp.read())


def download_file(url: str, save_path: Path):
    """下载文件到本地路径。"""
    with urlopen(url) as resp:
        save_path.write_bytes(resp.read())


def ensure_dirs():
    """确保兜底目录存在（向后兼容）。"""
    get_default_dir()
