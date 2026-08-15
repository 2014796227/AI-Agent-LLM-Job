"""M0-D3 演练（容器内）：两路并发 to_thread 网络IO 期间事件循环不阻塞、
心跳续租正常。在 api 容器内执行：
  docker compose cp scripts/m0_drill_concurrency.py api:/tmp/
  docker compose exec -e PYTHONPATH=/app api python /tmp/m0_drill_concurrency.py
载荷说明（M0 实测发现）：东财接口从 Docker Desktop 容器出网被断连（宿主机
正常、容器对 baidu/sina 正常）——真实网络载荷改用新浪行情 JS；
market.fetch_combined 的东财网络分支已在宿主机 B1/B3 实证。"""
import asyncio, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

DURATION_S = 12.0
URL = ("https://finance.sina.com.cn/realstock/company/"
       "sh600519/hisdata/klc_kl.js")

def net_work(tag: str) -> int:
    import requests
    n = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < DURATION_S:
        r = requests.get(URL, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        assert r.status_code == 200
        n += 1
    return n

async def main():
    from app import tasks as task_repo

    lags: list[float] = []
    stop = asyncio.Event()

    async def lag_monitor():
        while not stop.is_set():
            t0 = time.monotonic()
            await asyncio.sleep(0.01)
            lags.append(time.monotonic() - t0 - 0.01)

    hb = await task_repo.create("D3演练：心跳与并发", reserved=0)
    hb_id = str(hb["id"])
    assert await task_repo.claim(hb_id, 0)
    renew_count = [0]

    async def heartbeat():
        t0 = time.monotonic()
        while time.monotonic() - t0 < DURATION_S:
            await task_repo.renew(hb_id)
            renew_count[0] += 1
            await asyncio.sleep(0.2)

    mon = asyncio.create_task(lag_monitor())
    hb_t = asyncio.create_task(heartbeat())
    t0 = time.monotonic()
    na, nb = await asyncio.gather(
        asyncio.to_thread(net_work, "A"),
        asyncio.to_thread(net_work, "B"))
    elapsed = time.monotonic() - t0
    await asyncio.sleep(max(0, DURATION_S - elapsed))
    stop.set()
    await mon
    await hb_t
    row = await task_repo.get(hb_id)
    from app.db import pool
    p = await pool()
    await p.execute("DELETE FROM tasks WHERE id=$1", hb_id)
    mx, avg = max(lags), sum(lags) / len(lags)
    print(f"[1] 两路 to_thread 网络IO 并行 {elapsed:.1f}s: "
          f"A={na}次 B={nb}次 请求")
    print(f"[2] 事件循环 {len(lags)} 个 10ms 采样: max_lag={mx*1000:.1f}ms "
          f"avg_lag={avg*1000:.2f}ms（阈值 250ms）")
    print(f"[3] 心跳续租 renew 次数={renew_count[0]} "
          f"lease_expires_at={row['lease_expires_at']}")
    assert na > 0 and nb > 0
    assert mx < 0.25, "事件循环在 to_thread 网络IO 期间被阻塞"
    assert renew_count[0] >= 20 and row["lease_expires_at"] is not None
    print("D3 容器内演练通过")

if __name__ == "__main__":
    asyncio.run(main())
