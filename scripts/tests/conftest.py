"""Shared test fixtures for AGNES API unit tests."""

import json
import tempfile
from pathlib import Path
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test file operations."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def test_image_file(temp_dir):
    """Create a minimal valid PNG for image-related tests."""
    # Minimal 1x1 red PNG (base64-encoded)
    png_data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG header
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0x60, 0x60, 0x60, 0x00,
        0x00, 0x00, 0x04, 0x00, 0x01, 0x27, 0x34, 0x27,
        0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
        0xAE, 0x42, 0x60, 0x82,
    ])
    path = temp_dir / "test.png"
    path.write_bytes(png_data)
    return str(path)


@pytest.fixture
def mock_post():
    """Mock AgnesClient.post to return a canned response."""
    with patch("client.AgnesClient.post") as m:
        m.return_value = {"data": [{"url": "https://example.com/image.png"}]}
        yield m


@pytest.fixture
def mock_get():
    """Mock AgnesClient.get to return a canned response."""
    with patch("client.AgnesClient.get") as m:
        yield m


@pytest.fixture
def mock_urlopen():
    """Mock urllib.request.urlopen for download/HTTP tests.

    Returns a MagicMock whose context manager returns a BytesIO.
    Usage:
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"..."
    """
    with patch("client.urlopen") as m:
        cm = MagicMock()
        cm.read.return_value = b"fake-image-data"
        cm.__enter__.return_value = cm
        m.return_value = cm
        yield m


@pytest.fixture
def mock_urlopen_with_rotation():
    """Mock urlopen_with_rotation for client post/get."""
    with patch("client.urlopen_with_rotation") as m:
        cm = MagicMock()
        cm.read.return_value = json.dumps({"data": [{"url": "https://example.com/img.png"}]}).encode()
        m.return_value = cm
        yield m


@pytest.fixture
def mock_urlopen_with_rotation_raw():
    """Mock urlopen_with_rotation returning raw bytes (not JSON)."""
    with patch("client.urlopen_with_rotation") as m:
        yield m


@pytest.fixture
def mock_key_pool():
    """Provide a KeyPool pre-populated with fake keys, no config needed."""
    from utils import KeyPool

    pool = KeyPool()
    pool._keys = ["key-001", "key-002", "key-003"]
    pool._loaded = True
    pool._index = 0
    return pool


@pytest.fixture
def mock_get_key_pool(mock_key_pool):
    """Patch get_key_pool() to return a controlled KeyPool."""
    with patch("utils.get_key_pool", return_value=mock_key_pool) as m:
        yield m
