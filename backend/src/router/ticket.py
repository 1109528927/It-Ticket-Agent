from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.checklist import set_checklist_item
from crud.ticket import (
    add_comment_for_employee,
    add_reply_for_support,
    change_ticket_status_for_support,
    claim_ticket_for_support,
    close_ticket_for_employee,
    create_ticket_for_employee,
    employee_confirm_resolved,
    employee_reopen_unresolved,
    get_ticket_detail_for_employee,
    get_ticket_detail_for_support,
    list_tickets_for_employee,
    list_tickets_for_support,
)
from crud.ticket_action import (
    confirm_action_for_support,
    propose_action_for_support,
    reject_action_for_support,
)
from model.user import User
from schema.ticket import (
    ChecklistToggleIn,
    EmployeeReopenIn,
    TicketActionConfirmIn,
    TicketActionProposeIn,
    TicketActionRejectIn,
    TicketCommentIn,
    TicketCreateIn,
    TicketDetailOut,
    TicketListItem,
    TicketListOut,
    TicketReplyIn,
    TicketStatusIn,
)
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/tickets", tags=["ticket"])

CATEGORIES = {"account", "device", "network", "permission"}
STATUSES = {"pending", "processing", "pending_confirm", "resolved", "closed"}
SCOPES = {"unclaimed", "mine"}


def _require_employee(user: User) -> None:
    if user.role != "employee":
        raise HTTPException(status_code=403, detail="只有员工可以操作我的工单")


def _require_support(user: User) -> None:
    if user.role != "support":
        raise HTTPException(status_code=403, detail="只有客服可以操作工单池")


@router.get("")
async def list_tickets(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="状态不合法")
    if category is not None and category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="类别不合法")
    if scope is not None and scope not in SCOPES:
        raise HTTPException(status_code=400, detail="筛选不合法")

    if user.role == "employee":
        rows = await list_tickets_for_employee(
            db,
            user_id=user.id,
            status=status,
            category=category,
        )
    elif user.role == "support":
        rows = await list_tickets_for_support(
            db,
            support_id=user.id,
            scope=scope,
            status=status,
        )
    else:
        raise HTTPException(status_code=403, detail="无权查看工单")

    payload = TicketListOut(items=[TicketListItem.model_validate(row) for row in rows])
    return success_response(message="ok", data=payload.model_dump())


