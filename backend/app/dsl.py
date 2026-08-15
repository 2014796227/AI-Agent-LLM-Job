from typing import Literal, Union, Annotated
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Indicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["ind"] = "ind"
    ind: Literal["ma", "ema", "rsi", "hhv", "llv", "ret", "vol_ma"]
    n: int = Field(ge=2, le=500)

class PriceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["price"] = "price"
    src: Literal["close", "open", "high", "low", "volume"]

class Constant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["const"] = "const"
    value: float = Field(ge=-1e9, le=1e9)

Operand = Annotated[Union[Indicator, PriceRef, Constant],
                    Field(discriminator="kind")]

class LeafCond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["cross_up", "cross_down", "gt", "lt"]
    left: Operand
    right: Operand
    @model_validator(mode="after")
    def _shape(self):
        assert not isinstance(self.left, Constant), "左操作数必须是序列"
        both_ind = (isinstance(self.left, Indicator)
                    and isinstance(self.right, Indicator))
        if self.op.startswith("cross") and both_ind \
                and self.left.ind == self.right.ind:
            assert self.left.n != self.right.n, \
                "同族同窗口序列恒等，cross永不为真"
        both_price = (isinstance(self.left, PriceRef)
                      and isinstance(self.right, PriceRef))
        if self.op.startswith("cross") and both_price:
            assert self.left.src != self.right.src, \
                "同源价格序列恒等，cross永不为真"
        return self

def _depth(cond) -> int:
    return 1 if isinstance(cond, LeafCond) else \
        1 + max(_depth(cond.left), _depth(cond.right))

class BoolCond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["and", "or"]
    left: Union["LeafCond", "BoolCond"]
    right: Union["LeafCond", "BoolCond"]
    @model_validator(mode="after")
    def _depth_ok(self):
        assert _depth(self) <= 3, "条件嵌套深度>3"
        return self

Cond = Annotated[Union[LeafCond, BoolCond], Field(discriminator="op")]

class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe: list[str] = Field(min_length=1, max_length=1)  # v1 单标的
    entry: Cond
    exit: Cond
    position: Literal["long_only"] = "long_only"

# 语义契约（hfq 全链路；单测逐条断言）：
# ma(n)=close.rolling(n).mean()；ema(n)=close.ewm(span=n,adjust=False).mean()
# rsi(n)=Wilder RSI；横盘(up=dn=0)=50；首行NaN(无定义)
# hhv(n)=high.rolling(n).max().shift(1)；llv(n)=low.rolling(n).min().shift(1)
#        （前n日极值，不含当日）
# ret(n)=close.pct_change(n)（n日简单收益，T收盘后成立，无未来引用）
# vol_ma(n)=volume.rolling(n).mean()
# gt/lt=逐日布尔；cross_up=昨 l≤r 且今 l>r（右操作数可为常数）
# entry/exit 同日冲突=exit 优先（保守：不开仓）

class CompileError(Exception): ...

def _indicator_series(ind: Indicator, df: pd.DataFrame) -> pd.Series:
    c, h, l, v = df["close_hfq"], df["high_hfq"], df["low_hfq"], df["volume_hfq"]
    n = ind.n
    if ind.ind == "ma":
        return c.rolling(n).mean()
    if ind.ind == "ema":
        return c.ewm(span=n, adjust=False).mean()
    if ind.ind == "rsi":
        delta = c.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        rs = up / dn
        rsi = 100 - 100 / (1 + rs)
        flat = (up == 0) & (dn == 0)
        rsi = rsi.mask(flat, 50.0)
        return rsi.where(delta.notna())
    if ind.ind == "hhv":
        return h.rolling(n).max().shift(1)
    if ind.ind == "llv":
        return l.rolling(n).min().shift(1)
    if ind.ind == "ret":
        return c.pct_change(n)
    if ind.ind == "vol_ma":
        return v.rolling(n).mean()
    raise CompileError(f"未知指标 {ind.ind}")

def _operand_series(op, df):
    if isinstance(op, Constant):
        return op.value
    if isinstance(op, PriceRef):
        return df[f"{op.src}_hfq"]
    return _indicator_series(op, df)

def _leaf_series(cond: LeafCond, df: pd.DataFrame) -> pd.Series:
    left = _operand_series(cond.left, df)
    right = _operand_series(cond.right, df)
    if cond.op in ("gt", "lt"):
        cmp_ = (left > right) if cond.op == "gt" else (left < right)
        return cmp_.fillna(False) if hasattr(cmp_, "fillna") else cmp_
    prev_l = left.shift(1)
    prev_r = right.shift(1) if isinstance(right, pd.Series) else right
    if cond.op == "cross_up":
        raw = (prev_l <= prev_r) & (left > right)
    else:
        raw = (prev_l >= prev_r) & (left < right)
    return raw.fillna(False)

def _cond_series(cond, df: pd.DataFrame) -> pd.Series:
    if isinstance(cond, LeafCond):
        return _leaf_series(cond, df)
    l, r = _cond_series(cond.left, df), _cond_series(cond.right, df)
    return (l & r) if cond.op == "and" else (l | r)

def _max_window(cond) -> int:
    if isinstance(cond, LeafCond):
        ws = [o.n for o in (cond.left, cond.right)
              if isinstance(o, Indicator)]
        return max(ws or [0])
    return max(_max_window(cond.left), _max_window(cond.right))

def compile_signal(spec: StrategySpec, df: pd.DataFrame) -> pd.Series:
    need_win = max(_max_window(spec.entry), _max_window(spec.exit)) + 1
    if need_win > len(df):
        raise CompileError(
            f"数据仅{len(df)}行，不足以计算窗口{need_win}；"
            f"请缩短窗口或拉长区间")
    entry = _cond_series(spec.entry, df)
    exit_ = _cond_series(spec.exit, df)
    pos, holding = [], False
    for e, x in zip(entry.to_numpy(), exit_.to_numpy()):
        if x:
            holding = False
        elif e:
            holding = True
        pos.append(1.0 if holding else 0.0)
    return pd.Series(pos, index=df.index, dtype=float)
