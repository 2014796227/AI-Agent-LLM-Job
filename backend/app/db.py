import asyncio
from pathlib import Path
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()

async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    dsn=settings.database_url, min_size=2, max_size=8)
    return _pool

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

async def init_schema():
    p = await pool()
    async with p.acquire() as c:
        await c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    raw = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
    stmts = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    async with p.acquire() as c:
        for s in stmts:
            await c.execute(s)
