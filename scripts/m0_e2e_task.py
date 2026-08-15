"""M0 端到端真实任务演练：POST /api/chat → SSE（经 nginx，兼证反代不缓冲）→
终态 → 报告与事件摘要。
用法: cd backend && ./.venv/Scripts/python.exe ../scripts/m0_e2e_task.py [自定义输入]"""
import asyncio, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

BASE = "http://127.0.0.1"       # 经 nginx:80（同时验证 SSE 反代，预判故障#3）
TIMEOUT_S = 360

DEFAULT_INPUT = ("分析贵州茅台(600519)近三年走势与波动特征，"
                 "并回测20日均线上穿60日均线买入、下穿卖出策略，"
                 "区间2023-06-01至2026-05-31")

async def main():
    import httpx
    inp = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{BASE}/api/chat", json={"input": inp})
        r.raise_for_status()
        tid, trace = r.json()["task_id"], r.json()["trace_id"]
        print(f"task_id={tid} trace_id={trace}")

    events = []

    async def sse():
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream(
                    "GET", f"{BASE}/api/tasks/{tid}/stream?after=0") as resp:
                pending = []
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        pending.append(line[7:])
                    elif line.startswith("data: ") and pending:
                        ev = pending.pop(0)
                        d = json.loads(line[6:])
                        events.append((d["seq"], ev))
                        print(f"  #{d['seq']:>3} {ev}")
                        if ev in ("task_done", "task_failed",
                                  "task_interrupted", "stream_overflow"):
                            return

    t0 = time.monotonic()
    try:
        await asyncio.wait_for(sse(), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"SSE {TIMEOUT_S}s 超时")
    print(f"SSE 经 nginx 收到 {len(events)} 个事件，耗时 {time.monotonic()-t0:.0f}s")

    async with httpx.AsyncClient(timeout=15) as c:
        t = (await c.get(f"{BASE}/api/tasks/{tid}")).json()
        print(f"终态: status={t['status']} error={t.get('error')}")
        report = (t.get("result") or {}).get("report", "")
        print(f"报告长度 {len(report)} 字符；前 600 字：\n{report[:600]}")
        assert t["status"] in ("done", "degraded"), t.get("error")
        assert len(report) > 100, "报告过短"
        print("端到端演练通过")

if __name__ == "__main__":
    asyncio.run(main())
