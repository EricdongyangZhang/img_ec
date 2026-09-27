# -*- coding: utf-8 -*-
"""提示词模板存储：CRUD + prompts.json 持久化 + 激活模板选择。

模板用占位符 {base_color}（底色）和 {user_desc}（用户描述）。
渲染用 str.replace 而非 str.format，避免模板里出现其它花括号时报错。
"""
import json
import threading
import uuid
from pathlib import Path

from config import BASE_DIR

PROMPTS_FILE = BASE_DIR / "prompts.json"

DEFAULT_TEMPLATE = (
    "一件纯色{base_color}圆领短袖T恤，正面印有图案，图案设计为：{user_desc}。"
    "电商商品主图风格，T恤平铺拍摄，纯白背景，"
    "光线均匀，高清细节，专业产品摄影，面料质感真实"
)

_lock = threading.Lock()


def _default_doc() -> dict:
    return {
        "templates": [
            {
                "id": "default",
                "name": "默认（电商主图）",
                "template": DEFAULT_TEMPLATE,
                "is_active": True,
            }
        ]
    }


def _read() -> dict:
    """读取 prompts.json；不存在或损坏时返回默认并落盘。"""
    if not PROMPTS_FILE.exists():
        doc = _default_doc()
        _write(doc)
        return doc
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(PROMPTS_FILE, encoding=encoding) as f:
                doc = json.load(f)
            if not isinstance(doc, dict) or not doc.get("templates"):
                return _default_doc()
            return doc
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except Exception:
            return _default_doc()
    return _default_doc()


def _write(doc: dict) -> None:
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)


def render(template_str: str, base_color: str, user_desc: str) -> str:
    """把占位符替换为实际值。"""
    return (template_str or "").replace("{base_color}", base_color or "").replace(
        "{user_desc}", user_desc or ""
    )


# ---------- 对外 CRUD ----------

def list_templates() -> list:
    with _lock:
        return _read()["templates"]


def get_active() -> dict | None:
    with _lock:
        doc = _read()
    for t in doc["templates"]:
        if t.get("is_active"):
            return t
    return doc["templates"][0] if doc["templates"] else None


def get(tid: str) -> dict | None:
    with _lock:
        doc = _read()
    for t in doc["templates"]:
        if t["id"] == tid:
            return t
    return None


def add(name: str, template: str) -> dict:
    with _lock:
        doc = _read()
        t = {
            "id": uuid.uuid4().hex[:8],
            "name": (name or "未命名").strip(),
            "template": template if template is not None else DEFAULT_TEMPLATE,
            "is_active": False,
        }
        doc["templates"].append(t)
        _write(doc)
        return t


def update(tid: str, name: str = None, template: str = None) -> dict | None:
    with _lock:
        doc = _read()
        for t in doc["templates"]:
            if t["id"] == tid:
                if name is not None:
                    t["name"] = name.strip() or t["name"]
                if template is not None:
                    t["template"] = template
                _write(doc)
                return t
        return None


def delete(tid: str) -> bool:
    with _lock:
        doc = _read()
        before = len(doc["templates"])
        doc["templates"] = [t for t in doc["templates"] if t["id"] != tid]
        if len(doc["templates"]) == before:
            return False
        # 删掉的是激活模板时，自动激活第一个，保证始终有一个可用
        if doc["templates"] and not any(t.get("is_active") for t in doc["templates"]):
            doc["templates"][0]["is_active"] = True
        _write(doc)
        return True


def activate(tid: str) -> bool:
    with _lock:
        doc = _read()
        found = False
        for t in doc["templates"]:
            t["is_active"] = t["id"] == tid
            if t["id"] == tid:
                found = True
        if found:
            _write(doc)
        return found
