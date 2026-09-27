# -*- coding: utf-8 -*-
"""微信通道：独立子窗口 + 纯 UIA 只读轮询。

- AddListenChat 把「文件传输助手」独立成子窗口，机器人只在子窗口内活动；
- 消息读取用自带 uiautomation 库直接读控件树（纯只读操作，不抢焦点），
  不再调用 wxauto4 的 GetAllMessage（其发送者解析会激活窗口抢焦点）；
- 因此无需「空闲门槛」，你在任何窗口打字都不受影响。

注意：
- 免费版 wxauto4 仅支持微信客户端 4.1.8.107 及以下版本。
- 电脑微信必须保持登录；子窗口别关（关了机器人会自动重建）。
"""
import threading
import time
from collections import deque
from pathlib import Path

from channel_base import Channel

POLL_INTERVAL = 2  # 秒
WARMUP_SECONDS = 45  # 启动热身期：吸收已有消息不处理
CONTENT_DEDUP_SECONDS = 120  # 相同内容在该时间窗内视为同一条
SUB_WINDOW_AID = "ChatSingleWindowfilehelper"  # 文件传输助手子窗口 AutomationId
MSG_LIST_AID = "chat_message_list"  # 消息列表控件 AutomationId
TAIL_KEEP = 10  # 消息列表尾部保留条目数，用于新旧对比
RECREATE_AFTER_MISSES = 15  # 连续读不到窗口 N 次后重建子窗口

try:
    from wxauto4.uia import uiautomation as auto
except ImportError:
    auto = None


