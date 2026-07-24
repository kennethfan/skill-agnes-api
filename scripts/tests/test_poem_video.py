"""Tests for poem_video.py — _wrap_text, _auto_fit_subtitle."""

import pytest


# ─── _wrap_text ──────────────────────────────────────────────────

class TestWrapText:
    """Seam: _wrap_text — text wrapping by Chinese character count."""

    def test_short_text_no_wrap(self):
        """Text shorter than max_chars is returned as-is."""
        from poem_video import _wrap_text
        assert _wrap_text("静夜思", max_chars=15) == "静夜思"

    def test_long_text_wraps_by_char_count(self):
        """Text longer than max_chars is split into lines."""
        from poem_video import _wrap_text
        text = "床前明月光疑是地上霜举头望明月低头思故乡"
        result = _wrap_text(text, max_chars=5)
        assert "\n" in result
        lines = result.split("\n")
        assert all(len(line) <= 5 for line in lines)

    def test_wrap_at_punctuation(self):
        """_wrap_text prefers splitting after punctuation."""
        from poem_video import _wrap_text
        text = "白日依山尽，黄河入海流。欲穷千里目，更上一层楼。"
        result = _wrap_text(text, max_chars=10)
        lines = result.split("\n")
        # Should split at periods
        assert len(lines) >= 2

    def test_wrap_no_punctuation_breaks_at_limit(self):
        """Without punctuation, text breaks exactly at max_chars."""
        from poem_video import _wrap_text
        text = "一二三四五六七八九十一二三四五六七八九十"
        result = _wrap_text(text, max_chars=10)
        lines = result.split("\n")
        assert all(len(line) <= 10 for line in lines)
        assert lines[0] == "一二三四五六七八九十"

    def test_wrap_exact_match(self):
        """Text exactly matching max_chars is not wrapped."""
        from poem_video import _wrap_text
        assert _wrap_text("春眠不觉晓", max_chars=5) == "春眠不觉晓"

    def test_wrap_remaining_text_appended(self):
        """Short remainder after the last split is appended."""
        from poem_video import _wrap_text
        text = "这是一段比较长的文字需要被换行处理"
        result = _wrap_text(text, max_chars=5)
        lines = result.split("\n")
        assert lines[-1] == "处理"
        assert len(lines) >= 2

    def test_wrap_punctuation_at_boundary(self):
        """Punctuation at the split boundary is handled correctly."""
        from poem_video import _wrap_text
        text = "测试文本，这里有个逗号，然后继续"
        result = _wrap_text(text, max_chars=7)
        lines = result.split("\n")
        assert len(lines) >= 2


# ─── _auto_fit_subtitle ──────────────────────────────────────────

class TestAutoFitSubtitle:
    """Seam: _auto_fit_subtitle — font size adaptation."""

    def test_short_text_uses_max_font(self):
        """Short text fits at font_max with max_chars=15."""
        from poem_video import _auto_fit_subtitle
        text = "静夜思"
        wrapped, size = _auto_fit_subtitle(text, "", max_width=660, font_max=42, font_min=28)
        assert size == 42

    def test_long_text_reduces_font_size(self):
        """Longer text may reduce font size to fit max_width."""
        from poem_video import _auto_fit_subtitle
        text = "床前明月光疑是地上霜举头望明月低头思故乡"
        wrapped, size = _auto_fit_subtitle(text, "", max_width=660, font_max=42, font_min=28)
        assert 28 <= size <= 42

    def test_fallback_to_min_font(self):
        """Very long text falls back to min font size and narrowest wrap."""
        from poem_video import _auto_fit_subtitle
        text = "a" * 100
        wrapped, size = _auto_fit_subtitle(text, "", max_width=10, font_max=42, font_min=28)
        assert size == 28

    def test_fallback_always_returns(self):
        """Even with degenerate inputs, _auto_fit_subtitle returns a result."""
        from poem_video import _auto_fit_subtitle
        text = "x" * 200
        wrapped, size = _auto_fit_subtitle(text, "", max_width=1, font_max=42, font_min=28)
        assert isinstance(wrapped, str)
        assert isinstance(size, int)

    def test_result_never_exceeds_max_width_each_line(self):
        """Each line of the result must individually fit within max_width."""
        from poem_video import _auto_fit_subtitle
        text = "君不见黄河之水天上来奔流到海不复回"
        from poem_video import _measure_text_width

        font_path = ""
        wrapped, size = _auto_fit_subtitle(text, font_path, max_width=660, font_max=42, font_min=28)
        for line in wrapped.split("\n"):
            w = _measure_text_width(line, font_path, size)
            assert w <= 660, f"Line '{line}' width {w} > max_width 660"
