# -*- coding: utf-8 -*-
"""会话记录通道：包装真实通道，转发收发的同时把事件写入 session_store。

- SessionChannel：装饰任意 Channel（微信/网页），记录用户入站、bot 出站文本与图片。
- WebChannel：网页「手动模式」的内部空通道，不向外部发送，用户消息由 UI 注入，
  便于在没有微信的环境下也能跑通会话显示与生图流程。
"""
import threading
from pathlib import Path

from channel_base import Channel
from config import config
from session_store import session_store


def _rel_to_output(p) -> str:
    """把图片绝对路径转成相对 OUTPUT_DIR 的正斜杠路径，供 /media 提供。"""
    try:
        return Path(p).resolve().relative_to(config.OUTPUT_DIR.resolve()).as_posix()
    except Exception:
        return Path(p).name


class SessionChannel(Channel):
    def __init__(self, inner: Channel, store=None):
        self._inner = inner
        self._store = store or session_store
        self._on_text = None
        self._wrapped = None

    def start(self, on_text) -> None:
        self._on_text = on_text

        def wrapped(text):
            # 记录用户入站消息，再交给 bot 处理
            self._store.add("user", "text", text=text)
            on_text(text)

        self._wrapped = wrapped
        self._inner.start(wrapped)

    def send_text(self, text: str) -> None:
        self._store.add("bot", "text", text=text)
        self._inner.send_text(text)

    def send_images(self, paths) -> None:
        rels = [_rel_to_output(p) for p in paths]
        self._store.add("bot", "images", images=rels)
        self._inner.send_images(paths)

    def stop(self) -> None:
        if hasattr(self._inner, "stop"):
            self._inner.stop()

    def inject_user(self, text: str) -> None:
        """供 Web UI 模拟一条用户输入（等价于真实通道收到消息）。"""
        if self._wrapped:
            self._wrapped(text)

    def __getattr__(self, name):
        # 其余属性/方法透传给内部通道
        return getattr(self._inner, name)


class WebChannel(Channel):
    """网页手动模式：不向外部发送，start 立即返回不阻塞。"""

    def __init__(self):
        self._on_text = None
        self._stop = threading.Event()

    def start(self, on_text) -> None:
        self._on_text = on_text
        # 不阻塞：网页模式无需从外部读取输入，用户消息由 UI 注入

    def send_text(self, text: str) -> None:
        pass  # SessionChannel 已记录，网页模式无需外发

    def send_images(self, paths) -> None:
        pass

    def stop(self) -> None:
        self._stop.set()
