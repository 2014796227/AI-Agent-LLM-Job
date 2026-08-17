"""python scripts/run_eval.py [--cases evals/cases]
                             [--out docs/eval/results.md]
                             [--timeout-min 10]
报告 100% 脚本生成（自动嵌 commit hash/时间戳/明细），
人工只允许在末尾追加结论段。"""
import argparse, asyncio, json, subprocess, sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import yaml

TERMINALS = ("done", "failed", "degraded", "interrupted")

def commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True).strip()
    except Exception:
        return "no-git"

def _find_report(task) -> str:
    result = task["result"]
    parsed = json.loads(result) if isinstance(result, str) else (result or {})
    return parsed.get("report", "")

def _find_spec(trace):
    for e in trace:
        p = e["payload"]
        if e["type"] == "tool_call" and p.get("tool") == "engine.run_backtest":
            try:
                return json.loads(p["args"])["strategy_spec"]
            except Exception:
                continue
    return None

def _find_bt_artifact(trace):
    for e in trace:
        p = e["payload"]
        if e["type"] == "artifact_created" \
                and p.get("kind") == "backtest_result":
            return p["artifact_id"]
    return None

def _fmt_variants(v: float) -> set:
    return {f"{v:.2%}", f"{v:.1%}", f"{v:.4f}",
            f"{v:.2f}", f"{v * 100:.2f}"}

async def run_case(case: dict, timeout_min: int) -> dict:
    from app import orchestrator, tasks as task_repo, artifacts
    from app.events import fetch_history
    from app.llm import llm
    from app.agent_loop import parse_json_lenient
    from app.config import settings
    import pandas as pd
    from app.dsl import StrategySpec, compile_signal
    from app.backtest import vector_backtest

    task = await task_repo.create(case["input"])
    orchestrator.submit(
        str(task["id"]),
        eval_ctx={"fixture": case.get("fixture", {}).get("price"),
                  "symbol": case.get("symbol")})
    t = None
    for _ in range(timeout_min * 12):
        await asyncio.sleep(5)
        t = await task_repo.get(str(task["id"]))
        if t["status"] in TERMINALS:
            break
    trace = [json.loads(e.json())
             for e in await fetch_history(str(task["id"]))]
    spec = _find_spec(trace)
    metrics = None
    art = _find_bt_artifact(trace)
    if art:
        try:
            metrics = await artifacts.load_json(art)
        except Exception:
            metrics = None
    # 事件里的 args 被 on_event 截断到 2000 字符，超长 spec 解析失败→假阴性；
    # 回退到回测工件内的 strategy_spec——"实际执行的规范化 spec"本就是更准确
    # 的断言对象（v17 P2-1①）
    if spec is None and metrics:
        spec = metrics.get("strategy_spec")

    need = case.get("assert", {}).get("tools_called", [])
    called = [e["payload"].get("tool")
              for e in trace if e["type"] == "tool_call"]
    tools_ok = all(n in called for n in need) if need else None
    # ^ 空断言=None（未断言），而非 all([])=True 的空真（v17 P2-1②）
    spec_ok = _subset(
        case.get("assert", {}).get("strategy_spec_match"), spec)
    backtest_ok = None
    numbers_ok = None
    recompute = case.get("assert", {}).get("backtest_recompute", {})
    tol = float(recompute.get("tolerance", 1e-9))
    # ^ 按用例声明读取 fill/tolerance——原硬编码使 yaml 声明失效（v17 P2-1③）
    fixture = case.get("fixture", {}).get("price")
    if fixture and spec and metrics:
        # v30（M5 实测发现）：模型产出的 spec 可能非法（如 op:"le"）——任务内被
        # 工具正确拒绝属真实失败结果，评测器复算必须容错而非崩溃（曾致全量
        # 评测进程中断且被看门狗循环复现）
        try:
            df = pd.read_parquet(fixture)
            if "date" in df.columns:
                df = df.set_index("date")
            local = vector_backtest(
                df["close_hfq"],
                compile_signal(StrategySpec.model_validate(spec), df),
                fill=recompute.get("fill", "next_close"))
            backtest_ok = all(
                abs(local[k] - metrics.get(k, float("nan"))) < tol
                for k in ("total_return", "max_drawdown"))
            report = _find_report(t)
            if report:
                needle = set()
                for k in ("total_return", "annual_return", "max_drawdown"):
                    needle |= _fmt_variants(metrics.get(k, 0.0))
                numbers_ok = any(s in report for s in needle)
        except Exception:
            backtest_ok = False
    refusal_ok = (any(e["type"] == "task_refused" for e in trace)
                  if case.get("assert", {}).get("must_refuse")
                  else None)
    # v28（M5）：RAG 用例的引用断言——报告须含 [[指定doc#页]] 形式引用
    cite_need = case.get("assert", {}).get("must_cite", [])
    cite_ok = (any(f"[[{d}#" in _find_report(t) for d in cite_need)
               if cite_need else None)

    judge = {"pass": None}
    report = _find_report(t)
    if report:
        try:
            r = await llm().chat(
                [{"role": "system", "content":
                  f"你是评审。规则：{case.get('judge', {}).get('rubric', '报告数字须与工具返回一致，检查幻觉')}"
                  '。只输出JSON {"pass":bool,"issues":[]}'},
                 {"role": "user", "content": report}],
                model=settings.judge_model)
            v = parse_json_lenient(r.text)
            judge = {"pass": bool(v["pass"]),
                     "issues": v.get("issues", [])}
        except Exception:
            judge = {"pass": False, "note": "judge_error"}
    return {"case": case["id"], "status": t["status"],
            "tools_ok": tools_ok, "spec_ok": spec_ok,
            "backtest_ok": backtest_ok, "numbers_ok": numbers_ok,
            "refusal_ok": refusal_ok, "cite_ok": cite_ok, "judge": judge}

