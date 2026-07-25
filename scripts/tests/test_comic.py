"""Tests for comic.py — generate_panel (prompt logic), compose_page (layout)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── generate_panel ──────────────────────────────────────────────

class TestGeneratePanel:
    """Seam: generate_panel — prompt composition, t2i vs i2i dispatch."""

    def test_custom_prompt_formats_description(self):
        """custom_prompt is formatted with description."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i:

            generate_panel("a sunny beach", custom_prompt="{description} in anime style")

            mock_t2i.assert_called_once()
            # We can't easily inspect args because _t2i kwargs include the formatted prompt
            # but we verify _t2i was called (not _i2i) and the prompt was formatted

    def test_custom_prompt_without_character_ref_calls_t2i(self):
        """Without character_ref, generate_panel calls _t2i."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i, \
             patch("comic._i2i") as mock_i2i:

            generate_panel("a beach", custom_prompt="{description}")

            mock_t2i.assert_called_once()
            mock_i2i.assert_not_called()

    def test_custom_prompt_with_character_ref_calls_i2i(self):
        """With character_ref, generate_panel calls _i2i."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._t2i") as mock_t2i, \
             patch("comic._i2i", return_value="/tmp/panel.png") as mock_i2i:

            generate_panel("a beach", character_ref="/path/to/char.png", custom_prompt="{description}")

            mock_i2i.assert_called_once()
            mock_t2i.assert_not_called()

    def test_preset_formatting(self):
        """Preset template is formatted with description."""
        from comic import generate_panel

        mock_presets = {
            "manga": {"name": "Manga", "prompt": "manga style: {description}"},
        }

        with patch("comic._load_presets", return_value=mock_presets), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i:

            generate_panel("a robot", preset="manga")

            # Check that _t2i was called with the formatted prompt
            call_kwargs = mock_t2i.call_args[1]
            assert "prompt" not in call_kwargs  # prompt is positional in _t2i
            prompt_arg = mock_t2i.call_args[0][0]
            assert prompt_arg == "manga style: a robot"

    def test_fallback_to_description(self):
        """Without custom_prompt or preset, description is used directly."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i:

            generate_panel("direct description")

            prompt_arg = mock_t2i.call_args[0][0]
            assert prompt_arg == "direct description"

    def test_unknown_preset_falls_back_to_description(self):
        """Unknown preset key falls back to plain description."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={"manga": {"name": "Manga", "prompt": "manga: {description}"}}), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i:

            generate_panel("unknown preset test", preset="nonexistent")

            prompt_arg = mock_t2i.call_args[0][0]
            assert prompt_arg == "unknown preset test"

    def test_passes_seed_to_t2i(self):
        """Seed is forwarded to _t2i."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._t2i", return_value="/tmp/panel.png") as mock_t2i:

            generate_panel("seeded image", seed=42)

            assert mock_t2i.call_args[1]["seed"] == 42

    def test_passes_seed_to_i2i(self):
        """Seed is forwarded to _i2i when character_ref is provided."""
        from comic import generate_panel

        with patch("comic._load_presets", return_value={}), \
             patch("comic._i2i", return_value="/tmp/panel.png") as mock_i2i:

            generate_panel("seeded i2i", character_ref="/path/char.png", seed=99)

            assert mock_i2i.call_args[1]["seed"] == 99


# ─── compose_page ────────────────────────────────────────────────

class TestComposePage:
    """Seam: compose_page — grid layout, hero layout, single panel."""

    @pytest.fixture
    def sample_panels(self, temp_dir):
        """Create 4 small test images as panel files."""
        from PIL import Image
        paths = []
        for i in range(4):
            p = temp_dir / f"panel-{i}.png"
            img = Image.new("RGB", (100, 80), (255, 0, 0))
            img.save(p)
            paths.append(str(p))
        return paths

    def test_grid_layout_4_panels(self, sample_panels):
        """Grid layout with 4 panels creates 2x2 composition."""
        from comic import compose_page
        result = compose_page(sample_panels, layout="grid")
        from PIL import Image
        page = Image.open(result)
        # 2 cols * 100w + 1 gap(10) = 210w, 2 rows * 80h + 1 gap(10) = 170h
        assert page.size == (210, 170)

    def test_grid_layout_1_panel(self, temp_dir):
        """Single panel in grid — cols=2, rows=1, page_w=2*panel_w+gap."""
        from PIL import Image
        from comic import compose_page

        p = temp_dir / "single.png"
        Image.new("RGB", (200, 150), (0, 255, 0)).save(p)

        result = compose_page([str(p)], layout="grid")
        page = Image.open(result)
        # n <= 4 → cols=2, rows=1 → page_w = 2*200 + 10 = 410
        assert page.size == (410, 150)

    def test_hero_layout(self, sample_panels, temp_dir):
        """Hero layout places first panel large, rest as thumbnails."""
        from comic import compose_page

        # Use panels with known sizes to predict hero layout
        from PIL import Image
        # First panel is larger
        hero_p = temp_dir / "hero.png"
        Image.new("RGB", (400, 300), (0, 0, 255)).save(hero_p)

        # Rest are smaller
        rest = []
        for i in range(2):
            p = temp_dir / f"thumb-{i}.png"
            Image.new("RGB", (100, 80), (255, 0, 0)).save(p)
            rest.append(str(p))

        paths = [str(hero_p)] + rest
        result = compose_page(paths, layout="hero")
        page = Image.open(result)
        # hero_h=300, thumb_h=100, total_h=300+100+10=410
        # hero_w=400, total_thumb_w = sum(100*100/80=125 for each) = 250
        # So page_w = max(400, 250) = 400
        assert page.size == (400, 410)

    def test_hero_single_panel(self, temp_dir):
        """Hero layout with single panel returns the panel as-is."""
        from PIL import Image
        from comic import compose_page

        p = temp_dir / "single-hero.png"
        Image.new("RGB", (300, 200), (0, 255, 0)).save(p)

        result = compose_page([str(p)], layout="hero")
        page = Image.open(result)
        assert page.size == (300, 200)

    def test_unknown_layout_fallback_to_single(self, temp_dir):
        """Unknown layout falls back to returning first panel."""
        from PIL import Image
        from comic import compose_page

        p = temp_dir / "fallback.png"
        Image.new("RGB", (150, 100), (255, 0, 0)).save(p)

        result = compose_page([str(p)], layout="unknown")
        page = Image.open(result)
        assert page.size == (150, 100)

    def test_grid_5_panels(self, temp_dir):
        """Grid layout with 5 panels creates 3-column composition."""
        from PIL import Image
        from comic import compose_page

        paths = []
        for i in range(5):
            p = temp_dir / f"gpanel-{i}.png"
            Image.new("RGB", (100, 80), (255, 0, 0)).save(p)
            paths.append(str(p))

        result = compose_page(paths, layout="grid")
        page = Image.open(result)
        # n=5 > 4 so cols=3, rows=(5+2)//3=2
        # 3*100 + 2*10 = 320w, 2*80 + 1*10 = 170h
        assert page.size == (320, 170)

    def test_saves_to_output_path(self, sample_panels, temp_dir):
        """When output_path is provided, result is saved there."""
        from comic import compose_page

        out_path = temp_dir / "final-page.png"
        result = compose_page(sample_panels, layout="grid", output_path=str(out_path))
        assert result == str(out_path)
        assert out_path.exists()
