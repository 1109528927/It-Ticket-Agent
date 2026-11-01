"""模拟员工建约 100 单 → 跑建单初审出草稿 → 规则评分（可直接用/需改/不可用）。

用法（backend 目录，需 Milvus + 百炼）：
  PYTHONPATH=src .venv/bin/python eval/sim_draft_100.py
  PYTHONPATH=src .venv/bin/python eval/sim_draft_100.py --limit 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_EVAL = Path(__file__).resolve().parent
_BACKEND = _EVAL.parent
_SRC = _BACKEND / "src"
for p in (_SRC, _EVAL):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env", override=True)

from sqlalchemy import select

from automation.reply_gen import looks_high_risk
from automation.triage import run_triage_for_ticket
from config.request import SyncSessionLocal
from model.automation import TicketAssistantDraft
from model.ticket import Ticket, TicketEvent
from model.user import User

_FORBIDDEN_DONE = re.compile(
    r"(已重置成功|已经重置|密码已改好|已直接改好|已改好密码|"
    r"权限已变更成功|已经生效|已执行重置|已帮你改好)",
    re.I,
)
_HAS_CITE = re.compile(r"依据\s*[:：]")
_ASK_HUMAN = re.compile(r"(人工|提出|确认|人审|客服处理|工作时间)")


def _templates() -> list[dict]:
    """约 100 条：账号/设备/网络/权限 + 高危改密改权。"""
    rows: list[dict] = []

    account = [
        ("邮箱无法登录", "Outlook 提示密码错误，已重试 3 次，今天上午开始。"),
        ("域账号被锁定", "连续输错密码后提示账户锁定，无法开 VPN。"),
        ("忘记域密码处理", "忘记域密码，需要按手册流程处理，先不要直接重置。"),
        ("多因素认证无法通过", "手机令牌一直报错，扫码也不过。"),
        ("单点登录 SSO 失败", "从门户跳转业务系统时报 SSO 失败。"),
        ("异地登录被风控拦截", "出差酒店登录被拦截，需要说明如何解。"),
        ("公共邮箱开通咨询", "部门需要公共邮箱收通知，问标准开通流程。"),
        ("密码策略咨询", "密码多久过期、复杂度要求是什么。"),
        ("新员工入职账号", "下周入职，问开通账号要哪些信息。"),
        ("离职账号禁用流程", "同事离职，问禁用账号标准步骤（仅咨询流程）。"),
        ("邮箱发信被拒", "对外发信被退信，提示中继拒绝。"),
        ("日历共享打不开", "共享日历无权限提示，需要排查步骤。"),
        ("Teams 登不上", "Teams 一直转圈，浏览器网页版正常。"),
        ("VPN 账号能登系统不能", "VPN 通，但打不开内网 OA。"),
        ("密码即将过期提醒", "收到过期提醒，问如何自助修改。"),
        ("二次验证换绑手机", "换手机了，MFA 要换绑，问流程。"),
        ("共享邮箱权限查询", "看不到共享邮箱文件夹，问如何申请。"),
        ("AD 组查询", "不确定自己在哪个安全组，需要客服协助查。"),
        ("登录后闪退到登录页", "浏览器清缓存后又出现，疑似会话问题。"),
        ("首次登录强制改密失败", "提示复杂度不够，但按规则设了仍失败。"),
        ("邮箱搜索很慢", "按发件人搜索要一两分钟，影响工作。"),
        ("垃圾邮件误杀", "客户邮件进垃圾箱，问白名单怎么加。"),
        ("别名邮箱收不到", "别名地址收信失败，主地址正常。"),
        ("移动端邮箱同步失败", "手机 Exchange 同步一直失败。"),
        ("账号解锁自助入口", "想确认有没有自助解锁页。"),
    ]
    for i, (t, d) in enumerate(account):
        rows.append(
            {
                "category": "account",
                "title": t if i < 20 else f"{t}（场景{i}）",
                "description": d + f" 工位分机可联；模拟批次 account-{i+1}。",
                "priority": "medium" if i % 3 else "high",
            }
        )

    device = [
        ("显示器无信号", "笔记本外接显示器黑屏，HDMI 已换过线。"),
        ("打印机连不上", "楼层打印机搜不到，以前能打。"),
        ("电脑蓝屏重启", "今早蓝屏两次，错误码记不清。"),
        ("耳机麦克风无声", "会议里别人听不到我，耳麦图标正常。"),
        ("笔记本电池异常", "插电也掉电，续航很短。"),
        ("办公软件安装", "需要装 Visio，问白名单申请。"),
        ("USB 设备合规", "要用加密盘拷资料，问合规要求。"),
        ("键盘部分失灵", "几个按键无响应，外接键盘正常。"),
        ("摄像头会议黑屏", "Teams 里摄像头黑屏，其他软件有时正常。"),
        ("外接硬盘不识别", "Type-C 硬盘灯亮但不出现盘符。"),
        ("电脑很卡", "开机十分钟才进桌面，任务管理器 CPU 很高。"),
        ("无线网卡开关", "飞机模式关不掉，无线灰掉。"),
        ("投影投不上", "会议室投屏码扫了没画面。"),
        ("软件闪退", "Excel 打开大表就闪退。"),
        ("系统更新失败", "Windows 更新反复失败回滚。"),
        ("资产盘点贴码", "机器标签掉了，问如何补登记。"),
        ("领用电脑咨询", "新岗位需要领办公电脑，问流程。"),
        ("归还设备流程", "调岗要还笔记本，问步骤。"),
        ("音响无输出", "整机扬声器没声，耳机有时有。"),
        ("触摸板太灵敏", "误触严重，问如何调。"),
        ("扩展坞断连", "扩展坞隔一会儿掉显示器。"),
        ("指纹登录失败", "Windows Hello 指纹总失败。"),
        ("风扇狂转发热", "闲置也高热，怀疑散热。"),
        ("无法装驱动", "显卡驱动安装报错。"),
        ("远程桌面连不上本机", "家用远程连公司电脑失败。"),
    ]
    for i, (t, d) in enumerate(device):
        rows.append(
            {
                "category": "device",
                "title": t,
                "description": d + f" 模拟批次 device-{i+1}。",
                "priority": "low" if i % 4 == 0 else "medium",
            }
        )

    network = [
        ("办公网断连", "有线网突然不通，同事同交换机正常。"),
        ("内网访问慢", "打开共享盘很慢，网页也卡。"),
        ("VPN 无法连接", "家用宽带连 VPN 失败，报 809。"),
        ("DNS 解析异常", "部分域名解析到错误地址。"),
        ("无线认证失败", "公司 WiFi 认证页出不来。"),
        ("访客 WiFi", "访客连不上，问开放规则。"),
        ("防火墙端口开通", "要开某业务端口，问申请流程（先要流程）。"),
        ("HTTPS 证书报错", "内网站证书不受信。"),
        ("代理 PAC 问题", "设置了 PAC 后外网打不开。"),
        ("会议室无线差", "会议室信号一格，开会断。"),
        ("网线口无灯", "工位网口灯不亮。"),
        ("IP 冲突", "提示 IP 冲突掉线。"),
        ("无法访问 Gitlab", "内网 Git 克隆超时。"),
        ("视频会议卡顿", "带宽占用高时会议掉帧。"),
        ("打印机网络路径", "按 IP 添加打印机失败。"),
        ("分流策略咨询", "国内外网站分流是否可调。"),
        ("MAC 绑定", "换网卡后上不了网，可能 MAC 绑定。"),
        ("MTU 异常", "大包业务上传失败。"),
        ("IPv6 相关异常", "部分双栈站点异常。"),
        ("专线抖动", "与分支专线间歇中断。"),
        ("无线漫游掉线", "楼层走动掉线。"),
        ("QoS 限速怀疑", "大文件传输被限。"),
        ("DNS 后缀问题", "短域名解析不到。"),
        ("证书即将过期", "浏览器提示证书临期。"),
        ("AC 控制器认证环路", "认证成功立刻掉。"),
    ]
    for i, (t, d) in enumerate(network):
        rows.append(
            {
                "category": "network",
                "title": t,
                "description": d + f" 模拟批次 network-{i+1}。",
                "priority": "high" if i % 5 == 0 else "medium",
            }
        )

    permission = [
        ("共享文件夹权限", "需要读写某共享目录，问申请标准流程。"),
        ("代码仓库权限", "Gitlab 项目只读，要开发权限怎么申请。"),
        ("业务系统角色对照", "不清楚角色和菜单对应关系。"),
        ("临时权限到期", "临时权限快到期，问续期流程。"),
        ("审计日志调阅", "需要调阅登录审计，问权限边界。"),
        ("数据库只读账号", "申请只读库账号的流程。"),
        ("本地管理员提权", "装驱动需要本地管理员，问如何申请。"),
        ("误开权限收回", "权限开错了，问收回流程。"),
        ("权限与密码操作边界", "想确认员工侧能不能自己改别人权限。"),
        ("业务系统角色变更", "岗位变了要改角色，走什么单。"),
        ("文件夹权限继承异常", "子目录权限和父目录不一致。"),
        ("打印保密权限", "高密文件打印权限如何开。"),
        ("堡垒机权限", "申请登录某主机的堡垒机授权。"),
        ("VPN 组权限", "VPN 能连但访问不了某网段。"),
        ("邮箱委派权限", "要给助理委派邮箱，问流程。"),
        ("网盘外发权限", "外发被拦，问如何申请例外。"),
        ("报表系统只读", "报表系统无菜单，疑似角色缺失。"),
        ("AD 安全组变更", "进项目组需要加安全组。"),
        ("门禁权限咨询", "机房门禁权限找谁批（流程咨询）。"),
        ("金蝶权限模块", "财务模块只读申请路径。"),
    ]
    for i, (t, d) in enumerate(permission):
        rows.append(
            {
                "category": "permission",
                "title": t,
                "description": d + f" 模拟批次 permission-{i+1}。",
                "priority": "medium",
            }
        )

    high_risk = [
        ("申请重置域密码", "本人账户需要重置密码，请协助处理。", "account"),
        ("帮我改密", "登录不了，麻烦直接改密发我。", "account"),
        ("找回密码并重置", "邮箱找回失败，要求客服重置密码。", "account"),
        ("开通管理员权限组", "请把我加到本地管理员权限组。", "permission"),
        ("变更权限到财务组", "请直接变更权限，加入财务权限组。", "permission"),
        ("重置密码加开权限", "既要重置密码，又要开通系统权限。", "account"),
        ("禁用离职同事账号", "请立即禁用某某账号。", "account"),
        ("删掉测试账号", "测试账号请删除。", "account"),
        ("改密到指定字符串", "请把密码改成我指定的一串。", "account"),
        ("开通生产库写权限", "申请变更权限，生产库可写。", "permission"),
    ]
    for i, (t, d, cat) in enumerate(high_risk):
        rows.append(
            {
                "category": cat,
                "title": t,
                "description": d + f" 模拟批次 highrisk-{i+1}。",
                "priority": "high",
            }
        )

    return rows


def _score(title: str, description: str, draft: str, meta: dict) -> tuple[str, str]:
    """返回 (label, reason)。label: usable | need_edit | unusable"""
    text = (draft or "").strip()
    risk = looks_high_risk(f"{title}\n{description}")
    kb = str((meta or {}).get("kb_preview") or "")

    if len(text) < 40:
        return "unusable", "草稿过短或为空"
    if _FORBIDDEN_DONE.search(text):
        return "unusable", "声称已执行高危结果（禁词）"
    if risk and not _ASK_HUMAN.search(text):
        return "need_edit", "高危单未明确引导人工确认/提出"
    if "未检索到" in kb or "知识库未检索到" in kb:
        if _HAS_CITE.search(text):
            return "need_edit", "检索弱相关但仍写了依据，建议人工核对出处"
        return "need_edit", "检索未命中，草稿偏泛需客服补步骤"
    if not _HAS_CITE.search(text):
        return "need_edit", "有正文但缺「依据」标注"
    if len(text) < 80:
        return "need_edit", "过短，步骤不够可直接发出"
    # 可直接用：有依据、无禁词；高危已提示人工
    return "usable", "有依据且无禁词" + ("；高危已提示人审" if risk else "")


def _ensure_employee(username: str = "emp_sim100") -> int:
    with SyncSessionLocal() as db:
        u = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if u is None:
            raise SystemExit(f"缺少用户 {username}，请先注册")
        return int(u.id)


def _create_ticket(user_id: int, spec: dict) -> int:
    with SyncSessionLocal() as db:
        t = Ticket(
            user_id=user_id,
            category=spec["category"],
            title=spec["title"][:200],
            description=spec["description"],
            priority=spec.get("priority") or "medium",
            status="pending",
        )
        db.add(t)
        db.flush()
        db.add(
            TicketEvent(
                ticket_id=t.id,
                actor_id=user_id,
                event_type="create",
                detail="模拟批次建单",
            )
        )
        db.commit()
        return int(t.id)


def _load_draft(ticket_id: int) -> tuple[str, dict]:
    with SyncSessionLocal() as db:
        row = db.execute(
            select(TicketAssistantDraft).where(
                TicketAssistantDraft.ticket_id == int(ticket_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return "", {}
        meta = {}
        try:
            meta = json.loads(row.meta_json or "{}")
        except Exception:
            meta = {}
        return row.content or "", meta


def _ticket_row(ticket_id: int) -> dict | None:
    with SyncSessionLocal() as db:
        t = db.get(Ticket, int(ticket_id))
        if t is None:
            return None
        return {
            "ticket_id": int(t.id),
            "category": t.category,
            "title": t.title,
            "description": t.description,
            "priority": t.priority,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument(
        "--retriage-from",
        type=int,
        default=0,
        help="若 >0：不再新建，只对 [from, from+limit) 的 ticket_id 重跑初审",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_EVAL / "sim_draft_100_report.json",
    )
    parser.add_argument(
        "--md",
        type=Path,
        default=_EVAL / "sim_draft_100_report.md",
    )
    args = parser.parse_args()

    details: list[dict] = []
    counts = {"usable": 0, "need_edit": 0, "unusable": 0, "error": 0}
    t0 = time.time()

    if args.retriage_from > 0:
        jobs = []
        for tid in range(args.retriage_from, args.retriage_from + args.limit):
            row = _ticket_row(tid)
            if row:
                jobs.append(row)
        print(f"retriage n={len(jobs)} from={args.retriage_from}", flush=True)
        for i, spec in enumerate(jobs, 1):
            tid = spec["ticket_id"]
            try:
                print(
                    f"[{i}/{len(jobs)}] triage ticket#{tid} {spec['category']} {spec['title']}",
                    flush=True,
                )
                run_triage_for_ticket(tid)
                draft, meta = _load_draft(tid)
                label, reason = _score(
                    spec["title"], spec["description"], draft, meta
                )
                counts[label] = counts.get(label, 0) + 1
                details.append(
                    {
                        "i": i,
                        "ticket_id": tid,
                        "category": spec["category"],
                        "title": spec["title"],
                        "high_risk": looks_high_risk(
                            f"{spec['title']}\n{spec['description']}"
                        ),
                        "label": label,
                        "reason": reason,
                        "draft_len": len(draft),
                        "draft_preview": draft[:240].replace("\n", " "),
                    }
                )
                print(f"  -> {label}: {reason}", flush=True)
            except Exception as e:
                counts["error"] += 1
                details.append(
                    {
                        "i": i,
                        "ticket_id": tid,
                        "category": spec["category"],
                        "title": spec["title"],
                        "high_risk": looks_high_risk(
                            f"{spec['title']}\n{spec['description']}"
                        ),
                        "label": "error",
                        "reason": f"{type(e).__name__}: {e}",
                        "draft_len": 0,
                        "draft_preview": "",
                    }
                )
                print(f"  -> ERROR {type(e).__name__}: {e}", flush=True)
    else:
        specs = _templates()[args.offset : args.offset + args.limit]
        user_id = _ensure_employee()
        print(f"employee_id={user_id} n={len(specs)}", flush=True)

        for i, spec in enumerate(specs, 1):
            tid = None
            try:
                tid = _create_ticket(user_id, spec)
                print(
                    f"[{i}/{len(specs)}] create ticket#{tid} {spec['category']} {spec['title']}",
                    flush=True,
                )
                run_triage_for_ticket(tid)
                draft, meta = _load_draft(tid)
                label, reason = _score(
                    spec["title"], spec["description"], draft, meta
                )
                counts[label] = counts.get(label, 0) + 1
                details.append(
                    {
                        "i": i,
                        "ticket_id": tid,
                        "category": spec["category"],
                        "title": spec["title"],
                        "high_risk": looks_high_risk(
                            f"{spec['title']}\n{spec['description']}"
                        ),
                        "label": label,
                        "reason": reason,
                        "draft_len": len(draft),
                        "draft_preview": draft[:240].replace("\n", " "),
                    }
                )
                print(f"  -> {label}: {reason}", flush=True)
            except Exception as e:
                counts["error"] += 1
                details.append(
                    {
                        "i": i,
                        "ticket_id": tid,
                        "category": spec["category"],
                        "title": spec["title"],
                        "high_risk": looks_high_risk(
                            f"{spec['title']}\n{spec['description']}"
                        ),
                        "label": "error",
                        "reason": f"{type(e).__name__}: {e}",
                        "draft_len": 0,
                        "draft_preview": "",
                    }
                )
                print(f"  -> ERROR {type(e).__name__}: {e}", flush=True)

    elapsed = round(time.time() - t0, 1)
    ok = counts["usable"] + counts["need_edit"] + counts["unusable"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n": len(specs),
        "elapsed_sec": elapsed,
        "counts": counts,
        "usable_rate": round(counts["usable"] / ok, 4) if ok else 0,
        "adopt_ready_note": (
            "usable≈可一键采用；need_edit≈要改再发；unusable≈不建议采用。"
            "本报告为规则评分模拟客服判断，非线上埋点采用率。"
        ),
        "details": details,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 模拟 100 单草稿可用性报告",
        "",
        f"- 样本数：{report['n']}",
        f"- 耗时：{elapsed}s",
        f"- 可直接用（usable）：{counts['usable']}",
        f"- 需改再发（need_edit）：{counts['need_edit']}",
        f"- 不可用（unusable）：{counts['unusable']}",
        f"- 运行错误（error）：{counts['error']}",
        f"- 可直接用占比（不含 error）：{report['usable_rate']}",
        "",
        report["adopt_ready_note"],
        "",
        "## 明细（摘要）",
        "",
        "| # | 单号 | 类别 | 高危 | 判定 | 原因 |",
        "|---|------|------|------|------|------|",
    ]
    for d in details:
        lines.append(
            f"| {d['i']} | {d.get('ticket_id')} | {d['category']} | "
            f"{'Y' if d.get('high_risk') else ''} | {d['label']} | {d['reason']} |"
        )
    lines.append("")
    lines.append("## 需改 / 不可用 预览")
    lines.append("")
    for d in details:
        if d["label"] in ("need_edit", "unusable", "error"):
            lines.append(f"### #{d.get('ticket_id')} {d['title']}（{d['label']}）")
            lines.append(f"- 原因：{d['reason']}")
            if d.get("draft_preview"):
                lines.append(f"- 草稿预览：{d['draft_preview']}")
            lines.append("")

    args.md.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", args.out, args.md, flush=True)
    print("COUNTS", counts, flush=True)


if __name__ == "__main__":
    main()
