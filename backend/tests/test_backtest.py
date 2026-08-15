import pandas as pd
from app.backtest import vector_backtest

def _ser(*vals, idx=None):
    return pd.Series(list(vals),
                     index=idx or [f"d{i}" for i in range(len(vals))],
                     dtype=float)

def test_fill_timing_contract():
    closes = _ser(10, 10, 10, 11, 11)      # d0..d4
    sig = _ser(0, 1, 0, 0, 0)              # 信号T=d1
    r = vector_backtest(closes, sig, fee=0.0, fill="next_close")
    eq = r["equity_curve"]
    # 契约：d2收盘建仓（价10），首个收益区间 d2→d3 = 11/10
    assert eq["d1"] == 1.0 and eq["d2"] == 1.0
    assert abs(eq["d3"] - 1.1) < 1e-9
    assert abs(eq["d4"] - 1.1) < 1e-9
    assert abs(r["total_return"] - 0.1) < 1e-9
    r2 = vector_backtest(closes, sig, fee=0.0, fill="signal_close")
    # v19 修正手算：signal_close 建仓 d1 收盘→首收益区间 d1→d2=10/10-1=0；
    # 跳空发生在 d2→d3，早一日入场（仅 d2 持仓）捕获不到——与 next_close 的
    # 时序差即本断言的意义（原断言 1.1 与 docstring 契约 shift(1) 自相矛盾）
    assert abs(r2["equity_curve"]["d2"] - 1.0) < 1e-9
    assert abs(r2["total_return"] - 0.0) < 1e-9

def test_hand_computed_with_fee():
    closes = _ser(10, 10, 10, 11, 11)
    sig = _ser(0, 1, 0, 0, 0)
    r = vector_backtest(closes, sig, fee=0.0005, fill="next_close")
    # v19 修正手算：两笔换仓费各归其发生日——d3 入场费（0.1-0.0005=0.0995
    # →净值 1.0995）；d4 平仓费（0-0.0005 → 1.0995×0.9995≈1.0990，曲线按
    # 4 位小数舍入后为 1.099）。原手算漏计第二笔费。
    assert abs(r["equity_curve"]["d3"] - 1.0995) < 1e-9
    assert abs(r["equity_curve"]["d4"] - 1.099) < 1e-9

def test_fill_next_open_entry_day():
    closes = _ser(10, 10, 11)
    opens = _ser(10, 9, 10)
    sig = _ser(0, 1, 0)                    # d1信号→d2开盘成交（价10）
    r = vector_backtest(closes, sig, open_=opens,
                        fee=0.0, fill="next_open")
    assert abs(r["equity_curve"]["d2"] - 1.1) < 1e-9

def test_max_drawdown_and_sharpe_reasonable():
    # v19 修正数据：next_close 的 shift(2) 热身错过 d0→d2 段，原数据(…,12)的
    # 捕获段净额恰为 9/12×13/9×12/13=1（total_return=0）；末值改 14 使捕获段>0
    closes = _ser(10, 12, 9, 13, 14)
    sig = _ser(1, 1, 1, 1, 1)
    r = vector_backtest(closes, sig, fee=0.0, fill="next_close")
    assert r["max_drawdown"] < 0
    assert r["total_return"] > 0
