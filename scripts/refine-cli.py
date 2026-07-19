#!/usr/bin/env python3
"""图片精修 CLI 工具 — 基于 AGNES i2i

用法:
    # 查看可用预设风格
    python3 refine-cli.py --list-presets

    # 按操作描述精修
    python3 refine-cli.py --input photo.jpg --operation "去噪并调亮"

    # 使用预设风格
    python3 refine-cli.py --input photo.jpg --preset ghibli

    # 自定义 prompt
    python3 refine-cli.py --input photo.jpg --custom-prompt "Make it look like a vintage postcard"

    # 指定尺寸
    python3 refine-cli.py --input photo.jpg --preset cyberpunk --size 2K --ratio 16:9

    # 输入为 URL
    python3 refine-cli.py --input https://example.com/photo.jpg --operation "调亮+锐化"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from refine import refine, list_presets


def main():
    parser = argparse.ArgumentParser(description="图片精修工具 — 基于 AGNES i2i")
    parser.add_argument("--input", "-i", help="输入图片路径或 URL")
    parser.add_argument("--operation", "-o", help="操作描述，如 '去噪并调亮'")
    parser.add_argument("--preset", "-p", help="预设风格 key")
    parser.add_argument("--custom-prompt", "-c", help="自定义 prompt（覆盖预设和操作描述）")
    parser.add_argument("--size", default="2K", help="输出尺寸 (1K/2K/3K/4K)")
    parser.add_argument("--ratio", default="16:9", help="宽高比 (16:9, 9:16, 1:1, 3:4, 4:3)")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用预设风格")

    args = parser.parse_args()

    if args.list_presets:
        presets = list_presets()
        print("可用预设风格:")
        print(f"{'Key':<20} {'名称':<15} {'Prompt'}")
        print("-" * 80)
        for p in presets:
            print(f"{p['key']:<20} {p['name']:<15} {p['prompt'][:50]}...")
        return

    if not args.input:
        print("Error: --input 是必填参数")
        print("用法: python3 refine-cli.py --input photo.jpg --operation '去噪并调亮'")
        print("      python3 refine-cli.py --input photo.jpg --preset ghibli")
        print("      python3 refine-cli.py --list-presets")
        sys.exit(1)

    result = refine(
        image=args.input,
        operation=args.operation or "",
        preset=args.preset,
        custom_prompt=args.custom_prompt,
        size=args.size,
        ratio=args.ratio,
    )
    print(f"Saved to: {result}")


if __name__ == "__main__":
    main()
