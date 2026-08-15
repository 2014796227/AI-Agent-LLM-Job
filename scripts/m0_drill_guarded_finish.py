"""M0-D2 演练：guarded finish 冲突 + v18 P1-1 重启对账断言。
在 api 容器内执行：
  docker compose cp scripts/m0_drill_guarded_finish.py api:/tmp/
  docker compose exec -e PYTHONPATH=/app api python /tmp/m0_drill_guarded_finish.py
场景：①任务心跳停止超租约→watchdog 标 interrupted 并释放预留→迟到的
编排器 _finish 不覆盖（M_TASK_CONF+1、不再释放）；②人为污染当日 reserved
后 recover_on_boot 对账→断言 reserved == Σ(pending.reserved)。"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

async def q(sql, *args):
    from app.db import pool
    p = await pool()
    return await p.fetch(sql, *args)

async def q1(sql, *args):
    rows = await q(sql, *args)
    return rows[0] if rows else None

async def main():
    from app import tasks as task_repo, orchestrator
    from app.metrics import M_TASK_CONF
    from app.budget import TaskBudget

    # --- 场景1：watchdog 中断 → 预留释放；迟到 finish 不覆盖 ---
    # 镜像 /api/chat 完整路径：先 reserve_daily 预占，再建行落 reserved
    assert await task_repo.reserve_daily(50000)
    task = await task_repo.create("D2演练：guarded finish 冲突", reserved=50000)
    tid = str(task["id"])
    assert await task_repo.claim(tid, 50000)
    before = await q1("SELECT reserved FROM usage_day WHERE day=current_date")
    # 模拟心跳停止：租约与心跳都推到过去（宽限 90s 之前）
    await q("UPDATE tasks SET heartbeat_at=now()-interval '300 seconds', "
            "lease_expires_at=now()-interval '200 seconds' WHERE id=$1", tid)
    n = await task_repo.watchdog_tick()
    t = await task_repo.get(tid)
    after = await q1("SELECT reserved FROM usage_day WHERE day=current_date")
    print(f"[1] watchdog interrupted={n} status={t['status']} "
          f"error={t['error']} usage.reserved {before['reserved']} -> "
          f"{after['reserved']}（任务预留 50000 已释放）")
    assert n == 1 and t["status"] == "interrupted" \
        and t["error"] == "lease_expired"
    assert after["reserved"] == before["reserved"] - 50000

    # 迟到的编排器 finish（同一 worker 模拟）：guarded → False，不覆盖不释放
    conf0 = M_TASK_CONF._value.get()
    ok = await orchestrator._finalize(
        tid, "done", {"report": "late"}, None, None, {}, "trace-d2",
        TaskBudget(), reserved=50000)
    t2 = await task_repo.get(tid)
    conf1 = M_TASK_CONF._value.get()
    fin = await q1("SELECT reserved FROM usage_day WHERE day=current_date")
    print(f"[2] late_finish ok={ok} status={t2['status']} "
          f"result={'None(未覆盖)' if t2['result'] is None else '被覆盖!'} "
          f"M_TASK_CONF {conf0}->{conf1} usage.reserved={fin['reserved']}(未再释放)")
    assert ok is False and t2["status"] == "interrupted" \
        and t2["result"] is None
    assert conf1 == conf0 + 1 and fin["reserved"] == after["reserved"]

    # --- 场景2：重启对账（v18 P1-1 双重释放回归断言）---
    assert await task_repo.reserve_daily(30000)
    p_task = await task_repo.create("D2演练：重启对账", reserved=30000)
    await q("UPDATE usage_day SET reserved = reserved + 7777 "
            "WHERE day=current_date")
    polluted = await q1("SELECT reserved FROM usage_day WHERE day=current_date")
    interrupted, repend = await task_repo.recover_on_boot()
    row = await q1("SELECT reserved FROM usage_day WHERE day=current_date")
    s = await q1("SELECT COALESCE(SUM(reserved),0) AS s FROM tasks "
                 "WHERE status='pending'")
    print(f"[3] 对账前 reserved={polluted['reserved']}(人为污染+7777) -> "
          f"对账后={row['reserved']} == Σ(pending.reserved)={s['s']} "
          f"interrupted={len(interrupted)} requeued={len(repend)}")
    assert row["reserved"] == s["s"] and s["s"] >= 30000

    # 清理演练任务行（含此前失败运行残留；usage_day 计数留真实痕迹）
    await q("DELETE FROM tasks WHERE input LIKE 'D2演练%'")
    print("D2 演练全部通过")

if __name__ == "__main__":
    asyncio.run(main())
