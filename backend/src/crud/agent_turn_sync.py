"""Agent 回合记账：同步写入（供图节点 / save_turn 调用）。"""

from __future__ import annotations

import json

from config.request import SyncSessionLocal
from model.chat import AgentTurnLog


def save_agent_turn_log(
    *,
    user_id: int,
    role: str,
    tools: list[str],
    kb_hit_count: int = 0,
    hitl: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
    ticket_id: int | None = None,
) -> None:
    with SyncSessionLocal() as db:
        db.add(
            AgentTurnLog(
                user_id=user_id,
                ticket_id=ticket_id,
                role=role,
                tools_json=json.dumps(tools or [], ensure_ascii=False),
                kb_hit_count=int(kb_hit_count or 0),
                hitl=bool(hitl),
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
            )
        )
        db.commit()
