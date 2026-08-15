"""M0-B：AKShare 数据实证（B1 schema / B2 hfq 重叠窗口 / B3 冻结快照）。
用法（在 backend venv 内、仓库根执行）:
  python scripts/m0_akshare_checks.py
输出：逐项结论（供 docs/verification/M0-记录.md 回填，勿手工编造数字）。"""
import asyncio, datetime as dt, hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

SYMBOL = "600519"
W_SHORT = ("20230601", "20240630")     # B2 短窗
W_FULL = ("20230601", "20260531")      # B2 长窗 = B3 主快照
W_BREAKOUT = ("20240101", "20260531")  # breakout_001 用例快照
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "evals" / "fixtures"


async def main():
    from app import market
    import akshare as ak
    import pandas as pd

    # ---- B1 双口径拉取 + schema 校验（fetch_combined 内含 _validate）----
    df_full = await asyncio.to_thread(
        market.fetch_combined, SYMBOL, *W_FULL)
    print(f"B1 ok: symbol={SYMBOL} rows={len(df_full)} "
          f"cols={df_full.columns.tolist()} "
          f"range=[{df_full.index.min()}, {df_full.index.max()}]")
    assert len(df_full) > 0

    # ---- B2 hfq 重叠窗口实证（ADR-0003 待回填项）----
    df_short = await asyncio.to_thread(
        market.fetch_combined, SYMBOL, *W_SHORT)
    common = df_full.index.intersection(df_short.index)
    assert len(common) > 0
    diffs = {}
    for col in df_full.columns:
        a = df_full.loc[common, col].astype(float).to_numpy()
        b = df_short.loc[common, col].astype(float).to_numpy()
        d = float(abs(a - b).max())
        diffs[col] = d
    worst = max(diffs.values())
    verdict = "一致" if worst == 0.0 else "不一致"
    print(f"B2 overlap: common_days={len(common)} "
          f"per_col_max_absdiff={json.dumps(diffs, ensure_ascii=False)} "
          f"=> {verdict} (worst={worst})")

    # ---- B3 冻结快照（完整 10 列双口径帧 + meta 三字段）----
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for (start, end) in (W_FULL, W_BREAKOUT):
        frame = await asyncio.to_thread(
            market.fetch_combined, SYMBOL, start, end)
        name = f"{SYMBOL}_hfq_{start}_{end}.parquet"
        path = FIXTURE_DIR / name
        # date 作为列落盘（tools._load_fixture 兼容列/索引两种形态）
        frame.reset_index().to_parquet(path)
        checksum = hashlib.sha1(path.read_bytes()).hexdigest()
        meta = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "akshare_version": ak.__version__,
                "checksum": checksum,
                "symbol": SYMBOL, "start": start, "end": end,
                "rows": len(frame),
                "cols": frame.columns.tolist()}
        (FIXTURE_DIR / f"{name}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # 回读校验：_load_fixture 契约（10 列齐备）
        from app.tools import _load_fixture
        back = _load_fixture(str(path))
        assert list(back.columns) == list(frame.columns) and len(back) == len(frame)
        print(f"B3 fixture: {name} rows={len(frame)} "
              f"sha1={checksum[:12]}... akshare={ak.__version__} 回读校验OK")

    # ---- v15 预判故障 #1：人为改 NEED_COLS 触发 schema 校验报错 ----
    import pandas as pd
    import app.market as m
    orig = m.NEED_COLS
    fake_raw = pd.DataFrame({"日期": ["2024-01-02"], "开盘": [1.0]})  # 缺 收盘/最高/最低/成交量
    try:
        m.NEED_COLS = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}
        m._validate(fake_raw)
        print("故障预判#1 FAIL: 校验未触发")
    except AssertionError as e:
        print(f"故障预判#1 ok: schema 校验按预期触发 -> {e}")
    finally:
        m.NEED_COLS = orig

if __name__ == "__main__":
    asyncio.run(main())
