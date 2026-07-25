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

import yaml

from utils import get_default_dir, get_project_intermediate_dir, get_project_deliverable_dir, cleanup_intermediates, get_font_path

# 复用 poem_video 的函数
sys.path.insert(0, str(Path(__file__).parent))
from poem_video import (
    _t2i, _i2i,
    FFMPEG, FFPROBE, FRAME_W, FRAME_H, SCENE_W, SCENE_H,
    _auto_fit_subtitle,
)

OUTPUT_DIR = get_default_dir()

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


# ─── checkpoint 支持 ───────────────────────────────────────────

CHECKPOINT_FILE = ".story-state.yaml"


def _load_checkpoint(project_dir: str) -> dict | None:
    cp = Path(project_dir) / CHECKPOINT_FILE
    if not cp.exists():
        return None
    with open(cp, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_checkpoint(project_dir: str, state: dict):
    state["updated_at"] = int(_time.time())
    cp = Path(project_dir) / CHECKPOINT_FILE
    with open(cp, "w", encoding="utf-8") as f:
        yaml.dump(state, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _new_checkpoint(title: str) -> dict:
    return {
        "version": 1,
        "title": title,
        "created_at": int(_time.time()),
        "updated_at": int(_time.time()),
        "stages": {s: None for s in ("scenes", "title_card", "frames", "audio", "video")},
    }


def _stage_done(checkpoint: dict | None, stage: str) -> bool:
    return bool(checkpoint and checkpoint.get("stages", {}).get(stage) == "done")


# ──────────────────────────────────────────────────────────────


def _audio_duration(path: str) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, timeout=10,
    )
    return float(result.stdout.strip())


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


def _create_title_card_story(title: str, bg_image: str | None = None, output_dir: Path | None = None) -> str:
    """创建故事标题卡"""
    from PIL import Image, ImageDraw, ImageFont

    if bg_image:
        bg = Image.open(bg_image).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    else:
        bg = Image.new("RGB", (FRAME_W, FRAME_H), (240, 235, 225))

    draw = ImageDraw.Draw(bg)

    font_title = None
    font_path = get_font_path()
    if font_path:
        try:
            font_title = ImageFont.truetype(font_path, 56)
        except Exception:
            pass
    if font_title is None:
        font_title = ImageFont.load_default()

    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    tx = (FRAME_W - title_w) // 2
    ty = FRAME_H // 2 - 40
    draw.text((tx, ty), title, fill=(40, 35, 30), font=font_title)

    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-story-title-{int(_time.time())}.png"
    bg.save(save_path)
    return str(save_path)


def _create_scene_frame_story(scene_image_path: str, output_dir: Path | None = None) -> str:
    """将场景图缩放到视频尺寸（字幕由 ffmpeg drawtext 叠加）"""
    from PIL import Image
    scene = Image.open(scene_image_path).resize((FRAME_W, FRAME_H), Image.LANCZOS)
    save_dir = output_dir or OUTPUT_DIR
    save_path = save_dir / f"agnes-story-frame-{int(_time.time())}.png"
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
    project: str | None = None,
) -> str:
    import subprocess as _subprocess

    script = parse_story_script(script_path)
    title = script["title"]
    style = script.get("style", "american")
    scenes = script["scenes"]
    voice_overrides = script.get("characters", {})

    # 路径：项目 vs 默认
    if project:
        scenes_dir = Path(get_project_intermediate_dir(project, "scenes"))
        frames_dir = Path(get_project_intermediate_dir(project, "frames"))
        audio_dir = Path(get_project_intermediate_dir(project, "audio"))
        video_dir = Path(get_project_deliverable_dir(project, "videos"))
    else:
        scenes_dir = OUTPUT_DIR
        frames_dir = OUTPUT_DIR
        audio_dir = None
        video_dir = OUTPUT_DIR

    print(f"Generating story video: {title}")
    print(f"  Scenes: {len(scenes)}, Style: {style}, Default voice: {voice}")
    if project:
        print(f"  Project: {project}")

    # ─── Checkpoint 加载 ───
    checkpoint = None
    if project:
        checkpoint = _load_checkpoint(project)
        if checkpoint:
            done = [s for s, v in checkpoint["stages"].items() if v == "done"]
            print(f"  [checkpoint] Resuming — stages done: {done}")
        else:
            checkpoint = _new_checkpoint(title)

    # ─── Step 1: 生成场景图（带确定性 seed） ───
    if not _stage_done(checkpoint, "scenes"):
        scene_paths = []
        for i, scene in enumerate(scenes):
            dest = scenes_dir / f"scene-{i:02d}.jpg" if project else None
            if dest and dest.exists():
                scene_paths.append(str(dest))
                continue
            # 确定性 seed: 相同 description → 相同 seed → 可复现
            seed = abs(hash(scene["description"])) & 0xFFFFFFFF
            if i == 0:
                print(f"\n[1/6] Scene {i+1} (t2i, anchor, seed={seed})...")
                sp = _t2i(scene["description"], f"{SCENE_W}x{SCENE_H}", output_dir=scenes_dir, seed=seed)
            else:
                print(f"\n[1/6] Scene {i+1} (i2i, seed={seed})...")
                sp = _i2i(scene_paths[0], scene["description"], f"{SCENE_W}x{SCENE_H}", output_dir=scenes_dir, seed=seed)
            sp_path = Path(sp)
            if dest:
                if sp_path != dest:
                    sp_path.rename(dest)
                scene_paths.append(str(dest))
            else:
                scene_paths.append(sp)
            print(f"  Saved: {scene_paths[-1]}")

        if project:
            checkpoint["stages"]["scenes"] = "done"
            _save_checkpoint(project, checkpoint)
    else:
        scene_paths = [str(scenes_dir / f"scene-{i:02d}.jpg") for i in range(len(scenes))]
        # verify files actually exist
        missing = [p for p in scene_paths if not Path(p).exists()]
        if missing:
            print(f"  ⚠️ [checkpoint] Scenes marked done but files missing, regenerating: {missing}")
            scene_paths = []
            for i, scene in enumerate(scenes):
                dest = scenes_dir / f"scene-{i:02d}.jpg"
                seed = abs(hash(scene["description"])) & 0xFFFFFFFF
                if i == 0:
                    sp = _t2i(scene["description"], f"{SCENE_W}x{SCENE_H}", output_dir=scenes_dir, seed=seed)
                else:
                    sp = _i2i(scene_paths[0], scene["description"], f"{SCENE_W}x{SCENE_H}", output_dir=scenes_dir, seed=seed)
                src = Path(sp)
                if src != dest:
                    src.rename(dest)
                scene_paths.append(str(dest))
            checkpoint["stages"]["scenes"] = "done"
            _save_checkpoint(project, checkpoint)
        else:
            print(f"  [checkpoint] Scenes already done, {len(scene_paths)} images")

    # ─── Step 2: 制作标题卡 ───
    if not _stage_done(checkpoint, "title_card"):
        print(f"\n[2/6] Creating title card...")
        title_card = _create_title_card_story(title, bg_image=scene_paths[0], output_dir=frames_dir)
        if project:
            dest = frames_dir / "title.png"
            src = Path(title_card)
            if src != dest:
                src.rename(dest)
            title_card = str(dest)
        print(f"  Saved: {title_card}")

        if project:
            checkpoint["stages"]["title_card"] = "done"
            _save_checkpoint(project, checkpoint)
    else:
        title_card = str(frames_dir / "title.png")
        print(f"  [checkpoint] Title card already done")

    # ─── Step 3: 场景图缩放 ───
    if not _stage_done(checkpoint, "frames"):
        print(f"\n[3/6] Preparing scene frames...")
        frame_paths = []
        for i, sp in enumerate(scene_paths):
            dest = frames_dir / f"frame-{i:02d}.png" if project else None
            if dest and dest.exists():
                frame_paths.append(str(dest))
                continue
            frame = _create_scene_frame_story(sp, output_dir=frames_dir)
            fp = Path(frame)
            if dest:
                if fp != dest:
                    fp.rename(dest)
                frame_paths.append(str(dest))
            else:
                frame_paths.append(frame)
            print(f"  Frame {i+1}: {Path(frame_paths[-1]).name}")

        if project:
            checkpoint["stages"]["frames"] = "done"
            _save_checkpoint(project, checkpoint)
    else:
        frame_paths = [str(frames_dir / f"frame-{i:02d}.png") for i in range(len(scene_paths))]
        print(f"  [checkpoint] Frames already done, {len(frame_paths)} frames")

    # ─── Step 4: 生成音频 ───
    if not _stage_done(checkpoint, "audio"):
        print(f"\n[4/6] Generating audio (edge-tts)...")
        if project:
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_root = audio_dir
        else:
            audio_root = Path(tempfile.mkdtemp(prefix="story-video-"))

        segments = []

        # 标题音频
        title_ap = audio_root / "title.mp3"
        if title_ap.exists():
            dur = _audio_duration(str(title_ap))
            print(f"  [resume] Title audio exists ({dur:.1f}s)")
        else:
            dur = _generate_audio_story(title, "zh-CN-YunxiaNeural", str(title_ap))
            print(f"  Title audio: {dur:.1f}s")
        segments.append({
            "frame": title_card, "text": title,
            "audio": str(title_ap), "duration": dur, "is_title": True,
        })

        # 每条对话
        seg_idx = 0
        for si, scene in enumerate(scenes):
            for di, dialogue in enumerate(scene["dialogues"]):
                dialog_voice = _resolve_voice(dialogue["character"], voice_overrides)
                ap = audio_root / f"s{si:02d}_d{di:02d}.mp3"
                if ap.exists():
                    dur = _audio_duration(str(ap))
                    print(f"  [resume] Seg {seg_idx}: [{dialogue['character']}] exists ({dur:.1f}s)")
                else:
                    dur = _generate_audio_story(dialogue["text"], dialog_voice, str(ap))
                    print(f"  Seg {seg_idx}: [{dialogue['character']}] '{dialogue['text']}' ({dur:.1f}s)")
                segments.append({
                    "frame": frame_paths[si], "text": dialogue["text"],
                    "audio": str(ap), "duration": dur, "is_title": False,
                })
                seg_idx += 1

        if project:
            checkpoint["stages"]["audio"] = "done"
            checkpoint["segments_cache"] = segments
            _save_checkpoint(project, checkpoint)
    else:
        # 从 checkpoint 重建 segments（仅 project 模式）
        print(f"  [checkpoint] Audio already done, loading from checkpoint")
        segments = checkpoint.get("segments_cache", [])
        if not segments:
            # 容错：如果 checkpoint 中没有缓存 segments，从文件重建
            audio_root = audio_dir
            segments = []
            seg_idx = 0
            title_ap = audio_root / "title.mp3"
            if title_ap.exists():
                dur = _audio_duration(str(title_ap))
                segments.append({
                    "frame": title_card, "text": title,
                    "audio": str(title_ap), "duration": dur, "is_title": True,
                })
            for si, scene in enumerate(scenes):
                for di, dialogue in enumerate(scene["dialogues"]):
                    ap = audio_root / f"s{si:02d}_d{di:02d}.mp3"
                    if ap.exists():
                        dur = _audio_duration(str(ap))
                        segments.append({
                            "frame": frame_paths[si], "text": dialogue["text"],
                            "audio": str(ap), "duration": dur, "is_title": False,
                        })
                    seg_idx += 1

    # ─── Step 5: ffmpeg 合成视频（drawtext 字幕） ───
    if not _stage_done(checkpoint, "video"):
        print(f"\n[5/6] Composing video (ffmpeg)...")

        input_args = []
        for seg in segments:
            input_args.extend(["-loop", "1", "-t", f"{seg['duration']:.3f}", "-i", seg["frame"]])
            input_args.extend(["-i", seg["audio"]])

        font_path = get_font_path()

        filter_parts = []
        for i, seg in enumerate(segments):
            v_idx = 2 * i
            a_idx = 2 * i + 1
            if seg["is_title"]:
                filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS[v{i}]")
            else:
                subtitle_text, subtitle_size = _auto_fit_subtitle(
                    seg["text"], font_path,
                    max_width=FRAME_W - 60, font_max=42, font_min=28,
                )
                escaped_text = subtitle_text.replace("'", "'\\\\\\''").replace(":", "\\\\:")
                dt = (
                    f"drawtext=text='{escaped_text}'"
                    f":fontfile={font_path}"
                    f":fontsize={subtitle_size}:fontcolor=white"
                    f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
                    f":line_spacing=8"
                    f":x=(w-text_w)/2:y=h-text_h-60"
                )
                filter_parts.append(f"[{v_idx}:v]setpts=PTS-STARTPTS,{dt}[v{i}]")
            filter_parts.append(f"[{a_idx}:a]adelay=0|0[a{i}]")

        concat_input = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        filter_complex = "; ".join(filter_parts)
        filter_complex += f"; {concat_input}concat=n={len(segments)}:v=1:a=1[outv][outa]"

        output_path = output or str(video_dir / f"agnes-story-{int(_time.time())}.mp4")
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

        if project:
            checkpoint["stages"]["video"] = "done"
            checkpoint["output_path"] = output_path
            _save_checkpoint(project, checkpoint)

        print(f"\nVideo saved to: {output_path}")
    else:
        output_path = checkpoint.get("output_path", "")
        print(f"  [checkpoint] Video already done: {output_path}")

    # ─── 清理（仅非 project 模式，用临时目录时） ───
    if not project and 'audio_root' in vars():
        shutil.rmtree(audio_root, ignore_errors=True)

    return output_path


if __name__ == "__main__":
    # 直接运行测试
    if len(sys.argv) > 1:
        path = create_story_video(sys.argv[1])
        print(f"DONE: {path}")
    else:
        print("Usage: python3 story_video.py <script.yaml>")
