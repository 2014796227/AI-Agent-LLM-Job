import time, akshare as ak, pandas as pd
from diskcache import Cache
from app.config import settings

_CACHE_VER = "2026-08-15.1"
_cache = Cache(settings.cache_dir + "/market", size_limit=2 * 1024 ** 3)
NEED_COLS = {"日期", "开盘", "收盘", "最高", "最低", "成交量"}

def _retry(fn, *a, **kw):
    for i in range(3):
        try:
            return fn(*a, **kw)
        except Exception:
            if i == 2:
                raise
            time.sleep(2 ** i)

def _validate(df):
    assert NEED_COLS.issubset(df.columns), \
        f"数据源schema变更: {df.columns.tolist()}"
    assert len(df) > 0 and df["收盘"].notna().all(), "数据不完整"

def _std(df, suffix):
    return pd.DataFrame({
        "date": df["日期"].astype(str),
        f"open_{suffix}": df["开盘"].astype(float),
        f"high_{suffix}": df["最高"].astype(float),
        f"low_{suffix}": df["最低"].astype(float),
        f"close_{suffix}": df["收盘"].astype(float),
        f"volume_{suffix}": df["成交量"].astype(float)})

def _std_tx(df, suffix):
    return pd.DataFrame({
        "date": df["date"].astype(str),
        f"open_{suffix}": df["open"].astype(float),
        f"high_{suffix}": df["high"].astype(float),
        f"low_{suffix}": df["low"].astype(float),
        f"close_{suffix}": df["close"].astype(float),
        # 腾讯源成交量为股、东财为手——÷100 对齐口径
        # （实测 2026-05-29 茅台：EM 76478 手 vs TX 7647800 股，恰 100 倍，
        # 两次同日交叉校验价格完全一致）
        f"volume_{suffix}": df["volume"].astype(float) / 100.0})

def _tx_symbol(symbol: str) -> str:
    # v33：场内 ETF 代码段——沪 51/56/58、深 15/16/18（A 股个股无 5/1 开头段，
    # 无冲突；513100 类基金此前被误判深市致查无数据）
    if symbol.startswith(("51", "56", "58")):
        return "sh" + symbol
    if symbol.startswith(("15", "16", "18")):
        return "sz" + symbol
    if symbol.startswith(("6", "9")):
        return "sh" + symbol
    if symbol.startswith(("4", "8")):
        return "bj" + symbol
    return "sz" + symbol

def fetch_combined(symbol: str, start: str, end: str) -> pd.DataFrame:
    """hfq 计算口径 + raw 展示口径合并帧。同步函数——调用方必须 to_thread。
    双源（v32）：东财对源 IP 有累计限流（无 SLA，实测冷却数小时~数日）——
    失败自动回退腾讯源（akshare stock_zh_a_hist_tx，hfq/raw 双口径齐备）。"""
    key = f"{_CACHE_VER}|{symbol}|{start}|{end}"
    if key in _cache:
        df = pd.read_json(_cache.get(key), orient="split").set_index("date")
        df.index = df.index.astype(str)   # read_json 可能解析为 datetime——与新鲜路径 str 索引保持一致
        df.attrs["source"] = "cache"      # v36：溯源标识（缓存值 24h 内由下述源拉取）
        return df
    # v33：东财个股接口不覆盖场内基金代码段（对 ETF 直接 IndexError）——
    # ETF 径走腾讯源（hfq/raw 双口径实测可用；东财 fund_etf_hist_em 备选留 P2）
    is_etf = symbol[:2] in ("51", "56", "58", "15", "16", "18")
    em_ok = False
    if not is_etf:
        try:
            hfq = _retry(ak.stock_zh_a_hist, symbol=symbol, start_date=start,
                         end_date=end, adjust="hfq")
            raw = _retry(ak.stock_zh_a_hist, symbol=symbol, start_date=start,
                         end_date=end, adjust="")
            _validate(hfq)
            _validate(raw)
            df = _std(hfq, "hfq").merge(_std(raw, "raw"),
                                        on="date", how="inner")
            assert len(df) == len(hfq), "hfq/raw 日期未对齐"
            df.attrs["source"] = "eastmoney"   # v36：溯源标识
            em_ok = True
        except Exception:
            em_ok = False
    if not em_ok:
        txs = _tx_symbol(symbol)
        try:
            hfq = _retry(ak.stock_zh_a_hist_tx, symbol=txs,
                         start_date=start, end_date=end, adjust="hfq")
            raw = _retry(ak.stock_zh_a_hist_tx, symbol=txs,
                         start_date=start, end_date=end, adjust="")
        except Exception as e:
            raise ValueError(
                f"行情双源获取失败 {symbol}（东财={'不适用ETF' if is_etf else '失败'}，"
                f"腾讯源 {txs} 异常 {type(e).__name__}）——"
                f"支持 6 位 A 股个股与场内 ETF 代码") from e
        assert len(hfq) > 0 and len(raw) > 0, (
            f"双源均无数据: {symbol}（东财={'不适用ETF' if is_etf else '失败'}，"
            f"腾讯源 {txs} 空）——请确认是 6 位 A 股个股/场内 ETF 代码")
        df = _std_tx(hfq, "hfq").merge(_std_tx(raw, "raw"),
                                       on="date", how="inner")
        assert len(df) == len(hfq), "hfq/raw 日期未对齐(腾讯源)"
        df.attrs["source"] = "tencent"    # v36：溯源标识
    df = df.set_index("date")
    _cache.set(key, df.reset_index().to_json(orient="split"), expire=86400)
    return df
