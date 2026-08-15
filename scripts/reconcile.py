"""恢复后对账：逐行校验文件存在；孤儿文件（含 *.tmp 残留）删除并计数。
用法: python scripts/reconcile.py --data-dir .data"""
import argparse, asyncio, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

async def main(data_dir: str):
    from app.db import pool
    p = await pool()
    rows = await p.fetch("SELECT id, path FROM artifacts")
    dangling = [r["id"] for r in rows
                if not os.path.exists(os.path.join(data_dir, r["path"]))]
    orphans = []
    art_dir = os.path.join(data_dir, "artifacts")
    if os.path.isdir(art_dir):
        db_paths = {r["path"] for r in rows}
        for f in os.listdir(art_dir):
            if f"artifacts/{f}" not in db_paths:
                os.remove(os.path.join(art_dir, f))
                orphans.append(f)
    print(json.dumps(
        {"dangling": dangling, "orphans_removed": len(orphans)},
        ensure_ascii=False, indent=2))
    assert not dangling, "存在悬空引用（PG有行无文件）——恢复流程有误"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".data")
    a = ap.parse_args()
    asyncio.run(main(a.data_dir))
