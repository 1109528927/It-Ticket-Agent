"""从模型输出里解析回复正文与置信度；解析失败则降级（不崩批跑）。"""

from __future__ import annotations

import json
import re
from typing import Any


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def parse_draft_and_confidence(raw: str) -> dict[str, Any]:
    """
    期望模型输出 JSON：{"reply_draft":"...","confidence":0.0~1.0}
    失败时：整段当草稿，confidence=0.0，parse_ok=False。
    """
    text = (raw or "").strip()
    if not text:
        return {
            "content": "",
            "confidence": 0.0,
            "parse_ok": False,
            "error": "empty",
        }

    candidates = [text]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if fence:
        candidates.insert(0, fence.group(1).strip())
    m = _JSON_BLOCK.search(text)
    if m:
        candidates.append(m.group(0))

    for cand in candidates:
        try:
            data = json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        draft = data.get("reply_draft") or data.get("content") or data.get("draft")
        if not isinstance(draft, str) or not draft.strip():
            continue
        conf_raw = data.get("confidence", 0.0)
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        return {
            "content": draft.strip(),
            "confidence": conf,
            "parse_ok": True,
            "error": None,
        }

    return {
        "content": text,
        "confidence": 0.0,
        "parse_ok": False,
        "error": "json_parse_failed",
    }
