import asyncio
from dataclasses import dataclass
from app import artifacts, market, rag
from app.dsl import StrategySpec, compile_signal, CompileError
from app.backtest import vector_backtest

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: callable                 # async (args: dict, ctx: dict) -> dict

def _sch(props, required, defs=None):
    out = {"type": "object", "properties": props,
           "required": required, "additionalProperties": False}
    if defs:
        out["$defs"] = defs
    return out

# v23（M2 线上实测发现）：strategy_spec 原为无结构 {"type":"object"}——flash
# 4 次翻译全错（conditions 包裹层/args 代 left-right/kind 误写指标名）。
# 补全精确 JSON Schema（与 dsl.py 校验一一对应；嵌套≤3 用展开式 anyOf 表达，
# 规避部分网关对 $ref 的支持差异）。
def _operand_schema():
    return {"oneOf": [
        {"type": "object", "required": ["kind", "ind", "n"],
         "additionalProperties": False,
         "properties": {"kind": {"const": "ind"},
                        "ind": {"enum": ["ma", "ema", "rsi", "hhv",
                                         "llv", "ret", "vol_ma"]},
                        "n": {"type": "integer", "minimum": 2,
                              "maximum": 500}}},
        {"type": "object", "required": ["kind", "src"],
         "additionalProperties": False,
         "properties": {"kind": {"const": "price"},
                        "src": {"enum": ["close", "open", "high",
                                         "low", "volume"]}}},
        {"type": "object", "required": ["kind", "value"],
         "additionalProperties": False,
         "properties": {"kind": {"const": "const"},
                        "value": {"type": "number"}}}]}

def _leaf_schema():
    return {"type": "object", "required": ["op", "left", "right"],
            "additionalProperties": False,
            "properties": {"op": {"enum": ["gt", "lt", "cross_up",
                                           "cross_down"]},
                           "left": _operand_schema(),
                           "right": _operand_schema()}}

def _cond_schema(depth: int = 2):
    """depth=2 → Leaf | Bool(Leaf|Bool(Leaf,Leaf))，即嵌套≤3。"""
    if depth == 0:
        return _leaf_schema()
    sub = _cond_schema(depth - 1)
    return {"anyOf": [
        _leaf_schema(),
        {"type": "object", "required": ["op", "left", "right"],
         "additionalProperties": False,
         "properties": {"op": {"enum": ["and", "or"]},
                        "left": sub, "right": sub}}]}

def _strategy_spec_schema():
    return {"type": "object",
            "required": ["universe", "entry", "exit"],
            "additionalProperties": False,
            "properties": {
                "universe": {"type": "array", "items": {"type": "string"},
                             "minItems": 1, "maxItems": 1},
                "entry": _cond_schema(),
                "exit": _cond_schema(),
                "position": {"const": "long_only"}}}

_FIXTURE_COLS = {f"{col}_{k}"
                 for k in ("hfq", "raw")
                 for col in ("open", "high", "low", "close", "volume")}

def _load_fixture(path: str):
    """fixture=fetch_combined 完整帧快照（文件名中的 hfq 指信号计算口径，
    非仅 hfq 列）。加载即校验 10 列齐备：summary 需 raw 列、_run_backtest
    无条件取 open_hfq——缺列在这里报明确错误，好过运行期 KeyError（v18 P2-1）。"""
    import pandas as pd
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df = df.set_index("date")
    missing = _FIXTURE_COLS - set(df.columns)
    assert not missing, \
        f"fixture 缺列{sorted(missing)}，须为 fetch_combined 完整帧(hfq+raw×OHLCV)"
    return df

async def _price_history(args: dict, ctx: dict) -> dict:
    symbol, start, end = args["symbol"], args["start"], args["end"]
    if ctx.get("fixture"):
        df = _load_fixture(ctx["fixture"])
    else:
        df = await asyncio.to_thread(
            market.fetch_combined, symbol, start, end)
    art = await artifacts.save_dataframe(
        df, "price_history",
        meta={"symbol": symbol, "start": start, "end": end,
              "adjust": "hfq计算+raw展示",
              "fixture": bool(ctx.get("fixture"))})
    s = await artifacts.summary(art)
    return {**s, "note": "完整数据以artifact_id在服务端流转；展示价格为不复权raw口径"}

async def _run_backtest(args: dict, ctx: dict) -> dict:
    spec = StrategySpec.model_validate(args["strategy_spec"])
    df = await artifacts.load_dataframe(args["price_artifact_id"])
    symbol = spec.universe[0]
    if ctx.get("symbol") and symbol != ctx["symbol"]:
        raise CompileError(
            f"回测标的 {symbol} 与用例标的 {ctx['symbol']} 不符")
    signal = compile_signal(spec, df)
    result = vector_backtest(df["close_hfq"], signal, open_=df["open_hfq"])
    result["strategy_spec"] = spec.model_dump()
    result["symbol"] = symbol
    art = await artifacts.save_json(
        result, "backtest_result",
        meta={"price_artifact_id": args["price_artifact_id"],
              "symbol": symbol})
    return {"artifact_id": art, "kind": "backtest_result",
            "metrics": {k: result[k] for k in
                        ("fill", "total_return", "annual_return",
                         "max_drawdown", "sharpe", "assumptions")},
            "equity_preview": dict(
                list(result["equity_curve"].items())[:5]
                + list(result["equity_curve"].items())[-5:]),
            "note": "完整净值曲线经 GET /api/artifacts/{id}/equity 获取"}

async def _artifact_summary(args, ctx):
    return await artifacts.summary(args["artifact_id"])

async def _rag_search(args, ctx):
    return await rag.search(args["query"], top_k=int(args.get("top_k", 5)))

REGISTRY: dict[str, Tool] = {
    "market.price_history": Tool(
        "market.price_history",
        "获取A股日线行情(hfq计算口径+raw展示口径)，返回artifact句柄与摘要",
        _sch({"symbol": {"type": "string", "description": "6位代码，如600519"},
              "start": {"type": "string", "description": "YYYYMMDD"},
              "end": {"type": "string", "description": "YYYYMMDD"}},
             ["symbol", "start", "end"]),
        _price_history),
    "engine.run_backtest": Tool(
        "engine.run_backtest",
        "对已有行情工件执行白名单策略回测",
        _sch({"price_artifact_id": {"type": "string"},
              "strategy_spec": _strategy_spec_schema()},
             ["price_artifact_id", "strategy_spec"]),
        _run_backtest),
    "artifact.summary": Tool(
        "artifact.summary", "查看工件元信息与统计摘要",
        _sch({"artifact_id": {"type": "string"}}, ["artifact_id"]),
        _artifact_summary),
    "rag.search": Tool(
        "rag.search", "检索内置知识库，返回 [[doc_id#页码]] 引用片段",
        _sch({"query": {"type": "string"},
              "top_k": {"type": "integer", "default": 5}},
             ["query"]),
        _rag_search),
}

def schemas(names: list[str]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": REGISTRY[n].name, "description": REGISTRY[n].description,
        "parameters": REGISTRY[n].parameters}}
        for n in names if n in REGISTRY]

async def execute(name: str, args: dict, ctx: dict | None = None) -> dict:
    if name not in REGISTRY:
        return {"error": f"未知工具 {name}"}
    return await REGISTRY[name].fn(args, ctx or {})
