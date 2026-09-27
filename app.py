# -*- coding: utf-8 -*-
"""Flask Web 应用入口：提示词管理 / 配置管理 / 会话显示 / 机器人启停。

运行：python app.py  → 浏览器打开 http://127.0.0.1:5001
机器人（含微信 UIA 轮询线程、生图线程）运行在本进程的后台线程中；
服务仅绑定 127.0.0.1，避免 API Key 与会话外泄。
"""
import os
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request, send_from_directory

import prompt_store
from bot import TShirtBot
from channel_session import SessionChannel, WebChannel
from config import config, raw_env, save_env
from session_store import session_store

app = Flask(__name__)


# ---------- 机器人生命周期管理 ----------

class BotRunner:
    """管理机器人的启动/停止/状态；同一时刻只允许一个实例。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.bot = None
        self.channel = None  # SessionChannel
        self.inner = None  # 真实通道（微信/网页）
        self.running = False
        self.starting = False
        self.error = None
        self.kind = None

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "starting": self.starting,
                "channel": self.kind,
                "state": getattr(self.bot, "state", None),
                "error": self.error,
            }

    def start(self, kind: str = "wechat") -> dict:
        with self._lock:
            if self.running or self.starting:
                return {"ok": False, "error": "机器人已在运行或启动中"}
            self.starting = True
            self.error = None
            self.kind = kind
        threading.Thread(target=self._start_worker, args=(kind,), daemon=True).start()
        return {"ok": True, "starting": True}

    def _start_worker(self, kind: str) -> None:
        label = "网页手动" if kind == "web" else "微信"
        try:
            if kind == "web":
                inner = WebChannel()
            else:
                from channel_wechat import WeChatChannel

                inner = WeChatChannel(config.LISTEN_CHAT)
            sc = SessionChannel(inner)
            bot = TShirtBot(sc)
            # 微信：start() 完成初始化并派生轮询线程后返回；网页：立即返回
            sc.start(bot.handle_text)
            with self._lock:
                self.inner = inner
                self.channel = sc
                self.bot = bot
                self.running = True
                self.starting = False
            session_store.add("system", "system", text=f"机器人已启动（{label}）")
        except Exception as e:  # 微信版本过新 / 子窗口创建失败等
            with self._lock:
                self.running = False
                self.starting = False
                self.error = str(e)
            session_store.add("system", "system", text=f"启动失败：{e}")

    def stop(self) -> dict:
        with self._lock:
            if not self.running:
                return {"ok": False, "error": "机器人未运行"}
            ch = self.channel
            self.running = False
            self.starting = False
            self.bot = None
            self.channel = None
            self.inner = None
        try:
            if ch is not None:
                ch.stop()
        except Exception:
            pass
        session_store.add("system", "system", text="机器人已停止")
        return {"ok": True}

    def inject(self, text: str) -> dict:
        """网页手动模式：把一条文本当作用户消息注入 bot。"""
        with self._lock:
            ch = self.channel
            running = self.running
        if not running or ch is None:
            return {"ok": False, "error": "机器人未运行，请先启动"}
        threading.Thread(target=ch.inject_user, args=(text,), daemon=True).start()
        return {"ok": True}


runner = BotRunner()


# ---------- 页面 ----------

@app.route("/")
def index():
    return render_template("index.html")


# ---------- 机器人控制 ----------

@app.route("/api/status")
def api_status():
    return jsonify(runner.status())


@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "wechat")
    if kind not in ("wechat", "web"):
        kind = "wechat"
    return jsonify(runner.start(kind))


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    return jsonify(runner.stop())


# ---------- 会话 ----------

@app.route("/api/session")
def api_session():
    try:
        since = int(request.args.get("since", 0))
    except (TypeError, ValueError):
        since = 0
    return jsonify({"events": session_store.since(since), "seq": session_store.latest_seq()})


@app.route("/api/session/send", methods=["POST"])
def api_session_send():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "内容为空"}), 400
    return jsonify(runner.inject(text))


@app.route("/api/session/clear", methods=["POST"])
def api_session_clear():
    session_store.clear()
    return jsonify({"ok": True})


@app.route("/media/<path:relpath>")
def media(relpath):
    """从 OUTPUT_DIR 安全地提供图片（send_from_directory 会防目录穿越）。"""
    return send_from_directory(str(config.OUTPUT_DIR), relpath)


# ---------- 配置 ----------

@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(raw_env())


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data = request.get_json(silent=True) or {}
    save_env(data)
    return jsonify({"ok": True, "config": raw_env(), "warning": config.validate()})


# ---------- 提示词 ----------

@app.route("/api/prompts", methods=["GET"])
def api_prompts_list():
    return jsonify({"templates": prompt_store.list_templates()})


@app.route("/api/prompts", methods=["POST"])
def api_prompts_add():
    data = request.get_json(silent=True) or {}
    t = prompt_store.add(data.get("name", ""), data.get("template", ""))
    return jsonify({"ok": True, "template": t})


@app.route("/api/prompts/preview", methods=["POST"])
def api_prompts_preview():
    data = request.get_json(silent=True) or {}
    tpl = data.get("template")
    if tpl is None:
        active = prompt_store.get_active()
        tpl = active["template"] if active else prompt_store.DEFAULT_TEMPLATE
    rendered = prompt_store.render(
        tpl, data.get("base_color", "白色"), data.get("user_desc", "")
    )
    return jsonify({"ok": True, "rendered": rendered})


@app.route("/api/prompts/<tid>", methods=["PUT"])
def api_prompts_update(tid):
    data = request.get_json(silent=True) or {}
    t = prompt_store.update(tid, name=data.get("name"), template=data.get("template"))
    if not t:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    return jsonify({"ok": True, "template": t})


@app.route("/api/prompts/<tid>", methods=["DELETE"])
def api_prompts_delete(tid):
    return jsonify({"ok": prompt_store.delete(tid)})


@app.route("/api/prompts/<tid>/activate", methods=["POST"])
def api_prompts_activate(tid):
    return jsonify({"ok": prompt_store.activate(tid)})


# ---------- 启动 ----------

def _open_browser(port: int) -> None:
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception:
        pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    try:
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    print(f"[Web] 管理界面: http://127.0.0.1:{port}  （仅本机可访问，Ctrl+C 退出）")
    threading.Timer(1.5, _open_browser, args=(port,)).start()
    # threaded=True 让轮询请求不互相阻塞；关闭 reloader 避免多进程重复启动机器人
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
