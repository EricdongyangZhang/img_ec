# -*- coding: utf-8 -*-
"""提示词构建：从用户文字描述中解析底色（黑/白），拼装生图提示词。"""
import re

from prompt_store import DEFAULT_TEMPLATE, get_active, render

BASE_BLACK = "黑色"
BASE_WHITE = "白色"


def parse_base_color(text: str) -> str | None:
    """解析底色。

    返回 '黑色' / '白色'；无法判断时返回 None。
    同时出现黑白（如"黑色T恤胸前白色印花"）时，取修饰底色的那一个，
    规则：优先匹配 "X色/X底" 完整词，否则取更靠前的裸字。
    """
    for m in re.finditer(r"(黑色|白色)", text):
        return m.group(1) if m.group(1) else None
    # 完整词（黑色/白色）优先；没有则看裸字
    for m in re.finditer(r"(黑|白)(?=t恤|T恤|恤|底)", text, re.IGNORECASE):
        return BASE_BLACK if m.group(1) == "黑" else BASE_WHITE
    has_black = "黑" in text
    has_white = "白" in text
    if has_black and not has_white:
        return BASE_BLACK
    if has_white and not has_black:
        return BASE_WHITE
    return None


def build_prompt(user_desc: str, base_color: str) -> str:
    """用当前激活的提示词模板渲染最终生图提示词。

    模板来自 prompt_store（可在 Web 界面管理）；取不到时回退到内置默认模板。
    """
    tpl = get_active()
    template = tpl["template"] if tpl else DEFAULT_TEMPLATE
    return render(template, base_color, user_desc)
