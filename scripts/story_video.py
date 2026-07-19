"""故事视频生成模块 — 基于 AGNES t2i + i2i + edge-tts

面向 3-6 岁儿童的中文经典故事动画视频。
多角色配音（edge-tts 不同语音）、多 dialogue 同画面逐条拼接、纯文字字幕。

工作流:
  1. 解析故事 YAML 脚本
  2. t2i 生成第一张场景图（角色锚定起点）
  3. i2i 以首张为参考生成后续场景图
  4. 制作标题卡（故事名封面）
  5. edge-tts 逐条 dialogue 生成音频（每角色不同 voice）
  6. 场景图缩放到视频尺寸
  7. ffmpeg concat filter 合成（同画面多 dialogue 逐条拼接 + drawtext 字幕）

用法示例（AI 驱动）:
    from story_video import create_story_video
    path = create_story_video("my-story.yaml")
"""

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

# 复用 poem_video 的函数
sys.path.insert(0, str(Path(__file__).parent))
from poem_video import (
    _t2i, _i2i, _get_key, OUTPUT_DIR,
    FFMPEG, FFPROBE, FRAME_W, FRAME_H, SCENE_W, SCENE_H,
)

# --- 额外配置 ---

DEFAULT_VOICE = "zh-CN-YunxiaNeural"

# 角色 → voice 自动映射（可被 YAML 中 characters 覆盖）
ROLE_VOICE_MAP = {
    "旁白": "zh-CN-YunxiaNeural",
    "叙述": "zh-CN-YunxiaNeural",
    "大灰狼": "zh-CN-YunjianNeural",
    "灰狼": "zh-CN-YunjianNeural",
    "狼": "zh-CN-YunjianNeural",
    "狐狸": "zh-CN-YunjianNeural",
    "老虎": "zh-CN-YunjianNeural",
    "爸爸": "zh-CN-YunjianNeural",
    "妈妈": "zh-CN-XiaoxiaoNeural",
    "奶奶": "zh-CN-XiaoxiaoNeural",
    "外婆": "zh-CN-XiaoxiaoNeural",
    "小猪": "zh-CN-YunxiNeural",       # 活泼男声，适合小动物
    "小兔": "zh-CN-YunxiNeural",
    "小羊": "zh-CN-YunxiNeural",
    "小鸡": "zh-CN-YunxiNeural",
    "小鸭": "zh-CN-YunxiNeural",
    "小红帽": "zh-CN-XiaoyiNeural",    # 明亮活泼
    "姐姐": "zh-CN-XiaoyiNeural",
    "公主": "zh-CN-XiaoyiNeural",
}


def _resolve_voice(character: str, voice_overrides: dict | None = None) -> str:
    """解析角色语音。优先级: YAML override > 自动映射 > 默认"""
    if voice_overrides and character in voice_overrides:
        return voice_overrides[character]
    return ROLE_VOICE_MAP.get(character, DEFAULT_VOICE)


