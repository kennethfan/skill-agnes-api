"""诗词朗诵视频生成模块 — 基于 AGNES t2i + i2i + edge-tts

工作流:
  1. 解析诗词 YAML 脚本
  2. edge-tts 生成每句朗诵音频（--rate=-30% 慢速）
  3. AGNES t2i 生成第一张场景图（含小书童角色）
  4. AGNES i2i 生成后续场景图（以第一张为角色参考）
  5. 场景图缩放到视频尺寸
  6. ffmpeg concat filter 合成视频，drawtext 叠加字幕（纯文字，无背景条）

用法示例（AI 驱动）:
    from poem_video import create_poem_video
    path = create_poem_video("script.yaml")
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time as _time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from utils import get_default_dir, get_project_intermediate_dir, get_project_deliverable_dir, cleanup_intermediates, get_ffmpeg_bin, get_ffprobe_bin, get_font_path

# --- 路径配置 ---

OUTPUT_DIR = get_default_dir()
CONFIG_DIR = Path.home() / ".config" / "agnes"

API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"

# 完整版 ffmpeg（从 paths.yaml 读取，支持 drawtext、libfontconfig）
FFMPEG = get_ffmpeg_bin()
FFPROBE = get_ffprobe_bin()

# 默认童声
DEFAULT_VOICE = "zh-CN-YunxiaNeural"

# 9:16 竖屏尺寸（场景图与视频尺寸一致，无黑条）
FRAME_W = 720
FRAME_H = 1280
SCENE_W = 736   # AGNES 1K 9:16 标准尺寸
SCENE_H = 1312


def _get_key() -> str:
    from utils import get_api_key
    return get_api_key()


def _resolve_image(image: str) -> str:
    """将图片输入转为 AGNES 可用的 URL 或 Data URI"""
    parsed = urlparse(image)
    if parsed.scheme in ("http", "https"):
        return image
    path = Path(image).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image}")
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _wrap_text(text: str, max_chars: int = 15) -> str:
    """将长文本按中文字数拆为多行，供 drawtext 多行渲染"""
    lines = []
    while len(text) > max_chars:
        split = max_chars
        for pos in range(max_chars, max_chars // 2, -1):
            if pos < len(text) and text[pos] in ' ，。！？、；：)）':
                split = pos + 1
                break
        lines.append(text[:split])
        text = text[split:]
    if text:
        lines.append(text)
    return "\n".join(lines)


def _measure_text_width(text: str, font_path: str, fontsize: int) -> int:
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(font_path, fontsize)
        return int(font.getlength(text))
    except Exception:
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
        latin = len(text) - cjk
        return int(cjk * fontsize * 0.95 + latin * fontsize * 0.55)


def _auto_fit_subtitle(text: str, font_path: str, max_width: int = 660, font_max: int = 42, font_min: int = 28) -> tuple[str, int]:
    for max_chars in range(15, 7, -1):
        wrapped = _wrap_text(text, max_chars)
        if all(_measure_text_width(l, font_path, font_max) <= max_width for l in wrapped.split('\n')):
            return wrapped, font_max
    for fontsize in range(font_max - 2, font_min - 1, -2):
        for max_chars in range(12, 7, -1):
            wrapped = _wrap_text(text, max_chars)
            if all(_measure_text_width(l, font_path, fontsize) <= max_width for l in wrapped.split('\n')):
                return wrapped, fontsize
    return _wrap_text(text, 10), font_min


def _t2i(prompt: str, size: str = "736x1312", output_dir: Path | None = None) -> str:
    """文生图，返回保存的文件路径（带重试）

    Args:
        prompt: 图像描述
        size: 输出尺寸
        output_dir: 保存目录，默认使用 OUTPUT_DIR
    """
    max_retries = 5
    for attempt in range(max_retries):
        try:
            body = {"model": MODEL, "prompt": prompt, "size": size}
            req = Request(
                API_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            image_url = data["data"][0]["url"]
            timestamp = int(_time.time())
            save_dir = output_dir or OUTPUT_DIR
            save_path = save_dir / f"agnes-poem-scene-{timestamp}.png"
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


def _i2i(image: str, prompt: str, size: str = "736x1312", output_dir: Path | None = None) -> str:
    """图生图，返回保存的文件路径（带重试）

    Args:
        output_dir: 保存目录，默认使用 OUTPUT_DIR
    """
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
            req = Request(
                API_URL,
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            image_url = data["data"][0]["url"]
            timestamp = int(_time.time())
            save_dir = output_dir or OUTPUT_DIR
            save_path = save_dir / f"agnes-poem-scene-{timestamp}.png"
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


def _generate_audio(text: str, voice: str, output_path: str) -> float:
    """用 edge-tts 生成音频，返回时长（秒）"""
    import subprocess
    result = subprocess.run(
        ["edge-tts", "--voice", voice, "--text", text, "--write-media", output_path, "--rate=-30%"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"edge-tts failed: {result.stderr}")

    # 获取音频时长
    duration = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", output_path],
        capture_output=True, text=True, timeout=10,
    )
    return float(duration.stdout.strip())


def _create_title_card(title: str, author: str, bg_image: str | None = None, output_dir: Path | None = None) -> str:
    """创建片头图：诗名 + 作者，水墨背景

    Args:
        output_dir: 保存目录，默认使用 OUTPUT_DIR
    """
    from PIL import Image, ImageDraw, ImageFont

    if bg_image:
        bg = Image.open(bg_image).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    else:
        bg = Image.new("RGB", (FRAME_W, FRAME_H), (240, 235, 225))

    draw = ImageDraw.Draw(bg)

    # 加载中文字体（从 paths.yaml 读取）
    font_title = None
    font_author = None
    font_path = get_font_path()
    if font_path:
        try:
            font_title = ImageFont.truetype(font_path, 64)
            font_author = ImageFont.truetype(font_path, 36)
        except Exception:
            pass
    if font_title is None:
        font_title = ImageFont.load_default()
        font_author = ImageFont.load_default()

    # 绘制诗名
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    tx = (FRAME_W - title_w) // 2
    ty = FRAME_H // 2 - 80
    draw.text((tx, ty), title, fill=(40, 35, 30), font=font_title)

    # 绘制作者
    author_bbox = draw.textbbox((0, 0), author, font=font_author)
    author_w = author_bbox[2] - author_bbox[0]
    ax = (FRAME_W - author_w) // 2
    ay = ty + 100
    draw.text((ax, ay), author, fill=(80, 75, 70), font=font_author)

    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-poem-title-{int(_time.time())}.png"
    bg.save(save_path)
    return str(save_path)


def _create_scene_frame(scene_image_path: str, output_dir: Path | None = None) -> str:
    """将场景图缩放到视频尺寸（字幕由 ffmpeg drawtext 叠加）"""
    from PIL import Image
    scene = Image.open(scene_image_path).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-poem-frame-{int(_time.time())}.png"
    scene.save(save_path)
    return str(save_path)


def _get_audio_duration(audio_path: str) -> float:
    """获取音频时长（秒）"""
    import subprocess
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, timeout=10,
    )
    return float(result.stdout.strip())


def parse_script(script_path: str) -> dict:
    """解析诗词 YAML 脚本"""
    import yaml
    path = Path(script_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "lines" not in data:
        raise ValueError("Script must contain at least a 'lines' list")
    return data


def create_poem_video(
    script_path: str,
    voice: str = DEFAULT_VOICE,
    output: str | None = None,
    project: str | None = None,
) -> str:
    """完整诗词朗诵视频生成流程。

    Args:
        script_path: YAML 脚本路径
        voice: edge-tts 语音
        output: 输出视频路径（可选）
        project: 项目名（可选），指定后使用项目隔离目录

    Returns:
        视频文件路径
    """
    import subprocess as _subprocess
    import tempfile

    script = parse_script(script_path)
    title = script["title"]
    author = script.get("author", "")
    lines = script["lines"]

    # 路径：项目 vs 默认
    if project:
        scenes_dir = get_project_intermediate_dir(project, "scenes")
        frames_dir = get_project_intermediate_dir(project, "frames")
        video_dir = get_project_deliverable_dir(project, "videos")
    else:
        scenes_dir = OUTPUT_DIR
        frames_dir = OUTPUT_DIR
        video_dir = OUTPUT_DIR

    print(f"Generating poem video: {title} — {author}")
    print(f"  Lines: {len(lines)}, Voice: {voice}")
    if project:
        print(f"  Project: {project}")

    # ─── Step 1: 生成场景图（t2i，每句独立生成） ───
    scene_paths = []
    for i, line in enumerate(lines, start=1):
        print(f"\n[1/6] Generating scene {i} (t2i)...")
        scene = _t2i(line["description"], output_dir=scenes_dir)
        scene_paths.append(scene)
        print(f"  Saved: {scene}")

    # ─── Step 2: 生成标题卡 ───
    print(f"\n[2/5] Creating title card...")
    title_card = _create_title_card(title, author, bg_image=scene_paths[0], output_dir=frames_dir)
    print(f"  Saved: {title_card}")

    # ─── Step 3: 生成音频 ───
    print(f"\n[3/5] Generating audio (edge-tts)...")
    temp_dir = Path(tempfile.mkdtemp(prefix="poem-video-"))

    # 标题音频
    title_audio = temp_dir / "title.mp3"
    _generate_audio(f"{title}，{author}", voice, str(title_audio))
    title_duration = _get_audio_duration(str(title_audio))
    print(f"  Title audio: {title_duration:.1f}s")

    # 每句音频
    audio_paths = [str(title_audio)]
    durations = [title_duration]
    for i, line in enumerate(lines):
        audio_path = temp_dir / f"line-{i}.mp3"
        _generate_audio(line["text"], voice, str(audio_path))
        duration = _get_audio_duration(str(audio_path))
        audio_paths.append(str(audio_path))
        durations.append(duration)
        print(f"  Line {i+1} '{line['text']}': {duration:.1f}s")

    # ─── Step 4: 准备场景帧（字幕由 ffmpeg drawtext 叠加） ───
    print(f"\n[4/5] Preparing scene frames...")
    frame_paths = [title_card]
    for i, line in enumerate(lines):
        frame = _create_scene_frame(scene_paths[i], output_dir=frames_dir)
        frame_paths.append(frame)
        print(f"  Frame {i+1} saved")

    # ─── Step 5: ffmpeg 合成视频（concat filter 确保帧级同步） ───
    print(f"\n[5/5] Composing video (ffmpeg)...")

    # 构建 concat filter 输入
    input_args = []
    for i in range(len(frame_paths)):
        input_args.extend(["-loop", "1", "-t", str(durations[i]), "-i", frame_paths[i]])
        input_args.extend(["-i", audio_paths[i]])

    # 从 paths.yaml 读取中文字体路径（给 drawtext 用）
    font_path = get_font_path()

    # 构建 filter_complex 字符串（含 drawtext 字幕叠加）
    filter_parts = []
    for i in range(len(frame_paths)):
        v_idx = 2 * i
        a_idx = 2 * i + 1
        if i == 0:
            # 片头 — 无字幕
            filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS[v{i}]")
        else:
            # 场景 — drawtext 字幕，自动适配字号+换行防止溢出
            subtitle_text, subtitle_size = _auto_fit_subtitle(
                lines[i - 1]["text"], font_path,
                max_width=FRAME_W - 60, font_max=42, font_min=28,
            )
            dt = f"drawtext=text='{subtitle_text}':fontfile={font_path}:fontsize={subtitle_size}:fontcolor=white:shadowcolor=black@0.5:shadowx=2:shadowy=2:line_spacing=8:x=(w-text_w)/2:y=h-text_h-60"
            filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS,{dt}[v{i}]")
        filter_parts.append(f"[{a_idx}:a]adelay=0|0[a{i}]")

    concat_input = "".join(f"[v{i}][a{i}]" for i in range(len(frame_paths)))
    filter_complex = "; ".join(filter_parts)
    filter_complex += f"; {concat_input}concat=n={len(frame_paths)}:v=1:a=1[outv][outa]"

    output_path = output or str(video_dir / f"agnes-poem-{int(_time.time())}.mp4")
    cmd = [
        FFMPEG, "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    _subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # 清理临时文件
    shutil.rmtree(temp_dir)

    # 项目模式：询问清理中间产物
    if project:
        cleanup_intermediates(project)

    print(f"\nVideo saved to: {output_path}")
    return output_path
