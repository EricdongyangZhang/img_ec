# -*- coding: utf-8 -*-
"""GLM-Image 生图客户端：串行调用智谱图像生成 API，产出 N 张候选图。

串行而非并发：智谱对图像模型有「同一时刻正在处理请求数」的并发限制，
并行发 3 张很容易触发 429 限流，故改为一张接一张生成，遇到 429 自动退避重试。
"""
import time
from pathlib import Path

import requests

from config import config

RETRY_TIMES = 4  # 429 限流时最多重试次数
RETRY_DELAYS = [5, 10, 20, 30]  # 每次重试前的等待秒数
BATCH_INTERVAL = 1.0  # 两张图之间的间隔秒数，降低触发限流概率


class ImageGenError(Exception):
    """生图失败，message 面向用户展示。"""


class GLMImageClient:
    def __init__(self):
        self.api_key = config.GLM_API_KEY
        self.base_url = config.GLM_BASE_URL
        self.model = config.GLM_MODEL
        self.size = config.IMAGE_SIZE
        self.quality = config.IMAGE_QUALITY
        self.watermark_enabled = config.WATERMARK_ENABLED
        self.num_candidates = config.NUM_CANDIDATES
        self.output_dir = config.OUTPUT_DIR

    def generate_candidates(self, prompt: str) -> list[Path]:
        """串行生成 num_candidates 张图，保存到本地，返回文件路径列表。"""
        task_dir = self.output_dir / time.strftime("%Y%m%d_%H%M%S")
        task_dir.mkdir(parents=True, exist_ok=True)

        paths: list[Path] = []
        for i in range(1, self.num_candidates + 1):
            paths.append(self._gen_one(prompt, task_dir, i))
            if i < self.num_candidates:
                time.sleep(BATCH_INTERVAL)
        return paths

    def _gen_one(self, prompt: str, task_dir: Path, index: int) -> Path:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "quality": self.quality,
            "watermark_enabled": self.watermark_enabled,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_err: Exception | None = None
        for attempt in range(RETRY_TIMES + 1):
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 200 and "data" in body:
                url = body["data"][0]["url"]
                img_bytes = requests.get(url, timeout=120).content
                path = task_dir / f"candidate_{index}.png"
                path.write_bytes(img_bytes)
                return path

            last_err = ImageGenError(self._friendly_error(resp.status_code, body))
            # 仅限流(429)值得重试，其他错误立即放弃
            if resp.status_code != 429 or attempt >= RETRY_TIMES:
                raise last_err
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"[生图] 第{index}张触发限流(429)，{delay}秒后重试（第{attempt + 1}/{RETRY_TIMES}次）")
            time.sleep(delay)
        raise last_err or ImageGenError("生图失败：未知错误")

    @staticmethod
    def _friendly_error(status: int, body: dict) -> str:
        msg = ""
        err = body.get("error", {}) if isinstance(body, dict) else {}
        if isinstance(err, dict):
            msg = err.get("message", "")
        if status == 401:
            return "GLM API Key 无效，请检查 .env 中的 GLM_API_KEY"
        if status == 429:
            return "触发智谱速率限制，已自动重试多次仍失败，请稍等几分钟后再发"
        if "watermark" in str(msg).lower():
            return ("关闭水印失败：请先在智谱开放平台「个人中心-安全管理-去水印管理」签署免责声明，"
                    "或把 .env 中 WATERMARK_ENABLED 改为 true")
        if "quota" in str(msg).lower() or "余额" in str(msg):
            return f"账户余额不足：{msg}"
        return f"生图失败({status})：{msg or body}"
