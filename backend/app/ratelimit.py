"""IP 滑窗限流（进程内存态）。
单进程不变式（ADR-006 已记录取舍）：多 worker/多副本会使计数分裂、进程重启归零——
限流口径即失效。Dockerfile CMD 不开 --workers 即是本不变式的一部分；
多实例部署需 Redis 化，属生产化路径而非本演示项目范围。"""
import time, asyncio
from collections import defaultdict, deque
from app.config import settings

_hits: dict[str, deque] = defaultdict(deque)
_lock = asyncio.Lock()

def _prune(now: float):
    for ip in list(_hits.keys()):
        q = _hits[ip]
        while q and q[0] < now - 3600:
            q.popleft()
        if not q:
            del _hits[ip]

async def allow(ip: str) -> bool:
    async with _lock:
        now = time.time()
        if len(_hits) > 10_000:
            _prune(now)
        q = _hits[ip]
        while q and q[0] < now - 3600:
            q.popleft()
        if len(q) >= settings.rate_limit_per_ip_per_hour:
            return False
        q.append(now)
        return True
