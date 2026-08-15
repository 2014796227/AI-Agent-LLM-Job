import pandas as pd

FILL_ASSUMPTIONS = ("next_close成交(T信号T+1收盘建仓,首收益区间T+1→T+2)·"
                    "固定费率近似(无最低佣金/印花税/滑点)·"
                    "未建模涨跌停/停牌/整手/融资成本·日线粒度规避T+1日内回转")

def vector_backtest(close: pd.Series, signal: pd.Series,
                    open_: pd.Series = None, fee: float = 0.0005,
                    fill: str = "next_close") -> dict:
    """fill→shift 契约（单测逐条断言）：
    next_close: pos=signal.shift(2)；signal_close: pos=signal.shift(1)；
    next_open: pos=signal.shift(1)，入场日收益=close/open-1，其后close/close。
    收益序列与 signal 必须按同一索引对齐（调用方保证同一 df 派生）。"""
    if fill == "next_close":
        pos = signal.shift(2).fillna(0.0)
        daily = close.pct_change().fillna(0.0)
    elif fill == "signal_close":
        pos = signal.shift(1).fillna(0.0)
        daily = close.pct_change().fillna(0.0)
    elif fill == "next_open":
        assert open_ is not None, "next_open 需要 open 序列"
        pos = signal.shift(1).fillna(0.0)
        base = close.shift(1)
        entry = (pos == 1) & (pos.shift(1).fillna(0) == 0)
        base = base.mask(entry, open_)
        daily = (close / base - 1).fillna(0.0)
    else:
        raise ValueError(f"未知 fill 口径: {fill}")
    ret = daily * pos - fee * pos.diff().abs().fillna(0.0)
    equity = (1 + ret).cumprod()
    years = len(close) / 244
    return {"fill": fill,
            "total_return": float(equity.iloc[-1] - 1),
            "annual_return": float(equity.iloc[-1] ** (1 / years) - 1)
                if years > 0 else 0.0,
            "max_drawdown": float((equity / equity.cummax() - 1).min()),
            "sharpe": float(ret.mean() / ret.std() * 244 ** 0.5)
                if ret.std() > 0 else 0.0,
            "equity_curve": {str(k): round(float(v), 4)
                             for k, v in equity.items()},
            "assumptions": FILL_ASSUMPTIONS}
