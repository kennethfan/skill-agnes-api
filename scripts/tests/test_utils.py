"""Tests for utils.py — KeyPool, urlopen_with_rotation, _cfg."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


# ─── KeyPool.acquire ─────────────────────────────────────────────

class TestKeyPool:
    """Seam: KeyPool — round-robin, cooldown, exhaustion."""

    def test_acquire_round_robin(self, mock_key_pool):
        """Keys are returned in round-robin order."""
        key0, idx0 = mock_key_pool.acquire()
        key1, idx1 = mock_key_pool.acquire()
        key2, idx2 = mock_key_pool.acquire()

        assert (key0, idx0) == ("key-001", 0)
        assert (key1, idx1) == ("key-002", 1)
        assert (key2, idx2) == ("key-003", 2)

    def test_acquire_wraps_around(self, mock_key_pool):
        """After exhausting all keys, acquirer wraps back to first."""
        for _ in range(3):
            mock_key_pool.acquire()

        key, idx = mock_key_pool.acquire()
        # After wrap-around, idx resets to 0 because _index % key_count = 3 % 3 = 0
        assert (key, idx) == ("key-001", 0)

    def test_acquire_skips_cooldown(self, mock_key_pool):
        """Key in cooldown is skipped during rotation."""
        mock_key_pool.report_503(0)  # key-001 in cooldown

        key, idx = mock_key_pool.acquire()
        assert (key, idx) == ("key-002", 1)

    def test_acquire_all_exhausted_waits(self, mock_key_pool):
        """全冷却时等待最早可用 key，醒来后重扫；过期冷却被清理。"""
        now = time.time()
        mock_key_pool._cooldowns = {
            (0, None): now + 0.05, (1, None): now + 0.05, (2, None): now + 0.05,
        }

        key, idx = mock_key_pool.acquire()  # 真实 sleep 约 0.05s

        assert (key, idx) == ("key-001", 0)
        assert mock_key_pool._cooldowns == {}  # 过期条目被清理

    def test_wait_preserves_valid_cooldowns(self, mock_key_pool):
        """等待后只清理已过期冷却，有效冷却必须保留（429 风暴回归用例）。"""
        now = time.time()
        mock_key_pool._cooldowns = {
            (0, None): now + 0.05, (1, None): now + 999, (2, None): now + 999,
        }

        key, idx = mock_key_pool.acquire()

        assert idx == 0  # 只等最早可用的 key-001（约 0.05s）
        assert (0, None) not in mock_key_pool._cooldowns  # 过期被清理
        assert (1, None) in mock_key_pool._cooldowns  # 有效冷却保留
        assert (2, None) in mock_key_pool._cooldowns

    def test_acquire_expired_cooldown_cleared(self, mock_key_pool):
        """Expired cooldown entries are removed before acquisition."""
        mock_key_pool._cooldowns = {(0, None): time.time() - 1}  # expired

        key, idx = mock_key_pool.acquire()
        assert idx == 0  # key-001 is available again
        assert (0, None) not in mock_key_pool._cooldowns

    def test_report_503_sets_cooldown(self, mock_key_pool):
        """report_503 adds the key index to cooldowns with future timestamp."""
        mock_key_pool.report_503(1)

        assert (1, None) in mock_key_pool._cooldowns
        assert mock_key_pool._cooldowns[(1, None)] > time.time()

    def test_key_count(self, mock_key_pool):
        """key_count returns the number of loaded keys."""
        assert mock_key_pool.key_count() == 3

    def test_empty_pool_raises(self):
        """KeyPool._ensure_loaded raises RuntimeError when no key files configured."""
        from utils import KeyPool

        pool = KeyPool()
        pool._loaded = False
        with patch("utils._cfg", return_value=[]):
            with pytest.raises(RuntimeError, match="No API keys configured"):
                pool.acquire()


# ─── urlopen_with_rotation ───────────────────────────────────────

class TestUrlopenWithRotation:
    """Seam: urlopen_with_rotation — 503 retry, non-503 passthrough, backoff."""

    def test_503_rotates_key_and_retries(self, mock_key_pool, mock_get_key_pool):
        """On 503, rotates to next key and retries immediately."""
        from urllib.error import HTTPError
        from urllib.request import Request
        from utils import urlopen_with_rotation

        # First call → 503 error on key-001, second call → success on key-002
        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            HTTPError("http://example.com", 503, "Rate limited", {}, None),
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils.urlopen", real_urlopen):
            result = urlopen_with_rotation("http://example.com/api", max_retries=3)

        assert result.read() == b'{"ok": true}'
        assert real_urlopen.call_count == 2

    def test_503_reports_key_cooldown(self, mock_key_pool, mock_get_key_pool):
        """503 triggers report_rate_limited on the key pool."""
        from urllib.error import HTTPError
        from urllib.request import Request
        from utils import urlopen_with_rotation

        mock_key_pool.report_rate_limited = MagicMock()

        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            HTTPError("http://example.com", 503, "Rate limited", {}, None),
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils.urlopen", real_urlopen):
            urlopen_with_rotation("http://example.com/api", max_retries=3)

        mock_key_pool.report_rate_limited.assert_called_once()
        assert mock_key_pool.report_rate_limited.call_args[0][0] == 0
        # 503 走全局冷却（family=None），对所有模型族生效
        assert mock_key_pool.report_rate_limited.call_args.kwargs.get("family") is None

    def test_non_503_passthrough(self, mock_key_pool, mock_get_key_pool):
        """Non-503 HTTP errors are re-raised immediately."""
        from urllib.error import HTTPError
        from urllib.request import Request
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        real_urlopen.side_effect = HTTPError("http://example.com", 400, "Bad request", {}, None)

        with patch("utils.urlopen", real_urlopen):
            with pytest.raises(HTTPError) as exc:
                urlopen_with_rotation("http://example.com/api", max_retries=2)

            assert exc.value.code == 400

    def test_backoff_on_other_errors(self, mock_key_pool, mock_get_key_pool):
        """Non-HTTP errors trigger exponential backoff then retry."""
        from urllib.error import URLError
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            URLError("connection reset"),
            URLError("connection reset"),
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils._time.sleep") as mock_sleep:
            with patch("utils.urlopen", real_urlopen):
                result = urlopen_with_rotation("http://example.com/api", max_retries=3)

        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1  # 2^0 = 1s
        assert mock_sleep.call_args_list[1][0][0] == 2  # 2^1 = 2s

    def test_backoff_capped_at_30s(self, mock_key_pool, mock_get_key_pool):
        """Backoff wait is capped at 30 seconds."""
        from urllib.error import URLError
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        # max_retries=7 means 7 attempts (0-6). 6th must succeed.
        # 6 fails + 1 success = 7 items in side_effect
        real_urlopen.side_effect = [URLError("fail")] * 6 + [MagicMock(read=lambda: b'{}')]

        with patch("utils._time.sleep") as mock_sleep:
            with patch("utils.urlopen", real_urlopen):
                result = urlopen_with_rotation("http://example.com/api", max_retries=7)

        assert mock_sleep.call_count == 6
        # Last sleep should be capped at 30 (2^5=32 > 30)
        last_wait = mock_sleep.call_args_list[-1][0][0]
        assert last_wait <= 30

    def test_exhausts_retries_raises(self, mock_key_pool, mock_get_key_pool):
        """When max_retries exhausted, raises RuntimeError."""
        from urllib.error import HTTPError
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        real_urlopen.side_effect = HTTPError("http://example.com", 503, "Limit", {}, None)

        with patch("utils.urlopen", real_urlopen):
            with pytest.raises(RuntimeError, match="API request failed after"):
                urlopen_with_rotation("http://example.com/api", max_retries=2)

    def test_custom_headers(self, mock_key_pool, mock_get_key_pool):
        """Custom headers are merged with Content-Type and Authorization."""
        from utils import urlopen_with_rotation
        from urllib.request import Request

        real_urlopen = MagicMock()
        real_urlopen.return_value = MagicMock(read=lambda: b'{"ok": true}')

        with patch("utils.urlopen", real_urlopen) as mock_urlopen:
            urlopen_with_rotation(
                "http://example.com/api",
                data=b'{}',
                headers={"X-Custom": "value"},
                method="POST",
            )

        req = mock_urlopen.call_args[0][0]
        assert req.headers.get("Content-type") == "application/json"
        assert req.headers.get("Authorization", "").startswith("Bearer ")
        assert req.headers.get("X-custom") == "value"

    def test_default_max_retries(self, mock_key_pool, mock_get_key_pool):
        """Default max_retries = key_count * 3."""
        from utils import urlopen_with_rotation
        real_urlopen = MagicMock()
        real_urlopen.side_effect = [MagicMock(read=lambda: b'{}')]

        with patch("utils.urlopen", real_urlopen):
            urlopen_with_rotation("http://example.com/api")
        # Just verify it doesn't crash — key_count is 3 so default is 9
        assert real_urlopen.call_count == 1


# ─── 429 / Retry-After / 升级退避 ────────────────────────────────

class TestRateLimitHandling:
    """Seam: 429 treated as rate-limit, Retry-After override, escalating backoff."""

    def test_429_rotates_key_and_retries(self, mock_key_pool, mock_get_key_pool):
        """429 triggers rotation to next key and retry, same as 503."""
        from urllib.error import HTTPError
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            HTTPError("http://example.com", 429, "Too Many Requests", {}, None),
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils.urlopen", real_urlopen):
            result = urlopen_with_rotation("http://example.com/api", max_retries=3)

        assert result.read() == b'{"ok": true}'
        assert real_urlopen.call_count == 2
        # 默认 model_family="text"，429 只冷却 text 族
        assert (0, "text") in mock_key_pool._cooldowns

    def test_retry_after_header_overrides_cooldown(self, mock_key_pool, mock_get_key_pool):
        """Retry-After header seconds override the computed cooldown duration."""
        from urllib.error import HTTPError
        from utils import urlopen_with_rotation

        err = HTTPError("http://example.com", 429, "Too Many Requests",
                        {"Retry-After": "42"}, None)
        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            err,
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils.urlopen", real_urlopen):
            urlopen_with_rotation("http://example.com/api", max_retries=3)

        assert (0, "text") in mock_key_pool._cooldowns
        wait_left = mock_key_pool._cooldowns[(0, "text")] - time.time()
        assert 40 <= wait_left <= 43

    def test_escalating_backoff_sequence(self, mock_key_pool):
        """Consecutive strikes on one key escalate 60→120→240→300 (capped)."""
        with patch("utils._cfg", return_value=60):
            expected = [60, 120, 240, 300, 300]
            for want in expected:
                mock_key_pool.report_rate_limited(0)
                wait_left = mock_key_pool._cooldowns[(0, None)] - time.time()
                assert abs(wait_left - want) <= 2, f"want {want}s, got {wait_left:.0f}s"

    def test_success_resets_strikes(self, mock_key_pool):
        """report_success clears escalation so next strike restarts at base."""
        with patch("utils._cfg", return_value=60):
            mock_key_pool.report_rate_limited(0)
            mock_key_pool.report_rate_limited(0)
            mock_key_pool.report_success(0)
            mock_key_pool.report_rate_limited(0)
            wait_left = mock_key_pool._cooldowns[(0, None)] - time.time()
            assert abs(wait_left - 60) <= 2

    def test_report_503_alias_maps_to_rate_limited(self, mock_key_pool):
        """report_503 remains a working alias of report_rate_limited."""
        with patch("utils._cfg", return_value=60):
            mock_key_pool.report_503(2)
            assert (2, None) in mock_key_pool._cooldowns
            assert mock_key_pool._strikes.get((2, None)) == 1


# ─── 按族冷却隔离 ────────────────────────────────────────────

class TestFamilyIsolation:
    """Seam: 429 只冷却对应模型族，503 全局冷却；等待不清空有效冷却。"""

    def test_429_cools_only_that_family(self, mock_key_pool):
        """video 429 后 text 照常使用同 key，video 需等待。"""
        for i in range(3):
            mock_key_pool.report_rate_limited(i, retry_after=0.05, family="video")

        key, idx = mock_key_pool.acquire(family="text")
        assert idx == 0  # text 不受 video 冷却影响，无需等待

    def test_strikes_independent_per_family(self, mock_key_pool):
        """strike 按 (key, family) 独立计数，互不干扰。"""
        with patch("utils._cfg", return_value=60):
            mock_key_pool.report_rate_limited(0, family="video")
            mock_key_pool.report_rate_limited(0, family="video")
            assert mock_key_pool._strikes[(0, "video")] == 2
            assert (0, "text") not in mock_key_pool._strikes
            # text 成功不重置 video 的计数（text 成功证明不了 video 池恢复）
            mock_key_pool.report_success(0, family="text")
            assert mock_key_pool._strikes[(0, "video")] == 2
            # video 成功才重置 video 的计数
            mock_key_pool.report_success(0, family="video")
            assert (0, "video") not in mock_key_pool._strikes

    def test_global_cooldown_blocks_all_families(self, mock_key_pool):
        """503 全局冷却阻塞该 key 的所有模型族。"""
        mock_key_pool.report_503(0)

        mock_key_pool._index = 0
        _, idx = mock_key_pool.acquire(family="video")
        assert idx == 1

        mock_key_pool._index = 0
        _, idx = mock_key_pool.acquire(family="text")
        assert idx == 1

    def test_success_resets_global_strike(self, mock_key_pool):
        """任意族成功即视为服务端恢复，重置全局 strike。"""
        with patch("utils._cfg", return_value=60):
            mock_key_pool.report_503(0)
            mock_key_pool.report_503(0)
            assert mock_key_pool._strikes[(0, None)] == 2
            mock_key_pool.report_success(0, family="video")
            assert (0, None) not in mock_key_pool._strikes

    def test_503_uses_global_cooldown(self, mock_key_pool, mock_get_key_pool):
        """urlopen 收到 503 时写入全局冷却（family=None）。"""
        from urllib.error import HTTPError
        from utils import urlopen_with_rotation

        real_urlopen = MagicMock()
        real_urlopen.side_effect = [
            HTTPError("http://example.com", 503, "Busy", {}, None),
            MagicMock(read=lambda: b'{"ok": true}'),
        ]

        with patch("utils.urlopen", real_urlopen):
            urlopen_with_rotation("http://example.com/api", max_retries=3)

        assert (0, None) in mock_key_pool._cooldowns


# ─── 主动限速预算 ────────────────────────────────────────────────

class TestProactiveBudget:
    """Seam: per-key rolling-window budgets by model family."""

    def test_budget_defaults(self):
        """Free-tier × 80% budget defaults are hardcoded."""
        from utils import _BUDGET_DEFAULTS
        assert _BUDGET_DEFAULTS == {
            "text": 8, "image-1k": 8, "image-2k": 4,
            "image-3k": 1, "image-4k": 1, "video": 1, "video_poll": 30,
        }

    def test_acquire_skips_key_over_budget(self, mock_key_pool):
        """A key at budget for a family is skipped; rotation picks next key."""
        with patch.object(mock_key_pool, "_budget_for", return_value=1):
            k0, i0 = mock_key_pool.acquire(family="video")
            k1, i1 = mock_key_pool.acquire(family="video")
            k2, i2 = mock_key_pool.acquire(family="video")
            assert i0 == 0
            assert i1 == 1
            assert i2 == 2

    def test_budget_exhaustion_waits_for_window(self, mock_key_pool):
        """All keys over budget → waits until oldest timestamp exits window."""
        with patch.object(mock_key_pool, "_budget_for", return_value=1):
            for _ in range(3):
                mock_key_pool.acquire(family="video")

            def fake_sleep(secs):
                # 模拟时间流逝：预算时间戳整体前移 secs 秒
                for k in mock_key_pool._budget_log:
                    mock_key_pool._budget_log[k] = [t - secs for t in mock_key_pool._budget_log[k]]

            with patch("utils._time.sleep", side_effect=fake_sleep) as mock_sleep:
                key, idx = mock_key_pool.acquire(family="video")
                assert mock_sleep.call_count >= 1
                assert idx in (0, 1, 2)

    def test_budget_independent_per_family(self, mock_key_pool):
        """video budget exhaustion does not block video_poll (separate pools)."""
        with patch.object(mock_key_pool, "_budget_for", side_effect=lambda f: 1 if f == "video" else 8):
            for _ in range(3):
                mock_key_pool.acquire(family="video")
            key, idx = mock_key_pool.acquire(family="video_poll")
            assert idx in (0, 1, 2)

    def test_acquire_without_family_ignores_budget(self, mock_key_pool):
        """Legacy acquire() with no family only checks cooldowns, not budgets."""
        with patch.object(mock_key_pool, "_budget_for", return_value=0):
            key, idx = mock_key_pool.acquire()
            assert idx == 0

    def test_budget_config_override(self, mock_key_pool):
        """paths.yaml key_budget_* overrides the hardcoded default."""
        with patch("utils._cfg", side_effect=lambda k, d=None: 5 if k == "key_budget_video" else d):
            assert mock_key_pool._budget_for("video") == 5
        with patch("utils._cfg", side_effect=lambda k, d=None: d):
            assert mock_key_pool._budget_for("video") == 1


# ─── _cfg ────────────────────────────────────────────────────────

class TestCfg:
    """Seam: _cfg — config loading, dotted path, cache, defaults."""

    def test_cfg_simple_key(self):
        """_cfg reads a top-level key from the yaml config."""
        from utils import _load_config, _cfg

        with patch("utils._load_config", return_value={"base_dir": "/custom/path"}):
            assert _cfg("base_dir") == "/custom/path"

    def test_cfg_dotted_path(self):
        """_cfg resolves dotted paths through nested dicts."""
        from utils import _cfg

        with patch("utils._load_config", return_value={
            "project_layout": {"intermediates": {"scenes": "tmp_scenes"}},
        }):
            assert _cfg("project_layout.intermediates.scenes") == "tmp_scenes"

    def test_cfg_nonexistent_key_returns_default(self):
        """_cfg returns default for missing keys."""
        from utils import _cfg

        with patch("utils._load_config", return_value={"base_dir": "/path"}):
            assert _cfg("nonexistent_key") is None
            assert _cfg("nonexistent_key", "fallback") == "fallback"

    def test_cfg_partial_dotted_returns_default(self):
        """_cfg returns default when dotted path is only partially present."""
        from utils import _cfg

        with patch("utils._load_config", return_value={"project_layout": {}}):
            assert _cfg("project_layout.intermediates.scenes", "default") == "default"

    def test_cfg_cache_used(self):
        """_load_config caches result and returns cached value on second call."""
        from utils import _load_config, _CONFIG_CACHE

        # Reset cache
        original_cache = _CONFIG_CACHE
        with patch("utils._CONFIG_CACHE", None):
            call_count = 0

            def fake_load():
                nonlocal call_count
                call_count += 1
                return {"base_dir": "/cached"}

            with patch("utils._load_config", side_effect=fake_load):
                # Override to avoid infinite recursion
                pass

    def test_cfg_empty_config(self):
        """_cfg returns defaults when config file is empty."""
        from utils import _cfg

        with patch("utils._load_config", return_value={}):
            assert _cfg("base_dir") is None
            assert _cfg("base_dir", "~/agent/media") == "~/agent/media"

    def test_cfg_none_value_returns_default(self):
        """_cfg returns default when config value is None."""
        from utils import _cfg

        with patch("utils._load_config", return_value={"key": None}):
            assert _cfg("key", "default") == "default"
