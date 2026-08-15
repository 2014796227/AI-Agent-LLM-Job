"""行情缓存预灌（M2 线上兜底）：把 fixture parquet 经 diskcache API 灌入
marketcache 卷（东财对海外 IP 有累计限流，ADR-0003 快照哲学的运行时形态）。
在 api 容器内执行（fixture 须已在容器 /tmp）：
  docker compose cp evals/fixtures/xxx.parquet api:/tmp/f1.parquet
  docker compose exec -e PYTHONPATH=/app api python /tmp/m0_seed_cache.py
支持自定义窗口：python m0_seed_cache.py <parquet> <symbol> <start> <end>"""
import asyncio, sys
from pathlib import Path

async def main():
    import pandas as pd
    from diskcache import Cache
    from app.market import _CACHE_VER
    items = [(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])] if len(sys.argv) == 5 else [
        ("/tmp/f1.parquet", "600519", "20230601", "20260531"),
        ("/tmp/f2.parquet", "600519", "20240101", "20260531")]
    c = Cache(".cache/market")
    for path, sym, start, end in items:
        df = pd.read_parquet(path)
        if "date" in df.columns:
            df = df.set_index("date")
        c.set(f"{_CACHE_VER}|{sym}|{start}|{end}",
              df.reset_index().to_json(orient="split"), expire=86400 * 30)
        print("seeded", sym, start, end, "rows=", len(df))
    from app import market
    df = await asyncio.to_thread(
        market.fetch_combined, "600519", "20230601", "20260531")
    print("缓存命中验证 rows=", len(df))

if __name__ == "__main__":
    asyncio.run(main())
