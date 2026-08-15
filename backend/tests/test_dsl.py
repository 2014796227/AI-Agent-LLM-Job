import pandas as pd, numpy as np, pytest
from pydantic import ValidationError
from app.dsl import StrategySpec, compile_signal, CompileError

def _df(closes, highs=None, lows=None, opens=None, n=None):
    n = n or len(closes)
    return pd.DataFrame({
        "close_hfq": closes,
        "high_hfq": highs if highs is not None
            else [max(closes) + 1] * n,
        "low_hfq": lows if lows is not None
            else [min(closes) - 1] * n,
        "open_hfq": opens if opens is not None else closes,
        "volume_hfq": [1e6] * n,
    }, index=[f"d{i}" for i in range(n)])

MA5 = {"kind": "ind", "ind": "ma", "n": 5}
MA20 = {"kind": "ind", "ind": "ma", "n": 20}

def _x(l, r, op="cross_up"):
    return {"op": op, "left": l, "right": r}

def _spec(entry, exit_, uni=("600519",)):
    return {"universe": list(uni), "entry": entry, "exit": exit_}

def test_reject_n_small():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x({"kind": "ind", "ind": "ma", "n": 1}, MA20),
            _x(MA5, MA20, "cross_down")))

def test_reject_n_large():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x({"kind": "ind", "ind": "ma", "n": 501}, MA20),
            _x(MA5, MA20, "cross_down")))

def test_reject_unknown_ind():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x({"kind": "ind", "ind": "macd", "n": 5}, MA20),
            _x(MA5, MA20, "cross_down")))

def test_reject_extra_field():
    bad = _spec(_x(MA5, MA20), _x(MA5, MA20, "cross_down"))
    bad["leverage"] = 2
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(bad)

def test_reject_const_left():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x({"kind": "const", "value": 30}, MA20),
            _x(MA5, MA20, "cross_down")))

def test_reject_missing_exit():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(
            {"universe": ["600519"], "entry": _x(MA5, MA20)})

def test_reject_depth4():
    leaf = _x(MA5, MA20)
    l4 = {"op": "and",
          "left": {"op": "and",
                   "left": {"op": "and", "left": leaf, "right": leaf},
                   "right": leaf},
          "right": leaf}
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(l4, leaf))

def test_reject_same_family_same_window_cross():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x(MA20, MA20), _x(MA5, MA20, "cross_down")))

def test_reject_same_price_cross():
    close = {"kind": "price", "src": "close"}
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x(close, close), _x(MA5, MA20, "cross_down")))

def test_reject_window_exceeds_data():
    df = _df([10.0] * 30)
    spec = StrategySpec.model_validate(_spec(
        _x({"kind": "ind", "ind": "ma", "n": 500},
           {"kind": "ind", "ind": "ma", "n": 250}),
        _x(MA5, MA20, "cross_down")))
    with pytest.raises(CompileError):
        compile_signal(spec, df)

def test_reject_multi_symbol():
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_spec(
            _x(MA5, MA20), _x(MA5, MA20, "cross_down"),
            uni=("600519", "000858")))

def test_hhv_excludes_today():
    # v19 修正：原 5 行数据与 exit 的 MA20（需 21 行）冲突——编译期窗口校验
    # 正确拒绝（CompileError），测试自身数据不足；扩至 25 行，触发逻辑不变
    df = _df(closes=[9.0] * 24 + [11.0],
             highs=[10.0] * 24 + [99.0],
             lows=[5.0] * 25)
    spec = StrategySpec.model_validate(_spec(
        _x({"kind": "price", "src": "close"},
           {"kind": "ind", "ind": "hhv", "n": 2}),
        _x(MA5, MA20, "cross_down")))
    sig = compile_signal(spec, df)
    # hhv(2)@d24 = max(high d22,d23) = 10（不含当日99）；9≤10 且 11>10 → 触发
    assert sig["d24"] == 1.0
    assert sig.iloc[:24].sum() == 0

def test_llv_excludes_today():
    df = _df(closes=[6, 6, 6, 6, 4.0],
             highs=[10, 10, 10, 10, 10.0],
             lows=[5, 5, 5, 5, 1.0])
    spec = StrategySpec.model_validate(_spec(
        {"op": "gt", "left": {"kind": "price", "src": "close"},
         "right": {"kind": "const", "value": 0}},
        _x({"kind": "price", "src": "close"},
           {"kind": "ind", "ind": "llv", "n": 2}, "cross_down")))
    sig = compile_signal(spec, df)
    assert sig["d3"] == 1.0 and sig["d4"] == 0.0

def test_exit_priority_same_day():
    entry = {"op": "gt", "left": {"kind": "price", "src": "close"},
             "right": {"kind": "const", "value": 0}}
    spec = StrategySpec.model_validate(_spec(entry, entry))
    sig = compile_signal(spec, _df([10.0, 11.0, 12.0]))
    assert sig.sum() == 0

def test_ret_semantics():
    closes = list(np.linspace(10, 13, 30))
    spec = StrategySpec.model_validate(_spec(
        {"op": "gt", "left": {"kind": "ind", "ind": "ret", "n": 2},
         "right": {"kind": "const", "value": 0}},
        _x(MA5, MA20, "cross_down")))
    sig = compile_signal(spec, _df(closes))
    assert sig.iloc[0] == 0.0 and sig.iloc[1] == 0.0
    assert all(v == 1.0 for v in sig.iloc[2:])

def test_rsi_flat_is_50():
    spec = StrategySpec.model_validate(_spec(
        {"op": "gt", "left": {"kind": "ind", "ind": "rsi", "n": 14},
         "right": {"kind": "const", "value": 70}},
        _x(MA5, MA20, "cross_down")))
    sig = compile_signal(spec, _df([10.0] * 30))
    assert sig.sum() == 0
