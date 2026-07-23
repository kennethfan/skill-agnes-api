#!/usr/bin/env python3
"""
Pipeline: 古诗朗诵 — 三阶段视频制作管线

Stages:
  1. 场景图生成 — AGNES t2i 生成每张场景图（并行 + 自动重试 3 次）
  2. 素材准备 — Pillow 渲染字幕帧 + edge-tts 生成音频（按文件存在去重）
  3. 视频合成 — ffmpeg concat 合成最终 MP4（9:16 竖屏 720×1280）

YAML 格式（scenes→dialogues）:
  title: "咏鹅"
  author: "骆宾王"
  grade: "一年级上册"
  voice: "zh-CN-YunxiaNeural"  # optional, 默认童声
  scenes:
    - description: "Scene description for AGNES"
      dialogues:
        - text: "鹅，鹅，鹅，曲项向天歌。"
    - description: "..."
      dialogues:
        - text: "白毛浮绿水，红掌拨清波。"

使用:
  python3 scripts/poem-pipeline.py --yaml poem-咏鹅.yaml
  python3 scripts/poem-pipeline.py --yaml poem-江南.yaml --clean
  python3 scripts/poem-pipeline.py --yaml poem-咏鹅.yaml --force-stage 1
  python3 scripts/poem-pipeline.py --yaml poem-咏鹅.yaml --skip-stage 1
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from PIL import Image, ImageDraw, ImageFont
import yaml

# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

# Default paths (overridden by --work-dir at runtime)
_DEFAULT_WORK_DIR = Path.home() / "agent" / "media"
BASE_DIR: Path = _DEFAULT_WORK_DIR
IMAGES_DIR: Path = BASE_DIR / "images"
VIDEOS_DIR: Path = BASE_DIR / "videos"
TEMP_BASE: Path = BASE_DIR / "tmp"
CHECKPOINT_FILE: Path = BASE_DIR / ".pipeline_state.json"


def _set_work_dir(wd: Path) -> None:
    """Override module-level path constants with a custom work directory."""
    global BASE_DIR, IMAGES_DIR, VIDEOS_DIR, TEMP_BASE, CHECKPOINT_FILE
    BASE_DIR = wd.resolve()
    IMAGES_DIR = BASE_DIR / "images"
    VIDEOS_DIR = BASE_DIR / "videos"
    TEMP_BASE = BASE_DIR / "tmp"
    CHECKPOINT_FILE = BASE_DIR / ".pipeline_state.json"

# AGNES
AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.1-flash"
AGNES_KEY_FILE = Path.home() / ".config" / "agnes" / "key"
AGNES_SIZE = "2K"
AGNES_RATIO = "9:16"          # portrait for poetry vertical video
AGNES_MAX_WORKERS = 3          # poems are short, lower concurrency
AGNES_RETRIES = 3

# Video (9:16 portrait)
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
FPS = 24
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"

# Subtitle styling
SUBTITLE_FONT_SIZE = 42
TITLE_FONT_SIZE = 64
AUTHOR_FONT_SIZE = 30
INFO_FONT_SIZE = 26

# edge-tts
NARRATOR_VOICE = "zh-CN-YunxiaNeural"
EDGE_TTS_RATE = "-30%"

# Style suffix for AGNES prompts (same as existing poetry scripts)
STYLE_SUFFIX = (
    ", children's book illustration style, vibrant colors,"
    " clear composition, storybook quality, digital painting"
)


# ═══════════════════════════════════════════════════════════════════════
# Checkpoint
# ═══════════════════════════════════════════════════════════════════════

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_checkpoint(state: dict) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.rename(CHECKPOINT_FILE)


def stage_is_done(state: dict, key: str, stage: int) -> bool:
    return state.get(key, {}).get(f"stage{stage}_done", False)


def mark_stage_done(state: dict, key: str, stage: int) -> None:
    if key not in state:
        state[key] = {}
    state[key][f"stage{stage}_done"] = True
    state[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_checkpoint(state)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def yaml_stem(path: Path) -> str:
    """Return stem of YAML filename, e.g. 'poem-咏鹅' from '/path/to/poem-咏鹅.yaml'."""
    return path.stem  # e.g. "poem-咏鹅"


def checkpoint_key(path: Path) -> str:
    """Checkpoint key = yaml stem, e.g. 'poem-咏鹅'."""
    return yaml_stem(path)


# ═══════════════════════════════════════════════════════════════════════
# Stage 1 — Scene Image Generation
# ═══════════════════════════════════════════════════════════════════════

def _scene_image_name(stem: str, scene_idx: int, ts: int) -> str:
    """poem-{stem}-s{NN}-{ts}.png"""
    return f"poem-{stem}-s{scene_idx + 1:02d}-{ts}.png"


def _scene_image_pattern(stem: str) -> re.Pattern:
    return re.compile(rf"poem-{re.escape(stem)}-s(\d{{2}})-\d+\.png$")


def _load_agnes_key() -> str:
    return AGNES_KEY_FILE.read_text(encoding="utf-8").strip()


def _agnes_generate(prompt: str, api_key: str) -> str:
    full = prompt.strip().rstrip(",") + STYLE_SUFFIX
    body = {
        "model": AGNES_MODEL,
        "prompt": full,
        "size": AGNES_SIZE,
        "ratio": AGNES_RATIO,
        "extra_body": {"response_format": "url"},
    }
    req = Request(
        AGNES_API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["url"]
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}")
    except URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")


def _agnes_download(url: str, path: Path) -> None:
    with urlopen(url, timeout=120) as resp:
        path.write_bytes(resp.read())


def scan_poem_images(stem: str) -> dict[int, Path]:
    """Return {scene_num: latest_file_path} for this poem."""
    pat = _scene_image_pattern(stem)
    by_scene: dict[int, list[tuple[int, Path]]] = {}
    for f in sorted(IMAGES_DIR.glob(f"poem-{stem}-s*.png")):
        m = pat.search(f.name)
        if not m:
            continue
        sn = int(m.group(1))
        try:
            ts = int(f.stem.rsplit("-", 1)[-1])
        except ValueError:
            ts = 0
        by_scene.setdefault(sn, []).append((ts, f))
    result: dict[int, Path] = {}
    for sn, entries in by_scene.items():
        entries.sort(key=lambda x: x[0], reverse=True)
        result[sn] = entries[0][1]
    return result


def stage1_generate(stem: str, scenes: list[dict]) -> int:
    """
    Generate scene images via AGNES t2i.
    Returns number of failed scenes (0 = all OK).
    """
    print("\n" + "=" * 60)
    print(f"🎨 Stage 1: Scene Image Generation ({stem})")
    print("=" * 60)

    api_key = _load_agnes_key()
    print(f"🔑 Key loaded ({api_key[:8]}…{api_key[-4:]})")

    existing = scan_poem_images(stem)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    work: list[tuple[int, dict]] = []
    skip = 0
    for idx, sc in enumerate(scenes):
        sn = idx + 1
        if not sc.get("description"):
            print(f"  [{sn:2d}] ⏭️  No description")
            skip += 1
        elif sn in existing:
            print(f"  [{sn:2d}] ⏭️  Exists: {existing[sn].name}")
            skip += 1
        else:
            work.append((idx, sc))

    print(f"\n📊 {skip} skipped, {len(work)} to generate")
    if not work:
        print("✅ All scenes done")
        return 0

    def _work_one(idx: int, sc: dict) -> tuple[int, str | None, str | None]:
        desc = sc["description"]
        for attempt in range(1, AGNES_RETRIES + 1):
            try:
                print(f"  [{idx+1:2d}] (try {attempt}/{AGNES_RETRIES}) Generating…")
                url = _agnes_generate(desc, api_key)
                print(f"  [{idx+1:2d}]   Downloading…")
                fname = _scene_image_name(stem, idx, int(time.time()))
                _agnes_download(url, IMAGES_DIR / fname)
                return idx, fname, None
            except Exception as e:
                err = str(e)[:80]
                if attempt < AGNES_RETRIES:
                    print(f"  [{idx+1:2d}]   ⚠️  Try {attempt} failed: {err} … retry")
                    time.sleep(2**attempt)
                else:
                    print(f"  [{idx+1:2d}]   ❌ All {AGNES_RETRIES} failed: {err}")
                    return idx, None, str(e)
        return idx, None, "unreachable"

    results: list[tuple[int, str | None, str | None]] = []
    with concurrent.futures.ThreadPoolExecutor(AGNES_MAX_WORKERS) as pool:
        futs = {pool.submit(_work_one, idx, sc): idx for idx, sc in work}
        for f in concurrent.futures.as_completed(futs):
            r = f.result()
            results.append(r)
            i, fn, err = r
            if err:
                print(f"  ❌ [{i+1:2d}] FAILED: {err}")
            else:
                print(f"  ✅ [{i+1:2d}] Saved: {fn}")

    failed = sum(1 for _, f, _ in results if f is None)
    print(f"\n📊 Stage 1: {len(results) - failed} OK, {failed} failed")
    return failed


# ═══════════════════════════════════════════════════════════════════════
# Stage 2 — Frame Rendering + TTS Audio
# ═══════════════════════════════════════════════════════════════════════

def _resize_cover(img: Image.Image, tw: int, th: int) -> Image.Image:
    r = img.width / img.height
    tr = tw / th
    if r > tr:
        nh, nw = th, int(th * r)
    else:
        nw, nh = tw, int(tw / r)
    resized = img.resize((nw, nh), Image.LANCZOS)
    return resized.crop(((nw - tw) // 2, (nh - th) // 2, (nw + tw) // 2, (nh + th) // 2))


def _render_subtitle(img: Image.Image, text: str) -> Image.Image:
    """Bake poem text + semi-transparent bar. No character prefix."""
    img = img.convert("RGBA")
    font = ImageFont.truetype(FONT_PATH, SUBTITLE_FONT_SIZE)

    # Word-wrap
    max_w = int(img.width * 0.88)
    lines: list[str] = []
    for para in text.split("\n"):
        buf = ""
        for ch in para:
            test = buf + ch
            bw = font.getbbox(test)[2]
            if bw > max_w and buf:
                lines.append(buf)
                buf = ch
            else:
                buf = test
        if buf:
            lines.append(buf)
    if not lines:
        lines = [""]

    lh = font.getbbox("测")[3]
    spacing = 8
    pad = 20
    block_h = len(lines) * (lh + spacing) + pad * 2
    bar_y = img.height - block_h - 24

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        [12, bar_y, img.width - 12, img.height - 12],
        radius=10, fill=(0, 0, 0, 160),
    )
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        tw = font.getbbox(line)[2]
        x = (img.width - tw) // 2
        y = bar_y + pad + i * (lh + spacing)
        draw.text((x + 1, y + 1), line, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return img.convert("RGB")


def _create_title_card(
    title: str, author: str, grade: str, bg_img: Image.Image | None,
) -> Image.Image:
    """9:16 title card with darkened background + centred text."""
    if bg_img is not None:
        bg = _resize_cover(bg_img.convert("RGB"), VIDEO_WIDTH, VIDEO_HEIGHT)
    else:
        bg = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (20, 24, 40))

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 200))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    # Title
    tf = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    tw = draw.textbbox((0, 0), title, font=tf)[2]
    tx = (bg.width - tw) // 2
    ty = bg.height // 2 - 100
    draw.text((tx + 2, ty + 2), title, font=tf, fill=(0, 0, 0))
    draw.text((tx, ty), title, font=tf, fill=(255, 255, 255))

    # Author
    af = ImageFont.truetype(FONT_PATH, AUTHOR_FONT_SIZE)
    author_text = f"〔{author}〕"
    aw = draw.textbbox((0, 0), author_text, font=af)[2]
    ax = (bg.width - aw) // 2
    ay = ty + TITLE_FONT_SIZE + 20
    draw.text((ax + 1, ay + 1), author_text, font=af, fill=(0, 0, 0))
    draw.text((ax, ay), author_text, font=af, fill=(200, 200, 200))

    # Grade line
    inf = ImageFont.truetype(FONT_PATH, INFO_FONT_SIZE)
    grade_text = f"部编版 · {grade} · 古诗朗诵"
    gw = draw.textbbox((0, 0), grade_text, font=inf)[2]
    gx = (bg.width - gw) // 2
    gy = ay + AUTHOR_FONT_SIZE + 16
    draw.text((gx + 1, gy + 1), grade_text, font=inf, fill=(0, 0, 0))
    draw.text((gx, gy), grade_text, font=inf, fill=(160, 160, 160))

    return bg


def _audio_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def _generate_audio(text: str, voice: str, out: Path) -> None:
    subprocess.run(
        ["edge-tts", "--voice", voice, "--text", text,
         "--write-media", str(out), f"--rate={EDGE_TTS_RATE}"],
        check=True, capture_output=True, timeout=120,
    )


def stage2_prepare(
    stem: str, title: str, author: str, grade: str,
    voice: str, scenes: list[dict], temp_dir: Path,
) -> list[tuple[Path, Path, float]]:
    """
    Render frames + generate TTS audio for every dialogue.
    Returns list of (frame_path, audio_path, duration) segments.
    """
    print("\n" + "=" * 60)
    print(f"🎬 Stage 2: Asset Preparation ({stem})")
    print("=" * 60)

    temp_dir.mkdir(parents=True, exist_ok=True)
    image_map = scan_poem_images(stem)
    print(f"🖼️  Scene images: {len(image_map)}")

    missing = [n for n in range(1, len(scenes) + 1) if n not in image_map]
    if missing:
        print(f"⚠️  Missing images for scenes: {missing}")

    # --- Title card ---
    print("\n🏷️  Title card…")
    first_img = Image.open(image_map[1]).convert("RGB") if 1 in image_map else None
    title_img = _create_title_card(title, author, grade, first_img)
    title_frame = temp_dir / "frame_title.png"
    title_img.save(title_frame)

    title_audio = temp_dir / "audio_title.mp3"
    if not title_audio.exists():
        title_voice_text = f"{title}，{author}"
        _generate_audio(title_voice_text, voice, title_audio)
    dur_t = _audio_duration(title_audio)
    print(f"   Title audio: {dur_t:.2f}s")

    segments: list[tuple[Path, Path, float]] = [(title_frame, title_audio, dur_t)]

    # --- Scenes ---
    for si, sc in enumerate(scenes):
        sn = si + 1
        dlg_list: list[dict] = sc.get("dialogues", [])
        if not dlg_list:
            continue

        img_p = image_map.get(sn)
        if img_p is None:
            print(f"  ⚠️  Scene {sn} — no image, skip")
            continue

        desc = sc.get("description", "")[:50]
        print(f"\n🎬 S{sn:02d}/{len(scenes)}  {desc}…")

        base = Image.open(img_p).convert("RGB")
        base = _resize_cover(base, VIDEO_WIDTH, VIDEO_HEIGHT)

        for di, dlg in enumerate(dlg_list):
            text = dlg.get("text", "")
            tag = f"s{sn:02d}_d{di:02d}"

            print(f"   💬  {text[:40]}…")

            frame = _render_subtitle(base.copy(), text)
            fp = temp_dir / f"frame_{tag}.png"
            frame.save(fp)

            ap = temp_dir / f"audio_{tag}.mp3"
            if not ap.exists():
                _generate_audio(text, voice, ap)

            dur = _audio_duration(ap)
            segments.append((fp, ap, dur))

    total = len(segments)
    total_dur = sum(s[2] for s in segments)
    print(f"\n📦 {total} segments, ~{total_dur:.0f}s ({total_dur/60:.1f}m)")
    return segments


# ═══════════════════════════════════════════════════════════════════════
# Stage 3 — Video Composition
# ═══════════════════════════════════════════════════════════════════════

def stage3_compose(
    segments: list[tuple[Path, Path, float]],
    output: Path,
) -> None:
    """ffmpeg concat filter → output MP4."""
    print("\n" + "=" * 60)
    print("🎞️  Stage 3: Video Composition")
    print("=" * 60)

    n = len(segments)
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y"]
    for fp, ap, dur in segments:
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(fp)]
        cmd += ["-i", str(ap)]

    parts = "".join(f"[{i*2}:v][{i*2+1}:a]" for i in range(n))
    cplx = f"{parts}concat=n={n}:v=1:a=1[v][a]"

    cmd += [
        "-filter_complex", cplx,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-r", str(FPS), "-pix_fmt", "yuv420p",
        str(output),
    ]

    print(f"   ffmpeg concat ({n} segments)…")
    sys.stdout.flush()
    subprocess.run(cmd, check=True)

    final_dur = _audio_duration(output)
    mb = output.stat().st_size / (1024 * 1024)
    print(f"\n✅ Done: {output}")
    print(f"   Size: {mb:.1f} MB, Duration: {final_dur:.1f}s ({final_dur/60:.1f}m)")


# ═══════════════════════════════════════════════════════════════════════
# Load existing segments from temp dir (for skip / checkpoint recovery)
# ═══════════════════════════════════════════════════════════════════════

def _load_existing_segments(
    scenes: list[dict], temp_dir: Path,
) -> list[tuple[Path, Path, float]]:
    segs: list[tuple[Path, Path, float]] = []
    tf = temp_dir / "frame_title.png"
    ta = temp_dir / "audio_title.mp3"
    if tf.exists() and ta.exists():
        segs.append((tf, ta, _audio_duration(ta)))

    for si, sc in enumerate(scenes):
        sn = si + 1
        for di in range(len(sc.get("dialogues", []))):
            tag = f"s{sn:02d}_d{di:02d}"
            fp = temp_dir / f"frame_{tag}.png"
            ap = temp_dir / f"audio_{tag}.mp3"
            if fp.exists() and ap.exists():
                segs.append((fp, ap, _audio_duration(ap)))
    return segs


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="古诗朗诵 — 三阶段视频管线")
    p.add_argument("--yaml", required=True, help="诗稿 YAML 路径（绝对或相对项目目录）")
    p.add_argument("--output", default=None, help="输出视频路径（默认: videos/诗歌朗诵/{title}.mp4）")
    p.add_argument("--clean", action="store_true", help="成功后清理临时文件")
    p.add_argument("--work-dir", default=None, help="工作目录（默认 ~/agent/media/）")
    p.add_argument("--force-stage", type=int, choices=[1, 2, 3], help="强制重跑某阶段")
    p.add_argument("--skip-stage", type=int, choices=[1, 2], help="跳过某阶段")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- Apply work directory ---
    if args.work_dir:
        _set_work_dir(Path(args.work_dir))

    # Resolve YAML
    yaml_path = Path(args.yaml)
    if not yaml_path.is_absolute():
        # Search: project root, scripts/
        for d in [BASE_DIR, BASE_DIR / "scripts"]:
            candidate = d / args.yaml
            if candidate.exists():
                yaml_path = candidate.resolve()
                break
        else:
            print(f"❌ YAML not found: {args.yaml}")
            sys.exit(1)
    elif not yaml_path.exists():
        print(f"❌ YAML not found: {yaml_path}")
        sys.exit(1)

    print(f"📄 YAML: {yaml_path}")

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    title: str = data.get("title", "无题")
    author: str = data.get("author", "")
    grade: str = data.get("grade", "未知")
    voice: str = data.get("voice", NARRATOR_VOICE)
    scenes: list[dict] = data.get("scenes", [])

    # Fallback: convert old `lines` format to scenes→dialogues
    if not scenes and "lines" in data:
        lines = data["lines"]
        scenes = [{"dialogues": [{"text": ln["text"]}], "description": ln.get("description", "")}
                  for ln in lines]
        print("ℹ️  Converted legacy 'lines' format to 'scenes→dialogues'")

    if not scenes:
        print("❌ No scenes in YAML")
        sys.exit(1)

    print(f"📖 {len(scenes)} scenes, {title} ({author}) · {grade}")

    # Derive checkpoint key & image stem from YAML filename
    stem = yaml_path.stem  # e.g. "poem-咏鹅"
    ck_key = stem

    # Output path
    output = (
        Path(args.output)
        if args.output
        else VIDEOS_DIR / "诗歌朗诵" / f"{title}.mp4"
    )
    print(f"📁 Output: {output}")

    temp_dir = TEMP_BASE / f"pipeline_poem-{stem}"
    state = load_checkpoint()
    print(f"🔍 Checkpoint: {len(state)} entries")

    # ── Stage 1 ──
    skip_s1 = args.skip_stage == 1
    force_s1 = args.force_stage == 1
    if skip_s1:
        print("\n⏭️  Stage 1 skipped")
    elif stage_is_done(state, ck_key, 1) and not force_s1:
        print("\n⏭️  Stage 1 done (checkpoint), use --force-stage 1 to re-run")
    else:
        failed = stage1_generate(stem, scenes)
        if failed:
            print(f"⚠️  Stage 1 finished with {failed} failure(s)")
        mark_stage_done(state, ck_key, 1)

    # ── Stage 2 ──
    skip_s2 = args.skip_stage == 2
    force_s2 = args.force_stage == 2
    segments: list[tuple[Path, Path, float]] = []

    if skip_s2:
        print("\n⏭️  Stage 2 skipped, loading existing assets…")
        segments = _load_existing_segments(scenes, temp_dir)
        if not segments:
            print("❌ No existing assets found for Stage 2")
            sys.exit(1)
        print(f"   Loaded {len(segments)} segment(s)")
    elif stage_is_done(state, ck_key, 2) and not force_s2:
        print("\n⏭️  Stage 2 done (checkpoint), use --force-stage 2 to re-run")
        segments = _load_existing_segments(scenes, temp_dir)
        if not segments:
            print("❌ Stage 2 marked done but no assets found! Use --force-stage 2")
            sys.exit(1)
    else:
        segments = stage2_prepare(stem, title, author, grade, voice, scenes, temp_dir)
        mark_stage_done(state, ck_key, 2)

    # ── Stage 3 ──
    force_s3 = args.force_stage == 3
    if not segments:
        print("❌ No segments to compose")
        sys.exit(1)

    if stage_is_done(state, ck_key, 3) and not force_s3:
        print("\n⏭️  Stage 3 done (checkpoint), use --force-stage 3 to re-run")
    else:
        stage3_compose(segments, output)
        mark_stage_done(state, ck_key, 3)

    # ── Cleanup ──
    if args.clean and temp_dir.exists():
        print("\n🧹 Cleaning temp…")
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"\n🚀 Pipeline complete for 《{title}》!")


if __name__ == "__main__":
    main()
