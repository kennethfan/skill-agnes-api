#!/usr/bin/env python3
"""
动态短剧管线 dynamic-story-pipeline.py — 真动态视频（非贴画）

与 story-pipeline(只调 t2i 静态图+ffmpeg concat)不同，本管线调用 AGNES /v1/videos
视频端点，为每镜生成真实运动 clip：

  S1. i2i 定帧    ImageClient.i2i(锚定角色图, scene.frame) → 每镜静态关键帧 PNG
  S2. i2v 动态化  VideoClient.create({mode: reference, images, prompt: scene.motion, size: 720P, aspect_ratio, seconds}) → 运动 clip MP4
  S3. 音频/字幕   edge-tts 对白 + Pillow 字幕 PNG + ffmpeg overlay（按对白时间戳 enable）
  S4. 合成        ffmpeg concat 全部镜头 → 最终 MP4

使用:
  python3 scripts/pipelines/dynamic-story-pipeline.py --yaml 故事-小兔子爱洗手.yaml
  python3 scripts/pipelines/dynamic-story-pipeline.py --yaml xxx.yaml --subdir 儿童-短剧 --width 1080 --height 1920
"""

import argparse
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from client import ImageClient, VideoClient  # noqa: E402
from utils import (  # noqa: E402
    get_ffmpeg_bin, get_ffprobe_bin, get_font_path, get_video_model,
)

# ─────────────────────────── 路径（可 --work-dir 覆盖） ───────────────────────────
_DEFAULT_WORK = Path.home() / "agent" / "media"
BASE_DIR: Path = _DEFAULT_WORK
IMAGES_DIR: Path = BASE_DIR / "images"
VIDEOS_DIR: Path = BASE_DIR / "videos"
TEMP_BASE: Path = BASE_DIR / "tmp"


def _set_work_dir(wd: Path) -> None:
    global BASE_DIR, IMAGES_DIR, VIDEOS_DIR, TEMP_BASE
    BASE_DIR = wd.resolve()
    IMAGES_DIR = BASE_DIR / "images"
    VIDEOS_DIR = BASE_DIR / "videos"
    TEMP_BASE = BASE_DIR / "tmp"


# ─────────────────────────── 生成参数（可 --xxx 覆盖） ───────────────────────────
AGNES_SIZE = "2K"
AGNES_RATIO = "9:16"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
OUTPUT_SUBDIR = "儿童-短剧"
EDGE_TTS_RATE = "-30%"
NARRATOR_VOICE = "zh-CN-YunxiaNeural"

# Video 2.5 Flash 仅支持 720P，时长 4–12s（字符串）；分块上限取 10s 留余量
VIDEO_SIZE = "720P"
VIDEO_ASPECT = "9:16"  # main() 中按输出尺寸推导（横→16:9/竖→9:16/方→1:1）
VIDEO_SECONDS_MIN = 4
VIDEO_SECONDS_MAX = 12
MAX_BLOCK_SECONDS = 10.0


def _pick_seconds(bdur: float) -> str:
    """块音频时长 → Video 2.5 Flash 的 seconds 参数（4–12s 字符串，向上取整并夹紧）"""
    return str(max(VIDEO_SECONDS_MIN, min(VIDEO_SECONDS_MAX, math.ceil(bdur))))


