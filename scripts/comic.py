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

import time
from pathlib import Path
from client import ImageClient
from utils import get_default_dir, get_project_intermediate_dir, get_project_deliverable_dir, cleanup_intermediates, get_font_path

# --- 路径配置 ---

CONFIG_DIR = Path.home() / ".config" / "agnes"
PRESETS_PATH = CONFIG_DIR / "comic-presets.yaml"
OUTPUT_DIR = get_default_dir()


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


def _t2i(prompt: str, size: str = "1024x768", ratio: str | None = None, output_dir: Path | None = None, seed: int | None = None) -> str:
    """文生图，返回保存的文件路径。委托给 ImageClient。"""
    client = ImageClient()
    image_url = client.t2i(prompt, size=size, ratio=ratio, seed=seed)
    timestamp = int(time.time())
    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-comic-panel-{timestamp}.png"
    save_path.write_bytes(client.download(image_url))
    return str(save_path)


def _i2i(image: str, prompt: str, size: str = "1024x768", ratio: str | None = None, output_dir: Path | None = None, seed: int | None = None) -> str:
    """图生图，返回保存的文件路径。委托给 ImageClient。"""
    client = ImageClient()
    image_url = client.i2i(image, prompt, size=size, ratio=ratio, seed=seed)
    timestamp = int(time.time())
    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-comic-panel-{timestamp}.png"
    save_path.write_bytes(client.download(image_url))
    return str(save_path)


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
    output_dir: Path | None = None,
    seed: int | None = None,
) -> str:
    """生成单个漫画面板。

    Args:
        description: 场景描述
        character_ref: 角色参考图路径（可选，用于 i2i 角色锚定）
        preset: 风格预设 key
        custom_prompt: 自定义 prompt（覆盖预设）
        size: 输出尺寸
        seed: 随机种子（相同 seed 复现结果）

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
        return _i2i(character_ref, prompt, size=size, output_dir=output_dir, seed=seed)
    else:
        return _t2i(prompt, size=size, output_dir=output_dir, seed=seed)


# ─── 对话框叠加 ───────────────────────────────────────────────


def add_speech_bubble(image_path: str, text: str, position: str = "bottom", output_dir: Path | None = None) -> str:
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

    # 从 paths.yaml 读取中文字体路径
    font_path = get_font_path()
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, 28)
        except Exception:
            pass
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

    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-comic-bubble-{int(time.time())}.png"
    img.save(save_path)
    return str(save_path)


def compose_page(panel_paths: list[str], layout: str = "grid", output_path: str | None = None, output_dir: Path | None = None) -> str:
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
    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-comic-page-{int(time.time())}.png"
    page.save(save_path)
    return str(save_path)


def create_comic(
    script_path: str,
    preset: str | None = None,
    custom_prompt: str | None = None,
    panel_size: str = "1024x768",
    output: str | None = None,
    project: str | None = None,
) -> str:
    """完整漫画创作流程：解析脚本 → 逐格生成 → 叠加对话框 → 合成页面。

    Args:
        script_path: YAML 脚本路径
        preset: 风格预设 key（覆盖脚本中的 preset）
        custom_prompt: 自定义 prompt（覆盖预设）
        panel_size: 面板尺寸
        output: 输出路径（可选）
        project: 项目名（可选），指定后使用项目隔离目录

    Returns:
        最终页面图片路径
    """
    script = parse_script(script_path)
    preset = preset or script.get("preset")
    layout = script.get("layout", "grid")

    # 路径：项目 vs 默认
    if project:
        panels_dir = get_project_intermediate_dir(project, "panels")
        bubbles_dir = get_project_intermediate_dir(project, "bubbles")
        pages_dir = get_project_deliverable_dir(project, "comic_pages")
    else:
        panels_dir = OUTPUT_DIR
        bubbles_dir = OUTPUT_DIR
        pages_dir = OUTPUT_DIR

    panel_paths = []
    for i, panel in enumerate(script["panels"]):
        print(f"  [{i+1}/{len(script['panels'])}] Generating panel: {panel['description'][:40]}...")
        panel_path = generate_panel(
            description=panel["description"],
            character_ref=panel.get("character_ref"),
            preset=preset,
            custom_prompt=custom_prompt,
            size=panel_size,
            output_dir=panels_dir,
        )

        # 叠加对话框
        if panel.get("speech"):
            speech_pos = panel.get("speech_position", "bottom")
            panel_path = add_speech_bubble(panel_path, panel["speech"], position=speech_pos, output_dir=bubbles_dir)

        panel_paths.append(panel_path)

    # 合成页面
    layout = script.get("layout", "grid")
    result = compose_page(panel_paths, layout=layout, output_path=output, output_dir=pages_dir)

    if project:
        cleanup_intermediates(project)

    return result
