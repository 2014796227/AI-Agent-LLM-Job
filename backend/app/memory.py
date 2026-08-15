"""跨任务标的记忆（演示级 Memory）：memories 表 KV 读写。
口径：按 symbol 键存最近一次成功任务的分析摘要；注入规划上下文时
由编排器声明"事实与数字仍必须以工具返回为准"（防记忆污染事实链）。
非长期个性化记忆；不做向量检索（键前缀精确匹配足够，量级=标的数）。"""
import json
from app.db import pool

async def remember(key: str, value: dict):
    p = await pool()
    async with p.acquire() as c:
        await c.execute(
            "INSERT INTO memories(key, value, updated_at) "
            "VALUES($1,$2,now()) "
            "ON CONFLICT(key) DO UPDATE SET value=$2, updated_at=now()",
            key, json.dumps(value, ensure_ascii=False, default=str))

async def recall_prefix(prefix: str = "symbol:") -> dict[str, dict]:
    p = await pool()
    rows = await p.fetch(
        "SELECT key, value FROM memories WHERE key LIKE $1", prefix + "%")
    return {r["key"]: json.loads(r["value"]) for r in rows}
