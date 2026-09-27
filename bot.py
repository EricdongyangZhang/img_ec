# -*- coding: utf-8 -*-
"""状态机：等待描述 → 生图中 → 已发图待确认 →（确认后）完成。

状态：
  IDLE       等待新的商品描述
  GENERATING 生图中，忽略其他输入
  AWAITING   已发候选图，等待回复 1/2/3 或「重画」
"""
import shutil
import threading
from pathlib import Path

from channel_base import Channel
from config import config
from image_gen import GLMImageClient, ImageGenError
from prompt_builder import build_prompt, parse_base_color

IDLE, GENERATING, AWAITING = "IDLE", "GENERATING", "AWAITING"

CONFIRM_TEXTS = {"1": 1, "2": 2, "3": 3}
REDO_WORDS = ("重画", "重来", "重新", "换一批", "换图", "不满意", "再来")


class TShirtBot:
    def __init__(self, channel: Channel):
        self.channel = channel
        self.gen = GLMImageClient()
        self.state = IDLE
        self.lock = threading.Lock()
        self.candidates: list[Path] = []
        self._last_desc = ""
        self._pending_desc = None  # GENERATING 期间排队的最新输入

    def handle_text(self, text: str) -> None:
        with self.lock:
            if self.state == GENERATING:
                t = text.strip()
                if t in CONFIRM_TEXTS or any(w in t for w in REDO_WORDS) or self._is_new_desc(t):
                    self._pending_desc = t
                    self.channel.send_text("已收到新请求，当前批次完成后自动开始")
                else:
                    self.channel.send_text("正在生成图片，请稍等约1-2分钟…")
                return

            if self.state == AWAITING:
                if text.strip() in CONFIRM_TEXTS:
                    self._confirm(CONFIRM_TEXTS[text.strip()])
                elif any(w in text for w in REDO_WORDS):
                    self._start_generate()
                elif self._is_new_desc(text):
                    self._start_generate(text)
                else:
                    self.channel.send_text("请回复 1 / 2 / 3 选择满意的一张，或回复「重画」重新生成")
                return

            # IDLE：把输入当作商品描述
            self._start_generate(text)

    @staticmethod
    def _is_new_desc(text: str) -> bool:
        """判断是否像一条新的商品描述（含底色词或较长文本）。"""
        t = text.strip()
        return parse_base_color(t) is not None or len(t) >= 6

    # ---------- 内部 ----------

    def _start_generate(self, user_desc: str = "") -> None:
        if self.state == AWAITING:
            user_desc = self._last_desc or ""
        base = parse_base_color(user_desc)
        if base is None:
            self.channel.send_text(
                "无法判断底色。请在最前面注明底色，例如：\n"
                "黑色 胸前白色印花龙\n"
                "或\n"
                "白色 简约几何图案"
            )
            return
        self._last_desc = user_desc
        self.state = GENERATING

        def worker():
            prompt = build_prompt(user_desc, base)
            try:
                paths = self.gen.generate_candidates(prompt)
            except ImageGenError as e:
                self.channel.send_text(f"生成失败：{e}")
                with self.lock:
                    self.state = IDLE
                return
            except Exception as e:  # 兜底
                self.channel.send_text(f"生成失败（未知错误）：{e}")
                with self.lock:
                    self.state = IDLE
                return
            self.candidates = paths
            with self.lock:
                self.state = AWAITING
            self.channel.send_images(paths)
            self.channel.send_text(
                "已生成3张候选图，回复对应数字选择满意的一张：\n"
                "1️⃣ 图1  2️⃣ 图2  3️⃣ 图3\n"
                "或回复「重画」重新生成"
            )
            self._drain_pending()

        self.channel.send_text(f"收到描述（{base}），正在生成3张候选图，约1-2分钟…")
        threading.Thread(target=worker, daemon=True).start()

    def _drain_pending(self) -> None:
        """当前批次结束后，若生成期间有排队的新请求则自动处理。"""
        with self.lock:
            pending = self._pending_desc
            self._pending_desc = None
        if pending:
            self.handle_text(pending)

    def _confirm(self, choice: int) -> None:
        if not (1 <= choice <= len(self.candidates)):
            self.channel.send_text("无效选择")
            return
        src = self.candidates[choice - 1]
        confirmed_dir = config.OUTPUT_DIR / "confirmed"
        confirmed_dir.mkdir(parents=True, exist_ok=True)
        dest = confirmed_dir / f"confirmed_{src.stem}.png"
        shutil.copy2(src, dest)
        self.channel.send_text(f"已确认第{choice}张 ✅\n图片已保存到：{dest}")
        self.state = IDLE
        self.candidates = []
