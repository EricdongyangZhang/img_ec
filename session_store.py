# -*- coding: utf-8 -*-
"""会话事件存储：线程安全的环形缓冲 + JSONL 落盘历史。

浏览器通过 /api/session?since=<seq> 拉取增量事件，实现实时会话显示。
事件结构：{seq, ts, role, type, text?, images?}
  role: user | bot | system
  type: text | images | system
"""
import json
import threading
import time
from collections import deque
from pathlib import Path

from config import BASE_DIR

MAX_EVENTS = 200  # 内存中保留的最近事件数
HISTORY_FILE = BASE_DIR / "session_history.jsonl"


class SessionStore:
    def __init__(self, maxlen: int = MAX_EVENTS, history_file=HISTORY_FILE):
        self._lock = threading.Lock()
        self._events = deque(maxlen=maxlen)
        self._seq = 0
        self._history_file = Path(history_file)

    def add(self, role: str, type: str, text: str = None, images: list = None) -> dict:
        """追加一条会话事件，返回该事件。"""
        with self._lock:
            self._seq += 1
            ev = {
                "seq": self._seq,
                "ts": time.time(),
                "role": role,
                "type": type,
                "text": text,
                "images": images or [],
            }
            self._events.append(ev)
        self._persist(ev)
        return ev

    def _persist(self, ev: dict) -> None:
        try:
            with open(self._history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 落盘失败不影响实时显示

    def since(self, seq: int = 0) -> list:
        """返回 seq 之后的所有事件。"""
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        """清空内存事件（不动历史文件）。"""
        with self._lock:
            self._events.clear()
            self._seq = 0


# 全局单例，供通道包装器与 Flask 路由共享
session_store = SessionStore()
