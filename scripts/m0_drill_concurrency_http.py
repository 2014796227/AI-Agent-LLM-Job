"""M0-D3 演练（宿主机 HTTP 面）：两任务并行提交 + /api/healthz 时延监测。
用法（backend venv）: python scripts/m0_drill_concurrency_http.py
无 API key 时任务最终以 failed 终态（LLM 连接失败）——这正是演练点：
编排器运行/重试期间事件循环与 HTTP 面保持响应。"""
import asyncio, json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

BASE = "http://127.0.0.1:8000"

async def main():
    import httpx
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BASE}/api/healthz")
        print(f"[0] healthz 预检: {r.json()}")
        assert r.status_code == 200

        t0 = time.monotonic()
        r1, r2 = await asyncio.gather(
            c.post(f"{BASE}/api/chat",
                   json={"input": "D3冒烟任务A：分析600519近一年走势"}),
            c.post(f"{BASE}/api/chat",
                   json={"input": "D3冒烟任务B：分析000858近一年走势"}))
        print(f"[1] 并行提交耗时 {time.monotonic()-t0:.3f}s "
              f"A={r1.json().get('task_id', r1.text)[:8]}... "
              f"B={r2.json().get('task_id', r2.text)[:8]}...")
        assert r1.status_code == 200 and r2.status_code == 200

        # 两任务运行期间监测 healthz 时延（15s 窗口）
        lats = []
        for _ in range(60):
            t = time.monotonic()
            rr = await c.get(f"{BASE}/api/healthz")
            lats.append(time.monotonic() - t)
            assert rr.status_code == 200
            await asyncio.sleep(0.25)
        print(f"[2] 运行期 healthz 60 次: max={max(lats)*1000:.1f}ms "
              f"avg={sum(lats)/len(lats)*1000:.1f}ms")

        # 任务状态可见（running 或已终态）
        for tag, resp in (("A", r1), ("B", r2)):
            tid = resp.json()["task_id"]
            s = (await c.get(f"{BASE}/api/tasks/{tid}")).json()
            print(f"[3] 任务{tag} status={s['status']} "
                  f"trace_id={s['trace_id']}")

if __name__ == "__main__":
    asyncio.run(main())