class WeChatChannel(Channel):
    def __init__(self, listen_chat: str):
        self.listen_chat = listen_chat
        self._wx = None
        self._sub = None
        self._on_text = None
        self._sent = deque(maxlen=50)  # 机器人自己发过的内容，避免回环
        self._recent = {}  # content -> (时间, 是否已处理)，内容级去重
        self._warmup_until = 0.0
        self._prev_anchor = None  # 上次的时间锚点条目
        self._prev_after = ()  # 上次锚点之后的文本序列
        self._seen_anchors = set()  # 已见过的时间锚点，防止滚动回旧位置时重放
        self._misses = 0  # 连续读不到窗口的次数
        self._stop = threading.Event()

    # ---------- 生命周期 ----------

    def start(self, on_text) -> None:
        self._on_text = on_text
        try:
            from wxauto4 import WeChat
        except ImportError:
            raise RuntimeError("未安装 wxauto4，请先执行 pip install wxauto4")

        try:
            self._wx = WeChat(ads=False)
        except Exception as e:
            raise RuntimeError(
                f"微信初始化失败：{e}\n"
                f"原因通常是微信客户端版本过新（免费版 wxauto4 最高支持 4.1.8.107）。\n"
                f"可选：1) 把微信降级到 4.1.8.107；2) 换 Plus 版 wxautox4；3) 先用控制台通道。"
            )

        self._sub = self._ensure_sub()
        if self._sub is None:
            raise RuntimeError(f"无法创建「{self.listen_chat}」独立子窗口，请确认该会话存在")

        self._warmup_until = time.monotonic() + WARMUP_SECONDS
        threading.Thread(target=self._poll_loop, daemon=True).start()
        print(f"[微信通道] 已开始监听「{self.listen_chat}」（纯UIA只读模式，不抢焦点）")
        print(f"[微信通道] 启动热身约 {WARMUP_SECONDS} 秒，旧消息不会触发")

    def stop(self) -> None:
        self._stop.set()

    # ---------- 发送 ----------

    def send_text(self, text: str) -> None:
        # 加前缀区分机器人消息；记录实际发送的完整内容以防自我触发
        full = f"Bot : {text}"
        self._sent.append(full)
        print(f"[微信通道] 发送消息: {full}")
        self._sub.SendMsg(full)

    def send_images(self, paths: list[Path]) -> None:
        # 逐张发送并加「图N」标注，避免手机端因网络延时导致图片顺序不一致
        for idx, p in enumerate(paths, start=1):
            caption = f"Bot : 图{idx}"
            self._sent.append(caption)
            print(f"[微信通道] 发送消息: {caption}")
            self._sub.SendMsg(caption)
            time.sleep(1.2)
            print(f"[微信通道] 发送图片: {p}")
            self._sub.SendFiles([str(p)])
            time.sleep(1.2)

    # ---------- 子窗口管理 ----------

    @staticmethod
    def _noop_cb(msg, chat) -> None:
        pass  # 不用事件回调，仅借 AddListenChat 创建子窗口

    def _ensure_sub(self):
        """获取监听会话的子窗口；不存在则通过 AddListenChat 创建。"""
        try:
            sub = self._wx.GetSubWindow(self.listen_chat)
            if sub is not None:
                return sub
        except Exception:
            pass
        try:
            self._wx.AddListenChat(self.listen_chat, self._noop_cb)
        except Exception as e:
            print("[微信通道] AddListenChat 失败:", e)
        for _ in range(10):
            try:
                sub = self._wx.GetSubWindow(self.listen_chat)
                if sub is not None:
                    return sub
            except Exception:
                pass
            time.sleep(0.5)
        return None

    # ---------- 纯 UIA 只读轮询 ----------

    def _read_tail(self):
        """只读控件树，返回消息列表尾部条目序列 ((class, name), ...)。不激活任何窗口。"""
        if auto is None:
            return None
        try:
            win = auto.WindowControl(searchDepth=2, AutomationId=SUB_WINDOW_AID)
            if not win.Exists(0):
                return None
            lst = win.ListControl(searchDepth=15, AutomationId=MSG_LIST_AID)
            items = []
            for it in lst.GetChildren():
                try:
                    cls = it.ClassName or ""
                    name = (it.Name or "").strip()
                except Exception:
                    continue
                if name:
                    items.append((cls, name))
            return tuple(items[-TAIL_KEEP:])
        except Exception:
            return None

    def _poll_loop(self) -> None:
        try:
            import comtypes

            comtypes.CoInitialize()
        except Exception:
            pass
        while not self._stop.is_set():
            tail = self._read_tail()
            if tail is None:
                self._misses += 1
                if self._misses >= RECREATE_AFTER_MISSES:
                    print("[微信通道] 子窗口丢失，尝试重建…")
                    self._sub = self._ensure_sub()
                    self._misses = 0
            else:
                self._misses = 0
                self._diff_tail(tail)
            time.sleep(POLL_INTERVAL)

    def _diff_tail(self, tail) -> None:
        """以时间条目为锚点识别新消息。

        微信消息列表会周期性插入时间戳条目（如「03:06」）。
        视口很小（约4条），新消息进来时旧条目会被挤出，直接比尾部快照会对不齐；
        而时间戳之后的文本必然是在该时间点之后发送的，因此：
        - 锚点没变 → 新增文本 = 锚点后文本序列尾部多出来的部分；
        - 锚点变成新的时间戳 → 锚点后所有文本都是新消息；
        - 锚点回到见过的时间戳（用户向上滚动）→ 重新同步，不处理。
        """
        prev_anchor = self._prev_anchor
        prev_after = self._prev_after
        # 找最后一个时间条目作为锚点
        anchor_idx = -1
        for i, (cls, _name) in enumerate(tail):
            if "ChatTextItemView" not in cls and "ChatItemView" in cls:
                anchor_idx = i
        if anchor_idx < 0:
            self._prev_anchor = None
            self._prev_after = ()
            return
        anchor = tail[anchor_idx]
        after = tuple(name for (cls, name) in tail[anchor_idx + 1:] if "ChatTextItemView" in cls)

        if prev_anchor == anchor:
            # 同一时间段：新增文本 = 尾部多出来的部分
            if len(after) > len(prev_after) and after[: len(prev_after)] == prev_after:
                new = list(after[len(prev_after):])
            else:
                new = []  # 顺序对不上（滚动等），重新同步
        elif anchor not in self._seen_anchors:
            # 新时间段：该时间点之后的文本都是新消息
            self._seen_anchors.add(anchor)
            new = list(after)
        else:
            # 回滚到旧时间段，重新同步
            new = []
        self._prev_anchor = anchor
        self._prev_after = after
        if not new:
            return
        seen_in_poll = set()
        for name in new:
            if name in seen_in_poll:
                continue
            seen_in_poll.add(name)
            self._dispatch(name)

    def _dispatch(self, text: str) -> None:
        text = text.strip()
        # 跳过机器人自己发出的内容（含「Bot :」前缀），防止自我触发
        if text.startswith("Bot :") or text in self._sent:
            return
        now = time.monotonic()
        # 启动热身期：只吸收不处理，防止旧消息洪流
        if now < self._warmup_until:
            self._recent[text] = (now, False)
            return
        # 清理过期的内容记录
        for k in [k for k, (t, _) in self._recent.items() if now - t > 300]:
            del self._recent[k]
        # 内容近期出现过且未处理 → 重复条目，跳过
        last = self._recent.get(text)
        if last is not None and now - last[0] < CONTENT_DEDUP_SECONDS and not last[1]:
            return
        self._recent[text] = (now, True)
        print(f"[微信通道] 收到用户消息: {text}")
        if self._on_text:
            threading.Thread(target=self._on_text, args=(text,), daemon=True).start()
