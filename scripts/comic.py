"""漫画创作核心模块 — 基于 AGNES t2i + i2i

工作流:
  1. 解析 YAML 脚本 → 逐格描述
  2. 每格用 t2i 生成（可选 i2i 角色锚定）
  3. 用 Pillow 叠加对话框
  4. 按布局合成整页

用法示例（AI 驱动）:
    from comic import create_comic
    path = create_comic("script.yaml", preset="manga")
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# --- 路径配置 ---

if sys.platform == "win32":
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "agnes"
else:
    CONFIG_DIR = Path.home() / ".config" / "agnes"

KEY_PATH = CONFIG_DIR / "key"
PRESETS_PATH = CONFIG_DIR / "comic-presets.yaml"
OUTPUT_DIR = Path.home() / "agent" / "media" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"


def _get_key() -> str:
    return (KEY_PATH).read_text(encoding="utf-8").strip()


def _load_presets() -> dict:
    import yaml
    if PRESETS_PATH.exists():
        with open(PRESETS_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("presets", {}) if data else {}
    return {}


def list_presets() -> list[dict]:
    presets = _load_presets()
    return [{"key": k, "name": v["name"], "prompt": v["prompt"]} for k, v in presets.items()]


def _resolve_image(image: str) -> str:
    """将图片输入转为 AGNES 可用的 URL 或 Data URI"""
    from urllib.parse import urlparse
    parsed = urlparse(image)
    if parsed.scheme in ("http", "https"):
        return image
    import base64
    path = Path(image).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image}")
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _t2i(prompt: str, size: str = "1024x768", ratio: str | None = None) -> str:
    """文生图，返回保存的文件路径（带重试）"""
    import time as _time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            body = {"model": MODEL, "prompt": prompt, "size": size}
            if ratio:
                body["ratio"] = ratio
            req = Request(
                API_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            image_url = data["data"][0]["url"]
            timestamp = int(time.time())
            save_path = OUTPUT_DIR / f"agnes-comic-panel-{timestamp}.png"
            with urlopen(image_url) as img_resp:
                save_path.write_bytes(img_resp.read())
            return str(save_path)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt+1}/{max_retries} after {wait}s: {e}")
                _time.sleep(wait)
            else:
                raise


def _i2i(image: str, prompt: str, size: str = "1024x768", ratio: str | None = None) -> str:
    """图生图，返回保存的文件路径（带重试）"""
    import time as _time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            image_ref = _resolve_image(image)
            body = {
                "model": MODEL,
                "prompt": prompt,
                "size": size,
                "extra_body": {
                    "image": [image_ref],
                    "response_format": "url",
                },
            }
            if ratio:
                body["ratio"] = ratio
            req = Request(
                API_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            image_url = data["data"][0]["url"]
            timestamp = int(time.time())
            save_path = OUTPUT_DIR / f"agnes-comic-panel-{timestamp}.png"
            with urlopen(image_url) as img_resp:
                save_path.write_bytes(img_resp.read())
            return str(save_path)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"  Retry {attempt+1}/{max_retries} after {wait}s: {e}")
                _time.sleep(wait)
            else:
                raise


# ─── YAML 脚本解析 ───────────────────────────────────────────────


def parse_script(script_path: str) -> dict:
    """解析漫画 YAML 脚本文件

    YAML 格式:
        title: "漫画标题"
        preset: manga
        layout: grid       # grid | hero
        panels:
          - description: "场景描述"
            character_ref: "path/to/char.png"  # 可选，i2i 角色锚定
            speech: "对话框文字"               # 可选
    """
    import yaml
    path = Path(script_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "panels" not in data:
        raise ValueError("Script must contain at least a 'panels' list")
    return data


# ─── 面板生成 ───────────────────────────────────────────────


def generate_panel(
    description: str,
    character_ref: str | None = None,
    preset: str | None = None,
    custom_prompt: str | None = None,
    size: str = "1024x768",
) -> str:
    """生成单个漫画面板。

    Args:
        description: 场景描述
        character_ref: 角色参考图路径（可选，用于 i2i 角色锚定）
        preset: 风格预设 key
        custom_prompt: 自定义 prompt（覆盖预设）
        size: 输出尺寸

    Returns:
        面板图片路径
    """
    presets = _load_presets()
    if custom_prompt:
        prompt = custom_prompt.format(description=description)
    elif preset and preset in presets:
        template = presets[preset]["prompt"]
        prompt = template.format(description=description)
    else:
        prompt = description

    if character_ref:
        return _i2i(character_ref, prompt, size=size)
    else:
        return _t2i(prompt, size=size)


# ─── 对话框叠加 ───────────────────────────────────────────────


def add_speech_bubble(image_path: str, text: str, position: str = "bottom") -> str:
    """用 Pillow 在图片上叠加对话框。

    Args:
        image_path: 图片路径
        text: 对话框文字
        position: top | bottom | left | right

    Returns:
        新图片路径
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # 尝试加载中文字体
    font = None
    font_candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_candidates:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 28)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # 文字换行
    max_text_width = int(w * 0.7)
    lines = []
    for word in text:
        if not lines:
            lines.append(word)
            continue
        test_line = lines[-1] + word
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] > max_text_width:
            lines.append(word)
        else:
            lines[-1] += word

    # 气泡尺寸
    line_height = 36
    padding = 20
    bubble_w = min(max_text_width + padding * 2, w - 40)
    bubble_h = len(lines) * line_height + padding * 2

    # 定位
    margin = 30
    if position == "top":
        bx, by = margin, margin
    elif position == "left":
        bx, by = margin, h - bubble_h - margin
    elif position == "right":
        bx, by = w - bubble_w - margin, h - bubble_h - margin
    else:  # bottom
        bx, by = margin, h - bubble_h - margin

    # 绘制白色圆角气泡
    draw.rounded_rectangle([bx, by, bx + bubble_w, by + bubble_h], radius=12, fill="white", outline="black", width=2)

    # 绘制文字
    for i, line in enumerate(lines):
        draw.text((bx + padding, by + padding + i * line_height), line, fill="black", font=font)

    save_path = OUTPUT_DIR / f"agnes-comic-bubble-{int(time.time())}.png"
    img.save(save_path)
    return str(save_path)


