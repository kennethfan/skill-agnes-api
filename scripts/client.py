"""AGNES API Client — 统一 HTTP 传输层 + 业务语义层。

用法:
    from client import ImageClient, VideoClient

    img = ImageClient()
    url = img.t2i("a cat", size="1024x768")
    data = img.download(url)

    vid = VideoClient()
    task_id = vid.create({...})
    result = vid.poll(task_id)
"""

import base64
import json
import time as _time
from pathlib import Path
from urllib.request import urlopen
from utils import get_key_pool, urlopen_with_rotation


class AgnesClient:
    """基础客户端：HTTP 传输 + key rotation + 重试。

    所有业务 Client（ImageClient / VideoClient）继承此类。
    """

    BASE_URL = "https://apihub.agnes-ai.com"

    def __init__(self, max_retries: int | None = None):
        self._pool = get_key_pool()
        self._max_retries = max_retries

    def post(self, path: str, body: dict) -> dict:
        """POST 请求，返回 JSON 响应。"""
        resp = urlopen_with_rotation(
            f"{self.BASE_URL}{path}",
            data=json.dumps(body).encode(),
            method="POST",
            max_retries=self._max_retries,
        )
        return json.loads(resp.read())

    def get(self, path: str) -> dict:
        """GET 请求，返回 JSON 响应。"""
        resp = urlopen_with_rotation(
            f"{self.BASE_URL}{path}",
            method="GET",
            max_retries=self._max_retries,
        )
        return json.loads(resp.read())

    def download(self, url: str) -> bytes:
        """下载文件内容（CDN URL，无 key rotation）。"""
        with urlopen(url) as resp:
            return resp.read()


class ImageClient(AgnesClient):
    """图片生成客户端（t2i / i2i）。"""

    API_PATH = "/v1/images/generations"
    MODEL = "agnes-image-2.1-flash"

    def t2i(
        self,
        prompt: str,
        size: str = "1024x768",
        ratio: str | None = None,
        seed: int | None = None,
        **body_extras,
    ) -> str:
        """文生图，返回 image_url。

        Args:
            prompt: 图像描述
            size: 输出尺寸（如 1024x768、2K）
            ratio: 宽高比（如 16:9、1:1）
            seed: 随机种子（相同 seed 复现结果）
            **body_extras: 额外 body 字段（如 extra_body、return_base64）
        """
        body: dict = {"model": self.MODEL, "prompt": prompt, "size": size, **body_extras}
        if ratio:
            body["ratio"] = ratio
        if seed is not None:
            body["seed"] = seed
        data = self.post(self.API_PATH, body)
        return data["data"][0]["url"]

    def i2i(
        self,
        image: str,
        prompt: str,
        size: str = "1024x768",
        ratio: str | None = None,
        seed: int | None = None,
        **body_extras,
    ) -> str:
        """图生图，返回 image_url。

        Args:
            image: 本地路径或 URL
            prompt: 图像描述
            size: 输出尺寸
            ratio: 宽高比
            seed: 随机种子（相同 seed 复现结果）
            **body_extras: 额外 body 字段
        """
        image_ref = self._resolve_image(image)
        extra = dict(body_extras.pop("extra_body", {}))
        extra.setdefault("response_format", "url")
        extra.setdefault("image", [image_ref])
        body: dict = {
            "model": self.MODEL,
            "prompt": prompt,
            "size": size,
            "extra_body": extra,
            **body_extras,
        }
        if ratio:
            body["ratio"] = ratio
        if seed is not None:
            body["seed"] = seed
        data = self.post(self.API_PATH, body)
        return data["data"][0]["url"]

    @staticmethod
    def _resolve_image(image: str) -> str:
        """将图片输入转为 AGNES 可用的 URL 或 Data URI。"""
        from urllib.parse import urlparse

        parsed = urlparse(image)
        if parsed.scheme in ("http", "https"):
            return image
        path = Path(image).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image}")
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        mime = mime_map.get(suffix, "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"


class VideoClient(AgnesClient):
    """视频生成客户端（create / poll）。"""

    API_CREATE = "/v1/videos"
    MODEL = "agnes-video-v2.0"

    def create(self, body: dict) -> str:
        """创建视频生成任务，返回 task_id。"""
        full_body = {"model": self.MODEL, **body}
        data = self.post(self.API_CREATE, full_body)
        return data.get("id", "")

    def poll(self, task_id: str, timeout: int = 300, interval: int = 5) -> dict:
        """轮询视频任务直到完成或超时。

        Returns:
            包含 status/url/error 的 dict
        """
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            data = self.get(f"/v1/videos/{task_id}")
            status = data.get("status", "")
            if status in ("completed", "failed"):
                return data
            _time.sleep(interval)
        raise TimeoutError(f"Video task {task_id} not completed within {timeout}s")