def _subset(want, got):
    if not want:
        return None
    if not got:
        return False
    def sub(w, g):
        if isinstance(w, dict):
            return (isinstance(g, dict)
                    and all(sub(v, g.get(k)) for k, v in w.items()))
        if isinstance(w, list):
            return (isinstance(g, list) and len(g) == len(w)
                    and all(sub(a, b) for a, b in zip(w, g)))
        return w == g
    return sub(want, got)

async def _run_all(cases_dir: str, timeout_min: int, checkpoint: str = ""):
    from app.db import init_schema
    await init_schema()
    out, done = [], set()
    if checkpoint and Path(checkpoint).exists():
        for line in Path(checkpoint).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.append(r)
                done.add(r["case"])
        print(f"resume: {len(done)} 个用例已存，跳过", flush=True)
    files = sorted(Path(cases_dir).glob("*.yaml"))
    cases = [c for f in files
             for c in yaml.safe_load_all(f.read_text(encoding="utf-8"))]
    n = len(out)
    for case in cases:
        if case["id"] in done:
            continue
        r = await run_case(case, timeout_min)
        out.append(r)
        n += 1
        done.add(case["id"])   # v31：运行时同步跳过集（否则同轮后段同名用例重复跑）
        if checkpoint:   # v29：逐用例 checkpoint——评测进程被环境杀掉后可断点续跑
            with open(checkpoint, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[{n}/{len(cases)}] {case['id']} -> {r['status']}",
              flush=True)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="evals/cases")
    ap.add_argument("--out", default="docs/eval/results.md")
    ap.add_argument("--timeout-min", type=int, default=10)
    ap.add_argument("--checkpoint", default="",
                    help="逐用例结果 jsonl；存在则跳过已存用例（v29 断点续跑）")
    a = ap.parse_args()
    results = asyncio.run(_run_all(a.cases, a.timeout_min, a.checkpoint))
    md = ["# 评测报告（脚本生成，人工结论只允许追加于末尾）", "",
          f"- commit: `{commit_hash()}`",
          f"- 时间: {dt.datetime.now().isoformat()}", "",
          "| 用例 | 状态 | tools | spec | backtest | numbers | refusal | cite | judge |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(
            f"| {r['case']} | {r['status']} | {r['tools_ok']} "
            f"| {r['spec_ok']} | {r['backtest_ok']} | {r['numbers_ok']} "
            f"| {r['refusal_ok']} | {r['cite_ok']} | {r['judge'].get('pass')} |")
    Path(a.out).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"written {a.out}")

if __name__ == "__main__":
    main()
