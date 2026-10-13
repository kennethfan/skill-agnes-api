"""Tests for client.py — ImageClient (t2i/i2i), _resolve_image, VideoClient (poll)."""

import json
import time
from unittest.mock import MagicMock, call, patch

import pytest


# ─── ImageClient.t2i ─────────────────────────────────────────────

class TestImageClientT2I:
    """Seam: ImageClient.t2i body construction, seed handling, extras, return parsing."""

    def test_t2i_basic_body(self, mock_urlopen_with_rotation):
        """t2i sends correct minimal body with model, prompt, size."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        url = client.t2i("a cat", size="1024x768")

        client.post.assert_called_once()
        _path, body = client.post.call_args[0]
        assert body == {
            "model": "agnes-image-2.5-flash",
            "prompt": "a cat",
            "size": "1024x768",
        }

    def test_t2i_with_seed(self, mock_urlopen_with_rotation):
        """t2i includes seed in body when provided."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        client.t2i("a cat", seed=42)

        _path, body = client.post.call_args[0]
        assert body["seed"] == 42

    def test_t2i_with_ratio(self, mock_urlopen_with_rotation):
        """t2i includes ratio in body when provided."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        client.t2i("a cat", ratio="16:9")

        _path, body = client.post.call_args[0]
        assert body["ratio"] == "16:9"

    def test_t2i_with_body_extras(self, mock_urlopen_with_rotation):
        """t2i passes extra kwargs into body."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        client.t2i("a cat", extra_body={"quality": "high"}, return_base64=True)

        _path, body = client.post.call_args[0]
        assert body["extra_body"] == {"quality": "high"}
        assert body["return_base64"] is True

    def test_t2i_returns_image_url(self, mock_urlopen_with_rotation):
        """t2i returns the URL string from the response."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/result.png"}]})

        url = client.t2i("a cat")
        assert url == "https://example.com/result.png"

    def test_t2i_default_size(self, mock_urlopen_with_rotation):
        """t2i uses default size '1024x768' when not specified."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        client.t2i("a cat")
        _path, body = client.post.call_args[0]
        assert body["size"] == "1024x768"

    def test_t2i_no_seed_omitted(self, mock_urlopen_with_rotation):
        """t2i omits seed from body when not provided."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        client.t2i("a cat")
        _path, body = client.post.call_args[0]
        assert "seed" not in body


# ─── ImageClient.i2i ─────────────────────────────────────────────

class TestImageClientI2I:
    """Seam: ImageClient.i2i body construction, _resolve_image call, extras."""

    def test_i2i_basic_body(self):
        """i2i sends body with model, prompt, size, and image in extra_body."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        with patch.object(ImageClient, "_resolve_image", return_value="data:image/png;base64,abc"):
            client.i2i("/path/to/img.jpg", "make it vibrant")

        client.post.assert_called_once()
        _path, body = client.post.call_args[0]
        assert body["model"] == "agnes-image-2.5-flash"
        assert body["prompt"] == "make it vibrant"
        assert body["size"] == "1024x768"
        assert body["extra_body"]["image"] == ["data:image/png;base64,abc"]
        assert body["extra_body"]["response_format"] == "url"

    def test_i2i_with_ratio_and_seed(self):
        """i2i includes ratio and seed in body."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        with patch.object(ImageClient, "_resolve_image", return_value="data:image/png;base64,abc"):
            client.i2i("/path/img.jpg", "vivid", ratio="16:9", seed=77)

        _path, body = client.post.call_args[0]
        assert body["ratio"] == "16:9"
        assert body["seed"] == 77

    def test_i2i_calls_resolve_image(self):
        """i2i delegates image resolution to _resolve_image."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        with patch.object(ImageClient, "_resolve_image", return_value="data:image/png;base64,abc") as mock_resolve:
            client.i2i("~/photos/cat.png", "enhance")

            mock_resolve.assert_called_once_with("~/photos/cat.png")

    def test_i2i_preserves_extra_body_image_override(self):
        """i2i respects existing image in extra_body rather than replacing it completely."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/img.png"}]})

        with patch.object(ImageClient, "_resolve_image", return_value="data:image/png;base64,abc"):
            client.i2i("img.jpg", "enhance", extra_body={"response_format": "b64_json"})

        _path, body = client.post.call_args[0]
        assert body["extra_body"]["response_format"] == "b64_json"

    def test_i2i_returns_image_url(self):
        """i2i returns the URL string from the response."""
        from client import ImageClient
        client = ImageClient()
        client.post = MagicMock(return_value={"data": [{"url": "https://example.com/i2i.png"}]})

        with patch.object(ImageClient, "_resolve_image", return_value="data:image/png;base64,abc"):
            url = client.i2i("img.jpg", "enhance")

        assert url == "https://example.com/i2i.png"


# ─── _resolve_image ──────────────────────────────────────────────

class TestResolveImage:
    """Seam: _resolve_image — URL passthrough, file base64, FileNotFoundError."""

    def test_resolve_url_kept_as_is(self):
        """HTTP URL is returned unchanged."""
        from client import ImageClient

        result = ImageClient._resolve_image("https://example.com/photo.jpg")
        assert result == "https://example.com/photo.jpg"

    def test_resolve_https_url(self):
        """HTTPS URL is returned unchanged."""
        from client import ImageClient

        result = ImageClient._resolve_image("https://cdn.example.com/img.webp")
        assert result == "https://cdn.example.com/img.webp"

    def test_resolve_file_to_data_uri(self, test_image_file):
        """Local PNG file is converted to a data URI."""
        from client import ImageClient

        result = ImageClient._resolve_image(test_image_file)
        assert result.startswith("data:image/png;base64,")

    def test_resolve_file_jpg(self, temp_dir):
        """JPG file is converted to image/jpeg data URI."""
        from client import ImageClient

        jpg_path = temp_dir / "test.jpg"
        jpg_path.write_bytes(b"fake-jpeg-data")
        result = ImageClient._resolve_image(str(jpg_path))
        assert result.startswith("data:image/jpeg;base64,")

    def test_resolve_file_not_found(self):
        """Missing file raises FileNotFoundError."""
        from client import ImageClient

        with pytest.raises(FileNotFoundError, match="Image not found"):
            ImageClient._resolve_image("/nonexistent/path/image.png")

    def test_resolve_expands_user_home(self, temp_dir):
        """Tilde in path is expanded before checking existence."""
        from client import ImageClient
        import os
        from pathlib import Path
        test_path = temp_dir / "home" / "user" / "photo.png"
        test_path.parent.mkdir(parents=True)
        test_path.write_bytes(b"png-data")

        # Temporarily override HOME to point to our temp dir
        fake_home = str(temp_dir / "home" / "user")
        with patch.object(Path, "expanduser", return_value=test_path):
            result = ImageClient._resolve_image("~/photo.png")
            assert result.startswith("data:image/png;base64,")


# ─── VideoClient.poll ────────────────────────────────────────────

class TestVideoClientPoll:
    """Seam: VideoClient.poll — completed, failed, TimeoutError."""

    def test_poll_returns_completed(self):
        """poll returns data when status is 'completed'."""
        from client import VideoClient
        client = VideoClient()
        client.get = MagicMock(return_value={
            "status": "completed",
            "url": "https://example.com/video.mp4",
        })

        result = client.poll("task-123", timeout=10, interval=1)
        assert result["status"] == "completed"
        assert result["url"] == "https://example.com/video.mp4"

    def test_poll_returns_failed(self):
        """poll returns data when status is 'failed'."""
        from client import VideoClient
        client = VideoClient()
        client.get = MagicMock(return_value={
            "status": "failed",
            "error": "model crashed",
        })

        result = client.poll("task-456", timeout=10, interval=1)
        assert result["status"] == "failed"
        assert result["error"] == "model crashed"

    def test_poll_retries_processing(self):
        """poll retries while status is 'processing', then returns completed."""
        from client import VideoClient
        client = VideoClient()
        client.get = MagicMock(side_effect=[
            {"status": "processing"},
            {"status": "processing"},
            {"status": "completed", "url": "https://example.com/video.mp4"},
        ])

        result = client.poll("task-789", timeout=30, interval=1)
        assert result["status"] == "completed"
        assert client.get.call_count == 3

    def test_poll_timeout_raises(self):
        """poll raises TimeoutError when task does not complete before deadline."""
        from client import VideoClient
        client = VideoClient()
        client.get = MagicMock(return_value={"status": "processing"})

        with pytest.raises(TimeoutError, match="not completed within"):
            client.poll("task-timeout", timeout=1, interval=1)

    def test_poll_calls_correct_path(self):
        """poll GETs the correct task endpoint."""
        from client import VideoClient
        client = VideoClient()
        client.get = MagicMock(return_value={"status": "completed", "url": "https://example.com/v.mp4"})

        client.poll("task-abc", timeout=10, interval=1)
        client.get.assert_called_once_with("/v1/videos/task-abc")