@router.post("")
async def create_ticket(
    body: TicketCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_employee(user)

    row = await create_ticket_for_employee(
        db,
        user_id=user.id,
        category=body.category,
        title=body.title,
        description=body.description,
        priority=body.priority,
    )
    # 建单后异步初审：类别/优先级建议 + 带依据回复草稿（不阻塞创建响应）
    try:
        from automation.triage import schedule_triage_after_create

        schedule_triage_after_create(int(row["id"]))
    except Exception:
        pass

    from automation.reply_gen import create_success_message_for_user

    msg, high_risk = create_success_message_for_user(
        title=body.title, description=body.description
    )
    data = TicketListItem.model_validate(row).model_dump()
    # 前端要用：高危时换警告提示，并引导去详情看说明
    data["high_risk"] = high_risk
    return success_response(message=msg, data=data)


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "employee":
        row = await get_ticket_detail_for_employee(
            db,
            ticket_id=ticket_id,
            user_id=user.id,
        )
    elif user.role == "support":
        row = await get_ticket_detail_for_support(db, ticket_id=ticket_id)
    else:
        raise HTTPException(status_code=403, detail="无权查看工单")

    if not row:
        raise HTTPException(status_code=404, detail="工单不存在")

    return success_response(
        message="ok",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/comments")
async def add_ticket_comment(
    ticket_id: int,
    body: TicketCommentIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_employee(user)

    row = await add_comment_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user.id,
        detail=body.detail,
    )
    if not row:
        raise HTTPException(status_code=404, detail="工单不存在")

    return success_response(
        message="补充成功",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/close")
async def close_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_employee(user)

    code, row = await close_ticket_for_employee(
        db,
        ticket_id=ticket_id,
        user_id=user.id,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "not_pending":
        raise HTTPException(status_code=400, detail="只有待处理且未认领的工单可以撤销")

    return success_response(
        message="撤销成功",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/claim")
async def claim_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)

    code, row = await claim_ticket_for_support(
        db,
        ticket_id=ticket_id,
        support_id=user.id,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "not_claimable":
        raise HTTPException(status_code=400, detail="该工单不可认领或已被认领")

    return success_response(
        message="认领成功",
        data=TicketListItem.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/status")
async def change_ticket_status(
    ticket_id: int,
    body: TicketStatusIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)

    code, row = await change_ticket_status_for_support(
        db,
        ticket_id=ticket_id,
        support_id=user.id,
        to_status=body.status,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "bad_edge":
        raise HTTPException(status_code=400, detail="不允许这样改状态")
    if code == "blocked_pending_action":
        raise HTTPException(status_code=400, detail="存在待确认高风险动作，不能标记解决")
    if code == "blocked_checklist":
        raise HTTPException(
            status_code=400,
            detail="设备/网络类工单须勾选完处理清单才能标记解决",
        )

    return success_response(
        message="状态已更新",
        data=TicketListItem.model_validate(row).model_dump(),
    )


@router.patch("/{ticket_id}/checklist/{item_id}")
async def toggle_checklist_item(
    ticket_id: int,
    item_id: int,
    body: ChecklistToggleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """客服勾选处理清单。"""
    _require_support(user)
    code, rows = await set_checklist_item(
        db,
        ticket_id=ticket_id,
        item_id=item_id,
        checked=body.checked,
        support_id=user.id,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "not_applicable":
        raise HTTPException(status_code=400, detail="该类工单不需要处理清单")
    if code == "item_not_found":
        raise HTTPException(status_code=404, detail="清单项不存在")
    return success_response(message="已更新清单", data=rows)


@router.post("/{ticket_id}/employee-confirm")
async def employee_confirm_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工确认已解决：resolved → closed。"""
    _require_employee(user)
    code, row = await employee_confirm_resolved(
        db, ticket_id=ticket_id, user_id=user.id
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "bad_state":
        raise HTTPException(status_code=400, detail="只有「已解决」的工单可以确认关闭")
    return success_response(
        message="已确认解决并关闭",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/employee-reopen")
async def employee_reopen_ticket(
    ticket_id: int,
    body: EmployeeReopenIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工反馈仍未解决：resolved → processing。"""
    _require_employee(user)
    code, row = await employee_reopen_unresolved(
        db,
        ticket_id=ticket_id,
        user_id=user.id,
        reason=body.reason,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "bad_state":
        raise HTTPException(status_code=400, detail="只有「已解决」的工单可以反馈未解决")
    if code == "bad_reason":
        raise HTTPException(status_code=400, detail="请填写仍未解决的原因")
    return success_response(
        message="已重新打开，等待客服继续处理",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/actions")
async def propose_ticket_action(
    ticket_id: int,
    body: TicketActionProposeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)

    code, row = await propose_action_for_support(
        db,
        ticket_id=ticket_id,
        support_id=user.id,
        action_type=body.action_type,
        reason=body.reason,
        payload=body.payload,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="工单不存在")
    if code == "bad_state":
        raise HTTPException(status_code=409, detail="当前工单状态不允许提出高风险动作")
    if code == "bad_target":
        raise HTTPException(
            status_code=400,
            detail="目标工号不存在，或与本工单提单人不一致",
        )

    return success_response(
        message="已提出，等待确认",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/actions/{action_id}/confirm")
async def confirm_ticket_action(
    ticket_id: int,
    action_id: int,
    body: TicketActionConfirmIn | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)
    body = body or TicketActionConfirmIn()

    code, row = await confirm_action_for_support(
        db,
        ticket_id=ticket_id,
        action_id=action_id,
        support_id=user.id,
        new_password=body.new_password,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="动作不存在")
    if code == "bad_state":
        raise HTTPException(status_code=409, detail="动作不可确认或工单状态不对")
    if code == "need_password":
        raise HTTPException(status_code=400, detail="重置密码请填写临时新密码")
    if code == "exec_failed":
        msg = (row or {}).get("message") if isinstance(row, dict) else "执行失败"
        raise HTTPException(status_code=400, detail=msg)

    exec_msg = None
    if isinstance(row, dict):
        actions = row.get("actions") or []
        for a in actions:
            if a.get("id") == action_id:
                er = a.get("execution_result")
                if isinstance(er, dict):
                    exec_msg = er.get("message")
                break

    return success_response(
        message=exec_msg or "已确认并执行",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/actions/{action_id}/reject")
async def reject_ticket_action(
    ticket_id: int,
    action_id: int,
    body: TicketActionRejectIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)

    code, row = await reject_action_for_support(
        db,
        ticket_id=ticket_id,
        action_id=action_id,
        support_id=user.id,
        reason=body.reason,
    )
    if code == "not_found":
        raise HTTPException(status_code=404, detail="动作不存在")
    if code == "bad_state":
        raise HTTPException(status_code=409, detail="动作不可拒绝或工单状态不对")

    return success_response(
        message="已拒绝",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )


@router.post("/{ticket_id}/replies")
async def add_ticket_reply(
    ticket_id: int,
    body: TicketReplyIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_support(user)

    row = await add_reply_for_support(
        db,
        ticket_id=ticket_id,
        support_id=user.id,
        content=body.content,
    )
    if not row:
        raise HTTPException(status_code=404, detail="工单不存在")

    return success_response(
        message="回复成功",
        data=TicketDetailOut.model_validate(row).model_dump(),
    )
