#!/usr/bin/env python3
"""诗词朗诵视频 CLI 工具 — 基于 AGNES t2i + i2i + edge-tts

用法:
    # 从 YAML 脚本生成诗词朗诵视频
    python3 poem-video-cli.py --script my-poem.yaml

    # 指定童声
    python3 poem-video-cli.py --script my-poem.yaml --voice zh-CN-YunxiaNeural

    # 指定输出路径
    python3 poem-video-cli.py --script my-poem.yaml --output my-poem.mp4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from poem_video import create_poem_video


def main():
    parser = argparse.ArgumentParser(description="诗词朗诵视频生成工具 — 基于 AGNES + edge-tts")
    parser.add_argument("--script", "-s", help="YAML 诗词脚本路径")
    parser.add_argument("--voice", default="zh-CN-YunxiaNeural", help="edge-tts 语音 (默认: zh-CN-YunxiaNeural 童声)")
    parser.add_argument("--output", "-o", help="输出视频路径")
    parser.add_argument("--list-voices", action="store_true", help="列出可用的中文 edge-tts 语音")

    args = parser.parse_args()

    if args.list_voices:
        import subprocess
        result = subprocess.run(
            ["edge-tts", "--list-voices"],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.splitlines():
            if "zh-CN" in line:
                print(line)
        return

    if not args.script:
        print("Error: --script 是必填参数")
        print("用法: python3 poem-video-cli.py --script my-poem.yaml")
        print("      python3 poem-video-cli.py --list-voices")
        sys.exit(1)

    result = create_poem_video(
        script_path=args.script,
        voice=args.voice,
        output=args.output,
    )
    print(f"Poem video saved to: {result}")


if __name__ == "__main__":
    main()
