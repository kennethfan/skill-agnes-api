#!/usr/bin/env python3
"""
Pipeline: 儿童故事 — 三阶段视频制作管线

Stages:
  1. 场景图生成 — AGNES t2i（description 原文，不额外追加 style）
  2. 素材准备 — Pillow 渲染字幕帧（角色名：xxx）+ edge-tts 音频（按 YAML characters 映射音色）
  3. 视频合成 — ffmpeg concat 合成最终 MP4

使用:
  python3 scripts/story-pipeline.py --yaml story-小红帽.yaml
  python3 scripts/story-pipeline.py --yaml story-小红帽.yaml --clean
  python3 scripts/story-pipeline.py --yaml story-龟兔赛跑.yaml --force-stage 2
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
AGNES_RATIO = "16:9"
AGNES_MAX_WORKERS = 5
AGNES_RETRIES = 3

# Video — 16:9 same as today-in-history
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FPS = 24
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
SUBTITLE_FONT_SIZE = 40
TITLE_FONT_SIZE = 80
SUB_TITLE_FONT_SIZE = 32
NARRATOR_VOICE = "zh-CN-YunxiaNeural"
MALE_VOICE = "zh-CN-YunjianNeural"
FEMALE_VOICE = "zh-CN-XiaoxiaoNeural"
KID_VOICE = "zh-CN-YunxiNeural"
GIRL_VOICE = "zh-CN-XiaoyiNeural"
EDGE_TTS_RATE = "-30%"

# YAML search dirs (relative to BASE_DIR)
YAML_SEARCH_DIRS = [Path("."), Path("scripts")]

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
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
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
# YAML resolution
# ═══════════════════════════════════════════════════════════════════════

def resolve_yaml(path_str: str) -> tuple[Path, str]:
    """Return (resolved_path, yaml_stem)."""
    p = Path(path_str)
    if p.is_absolute():
        if not p.exists():
            raise FileNotFoundError(f"YAML not found: {p}")
        return p.resolve(), p.stem
    for d in YAML_SEARCH_DIRS:
        candidate = (BASE_DIR / d / p).resolve()
        if candidate.exists():
            return candidate, candidate.stem
    raise FileNotFoundError(
        f"YAML not found: {path_str}\n"
        f"  Searched: {[str(BASE_DIR / d / path_str) for d in YAML_SEARCH_DIRS]}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Stage 1 — Scene Image Generation
# ═══════════════════════════════════════════════════════════════════════

def _image_name(stem: str, scene_idx: int, ts: int) -> str:
    """story-{stem}-s{NN}-{ts}.png"""
    return f"story-{stem}-s{scene_idx + 1:02d}-{ts}.png"


def _image_pattern(stem: str) -> re.Pattern:
    return re.compile(rf"story-{re.escape(stem)}-s(\d{{2}})-.+\.png$")


def _load_agnes_key() -> str:
    return AGNES_KEY_FILE.read_text(encoding="utf-8").strip()


def _agnes_generate(prompt: str, api_key: str) -> str:
    """Call AGNES t2i, return download URL. No extra style suffix — description is used as-is."""
    body = {
        "model": AGNES_MODEL,
        "prompt": prompt.strip(),
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


def scan_story_images(stem: str) -> dict[int, Path]:
    """Return {scene_num: latest_file_path} for given story stem."""
    pat = _image_pattern(stem)
    by_scene: dict[int, list[tuple[int, Path]]] = {}
    for f in sorted(IMAGES_DIR.glob(f"story-{stem}-*.png")):
        m = pat.search(f.name)
        if not m:
            continue
        sn = int(m.group(1))
        try:
            ts = int(f.stem.split("-")[-1])
        except ValueError:
            ts = 0
        by_scene.setdefault(sn, []).append((ts, f))
    result: dict[int, Path] = {}
    for sn, entries in by_scene.items():
        entries.sort(key=lambda x: x[0], reverse=True)
        result[sn] = entries[0][1]
    return result


def stage1_generate(stem: str, scenes: list[dict]) -> int:
    """Generate scene images via AGNES t2i. Returns number of failures."""
    print("\n" + "=" * 60)
    print(f"🎨 Stage 1: Scene Image Generation ({stem})")
    print("=" * 60)

    api_key = _load_agnes_key()
    print(f"🔑 Key loaded ({api_key[:8]}…{api_key[-4:]})")

    existing = scan_story_images(stem)
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
                fname = _image_name(stem, idx, int(time.time()))
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

def _resolve_voice(character: str, char_map: dict[str, str]) -> str:
    """Resolve voice: YAML characters map first, then hardcoded fallback."""
    c = character.strip()
    # YAML-defined mapping takes priority
    if c in char_map:
        return char_map[c]

    # Hardcoded fallback
    if c in ("", "旁白", "叙述", "叙述者"):
        return NARRATOR_VOICE
    # Gender-based deduction from known voice lists
    known_male = {"大灰狼", "猎人", "爸爸", "国王", "爷爷", "皇帝", "农夫", "狮子", "老虎", "狐狸"}
    known_female = {"奶奶", "妈妈", "公主", "王后", "仙女", "外婆", "小红帽(母)"}
    known_kid = {"乌龟", "兔子", "小猫", "小狗", "小鸭", "小鸡", "小猪"}
    known_girl = {"小红帽"}

    if c in known_girl:
        return GIRL_VOICE
    if c in known_kid:
        return KID_VOICE
    if c in known_male:
        return MALE_VOICE
    if c in known_female:
        return FEMALE_VOICE

    # Last resort — guess by heuristics
    if c.endswith("哥") or c.endswith("弟") or c.endswith("爸"):
        return MALE_VOICE
    if c.endswith("姐") or c.endswith("妹") or c.endswith("妈") or c.endswith("娘") or c.endswith("婆"):
        return FEMALE_VOICE

    return NARRATOR_VOICE


def _resize_cover(img: Image.Image, tw: int, th: int) -> Image.Image:
    r = img.width / img.height
    tr = tw / th
    if r > tr:
        nh, nw = th, int(th * r)
    else:
        nw, nh = tw, int(tw / r)
    resized = img.resize((nw, nh), Image.LANCZOS)
    return resized.crop(((nw - tw) // 2, (nh - th) // 2, (nw + tw) // 2, (nh + th) // 2))


def _render_subtitle(img: Image.Image, text: str, character: str) -> Image.Image:
    """Bake '{character}：{text}' + semi-transparent bar into image."""
    img = img.convert("RGBA")
    font = ImageFont.truetype(FONT_PATH, SUBTITLE_FONT_SIZE)
    draw = ImageDraw.Draw(img)

    prefix = f"{character}：" if character else ""
    full = prefix + text
    max_w = int(img.width * 0.88)

    lines: list[str] = []
    for para in full.split("\n"):
        buf = ""
        for ch in para:
            test = buf + ch
            if draw.textbbox((0, 0), test, font=font)[2] > max_w and buf:
                lines.append(buf)
                buf = ch
            else:
                buf = test
        if buf:
            lines.append(buf)
    if not lines:
        lines = [""]

    lh = draw.textbbox((0, 0), "测", font=font)[3]
    spacing = 10
    block_h = len(lines) * (lh + spacing) + 24
    bar_y = img.height - block_h - 36

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        [12, bar_y, img.width - 12, img.height - 12],
        radius=12, fill=(0, 0, 0, 160),
    )
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        tw = draw.textbbox((0, 0), line, font=font)[2]
        x = (img.width - tw) // 2
        y = bar_y + 12 + i * (lh + spacing)
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return img.convert("RGB")


def _create_title_card(title: str, source: str, bg_img: Image.Image | None) -> Image.Image:
    """Dark overlay + centred title + source attribution."""
    if bg_img is not None:
        bg = _resize_cover(bg_img.convert("RGB"), VIDEO_WIDTH, VIDEO_HEIGHT)
    else:
        bg = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (16, 16, 32))

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 190))
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    # Title
    tf = ImageFont.truetype(FONT_PATH, TITLE_FONT_SIZE)
    tw = draw.textbbox((0, 0), title, font=tf)[2]
    tx = (bg.width - tw) // 2
    ty = bg.height // 2 - 80
    draw.text((tx + 3, ty + 3), title, font=tf, fill=(0, 0, 0))
    draw.text((tx, ty), title, font=tf, fill=(255, 255, 255))

    # Source line
    if source:
        sf = ImageFont.truetype(FONT_PATH, SUB_TITLE_FONT_SIZE)
        src_text = f"改编自{source}"
        sw = draw.textbbox((0, 0), src_text, font=sf)[2]
        sx = (bg.width - sw) // 2
        sy = ty + TITLE_FONT_SIZE + 28
        draw.text((sx + 2, sy + 2), src_text, font=sf, fill=(0, 0, 0))
        draw.text((sx, sy), src_text, font=sf, fill=(200, 200, 200))

        # Bottom tag
        tag_text = "儿童故事 · 动画版"
        tb = draw.textbbox((0, 0), tag_text, font=sf)
        tg_x = (bg.width - (tb[2] - tb[0])) // 2
        tg_y = sy + SUB_TITLE_FONT_SIZE + 16
        draw.text((tg_x + 2, tg_y + 2), tag_text, font=sf, fill=(0, 0, 0))
        draw.text((tg_x, tg_y), tag_text, font=sf, fill=(180, 180, 180))

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
    stem: str, title: str, source: str, scenes: list[dict],
    char_map: dict[str, str], temp_dir: Path,
) -> list[tuple[Path, Path, float]]:
    """Render frames + TTS audio. Returns segments for Stage 3."""
    print("\n" + "=" * 60)
    print(f"🎬 Stage 2: Asset Preparation ({stem})")
    print("=" * 60)

    temp_dir.mkdir(parents=True, exist_ok=True)
    image_map = scan_story_images(stem)
    print(f"🖼️  Scene images: {len(image_map)}")

    missing = [n for n in range(1, len(scenes) + 1) if n not in image_map]
    if missing:
        print(f"⚠️  Missing images for scenes: {missing}")

    # --- Title card ---
    print("\n🏷️  Title card…")
    first_img = Image.open(image_map[1]).convert("RGB") if 1 in image_map else None
    title_img = _create_title_card(title, source, first_img)
    title_frame = temp_dir / "frame_title.png"
    title_img.save(title_frame)

    title_audio = temp_dir / "audio_title.mp3"
    if not title_audio.exists():
        tts_text = f"{title}，让我们一起听故事吧。"
        _generate_audio(tts_text, NARRATOR_VOICE, title_audio)
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

        desc = sc.get("description", "")[:55]
        print(f"\n🎬 S{sn:02d}/{len(scenes)}  {desc}…")

        base = Image.open(img_p).convert("RGB")
        base = _resize_cover(base, VIDEO_WIDTH, VIDEO_HEIGHT)

        for di, dlg in enumerate(dlg_list):
            char = dlg.get("character", "旁白")
            text = dlg.get("text", "")
            voice = _resolve_voice(char, char_map)
            tag = f"s{sn:02d}_d{di:02d}"

            print(f"   💬 {char} → {voice}: {text[:45]}…")

            frame = _render_subtitle(base.copy(), text, char)
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
# Load existing segments from temp dir
# ═══════════════════════════════════════════════════════════════════════

def _load_existing_segments(
    scenes: list[dict], temp_dir: Path,
) -> list[tuple[Path, Path, float]]:
    segs: list[tuple[Path, Path, float]] = []
    title_frame = temp_dir / "frame_title.png"
    title_audio = temp_dir / "audio_title.mp3"
    if title_frame.exists() and title_audio.exists():
        dur = _audio_duration(title_audio)
        segs.append((title_frame, title_audio, dur))

    for si, sc in enumerate(scenes):
        sn = si + 1
        for di in range(len(sc.get("dialogues", []))):
            tag = f"s{sn:02d}_d{di:02d}"
            fp = temp_dir / f"frame_{tag}.png"
            ap = temp_dir / f"audio_{tag}.mp3"
            if fp.exists() and ap.exists():
                dur = _audio_duration(ap)
                segs.append((fp, ap, dur))
    return segs


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="儿童故事 — 三阶段视频管线")
    p.add_argument("--yaml", required=True, help="YAML 剧本路径（story-小红帽.yaml）")
    p.add_argument("--output", default=None, help="输出视频路径（默认自动）")
    p.add_argument("--clean", action="store_true", help="成功后清理 temp")
    p.add_argument("--work-dir", default=None, help="工作目录（默认 ~/agent/media/）")
    p.add_argument("--force-stage", type=int, choices=[1, 2, 3], help="强制重跑某阶段")
    p.add_argument("--skip-stage", type=int, choices=[1, 2], help="跳过某阶段")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- Apply work directory ---
    if args.work_dir:
        _set_work_dir(Path(args.work_dir))

    # --- Resolve YAML ---
    try:
        yaml_path, stem = resolve_yaml(args.yaml)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(f"📄 YAML: {yaml_path}")
    print(f"🏷️  Stem: {stem}")

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    title: str = data.get("title", stem)
    source: str = data.get("source", "")
    char_map: dict[str, str] = data.get("characters", {})
    scenes: list[dict] = data.get("scenes", [])
    if not scenes:
        print("❌ No scenes in YAML")
        sys.exit(1)
    print(f"📖 {len(scenes)} scenes, title={title!r}, source={source!r}")
    print(f"🗣️  Characters mapped: {list(char_map.keys()) if char_map else '(none)'}")

    # --- Checkpoint key ---
    cp_key = f"story-{stem}"

    # --- Output ---
    output = (
        Path(args.output)
        if args.output
        else VIDEOS_DIR / "儿童故事" / f"{title}.mp4"
    )
    print(f"📁 Output: {output}")

    temp_dir = TEMP_BASE / f"pipeline_{cp_key}"
    state = load_checkpoint()
    print(f"🔍 Checkpoint entries: {len(state)}")

    # ── Stage 1 ──
    skip_s1 = args.skip_stage == 1
    force_s1 = args.force_stage == 1
    if skip_s1:
        print("\n⏭️  Stage 1 skipped")
    elif stage_is_done(state, cp_key, 1) and not force_s1:
        print(f"\n⏭️  Stage 1 done (checkpoint), use --force-stage 1 to re-run")
    else:
        failed = stage1_generate(stem, scenes)
        if failed:
            print(f"⚠️  Stage 1 finished with {failed} failure(s)")
        mark_stage_done(state, cp_key, 1)

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
    elif stage_is_done(state, cp_key, 2) and not force_s2:
        print(f"\n⏭️  Stage 2 done (checkpoint), use --force-stage 2 to re-run")
        segments = _load_existing_segments(scenes, temp_dir)
        if not segments:
            print("❌ Stage 2 marked done but no assets found! Use --force-stage 2")
            sys.exit(1)
    else:
        segments = stage2_prepare(stem, title, source, scenes, char_map, temp_dir)
        mark_stage_done(state, cp_key, 2)

    # ── Stage 3 ──
    force_s3 = args.force_stage == 3
    if not segments:
        print("❌ No segments to compose")
        sys.exit(1)

    if stage_is_done(state, cp_key, 3) and not force_s3:
        print(f"\n⏭️  Stage 3 done (checkpoint), use --force-stage 3 to re-run")
    else:
        stage3_compose(segments, output)
        mark_stage_done(state, cp_key, 3)

    # ── Cleanup ──
    if args.clean and temp_dir.exists():
        print("\n🧹 Cleaning temp…")
        shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"\n🚀 Pipeline complete for {title}!")


if __name__ == "__main__":
    main()
