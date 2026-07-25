"""Tests for story_video.py — _resolve_voice, checkpoint _stage_done."""

import json
from pathlib import Path

import pytest


# ─── _resolve_voice ──────────────────────────────────────────────

class TestResolveVoice:
    """Seam: _resolve_voice — role mapping, overrides, default fallback."""

    def test_direct_match(self):
        """Known role returns its mapped voice."""
        from story_video import _resolve_voice
        voice = _resolve_voice("旁白")
        assert voice == "zh-CN-YunxiaNeural"

    def test_override_takes_priority(self):
        """YAML voice_overrides takes priority over built-in mapping."""
        from story_video import _resolve_voice
        voice = _resolve_voice("小红帽", voice_overrides={"小红帽": "zh-CN-XiaoyiNeural"})
        assert voice == "zh-CN-XiaoyiNeural"

    def test_override_for_unknown_role(self):
        """Override works for character not in ROLE_VOICE_MAP."""
        from story_video import _resolve_voice
        voice = _resolve_voice("树精", voice_overrides={"树精": "zh-CN-YunxiNeural"})
        assert voice == "zh-CN-YunxiNeural"

    def test_unknown_role_returns_default(self):
        """Unknown role without override returns default voice."""
        from story_video import _resolve_voice
        voice = _resolve_voice("树精")
        assert voice == "zh-CN-YunxiaNeural"

    def test_empty_character_returns_default(self):
        """Empty character string returns default voice."""
        from story_video import _resolve_voice
        voice = _resolve_voice("")
        assert voice == "zh-CN-YunxiaNeural"

    def test_override_none(self):
        """None voice_overrides is treated identically to no overrides."""
        from story_video import _resolve_voice
        voice = _resolve_voice("大灰狼", None)
        assert voice == "zh-CN-YunjianNeural"

    def test_role_variants_all_map_correctly(self):
        """All listed role variants in ROLE_VOICE_MAP resolve correctly."""
        from story_video import _resolve_voice, ROLE_VOICE_MAP
        for role, expected_voice in ROLE_VOICE_MAP.items():
            assert _resolve_voice(role) == expected_voice, f"Role '{role}' should map to {expected_voice}"


# ─── checkpoint _stage_done ──────────────────────────────────────

class TestStageDone:
    """Seam: _stage_done — None checkpoint, stage done, stage not done."""

    def test_none_checkpoint_returns_false(self):
        """_stage_done returns False when checkpoint is None."""
        from story_video import _stage_done
        assert _stage_done(None, "scenes") is False

    def test_stage_done_returns_true(self):
        """_stage_done returns True when stage is 'done'."""
        from story_video import _stage_done
        checkpoint = {"stages": {"scenes": "done"}}
        assert _stage_done(checkpoint, "scenes") is True

    def test_stage_not_done_returns_false(self):
        """_stage_done returns False when stage is not 'done'."""
        from story_video import _stage_done
        checkpoint = {"stages": {"scenes": "started"}}
        assert _stage_done(checkpoint, "scenes") is False

    def test_stage_missing_returns_false(self):
        """_stage_done returns False when stage key doesn't exist."""
        from story_video import _stage_done
        checkpoint = {"stages": {"scenes": "done"}}
        assert _stage_done(checkpoint, "audio") is False

    def test_empty_stages_returns_false(self):
        """_stage_done returns False when stages dict is empty."""
        from story_video import _stage_done
        checkpoint = {"stages": {}}
        assert _stage_done(checkpoint, "scenes") is False

    def test_checkpoint_without_stages_key(self):
        """_stage_done handles checkpoint missing 'stages' key gracefully."""
        from story_video import _stage_done
        checkpoint = {"title": "test"}
        # Should not crash — .get("stages", {}) returns empty dict
        assert _stage_done(checkpoint, "scenes") is False
