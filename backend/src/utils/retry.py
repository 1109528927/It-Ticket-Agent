"""工具调用轻量重试：失败再试一次，避免偶发网络抖一下就空结果。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_retry(
    fn: Callable[..., T],
    *args,
    retries: int = 1,
    delay_sec: float = 0.35,
    label: str = "call",
    **kwargs,
) -> T:
    last: Exception | None = None
    attempts = max(0, int(retries)) + 1
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            if i + 1 >= attempts:
                break
            logger.warning("%s 失败，重试 %s/%s：%s", label, i + 1, retries, e)
            time.sleep(delay_sec)
    assert last is not None
    raise last