def _generate_audio_story(text: str, voice: str, output_path: str) -> float:
    """用 edge-tts 生成音频，返回时长（秒），带重试"""
    max_retries = 3
    for attempt in range(max_retries):
        result = subprocess.run(
            ["edge-tts", "--voice", voice, "--text", text,
             "--write-media", output_path, "--rate=-30%"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            break
        if attempt < max_retries - 1:
            wait = 2 ** attempt
            print(f"  ⚠️ Retry {attempt+1}/{max_retries} after {wait}s: edge-tts voice {voice}")
            _time.sleep(wait)
        else:
            raise RuntimeError(f"edge-tts failed after {max_retries} attempts: {result.stderr}")

    duration = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", output_path],
        capture_output=True, text=True, timeout=10,
    )
    return float(duration.stdout.strip())


def _wrap_text(text: str, max_chars: int = 15) -> str:
    """将长文本按中文字数拆为多行，供 drawtext 多行渲染"""
    import re
    lines = []
    while len(text) > max_chars:
        split = max_chars
        # 优先在标点后换行
        for pos in range(max_chars, max_chars // 2, -1):
            if pos < len(text) and text[pos] in ' ，。！？、；：)）':
                split = pos + 1
                break
        lines.append(text[:split])
        text = text[split:]
    if text:
        lines.append(text)
    return "\n".join(lines)


def _create_title_card_story(title: str, bg_image: str | None = None) -> str:
    """创建故事标题卡"""
    from PIL import Image, ImageDraw, ImageFont

    if bg_image:
        bg = Image.open(bg_image).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    else:
        bg = Image.new("RGB", (FRAME_W, FRAME_H), (240, 235, 225))

    draw = ImageDraw.Draw(bg)

    font_title = None
    for fp in ["/System/Library/Fonts/PingFang.ttc",
               "/System/Library/Fonts/STHeiti Light.ttc"]:
        if Path(fp).exists():
            try:
                font_title = ImageFont.truetype(fp, 56)
                break
            except Exception:
                continue
    if font_title is None:
        font_title = ImageFont.load_default()

    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    tx = (FRAME_W - title_w) // 2
    ty = FRAME_H // 2 - 40
    draw.text((tx, ty), title, fill=(40, 35, 30), font=font_title)

    save_path = OUTPUT_DIR / f"agnes-story-title-{int(_time.time())}.png"
    bg.save(save_path)
    return str(save_path)


def _create_scene_frame_story(scene_image_path: str) -> str:
    """将场景图缩放到视频尺寸（字幕由 ffmpeg drawtext 叠加）"""
    from PIL import Image
    scene = Image.open(scene_image_path).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    save_path = OUTPUT_DIR / f"agnes-story-frame-{int(_time.time())}.png"
    scene.save(save_path)
    return str(save_path)


def parse_story_script(script_path: str) -> dict:
    """解析故事 YAML 脚本"""
    import yaml
    path = Path(script_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "scenes" not in data:
        raise ValueError("Script must contain at least a 'scenes' list")
    return data


def create_story_video(
    script_path: str,
    voice: str = DEFAULT_VOICE,
    output: str | None = None,
) -> str:
    """完整故事视频生成流程。

    Args:
        script_path: YAML 故事脚本路径
        voice: 默认语音（旁白）
        output: 输出视频路径（可选）

    Returns:
        视频文件路径
    """
    import subprocess as _subprocess
    import tempfile

    script = parse_story_script(script_path)
    title = script["title"]
    style = script.get("style", "american")
    scenes = script["scenes"]
    voice_overrides = script.get("characters", {})

    print(f"Generating story video: {title}")
    print(f"  Scenes: {len(scenes)}, Style: {style}, Default voice: {voice}")

    # ─── Step 1: 生成场景图 ───
    # 第一张 t2i（角色锚定起点），后续 i2i
    scene_paths = []
    for i, scene in enumerate(scenes):
        if i == 0:
            print(f"\n[1/6] Generating scene {i+1} (t2i, anchor)...")
            scene_path = _t2i(scene["description"], f"{SCENE_W}x{SCENE_H}")
        else:
            print(f"\n[1/6] Generating scene {i+1} (i2i, anchored to first)...")
            scene_path = _i2i(scene_paths[0], scene["description"], f"{SCENE_W}x{SCENE_H}")
        scene_paths.append(scene_path)
        print(f"  Saved: {scene_path}")

    # ─── Step 2: 制作标题卡 ───
    print(f"\n[2/6] Creating title card...")
    title_card = _create_title_card_story(title, bg_image=scene_paths[0])
    print(f"  Saved: {title_card}")

    # ─── Step 3: 场景图缩放 ───
    print(f"\n[3/6] Preparing scene frames...")
    frame_paths = []
    for i, sp in enumerate(scene_paths):
        frame = _create_scene_frame_story(sp)
        frame_paths.append(frame)
        print(f"  Frame {i+1}: {Path(frame).name}")

    # ─── Step 4: 生成音频（逐条 dialogue） ───
    print(f"\n[4/6] Generating audio (edge-tts)...")
    temp_dir = Path(tempfile.mkdtemp(prefix="story-video-"))

    # 收集所有 segment：[frame_path, dialogue_text, voice, is_title]
    segments = []

    # 标题音频
    title_audio = temp_dir / "title.mp3"
    dur = _generate_audio_story(title, "zh-CN-YunxiaNeural", str(title_audio))
    segments.append({
        "frame": title_card,
        "text": title,
        "audio": str(title_audio),
        "duration": dur,
        "is_title": True,
    })
    print(f"  Title audio: {dur:.1f}s")

    # 每条对话
    seg_idx = 0
    for si, scene in enumerate(scenes):
        for di, dialogue in enumerate(scene["dialogues"]):
            dialog_voice = _resolve_voice(dialogue["character"], voice_overrides)
            audio_path = temp_dir / f"seg-{seg_idx}.mp3"
            dur = _generate_audio_story(dialogue["text"], dialog_voice, str(audio_path))
            segments.append({
                "frame": frame_paths[si],
                "text": dialogue["text"],
                "audio": str(audio_path),
                "duration": dur,
                "is_title": False,
            })
            print(f"  Seg {seg_idx}: [{dialogue['character']}] '{dialogue['text']}' ({dur:.1f}s, {dialog_voice})")
            seg_idx += 1

    # ─── Step 5: ffmpeg 合成视频（drawtext 字幕） ───
    print(f"\n[5/6] Composing video (ffmpeg)...")

    input_args = []
    for seg in segments:
        input_args.extend(["-loop", "1", "-t", f"{seg['duration']:.3f}", "-i", seg["frame"]])
        input_args.extend(["-i", seg["audio"]])

    # 查找中文字体
    font_path = None
    for fp in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]:
        if Path(fp).exists():
            font_path = fp
            break

    # 构建 filter_complex
    filter_parts = []
    for i, seg in enumerate(segments):
        v_idx = 2 * i
        a_idx = 2 * i + 1
        if seg["is_title"]:
            filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS[v{i}]")
        else:
            text = _wrap_text(seg["text"], 15)
            # 实际换行符 -> ffmpeg drawtext '\n' 序列
            text = text.replace("\n", "\\n")
            escaped_text = text.replace("'", "'\\\\\\''").replace(":", "\\\\:")
            dt = (
                f"drawtext=text='{escaped_text}'"
                f":fontfile={font_path}"
                f":fontsize=42:fontcolor=white"
                f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
                f":line_spacing=8"
                f":x=(w-text_w)/2:y=h-text_h-60"
            )
            filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS,{dt}[v{i}]")
        filter_parts.append(f"[{a_idx}:a]adelay=0|0[a{i}]")

    concat_input = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    filter_complex = "; ".join(filter_parts)
    filter_complex += f"; {concat_input}concat=n={len(segments)}:v=1:a=1[outv][outa]"

    output_path = output or str(OUTPUT_DIR / f"agnes-story-{int(_time.time())}.mp4")
    cmd = [
        FFMPEG, "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    _subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    # ─── Step 6: 清理 ───
    shutil.rmtree(temp_dir)

    print(f"\nVideo saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    # 直接运行测试
    if len(sys.argv) > 1:
        path = create_story_video(sys.argv[1])
        print(f"DONE: {path}")
    else:
        print("Usage: python3 story_video.py <script.yaml>")
