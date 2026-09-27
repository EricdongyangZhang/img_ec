# -*- coding: utf-8 -*-
"""配置加载与持久化：从 .env 读取，支持热刷新与写盘（供 Web 配置页使用）。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# .env 中受管理的字段（顺序即写盘顺序）
ENV_KEYS = [
    "GLM_API_KEY",
    "GLM_BASE_URL",
    "GLM_MODEL",
    "IMAGE_SIZE",
    "IMAGE_QUALITY",
    "WATERMARK_ENABLED",
    "NUM_CANDIDATES",
    "LISTEN_CHAT",
    "OUTPUT_DIR",
]

# 缺省值（.env 未写该键时使用，也用于配置表单占位）
_DEFAULTS = {
    "GLM_API_KEY": "",
    "GLM_BASE_URL": "https://open.bigmodel.cn/api/paas/v4/images/generations",
    "GLM_MODEL": "glm-image",
    "IMAGE_SIZE": "1280x1280",
    "IMAGE_QUALITY": "hd",
    "WATERMARK_ENABLED": "false",
    "NUM_CANDIDATES": "3",
    "LISTEN_CHAT": "文件传输助手",
    "OUTPUT_DIR": "output",
}

MASK_PREFIX = "****"


def _load_env(override: bool = False) -> None:
    """加载 .env，兼容 UTF-8 / GBK（记事本可能另存为 ANSI）两种编码。

    override=True 时用文件里的值覆盖已存在的环境变量（热刷新需要）。
    """
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            load_dotenv(ENV_PATH, encoding=encoding, override=override)
            return
        except (UnicodeDecodeError, LookupError):
            continue


class Config:
    # 以下属性由 _refresh() 从环境变量填充
    GLM_API_KEY = ""
    GLM_BASE_URL = _DEFAULTS["GLM_BASE_URL"]
    GLM_MODEL = _DEFAULTS["GLM_MODEL"]
    IMAGE_SIZE = _DEFAULTS["IMAGE_SIZE"]
    IMAGE_QUALITY = _DEFAULTS["IMAGE_QUALITY"]
    WATERMARK_ENABLED = False
    NUM_CANDIDATES = 3
    LISTEN_CHAT = _DEFAULTS["LISTEN_CHAT"]
    OUTPUT_DIR = BASE_DIR / _DEFAULTS["OUTPUT_DIR"]

    @classmethod
    def _refresh(cls) -> None:
        cls.GLM_API_KEY = os.getenv("GLM_API_KEY", "")
        cls.GLM_BASE_URL = os.getenv("GLM_BASE_URL", _DEFAULTS["GLM_BASE_URL"])
        cls.GLM_MODEL = os.getenv("GLM_MODEL", _DEFAULTS["GLM_MODEL"])
        cls.IMAGE_SIZE = os.getenv("IMAGE_SIZE", _DEFAULTS["IMAGE_SIZE"])
        cls.IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", _DEFAULTS["IMAGE_QUALITY"])
        cls.WATERMARK_ENABLED = os.getenv("WATERMARK_ENABLED", "false").lower() == "true"
        try:
            cls.NUM_CANDIDATES = int(os.getenv("NUM_CANDIDATES", "3"))
        except ValueError:
            cls.NUM_CANDIDATES = 3
        cls.LISTEN_CHAT = os.getenv("LISTEN_CHAT", _DEFAULTS["LISTEN_CHAT"])
        out = Path(os.getenv("OUTPUT_DIR", _DEFAULTS["OUTPUT_DIR"]))
        cls.OUTPUT_DIR = out if out.is_absolute() else BASE_DIR / out

    @classmethod
    def reload(cls) -> None:
        """重新从 .env 读取并刷新内存中的配置（覆盖旧环境变量）。"""
        _load_env(override=True)
        cls._refresh()

    @classmethod
    def validate(cls) -> str | None:
        """返回错误信息，无错误返回 None。"""
        if not cls.GLM_API_KEY:
            return "GLM_API_KEY 未配置，请在配置页填写智谱开放平台的 API Key"
        return None


_load_env()
Config._refresh()
config = Config()


# ---------- 供 Web 配置页使用的读写辅助 ----------

def mask_key(key: str) -> str:
    """把 API Key 掩码为 ****后四位，避免在界面/接口明文回显。"""
    if not key:
        return ""
    return MASK_PREFIX + key[-4:] if len(key) >= 4 else MASK_PREFIX


def raw_env() -> dict:
    """返回 .env 的原始字符串值（用于配置表单），API Key 已掩码。"""
    vals = {k: (os.getenv(k) or _DEFAULTS.get(k, "")) for k in ENV_KEYS}
    vals["GLM_API_KEY"] = mask_key(vals.get("GLM_API_KEY", ""))
    vals["_has_key"] = bool(config.GLM_API_KEY)
    return vals


def save_env(values: dict) -> None:
    """把配置写入 .env 并热刷新。

    API Key：传入为空或以掩码前缀开头时，沿用 .env 中已有的旧值，避免误清空。
    """
    ak = (values.get("GLM_API_KEY") or "").strip()
    if not ak or ak.startswith(MASK_PREFIX):
        ak = config.GLM_API_KEY

    def s(k: str) -> str:
        v = values.get(k)
        if v is None or str(v).strip() == "":
            return _DEFAULTS.get(k, "")
        return str(v).strip()

    wm = values.get("WATERMARK_ENABLED")
    if isinstance(wm, bool):
        wm_str = "true" if wm else "false"
    else:
        wm_str = "true" if str(wm).strip().lower() in ("true", "1", "yes", "on") else "false"

    try:
        num_str = str(int(values.get("NUM_CANDIDATES")))
    except (TypeError, ValueError):
        num_str = _DEFAULTS["NUM_CANDIDATES"]

    content = (
        "# ===== GLM-Image 生图 API =====\n"
        "# 在智谱开放平台 https://bigmodel.cn/usercenter/proj-mgmt/apikeys 获取\n"
        f"GLM_API_KEY={ak}\n"
        f"GLM_BASE_URL={s('GLM_BASE_URL')}\n"
        f"GLM_MODEL={s('GLM_MODEL')}\n"
        "\n"
        "# ===== 生成参数 =====\n"
        f"IMAGE_SIZE={s('IMAGE_SIZE')}\n"
        f"IMAGE_QUALITY={s('IMAGE_QUALITY')}\n"
        f"WATERMARK_ENABLED={wm_str}\n"
        f"NUM_CANDIDATES={num_str}\n"
        "\n"
        "# ===== 微信通道 =====\n"
        f"LISTEN_CHAT={s('LISTEN_CHAT')}\n"
        "\n"
        "# ===== 输出目录 =====\n"
        f"OUTPUT_DIR={s('OUTPUT_DIR')}\n"
    )
    ENV_PATH.write_text(content, encoding="utf-8")
    Config.reload()
