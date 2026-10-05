"""在现有 content 列中保存版本化回答状态, 读取时还原正文; 兼容旧纯文本。"""

import json

PREFIX = "PETROCHAT_MESSAGE_V1\n"


def encode_answer(text: str, status: str) -> str:
    if status not in {"completed", "partial", "failed", "unknown"}:
        raise ValueError("无效回答状态")
    return PREFIX + json.dumps({"text": text, "status": status}, ensure_ascii=False)


def decode_answer(content: str) -> tuple[str, str]:
    if content.startswith(PREFIX):
        try:
            data = json.loads(content[len(PREFIX) :])
            if isinstance(data.get("text"), str) and data.get("status") in {
                "completed",
                "partial",
                "failed",
                "unknown",
            }:
                return data["text"], data["status"]
        except (ValueError, TypeError, AttributeError):
            pass
    return content, "unknown"
