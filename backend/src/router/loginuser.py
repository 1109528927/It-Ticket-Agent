from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.user import (
    add_user,
    create_token,
    get_user_by_employee_no,
    get_user_by_username,
)
from model.user import User
from schema.user import LoginIn, LoginOut, RegisterIn, UserOut
from utils.auth import get_current_user
from utils.response import success_response
from utils.security import verify_password

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if await get_user_by_username(db, body.username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    employee_no = (body.employee_no or "").strip() or f"U{uuid4().hex[:8]}"
    if await get_user_by_employee_no(db, employee_no):
        raise HTTPException(status_code=400, detail="工号已存在")

    user = await add_user(
        db,
        username=body.username,
        password=body.password,
        employee_no=employee_no,
        role="employee",
    )
    return success_response(
        message="注册成功",
        data=UserOut.model_validate(user).model_dump(),
    )


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, body.username)
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(status_code=400, detail="用户名或密码错误")

    token_row = await create_token(db, user.id)
    payload = LoginOut(
        token=token_row.token,
        expires_at=token_row.expires_at,
        user=UserOut.model_validate(user),
    )
    return success_response(message="登录成功", data=payload.model_dump())


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return success_response(
        message="ok",
        data=UserOut.model_validate(user).model_dump(),
    )


@router.post("/support")
async def create_support(
    body: RegisterIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "support":
        raise HTTPException(status_code=403, detail="只有客服可以开通客服账号")

    if await get_user_by_username(db, body.username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    employee_no = (body.employee_no or "").strip() or f"S{uuid4().hex[:8]}"
    if await get_user_by_employee_no(db, employee_no):
        raise HTTPException(status_code=400, detail="工号已存在")

    await add_user(
        db,
        username=body.username,
        password=body.password,
        employee_no=employee_no,
        role="support",
    )
    return success_response(message="开通成功")
