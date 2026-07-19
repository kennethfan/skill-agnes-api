#!/usr/bin/env python3
"""故事视频 CLI 工具 — 基于 AGNES t2i + i2i + edge-tts

用法:
    # 搜索故事 → 全自动生成视频
    python3 story-video-cli.py --title "三只小猪"

    # 从 YAML 脚本生成
    python3 story-video-cli.py --script my-story.yaml

    # 指定视觉风格
    python3 story-video-cli.py --title "三只小猪" --style ink-wash

    # 跳过搜索，直接给文本文件
    python3 story-video-cli.py --textfile my-story.txt --style american

    # 指定输出路径
    python3 story-video-cli.py --script my-story.yaml -o my-story.mp4

    # 列出可用中文语音
    python3 story-video-cli.py --list-voices
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description="故事视频生成工具 — 面向3-6岁儿童")
    parser.add_argument("--title", "-t", help="故事名称（搜索模式）")
    parser.add_argument("--script", "-s", help="YAML 故事脚本路径")
    parser.add_argument("--textfile", "-f", help="故事文本文件路径（跳过搜索）")
    parser.add_argument("--style", default="american", help="视觉风格 preset (默认: american)")
    parser.add_argument("--voice", default="zh-CN-YunxiaNeural", help="默认语音 (默认: zh-CN-YunxiaNeural)")
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

    # 优先使用 YAML 脚本
    if args.script:
        from story_video import create_story_video
        result = create_story_video(
            script_path=args.script,
            voice=args.voice,
            output=args.output,
        )
        print(f"Story video saved to: {result}")
        return

    # 否则需要 title 或 textfile
    if not args.title and not args.textfile:
        print("Error: 请提供 --title（故事名）或 --script（YAML 脚本）或 --textfile（故事文本）")
        print("用法: python3 story-video-cli.py --title '三只小猪'")
        print("      python3 story-video-cli.py --script my-story.yaml")
        sys.exit(1)

    print("Story search mode not yet implemented in CLI.")
    print("Please use --script with a prepared YAML file for now.")
    print(f"Example: python3 story-video-cli.py --script {args.title or 'story'}.yaml")
    sys.exit(1)


if __name__ == "__main__":
    main()
