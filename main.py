# -*- coding: utf-8 -*-
"""入口：选择通道启动 T 恤生图机器人。

用法：
  python main.py              # 默认微信通道
  python main.py --console    # 控制台通道（调试/兜底）
"""
import argparse
import sys
import time

from bot import TShirtBot
from config import config


def main():
    parser = argparse.ArgumentParser(description="T恤生图机器人")
    parser.add_argument("--console", action="store_true", help="使用控制台通道（默认微信通道）")
    args = parser.parse_args()

    err = config.validate()
    if err:
        print(f"[配置错误] {err}")
        print("请复制 .env.example 为 .env 并填写 GLM_API_KEY")
        sys.exit(1)

    if args.console:
        from channel_console import ConsoleChannel
        channel = ConsoleChannel()
    else:
        from channel_wechat import WeChatChannel
        try:
            channel = WeChatChannel(config.LISTEN_CHAT)
        except RuntimeError as e:
            print(f"[微信通道不可用]\n{e}")
            print("\n提示：可以先用控制台通道跑通流程：python main.py --console")
            sys.exit(1)

    bot = TShirtBot(channel)
    try:
        channel.start(bot.handle_text)
        # 通道的监听在后台线程运行，主线程必须保持存活
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
