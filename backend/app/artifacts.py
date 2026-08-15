import os, json, uuid, asyncio, contextlib, datetime as dt
import pandas as pd
from app.config import settings
from app.db import pool

class ArtifactNotFound(Exception): ...
class ArtifactGone(Exception): ...

def _dir() -> str:
    os.makedirs(settings.data_dir + "/artifacts", exist_ok=True)
    return settings.data_dir + "/artifacts"

def _write_file(path: str, data: bytes) -> None:
    """原子写：tmp → fsync → os.replace。
    tar/读端任何时刻只能看到完整文件（备份一致性基础）。"""
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

async def save_dataframe(df: pd.DataFrame, kind: str, meta: dict) -> str:
    art_id = "art_" + uuid.uuid4().hex[:12]
    rel = f"artifacts/{art_id}.parquet"
    path = os.path.join(_dir(), f"{art_id}.parquet")
    data = await asyncio.to_thread(df.to_parquet)
    await asyncio.to_thread(_write_file, path, data)
    p = await pool()
    async with p.acquire() as c:
        await c.execute(
            "INSERT INTO artifacts(id, kind, path, meta, expires_at) "
            "VALUES($1,$2,$3,$4,$5)",
            art_id, kind, rel,
            json.dumps({**meta, "rows": len(df)},
                       ensure_ascii=False, default=str),
            _utcnow() + dt.timedelta(hours=settings.artifact_ttl_hours))
    return art_id

async def save_json(obj: dict, kind: str, meta: dict) -> str:
    df = pd.DataFrame([{"payload": json.dumps(obj, ensure_ascii=False,
                                              default=str)}])
    return await save_dataframe(df, kind, meta)

async def load_dataframe(art_id: str) -> pd.DataFrame:
    p = await pool()
    row = await p.fetchrow("SELECT path FROM artifacts WHERE id=$1", art_id)
    if row is None:
        raise ArtifactNotFound(art_id)
    path = os.path.join(settings.data_dir, row["path"])
    if not os.path.exists(path):
        raise ArtifactGone(art_id)
    return await asyncio.to_thread(pd.read_parquet, path)

async def load_json(art_id: str) -> dict:
    df = await load_dataframe(art_id)
    return json.loads(df["payload"].iloc[0])

async def summary(art_id: str) -> dict:
    p = await pool()
    row = await p.fetchrow(
        "SELECT kind, meta, created_at FROM artifacts WHERE id=$1", art_id)
    if row is None:
        raise ArtifactNotFound(art_id)
    meta = json.loads(row["meta"])
    if row["kind"] == "price_history":
        df = await load_dataframe(art_id)
        c = df["close_hfq"]
        ret = c.pct_change()
        monthly = (df.assign(_m=[str(i)[:7] for i in df.index])
                     .groupby("_m")["close_raw"].last())
        meta = {**meta,
                "date_range": [str(df.index.min()), str(df.index.max())],
                "last_raw_close": float(df["close_raw"].iloc[-1]),
                "high_raw": float(df["high_raw"].max()),
                "low_raw": float(df["low_raw"].min()),
                "interval_return_hfq": float(c.iloc[-1] / c.iloc[0] - 1),
                "ann_vol_hfq": float(ret.std() * 244 ** 0.5),
                "max_drawdown_hfq": float((c / c.cummax() - 1).min()),
                "monthly_close_raw": {k: round(float(v), 2)
                                      for k, v in monthly.items()}}
    return {"artifact_id": art_id, "kind": row["kind"], "meta": meta,
            "created_at": str(row["created_at"])}

async def ttl_cleanup() -> int:
    """先行后文件；顺带清理崩溃残留 *.tmp；仅主机 cron 链触发。"""
    p = await pool()
    rows = await p.fetch(
        "DELETE FROM artifacts WHERE expires_at < now() RETURNING id, path")
    n = 0
    for r in rows:
        try:
            await asyncio.to_thread(
                os.remove, os.path.join(settings.data_dir, r["path"]))
            n += 1
        except FileNotFoundError:
            pass
    art_dir = os.path.join(settings.data_dir, "artifacts")
    if os.path.isdir(art_dir):
        for f in await asyncio.to_thread(os.listdir, art_dir):
            if f.endswith(".tmp"):
                with contextlib.suppress(FileNotFoundError):
                    await asyncio.to_thread(
                        os.remove, os.path.join(art_dir, f))
                n += 1
    return n