def compose_page(panel_paths: list[str], layout: str = "grid", output_path: str | None = None) -> str:
    """将多个面板合成为一页漫画。

    Args:
        panel_paths: 面板图片路径列表
        layout: grid | hero
        output_path: 输出路径（可选）

    Returns:
        合成后的图片路径
    """
    from PIL import Image

    panels = [Image.open(p) for p in panel_paths]
    n = len(panels)

    if layout == "hero":
        # 首格占 2/3 高度，其余横向排列在底部
        hero = panels[0]
        hero_w, hero_h = hero.size
        rest = panels[1:] if len(panels) > 1 else []

        if rest:
            # 底部缩略图高度 = hero_h // 3
            thumb_h = hero_h // 3
            total_thumb_w = sum(int(r.width * thumb_h / r.height) for r in rest)
            page_w = max(hero_w, total_thumb_w)
            page_h = hero_h + thumb_h + 10
            page = Image.new("RGB", (page_w, page_h), "white")

            # 粘贴主图
            page.paste(hero, ((page_w - hero_w) // 2, 0))

            # 粘贴缩略图
            x = (page_w - total_thumb_w) // 2
            y = hero_h + 10
            for r in rest:
                rh = thumb_h
                rw = int(r.width * thumb_h / r.height)
                r_resized = r.resize((rw, rh), Image.LANCZOS)
                page.paste(r_resized, (x, y))
                x += rw + 10
        else:
            page = panels[0].copy()
    elif layout == "grid":
        # 自动计算网格：尽量接近正方形
        n = len(panels)
        cols = 2 if n <= 4 else 3
        rows = (n + cols - 1) // cols

        # 统一面板尺寸
        panel_w = max(p.width for p in panels)
        panel_h = max(p.height for p in panels)
        gap = 10
        page_w = cols * panel_w + (cols - 1) * gap
        page_h = rows * panel_h + (rows - 1) * gap
        page = Image.new("RGB", (page_w, page_h), "white")

        for i, p in enumerate(panels):
            row, col = divmod(i, cols)
            x = col * (panel_w + gap)
            y = row * (panel_h + gap)
            # 统一尺寸
            p_resized = p.resize((panel_w, panel_h), Image.LANCZOS)
            page.paste(p_resized, (x, y))
    else:
        # 单格（直接返回原图）
        page = panels[0].copy()

    if output_path:
        page.save(output_path)
        return output_path
    save_path = OUTPUT_DIR / f"agnes-comic-page-{int(time.time())}.png"
    page.save(save_path)
    return str(save_path)


def create_comic(
    script_path: str,
    preset: str | None = None,
    custom_prompt: str | None = None,
    panel_size: str = "1024x768",
    output: str | None = None,
) -> str:
    """完整漫画创作流程：解析脚本 → 逐格生成 → 叠加对话框 → 合成页面。

    Args:
        script_path: YAML 脚本路径
        preset: 风格预设 key（覆盖脚本中的 preset）
        custom_prompt: 自定义 prompt（覆盖预设）
        panel_size: 面板尺寸
        output: 输出路径（可选）

    Returns:
        最终页面图片路径
    """
    script = parse_script(script_path)
    preset = preset or script.get("preset")
    layout = script.get("layout", "grid")

    panel_paths = []
    for i, panel in enumerate(script["panels"]):
        print(f"  [{i+1}/{len(script['panels'])}] Generating panel: {panel['description'][:40]}...")
        panel_path = generate_panel(
            description=panel["description"],
            character_ref=panel.get("character_ref"),
            preset=preset,
            custom_prompt=custom_prompt,
            size=panel_size,
        )

        # 叠加对话框
        if panel.get("speech"):
            speech_pos = panel.get("speech_position", "bottom")
            panel_path = add_speech_bubble(panel_path, panel["speech"], position=speech_pos)

        panel_paths.append(panel_path)

    # 合成页面
    layout = script.get("layout", "grid")
    return compose_page(panel_paths, layout=layout, output_path=output)
