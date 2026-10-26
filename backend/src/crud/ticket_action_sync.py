"""高风险提出的同步核心，给 Agent 工具 / 图节点用（不 await、不调大模型）。"""

import json
import logging
from datetime import datetime

from sqlalchemy import select, update

from config.request import SyncSessionLocal
from model.ticket import Ticket, TicketAction, TicketEvent
from model.user import User

logger = logging.getLogger(__name__)

_ALLOWED = {"reset_password", "change_permission"}


def propose_action_core(
    *,
    ticket_id: int,
    support_id: int,
    action_type: str,
    reason: str,
    payload: dict | None = None,
) -> tuple[str, dict | None]:
    """条件更新 processing→pending_confirm，再插 pending action + propose event。

    返回 code：ok / not_found / bad_state / bad_type / bad_reason / bad_target。
    """
    if action_type not in _ALLOWED:
        return "bad_type", None
    reason = (reason or "").strip()
    if not reason:
        return "bad_reason", None

    with SyncSessionLocal() as db:
        ticket = db.execute(
            select(Ticket).where(Ticket.id == ticket_id)
        ).scalar_one_or_none()
        if ticket is None:
            return "not_found", None

        # 重置密码：目标工号一律取提单人，不采信模型 / 前端乱填
        if action_type == "reset_password":
            owner = db.execute(
                select(User).where(User.id == ticket.user_id)
            ).scalar_one_or_none()
            if owner is None or not (owner.employee_no or "").strip():
                return "bad_target", None
            payload = {"target_employee_no": owner.employee_no.strip()}

        now = datetime.now()
        result = db.execute(
            update(Ticket)
            .where(Ticket.id == ticket_id, Ticket.status == "processing")
            .values(status="pending_confirm", updated_at=now)
        )
        if result.rowcount != 1:
            logger.warning(
                "propose_action_core 冲突 ticket_id=%s actor=%s action_type=%s",
                ticket_id,
                support_id,
                action_type,
            )
            db.rollback()
            return "bad_state", None

        action = TicketAction(
            ticket_id=ticket_id,
            proposer_id=support_id,
            action_type=action_type,
            reason=reason,
            payload=json.dumps(payload or {}, ensure_ascii=False),
            status="pending",
        )
        db.add(action)
        db.flush()

        snap = {
            "action_id": action.id,
            "action_type": action_type,
            "reason": reason,
            "payload": payload or {},
        }
        db.add(
            TicketEvent(
                ticket_id=ticket_id,
                actor_id=support_id,
                event_type="propose",
                detail=json.dumps(snap, ensure_ascii=False),
            )
        )
        db.commit()

        logger.info(
            "propose_action_core ok ticket_id=%s action_id=%s actor=%s",
            ticket_id,
            action.id,
            support_id,
        )
        return "ok", {"action_id": action.id, "action_type": action_type}
