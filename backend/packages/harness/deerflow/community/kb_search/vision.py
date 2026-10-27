"""Optional vision extraction for scanned pages and embedded document images."""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import httpx

from .config import VisionConfig, load_kb_config

VISION_PROMPT = """你是企业知识库文档解析器。请忠实提取图片中的可检索信息：
1. 按阅读顺序转写全部可见文字和数值；
2. 表格使用 Markdown 表格表达；
3. 流程图、架构图和故障图说明节点、连线关系与结论；
4. 不猜测看不清的内容，不添加图片中不存在的信息；
5. 只输出适合进入知识库的正文，不要寒暄。"""


class VisionExtractor:
    name: str = "base"
    pdf_dpi: int = 144

    def extract(self, image_bytes: bytes, media_type: str, *, context: str = "") -> str:
        raise NotImplementedError


class OpenAICompatibleVisionExtractor(VisionExtractor):
    def __init__(
        self,
        config: VisionConfig,
        api_key: str,
        *,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.name = f"openai:{config.model}"
        self.pdf_dpi = config.pdf_dpi
        self.endpoint = config.base_url.rstrip("/") + "/chat/completions"
        self.client = client or httpx.Client(
            timeout=config.timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _data_uri(self, image_bytes: bytes, media_type: str) -> str:
        if not image_bytes:
            raise ValueError("Vision input image is empty")
        if len(image_bytes) > self.config.max_image_bytes:
            raise ValueError(f"Vision input image exceeds {self.config.max_image_bytes} bytes")
        if not media_type.startswith("image/"):
            raise ValueError(f"Unsupported vision media type: {media_type}")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{media_type};base64,{encoded}"

    @staticmethod
    def _response_text(payload: dict) -> str:
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Vision response does not contain message content") from exc
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            text = "\n".join(item.get("text", "").strip() for item in content if isinstance(item, dict) and item.get("type") in {None, "text"}).strip()
        else:
            text = ""
        if not text:
            raise RuntimeError("Vision response content is empty")
        return text

    def extract(self, image_bytes: bytes, media_type: str, *, context: str = "") -> str:
        prompt = VISION_PROMPT
        if context:
            prompt += f"\n\n文档位置：{context}"
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": self._data_uri(image_bytes, media_type)},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": self.config.max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.post(self.endpoint, json=payload)
                response.raise_for_status()
                return self._response_text(response.json())
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                time.sleep(min(0.25 * (2**attempt), 2.0))
        raise RuntimeError("Vision extraction request failed") from last_error


def get_vision_extractor(config: VisionConfig | None = None) -> VisionExtractor | None:
    config = config or load_kb_config().vision
    if config.backend == "none":
        return None
    if not config.model:
        raise RuntimeError("KB_VISION_BACKEND=openai requires KB_VISION_MODEL")
    api_key = os.environ.get("KB_VISION_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("KB_VISION_BACKEND=openai requires KB_VISION_API_KEY")
    return OpenAICompatibleVisionExtractor(config, api_key)
