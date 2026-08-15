import uuid, socket, os, json
import asyncpg
from app.config import settings
from app.db import pool
from app.metrics import M_TASK

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:4]}"
LEASE_S = 60
WATCHDOG_GRACE_S = 90

async def create(input_text: str, reserved: int = 0) -> asyncpg.Record:
    """reserved 在建行即落值（而非 claim 时）——启动对账按 Σ(pending.reserved)
    重建当日预留的依据；/api/chat 在 create 之前已完成 usage_day 预占。"""
    p = await pool()
    tid, trace = uuid.uuid4(), uuid.uuid4().hex[:12]
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute(
                "INSERT INTO usage_day(day, tasks) VALUES(current_date, 1) "
                "ON CONFLICT(day) DO UPDATE SET tasks = usage_day.tasks + 1")
            return await c.fetchrow(
                "INSERT INTO tasks(id, trace_id, status, input, reserved) "
                "VALUES($1,$2,'pending',$3,$4) RETURNING *",
                tid, trace, input_text, reserved)

async def get(task_id: str) -> asyncpg.Record | None:
    p = await pool()
    return await p.fetchrow("SELECT * FROM tasks WHERE id=$1", task_id)

async def claim(task_id: str, reserved: int = 0) -> bool:
    """CAS 抢占；登记本任务预留额（watchdog 中断时据此释放）。"""
    p = await pool()
    async with p.acquire() as c:
        row = await c.fetchrow(
            "UPDATE tasks SET status='running', worker_id=$2, reserved=$3, "
            "heartbeat_at=now(), "
            f"lease_expires_at=now()+interval '{LEASE_S} seconds' "
            "WHERE id=$1 AND status='pending' RETURNING id",
            task_id, WORKER_ID, reserved)
        return row is not None

async def renew(task_id: str):
    p = await pool()
    async with p.acquire() as c:
        await c.execute(
            f"UPDATE tasks SET heartbeat_at=now(), lease_expires_at=now()+interval '{LEASE_S} seconds', "
            "updated_at=now() WHERE id=$1 AND status='running' AND worker_id=$2",
            task_id, WORKER_ID)

async def finish(task_id: str, status: str, result, error, plan, context) -> bool:
    """guarded finish：仅当任务仍为 running 且 worker 是本人时更新。
    返回 False=状态已被迁移（典型：watchdog→interrupted）——调用方必须跳过
    终态事件发射与预留释放（迁移方已做），仅记冲突日志与指标。"""
    p = await pool()
    async with p.acquire() as c:
        row = await c.fetchrow(
            "UPDATE tasks SET status=$2, result=$3, error=$4, plan=$5, context=$6, "
            "updated_at=now(), lease_expires_at=NULL "
            "WHERE id=$1 AND status='running' AND worker_id=$7 RETURNING id",
            task_id, status,
            json.dumps(result, ensure_ascii=False, default=str) if result else None,
            error,
            json.dumps(plan, ensure_ascii=False) if plan else None,
            json.dumps(context, ensure_ascii=False, default=str),
            WORKER_ID)
        return row is not None

async def _release_of(row) -> None:
    """中断迁移方释放该任务的预留。仅 watchdog_tick 使用——recover_on_boot
    的预留已由对账 upsert 整列重置覆盖，不得再调用本函数（v18 P1-1）。"""
    if row["reserved"]:
        await release_daily(row["reserved"], 0)