def _audio_duration(path: Path) -> float:
    r = subprocess.run([get_ffprobe_bin(), "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def _generate_audio(text: str, voice: str, out: Path) -> None:
    subprocess.run(["edge-tts", "--voice", voice, "--text", text,
                    "--write-media", str(out), f"--rate={EDGE_TTS_RATE}"],
                   check=True, capture_output=True, timeout=120)


def _resolve_voice(character: str, char_map: dict) -> str:
    c = character.strip()
    if c in char_map:
        return char_map[c]
    if c in ("", "旁白", "叙述"):
        return NARRATOR_VOICE
    return NARRATOR_VOICE


def _wrap_text(text: str, max_chars: int = 15) -> str:
    lines, rest = [], text
    while len(rest) > max_chars:
        cut = max_chars
        for pos in range(max_chars, max_chars // 2, -1):
            if pos < len(rest) and rest[pos] in ' ，。！？、；：)）':
                cut = pos + 1
                break
        lines.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        lines.append(rest)
    return "\n".join(lines)


def _subtitle_png(text: str, font_path: str, w: int = 0, h: int = 0) -> Path:
    """把多行对白渲染成透明字幕 PNG（白字黑边，适合 overlay 到动态视频）"""
    max_w = int(VIDEO_WIDTH * 0.86)
    for size in (44, 40, 36, 32):
        font = ImageFont.truetype(font_path, size)
        lines = _wrap_text(text, 12)
        widths = [int(font.getlength(l)) for l in lines.split("\n")]
        if max(widths) <= max_w:
            break
    line_h = int(size * 1.35)
    tw = max(widths) + 24
    th = line_h * len(lines.split("\n")) + 24
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines.split("\n")):  # type: ignore[possibly-undefined]
        lw = font.getlength(l)
        x = (tw - lw) / 2
        y = 8 + i * line_h
        d.text((x + 2, y + 2), l, font=font, fill=(0, 0, 0, 190))
        d.text((x, y), l, font=font, fill=(255, 255, 255, 255))
    out = TEMP_BASE / "subs" / f"sub-{int(time.time()*1000)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def load_yaml(p: str) -> dict:
    p = Path(p)
    if not p.is_absolute():
        for d in [BASE_DIR, BASE_DIR / "scripts"]:
            cand = d / p
            if cand.exists():
                p = cand
                break
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="儿童短剧真动态管线（AGNES i2i + i2v）")
    parser.add_argument("--yaml", required=True, help="YAML 剧本路径（故事-xxx.yaml）")
    parser.add_argument("--output", default=None, help="输出视频路径")
    parser.add_argument("--work-dir", default=None, help="工作目录（默认 ~/agent/media/）")
    parser.add_argument("--subdir", default=None, help="输出子目录相对 videos/（默认: 儿童-短剧）")
    parser.add_argument("--width", type=int, default=None, help="视频宽度（默认 1080）")
    parser.add_argument("--height", type=int, default=None, help="视频高度（默认 1920）")
    parser.add_argument("--size", default=None, help="AGNES 图片尺寸（默认 2K）")
    parser.add_argument("--rate", default=None, help="edge-tts 语速（默认 -30%）")
    parser.add_argument("--force", action="store_true", help="强制重跑已存在产物")
    args = parser.parse_args()

    if args.work_dir:
        _set_work_dir(Path(args.work_dir))
    global OUTPUT_SUBDIR, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_ASPECT, AGNES_SIZE, EDGE_TTS_RATE
    if args.subdir:
        OUTPUT_SUBDIR = args.subdir
    if args.width:
        VIDEO_WIDTH = args.width
    if args.height:
        VIDEO_HEIGHT = args.height
    VIDEO_ASPECT = "16:9" if VIDEO_WIDTH > VIDEO_HEIGHT else ("1:1" if VIDEO_WIDTH == VIDEO_HEIGHT else "9:16")
    if args.size:
        AGNES_SIZE = args.size
    if args.rate:
        EDGE_TTS_RATE = args.rate

    data = load_yaml(args.yaml)
    char_map = data.get("characters", {})
    anchors = data.get("anchors", {})
    scenes = data.get("scenes", [])
    title = data.get("title", "未命名")
    print(f"🎬 {title} | {len(scenes)} 镜 | {VIDEO_WIDTH}×{VIDEO_HEIGHT} 竖屏")

    work = TEMP_BASE / "dynamic-story"
    work.mkdir(parents=True, exist_ok=True)
    imgs = ImageClient()
    vids = VideoClient()

    # ───────── S1+S2: 逐镜 i2i 定帧 → i2v 动态 clip（超 10s 镜自动拆块） ─────────
    per_scene: dict[int, dict] = {}
    for si, sc in enumerate(scenes):
        n = si + 1
        print(f"\n── 镜 {n}/{len(scenes)} ──")
        # 1) 对白音频（先出音频才能定帧数）
        diag = sc.get("dialogues", [])
        audios: list[Path] = []
        for d in diag:
            v = _resolve_voice(d["character"], char_map)
            ap = work / f"s{si:02d}-d{len(audios)}.mp3"
            if not ap.exists() or args.force:
                print(f"  [tts] {d['character']}: {d['text'][:18]}…")
                _generate_audio(d["text"], v, ap)
            audios.append(ap)
        # 音频累计时长 → 分块（每块 ≤10s），跨块的对白被切断处无需精确切分：
        # 块边界取对白边界，保证每块整段对白完整
        adurs = [_audio_duration(a) for a in audios]
        total_dur = sum(adurs)
        blocks: list[list[int]] = [[]]  # 每块是对白索引列表
        cur = 0.0
        for j, ad in enumerate(adurs):
            if blocks[-1] and cur + ad > MAX_BLOCK_SECONDS:
                blocks.append([])
                cur = 0.0
            blocks[-1].append(j)
            cur += ad
        print(f"  对白总长 {total_dur:.1f}s → 拆 {len(blocks)} 块（每块≤10s）")

        # 2) i2i 定帧（每镜一张，各块共用）
        frame_png = work / f"s{si:02d}-frame.png"
        if not frame_png.exists() or args.force:
            print(f"  [i2i] 定帧…")
            anchor = anchors.get(sc.get("anchor", ""), "")
            if anchor:
                ap = Path(anchor)
                if not ap.is_absolute():
                    ap = BASE_DIR / anchor
                url = imgs.i2i(str(ap), sc["frame"], size=AGNES_SIZE, ratio=AGNES_RATIO)
            else:
                url = imgs.t2i(sc["frame"], size=AGNES_SIZE, ratio=AGNES_RATIO)
            frame_png.write_bytes(imgs.download(url))
        print(f"  [i2i] 定帧 ✓ {frame_png.name}")

        # 3) i2v 动态化（Video 2.5 Flash reference 模式：images 数组传定帧 data URI；
        #    仅支持 720P，宽高比按输出尺寸推导）
        block_clips: list[Path] = []
        ok = True
        for bi, idxs in enumerate(blocks):
            bdur = sum(adurs[j] for j in idxs)
            bsec = _pick_seconds(bdur)
            clip = work / f"s{si:02d}-b{bi}-clip.mp4"
            if not clip.exists() or args.force:
                print(f"  [i2v] 块{bi+1}/{len(blocks)}（音频 {bdur:.1f}s → 请求 {bsec}s）…")
                image_ref = ImageClient._resolve_image(str(frame_png))
                task = None
                for _try in range(10):
                    try:
                        task = vids.create({"prompt": sc["motion"], "mode": "reference",
                                            "size": VIDEO_SIZE, "aspect_ratio": VIDEO_ASPECT,
                                            "seconds": bsec, "images": [image_ref]})
                        break
                    except Exception:
                        time.sleep(12)
                if not task:
                    print(f"  ⚠️ 镜 {n} 块{bi+1} create 失败（限流），跳过，下次运行续跑")
                    ok = False
                    break
                # 自定义轮询（Video 2.5 Flash 端点）：容忍 GET 偶发 HTTP 400（任务仍在推进）
                deadline = time.time() + 600
                status = None
                data = {}
                while time.time() < deadline:
                    try:
                        data = vids.get(f"/agnesapi?{urlencode({'video_id': task, 'model_name': get_video_model()})}")
                        status = data.get("status", "")
                        if status in ("completed", "failed"):
                            break
                    except Exception:
                        time.sleep(8)
                        continue
                    time.sleep(8)
                if status != "completed":
                    print(f"  ⚠️ 镜 {n} 块{bi+1} 视频失败: {data.get('error') if status else '超时'}，跳过，下次运行续跑")
                    ok = False
                    break
                # 下载地址来自独立端点 /agnesapi?video_id=&model_name=（429 限流时等待重试；
                # Video 2.5 Flash 的 URL 在 metadata.url 中）
                dl = None
                for _try in range(12):
                    try:
                        dl = vids.get(f"/agnesapi?{urlencode({'video_id': task, 'model_name': get_video_model()})}")
                        break
                    except Exception:
                        time.sleep(10)
                video_url = ((dl.get("metadata", {}) if dl else {}) or {}).get("url", "")
                if not video_url and dl:
                    video_url = dl.get("url", "")  # 兼容旧格式
                if not dl or dl.get("status") != "completed" or not video_url:
                    print(f"  ⚠️ 镜 {n} 块{bi+1} 下载地址获取失败: {dl}，跳过，下次运行续跑")
                    ok = False
                    break
                clip.write_bytes(imgs.download(video_url))
            block_clips.append(clip)
        if not ok:
            print(f"  ⏭ 镜 {n} 有块失败，整体跳过（下次运行续跑）")
            continue
        # 同镜多块顺序 concat → 镜级 clip
        if len(block_clips) == 1:
            scene_clip = block_clips[0]
        else:
            scene_clip = work / f"s{si:02d}-clip.mp4"
            if not scene_clip.exists() or args.force:
                lst = work / f"s{si:02d}-blocks.txt"
                lst.write_text("".join(f"file '{c}'\n" for c in block_clips), encoding="utf-8")
                r = subprocess.run([get_ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
                                    "-i", str(lst), "-c", "copy", str(scene_clip)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    print(f"  ❌ 镜 {n} 块拼接失败:\n{r.stderr[-500:]}")
                    sys.exit(1)
        per_scene[si] = {"audios": audios, "diag": diag, "adurs": adurs,
                         "dur": _audio_duration(scene_clip), "clip": scene_clip}

    # ───────── S3+S4: 每镜字幕+音频合成 → concat ─────────
    print("\n── 合成字幕/音频 → 成片 ──")
    font_path = get_font_path()
    finals: list[Path] = []
    for si in range(len(scenes)):
        if si not in per_scene:
            print(f"  ⏭ 镜 {si+1} 无镜级 clip（i2v 失败跳过），略过")
            continue
        n = si + 1
        clip = info["clip"]
        info = per_scene[si]
        final = work / f"s{si:02d}-final.mp4"
        if not final.exists() or args.force:
            parts = []
            t = 0.0
            for ap in info["audios"]:
                ad = _audio_duration(ap)
                parts.append((ap, t, ad))
                t += ad
            pad = max(0.0, info["dur"] - t)
            # 字幕 PNG 每对白一张，作为独立输入流参与 overlay
            subs = [_subtitle_png(d["text"], font_path) for d in info["diag"]]
            # inputs: [0]=clip, [1..M]=音频, [M+1..]=字幕 PNG
            inputs = [clip] + [p[0] for p in parts] + subs
            m = len(parts)
            ic = "".join(f"[{i}:a]" for i in range(1, m + 1)) \
                 + f"concat=n={m}:v=0:a=1[aud];"
            ic += f"[aud]apad=pad_dur={pad:.3f}[audp];"
            # 视频：链式 overlay，每个 overlay 叠一张字幕（enable 按对白时间窗）
            # base 始终为上一个输出 [v{k}]，叠加第 (m+1+j) 输入的字幕 PNG
            vf_parts = []
            vid_idx = 0
            base_label = "0:v"
            for j, d in enumerate(info["diag"]):
                start = info["adurs"][:j] and sum(info["adurs"][:j]) or 0.0
                end = start + info["adurs"][j]
                vf_parts.append(
                    f"[{base_label}][{m+1+j}:v]overlay=(W-w)/2:H-h-140:"
                    f"enable='between(t,{start:.2f},{end:.2f})'[v{vid_idx+1}]"
                )
                base_label = f"v{vid_idx+1}"
                vid_idx += 1
            vchain = ";".join(vf_parts)
            cmd = [get_ffmpeg_bin(), "-y"] + \
                  [item for i in inputs for item in ["-i", str(i)]] + \
                  ["-filter_complex", f"{ic}{vchain}",
                   "-map", f"[v{vid_idx}]", "-map", "[audp]",
                   "-t", f"{info['dur']:.3f}", "-pix_fmt", "yuv420p", str(final)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  ❌ 镜 {n} 合成失败:\n{r.stderr[-800:]}")
                sys.exit(1)
        finals.append(final)
        print(f"  镜 {n} ✓ {final.name}")

    # concat 列表
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in finals), encoding="utf-8")
    out = Path(args.output) if args.output else VIDEOS_DIR / OUTPUT_SUBDIR / f"{title}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([get_ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"❌ 最终合成失败:\n{r.stderr[-800:]}")
        sys.exit(1)
    print(f"\n✅ 成片: {out}")


if __name__ == "__main__":
    main()