#!/usr/bin/env python3
"""
Comic page layout generator — overlays speech bubbles on existing scene images
and arranges them into 2x2 grid pages.
"""

import os
import sys
import yaml
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from utils import get_default_dir, get_font_path

# ─── Config ───────────────────────────────────────────────────────────

IMAGES_DIR = get_default_dir()
SCRIPT_PATH = Path.home() / "agent" / "media" / "today-in-history-comic.yaml"
OUTPUT_DIR = IMAGES_DIR

PANEL_SIZE = (1200, 900)   # 4:3 ratio matching source images
GAP = 10                    # px between panels
PANELS_PER_PAGE = 4         # 2x2 grid
FONT_PATH = get_font_path() or "/System/Library/Fonts/PingFang.ttc"


def find_latest_scene_images() -> dict[int, Path]:
    """Find the latest version of each comic-scene-NN.png."""
    scenes: dict[int, tuple[str, int]] = {}
    for f in sorted(os.listdir(IMAGES_DIR)):
        if not (f.startswith("comic-scene-") and f.endswith(".png")):
            continue
        parts = f.replace("comic-scene-", "").replace(".png", "").split("-")
        num = int(parts[0])
        ts = int(parts[1]) if len(parts) > 1 else 0
        if num not in scenes or ts > scenes[num][1]:
            scenes[num] = (f, ts)

    return {n: IMAGES_DIR / info[0] for n, info in sorted(scenes.items())}


def load_script() -> dict:
    with open(SCRIPT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_dialogue_text(dialogues: list[dict]) -> str:
    """Combine dialogues into text lines for speech bubble."""
    lines = []
    for d in dialogues:
        char = d.get("character", "")
        text = d.get("text", "")
        if char:
            lines.append(f"{char}：{text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def wrap_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text to fit max_width, splitting on newlines first."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def add_speech_bubble(img: Image.Image, dialogues: list[dict]) -> Image.Image:
    """Overlay a speech bubble with dialogue text at the bottom of the image."""
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Font
    try:
        font = ImageFont.truetype(FONT_PATH, 24)
    except Exception:
        font = ImageFont.load_default()

    # Build text lines
    text = make_dialogue_text(dialogues)

    # Wrap text
    max_text_width = int(w * 0.78)
    lines = wrap_text(draw, text, font, max_text_width)

    if not lines:
        return img

    # Bubble dimensions
    line_height = 32
    padding_h = 14  # horizontal padding
    padding_v = 12  # vertical padding
    bubble_w = min(max_text_width + padding_h * 2, w - 24)
    bubble_h = len(lines) * line_height + padding_v * 2

    # Position: centered at bottom with margin
    margin_b = 16
    bx = (w - bubble_w) // 2
    by = h - bubble_h - margin_b

    # Draw rounded rectangle with shadow
    shadow_offset = 3
    draw.rounded_rectangle(
        [bx + shadow_offset, by + shadow_offset, bx + bubble_w + shadow_offset, by + bubble_h + shadow_offset],
        radius=10,
        fill=(0, 0, 0, 80),
    )
    draw.rounded_rectangle(
        [bx, by, bx + bubble_w, by + bubble_h],
        radius=10,
        fill="white",
        outline="black",
        width=2,
    )

    # Draw text
    text_x = bx + padding_h
    text_y = by + padding_v
    for line in lines:
        draw.text((text_x, text_y), line, fill="black", font=font)
        text_y += line_height

    return img


def build_page_image(panel_imgs: list[Image.Image], page_num: int) -> Image.Image:
    """Arrange panel images into a 2x2 grid page."""
    assert len(panel_imgs) <= PANELS_PER_PAGE
    cols = 2
    rows = (len(panel_imgs) + 1) // 2 if len(panel_imgs) > 2 else 1

    panel_w, panel_h = PANEL_SIZE

    page_w = cols * panel_w + (cols - 1) * GAP
    page_h = rows * panel_h + (rows - 1) * GAP
    page = Image.new("RGB", (page_w, page_h), "white")

    for i, p_img in enumerate(panel_imgs):
        # Resize to panel size
        p_resized = p_img.resize((panel_w, panel_h), Image.LANCZOS)
        col = i % cols
        row = i // cols
        x = col * (panel_w + GAP)
        y = row * (panel_h + GAP)
        page.paste(p_resized, (x, y))

    return page


def main():
    # Load script
    script = load_script()
    scenes = script["scenes"]
    print(f"Loaded script: {script.get('title', 'Untitled')}")
    print(f"Total scenes: {len(scenes)}")

    # Find images
    image_map = find_latest_scene_images()
    print(f"Found {len(image_map)} scene images (expected 19)")

    # Process each scene: add speech bubble
    bubbled_imgs = []
    for i, scene in enumerate(scenes):
        scene_num = i + 1
        print(f"\nScene {scene_num:2d}/{len(scenes)}: {scene['description'][:50]}...")

        # Get image
        img_path = image_map.get(scene_num)
        if img_path is None:
            print(f"  ⚠ No image found for scene {scene_num}, skipping")
            continue

        # Load and resize to panel size
        img = Image.open(img_path).convert("RGB")
        img_resized = img.resize(PANEL_SIZE, Image.LANCZOS)

        # Add speech bubble
        dialogues = scene.get("dialogues", [])
        if dialogues:
            img_bubbled = add_speech_bubble(img_resized, dialogues)
        else:
            img_bubbled = img_resized

        bubbled_imgs.append(img_bubbled)
        print(f"  ✓ Processed ({img_bubbled.size[0]}×{img_bubbled.size[1]})")

    # Compose into pages (4 per page, 2x2 grid)
    total_panels = len(bubbled_imgs)
    total_pages = (total_panels + PANELS_PER_PAGE - 1) // PANELS_PER_PAGE
    print(f"\n{'='*60}")
    print(f"Composing {total_panels} panels into {total_pages} pages...")

    for page_idx in range(total_pages):
        start = page_idx * PANELS_PER_PAGE
        end = min(start + PANELS_PER_PAGE, total_panels)
        page_panels = bubbled_imgs[start:end]

        page_img = build_page_image(page_panels, page_idx + 1)

        # Save
        output_path = OUTPUT_DIR / f"comic-page-{page_idx + 1:02d}.png"
        page_img.save(output_path, quality=95)
        print(f"  Page {page_idx + 1:02d}: {output_path} ({page_img.size[0]}×{page_img.size[1]}) "
              f"— panels {start + 1}–{end}")

    print(f"\n✓ Done! {total_pages} pages created in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
