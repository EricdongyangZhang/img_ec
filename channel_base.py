# -*- coding: utf-8 -*-
"""通道抽象：消息入口与出口，具体实现见 console.py / wechat.py。"""
from abc import ABC, abstractmethod
from pathlib import Path


class Channel(ABC):
    """消息通道：负责接收用户文字、回发文字与图片。"""

    @abstractmethod
    def start(self, on_text) -> None:
        """启动监听，收到用户文字时回调 on_text(text)。"""

    @abstractmethod
    def send_text(self, text: str) -> None:
        """给用户发文字。"""

    @abstractmethod
    def send_images(self, paths: list[Path]) -> None:
        """给用户发图片。"""
