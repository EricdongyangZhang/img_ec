# -*- coding: utf-8 -*-
"""配置加载：从 .env 读取，缺省时用默认值。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def _load_env() -> None:
    """加载 .env，兼容 UTF-8 / GBK（记事本可能另存为 ANSI）两种编码。"""
    env_path = BASE_DIR / ".env"
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            load_dotenv(env_path, encoding=encoding)
            return
        except (UnicodeDecodeError, LookupError):
            continue


_load_env()


class Config:
    # GLM-Image
    GLM_API_KEY = os.getenv("GLM_API_KEY", "")
    GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/images/generations")
    GLM_MODEL = os.getenv("GLM_MODEL", "glm-image")
    IMAGE_SIZE = os.getenv("IMAGE_SIZE", "1280x1280")
    IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "hd")
    WATERMARK_ENABLED = os.getenv("WATERMARK_ENABLED", "false").lower() == "true"
    NUM_CANDIDATES = int(os.getenv("NUM_CANDIDATES", "3"))

    # 微信通道
    LISTEN_CHAT = os.getenv("LISTEN_CHAT", "文件传输助手")

    # 输出
    OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
    if not OUTPUT_DIR.is_absolute():
        OUTPUT_DIR = BASE_DIR / OUTPUT_DIR

    @classmethod
    def validate(cls) -> str | None:
        """返回错误信息，无错误返回 None。"""
        if not cls.GLM_API_KEY:
            return "GLM_API_KEY 未配置，请在 .env 中填写智谱开放平台的 API Key"
        return None


config = Config()
