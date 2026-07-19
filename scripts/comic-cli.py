#!/usr/bin/env python3
"""漫画创作 CLI 工具 — 基于 AGNES t2i + i2i

用法:
    # 查看可用预设风格
    python3 comic-cli.py --list-presets

    # 从 YAML 脚本生成漫画
    python3 comic-cli.py --script my-comic.yaml

    # 指定风格预设
    python3 comic-cli.py --script my-comic.yaml --preset manga

    # 自定义 prompt（覆盖预设）
    python3 comic-cli.py --script my-comic.yaml --custom-prompt "{description}, cinematic lighting"

    # 指定面板尺寸
    python3 comic-cli.py --script my-comic.yaml --panel-size 1024x768

    # 指定输出路径
    python3 comic-cli.py --script my-comic.yaml --output my-comic.png
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comic import create_comic, list_presets


def main():
    parser = argparse.ArgumentParser(description="漫画创作工具 — 基于 AGNES t2i + i2i")
    parser.add_argument("--script", "-s", help="YAML 漫画脚本路径")
    parser.add_argument("--preset", "-p", help="风格预设 key（覆盖脚本中的 preset）")
    parser.add_argument("--custom-prompt", "-c", help="自定义 prompt（覆盖预设），用 {description} 引用场景描述")
    parser.add_argument("--panel-size", default="1024x768", help="面板尺寸 (默认 1024x768)")
    parser.add_argument("--output", "-o", help="输出路径")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用预设风格")

    args = parser.parse_args()

    if args.list_presets:
        presets = list_presets()
        print("可用漫画风格预设:")
        print(f"{'Key':<20} {'名称':<15} {'Prompt'}")
        print("-" * 80)
        for p in presets:
            print(f"{p['key']:<20} {p['name']:<15} {p['prompt'][:50]}...")
        return

    if not args.script:
        print("Error: --script 是必填参数")
        print("用法: python3 comic-cli.py --script my-comic.yaml")
        print("      python3 comic-cli.py --list-presets")
        sys.exit(1)

    result = create_comic(
        script_path=args.script,
        preset=args.preset,
        custom_prompt=args.custom_prompt,
        panel_size=args.panel_size,
        output=args.output,
    )
    print(f"Comic saved to: {result}")


if __name__ == "__main__":
    main()