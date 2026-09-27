# -*- coding: utf-8 -*-
"""控制台通道：在本机命令行里输入描述、回复数字确认。适合调试与兜底。"""
from pathlib import Path

from channel_base import Channel


class ConsoleChannel(Channel):
    def start(self, on_text) -> None:
        print("=" * 50)
        print("控制台模式：直接输入商品描述（如：黑色 胸前白色印花龙）")
        print("图片生成后输入 1/2/3 选择，输入「重画」重新生成，Ctrl+C 退出")
        print("=" * 50)
        while True:
            try:
                text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            on_text(text)

    def send_text(self, text: str) -> None:
        print(text)

    def send_images(self, paths: list[Path]) -> None:
        for i, p in enumerate(paths, 1):
            print(f"[{i}] {p}")