async def recover_on_boot() -> tuple[list[str], list[tuple[str, int]]]:
    """running→interrupted；pending 保留重排队（携带行内 reserved）。
    当日 reserved 对账=Σ(pending.reserved)（upsert **整列重置**，替代 v15 前的
    一刀切清零）：恢复任务的预留得以延续、仍受预算闸门约束；极端崩溃场景
    （对账额+当日 tokens 超预算）允许短暂超占，由后续 release / 下次启动
    对账自愈。running→interrupted 的预留**不得**再逐个 _release_of——upsert
    重置后的 reserved 本就不含它们，再释放=二次扣减→闸门被低估放行（v18
    P1-1）；watchdog 路径仍逐个释放（其无对账，见 _release_of 注释）。
    已知边界（v18 D-5）：claim/get 阶段 DB 瞬断会使任务滞留 pending（finish
    的 running 条件不匹配→仅冲突计数），由本函数重启对账自愈——演示级
    接受，不加运行时重试。"""
    from app.events import bus
    p = await pool()
    async with p.acquire() as c:
        interrupted = await c.fetch(
            "UPDATE tasks SET status='interrupted', error='process_restart', "
            "lease_expires_at=NULL, updated_at=now() "
            "WHERE status='running' RETURNING id, trace_id, reserved")
        pending = await c.fetch(
            "SELECT id, reserved FROM tasks WHERE status='pending' "
            "ORDER BY created_at")
        await c.execute(
            "INSERT INTO usage_day(day, reserved) VALUES(current_date, $1) "
            "ON CONFLICT(day) DO UPDATE SET reserved = EXCLUDED.reserved",
            sum(r["reserved"] or 0 for r in pending))
    for r in interrupted:
        await bus.emit(str(r["id"]), "task_interrupted",
                       {"reason": "process_restart", "trace_id": r["trace_id"]})
        M_TASK.labels("interrupted").inc()
    return ([str(r["id"]) for r in interrupted],
            [(str(r["id"]), r["reserved"] or 0) for r in pending])

async def watchdog_tick() -> int:
    """租约过期且心跳超宽限→interrupted；同步释放其 reserved。"""
    from app.events import bus
    p = await pool()
    rows = await p.fetch(
        "UPDATE tasks SET status='interrupted', error='lease_expired', "
        "lease_expires_at=NULL, updated_at=now() "
        "WHERE status='running' AND lease_expires_at < now() "
        f"AND heartbeat_at < now() - interval '{WATCHDOG_GRACE_S} seconds' "
        "RETURNING id, trace_id, reserved")
    for r in rows:
        await bus.emit(str(r["id"]), "task_interrupted",
                       {"reason": "lease_expired", "trace_id": r["trace_id"]})
        M_TASK.labels("interrupted").inc()
        await _release_of(r)
    return len(rows)

async def reserve_daily(amount: int) -> bool:
    assert amount <= settings.daily_token_budget, "预留额超过日预算（配置错误）"
    # 单语句原子性：ON CONFLICT DO UPDATE 的行锁将并发预留串行化，
    # 后到请求在锁下重读已提交的 reserved 再评估 WHERE——
    # asyncpg 自动提交模式下语句自身即原子单元，无需应用层事务/重试
    p = await pool()
    async with p.acquire() as c:
        row = await c.fetchrow(
            "INSERT INTO usage_day(day, reserved) VALUES(current_date, $1) "
            "ON CONFLICT(day) DO UPDATE SET reserved = usage_day.reserved + $1 "
            "WHERE usage_day.tokens + usage_day.reserved + $1 <= $2 "
            "RETURNING reserved", amount, settings.daily_token_budget)
        return row is not None

async def release_daily(reserved: int, actual_tokens: int, llm_calls: int = 0):
    """已知边界（v17 D-2/D-3 声明，演示级接受）：
    ① 跨午夜任务：UPDATE 落在 current_date 新行（可能不存在→no-op）——实际
      token 丢失不计、昨日 reserved 永久滞留该行（无害）；偏差方向为低估
      消耗，保守正确。
    ② 中断任务（watchdog/启动恢复）只释放 reserved、实际消耗不入账——死亡
      进程消耗不可知；释放权唯一性（不变式7）优先于记账精度。"""
    p = await pool()
    async with p.acquire() as c:
        await c.execute(
            "UPDATE usage_day SET reserved = GREATEST(reserved - $1, 0), "
            "tokens = tokens + $2, llm_calls = llm_calls + $3 WHERE day=current_date",
            reserved, actual_tokens, llm_calls)
