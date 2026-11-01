"""自动化开关与阈值（环境变量）。"""

from __future__ import annotations

import os


def env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


# 总开关：关闭后调度不跑，手动 API 仍可用（便于演示）
AUTOMATION_ENABLED = env_bool("AUTOMATION_ENABLED", True)

# 批跑：积压 pending / 久未更新的 processing
BATCH_INTERVAL_MINUTES = int(os.getenv("AUTOMATION_BATCH_INTERVAL_MIN", "60"))
BATCH_LIMIT = int(os.getenv("AUTOMATION_BATCH_LIMIT", "20"))
BATCH_STALE_HOURS = int(os.getenv("AUTOMATION_BATCH_STALE_HOURS", "4"))

# SLA
SLA_INTERVAL_MINUTES = int(os.getenv("AUTOMATION_SLA_INTERVAL_MIN", "15"))
SLA_UNCLAIMED_HOURS = int(os.getenv("AUTOMATION_SLA_UNCLAIMED_HOURS", "24"))
SLA_CONFIRM_HOURS = int(os.getenv("AUTOMATION_SLA_CONFIRM_HOURS", "12"))

# 建单后初审
TRIAGE_ON_CREATE = env_bool("AUTOMATION_TRIAGE_ON_CREATE", True)

# 事件 actor：须是已存在的 user.id（建议客服账号）；未配则运行时查第一个 support
AUTOMATION_ACTOR_USER_ID = os.getenv("AUTOMATION_ACTOR_USER_ID", "").strip()

# 单票处理失败重试
PER_TICKET_RETRIES = int(os.getenv("AUTOMATION_TICKET_RETRIES", "1"))
