import asyncio, datetime as dt, json, re
from pydantic import BaseModel, Field, model_validator
from app.agents import AGENTS
from app.agent_loop import run_agent, parse_json_lenient
from app.budget import TaskBudget, BudgetExceeded
from app.config import settings
from app.events import bus
from app.llm import llm
from app.memory import recall_prefix, remember
from app.metrics import (M_TASK, M_BUDGET, M_EMIT_FAIL, M_TASK_CONF,
                         M_CRITIC_FAILOPEN)
from app import tasks as task_repo
import structlog

log = structlog.get_logger()
SPEC_AGENTS = {"research", "strategy", "writer"}

class PlanNode(BaseModel):
    id: str
    agent: str
    instruction: str = Field(min_length=4)
    depends_on: list[str] = []

class Plan(BaseModel):
    nodes: list[PlanNode] = []
    final: str = ""
    refuse: bool = False
    reason: str = ""
    supported: str = ""
    @model_validator(mode="after")
    def _shape(self):
        if self.refuse:
            assert self.reason, "refuse 必须给 reason"
            assert not self.nodes and not self.final, "拒绝时不得包含计划节点"
        else:
            assert self.nodes and self.final, "非拒绝计划必须含 nodes 与 final"
        return self

def _topo_order(plan: Plan) -> list[PlanNode]:
    by_id = {n.id: n for n in plan.nodes}
    indeg = {n.id: 0 for n in plan.nodes}
    for n in plan.nodes:
        for d in n.depends_on:
            indeg[n.id] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    order = []
    while queue:
        cur = queue.pop()
        order.append(by_id[cur])
        for n in plan.nodes:
            if cur in n.depends_on:
                indeg[n.id] -= 1
                if indeg[n.id] == 0:
                    queue.append(n.id)
    assert len(order) == len(plan.nodes), "DAG 存在环"
    return order

def _validate_plan(plan: Plan):
    ids = [n.id for n in plan.nodes]
    assert len(ids) == len(set(ids)), "节点 id 重复"
    assert len(plan.nodes) <= settings.budget_max_dag_nodes, "节点数超上限"
    by_id = {n.id: n for n in plan.nodes}
    for n in plan.nodes:
        assert n.agent in SPEC_AGENTS, f"未知 agent: {n.agent}"
        for d in n.depends_on:
            assert d in ids, f"依赖不存在: {d}"
    assert plan.final in ids and by_id[plan.final].agent == "writer", \
        "final 节点必须是 writer"

def _digest(context: dict) -> str:
    lines = [f"[{k} · {v.get('agent','')}] {v.get('output','')[:600]}"
             for k, v in context.items() if not k.startswith("_")]
    return "\n".join(lines) or "（无上游结论）"

def _symbols_in(text: str) -> list[str]:
    """A 股标的代码：按交易所前缀识别（沪主板60/深主板00·含001·002/创业板30/
    科创板68/北交所43·83·87·92）。v17 收紧——裸六位数字会把"100000股"这类
    数量词误判为标的（误写 memories+误注入无关记忆）；"600000元"类残余
    歧义语言层面不可消，接受。"""
    return sorted(set(re.findall(
        r"\b(?:60|00|30|68|43|83|87|92)\d{4}\b", text)))

async def _memory_lines(input_text: str) -> str:
    """命中 memories 的标的注入规划上下文（背景参考；事实以工具返回为准）。"""
    try:
        mem = await recall_prefix("symbol:")
    except Exception:
        return ""
    lines = []
    for s in _symbols_in(input_text):
        m = mem.get(f"symbol:{s}")
        if m:
            lines.append(f"[{s} · 上次分析 {m.get('date', '')}] "
                         f"{str(m.get('abstract', ''))[:200]}")
    return "\n".join(lines)

async def _remember_symbols(input_text: str, trace_id: str, context: dict):
    """done 后按标的落存分析摘要；失败仅告警，不影响任务终态。"""
    report = (context.get("_report") or "")[:400]
    if not report:
        return
    for s in _symbols_in(input_text):
        try:
            await remember(f"symbol:{s}",
                           {"trace_id": trace_id,
                            "date": dt.date.today().isoformat(),
                            "abstract": report})
        except Exception as e:
            log.warning("memory_remember_failed", symbol=s, err=str(e))

async def _emit_safe(task_id: str, type_: str, payload: dict | None = None):
    try:
        await bus.emit(task_id, type_, payload or {})
    except Exception as e:
        M_EMIT_FAIL.inc()
        log.warning("emit_failed", task_id=task_id, type=type_, err=str(e))

_inflight: set[asyncio.Task] = set()

def submit(task_id: str, eval_ctx: dict | None = None, reserved: int = 0):
    t = asyncio.create_task(_run(task_id, eval_ctx or {}, reserved))
    _inflight.add(t)
    t.add_done_callback(_inflight.discard)

async def _release_reserved(task_id: str, reserved: int, budget: TaskBudget):
    """归还预留并记账实际消耗——**无条件**执行（reserved=0 的恢复/评测任务
    其 tokens/llm_calls 也如实入账）；瞬时故障重试 3 次，最终失败仅告警，
    由下次启动对账兜底。"""
    for attempt in range(3):
        try:
            await task_repo.release_daily(reserved, budget.tokens,
                                          budget.llm_calls)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt == 2:
                log.warning("release_daily_failed", task_id=task_id)
            else:
                await asyncio.sleep(0.5 * (attempt + 1))

async def _finalize(task_id: str, status: str, result, error, plan, context,
                    trace_id: str, budget: TaskBudget, reserved: int,
                    emit_terminal: str = "task_done",
                    terminal_payload: dict | None = None,
                    pre_events: list[tuple[str, dict]] | None = None) -> bool:
    """终态序列：先 guarded finish；成功→(可选前置事件)→终态事件→释放预留；
    失败(状态已被迁移)→只记冲突，不发事件不释放（迁移方 watchdog 已做）。"""
    ok = await task_repo.finish(task_id, status, result, error, plan, context)
    if not ok:
        M_TASK_CONF.inc()
        log.warning("finish_conflict", task_id=task_id, want=status)
        return False
    M_TASK.labels(status).inc()
    for type_, payload in (pre_events or []):
        await _emit_safe(task_id, type_, payload)
    await _emit_safe(task_id, emit_terminal,
                     terminal_payload or {"trace_id": trace_id})
    rel = asyncio.ensure_future(_release_reserved(task_id, reserved, budget))
    try:
        await asyncio.shield(rel)   # 外层取消不打断释放；瞬时故障在 helper 内重试
    except asyncio.CancelledError:
        raise
    except Exception:
        pass                        # 已在 helper 内记 warning
    return True

async def _run(task_id: str, eval_ctx: dict, reserved: int):
    budget = TaskBudget()
    hb: asyncio.Task | None = None
    try:
        if not await task_repo.claim(task_id, reserved):
            if reserved:                      # 抢占失败：释放自己名下预留
                await task_repo.release_daily(reserved, 0)
            return
        task = await task_repo.get(task_id)
        if task is None:
            if reserved:
                await task_repo.release_daily(reserved, 0)
            return
        trace_id = task["trace_id"]
        await _emit_safe(task_id, "task_started",
                         {"trace_id": trace_id, "input": task["input"]})
        hb = asyncio.create_task(_heartbeat(task_id))
        context: dict = {}
        try:
            await asyncio.wait_for(
                _execute(task_id, task["input"], budget, context, eval_ctx),
                timeout=settings.budget_wall_clock_s + 60)
            budget.final_check()
            plan_dump = context.get("_plan") or {}
            ok = await _finalize(task_id, "done", _compose_result(context), None,
                                 context.pop("_plan", None), context, trace_id,
                                 budget, reserved)
            if ok and not plan_dump.get("refuse"):
                await _remember_symbols(task["input"], trace_id, context)
        except BudgetExceeded as e:
            M_BUDGET.labels(e.reason).inc()
            result = {**_compose_result(context), "degraded_reason": e.reason}
            await _finalize(
                task_id, "degraded", result, f"budget:{e.reason}",
                context.pop("_plan", None), context, trace_id, budget, reserved,
                pre_events=[("budget_degraded",
                             {"reason": e.reason, "trace_id": trace_id})],
                terminal_payload={"trace_id": trace_id, "degraded": True})
        except asyncio.TimeoutError:
            M_BUDGET.labels("wall_clock").inc()
            result = {**_compose_result(context), "degraded_reason": "wall_clock"}
            await _finalize(
                task_id, "degraded", result, "budget:wall_clock",
                context.pop("_plan", None), context, trace_id, budget, reserved,
                pre_events=[("budget_degraded",
                             {"reason": "wall_clock", "trace_id": trace_id})],
                terminal_payload={"trace_id": trace_id, "degraded": True})
        except asyncio.CancelledError:
            # v14：取消路径不释放、不 finish——任务保持 running，
            # 由 watchdog(租约到期→interrupted+释放)→启动恢复 链兜底；
            # 这使释放权始终唯一（状态迁移方），机制上杜绝双重释放。
            raise
        except Exception as e:
            await _finalize(task_id, "failed", None,
                            f"{type(e).__name__}: {e}",
                            context.pop("_plan", None), context, trace_id,
                            budget, reserved, emit_terminal="task_failed")
    finally:
        if hb:
            hb.cancel()

def _compose_result(context: dict) -> dict:
    return {"report": context.get("_report", ""),
            "nodes": {k: v.get("output", "")[:300]
                      for k, v in context.items() if not k.startswith("_")}}

async def _heartbeat(task_id: str):
    try:
        while True:
            await asyncio.sleep(10)
            await task_repo.renew(task_id)
    except asyncio.CancelledError:
        pass

async def _execute(task_id: str, input_text: str, budget: TaskBudget,
                   context: dict, eval_ctx: dict):
    sup = AGENTS["supervisor"]
    mem = await _memory_lines(input_text)
    user_msg = (input_text if not mem else
                input_text + "\n\n（跨任务记忆，仅供背景参考，"
                "事实与数字仍必须以工具返回为准：）\n" + mem)
    budget.check_llm()
    r = await llm().chat([{"role": "system", "content": sup.system_prompt},
                          {"role": "user", "content": user_msg}], model=sup.model)
    budget.spend_llm(r.usage_tokens)
    await _emit_safe(task_id, "llm_response", {"agent": "supervisor", "step": 0})
    try:
        plan = Plan.model_validate(parse_json_lenient(r.text))
        if not plan.refuse:
            _validate_plan(plan)
    except Exception as first_err:
        budget.check_llm()
        r2 = await llm().chat(
            [{"role": "system", "content": sup.system_prompt},
             {"role": "user", "content": user_msg},
             {"role": "assistant", "content": r.text},
             {"role": "user", "content":
              f"你上次的输出不合规：{first_err}。请严格按规则重新只输出JSON。"}],
            model=sup.model)
        budget.spend_llm(r2.usage_tokens)
        plan = Plan.model_validate(parse_json_lenient(r2.text))
        if not plan.refuse:
            _validate_plan(plan)
    if plan.refuse:
        context["_plan"] = plan.model_dump()
        context["_report"] = f"{plan.reason}\n\n支持范围：{plan.supported}"
        await _emit_safe(task_id, "task_refused", {"reason": plan.reason})
        return
    context["_plan"] = plan.model_dump()
    await _emit_safe(task_id, "plan_created", {"nodes": [
        {"id": n.id, "agent": n.agent, "depends_on": n.depends_on}
        for n in plan.nodes]})

    for node in _topo_order(plan):
        spec = AGENTS[node.agent]
        await _emit_safe(task_id, "agent_start",
                         {"agent": node.agent, "node": node.id})

        # 闭包晚绑定 node 在当前串行拓扑下安全（run_agent await 完成后才进入
        # 下一轮重绑）；若按 ADR-0001 的并行化 P2 演进，需改为按 node 显式
        # 传参（v18 P3-6 注释声明，不改行为）
        async def on_event(**kw):
            await _emit_safe(task_id, kw.pop("type"), {"node": node.id, **kw})

        text, _ = await run_agent(
            spec, node.instruction,
            _digest({k: v for k, v in context.items() if not k.startswith("_")}),
            budget, ctx=eval_ctx, on_event=on_event)
        context[node.id] = {"agent": node.agent, "output": text}
        await _emit_safe(task_id, "agent_end",
                         {"agent": node.agent, "node": node.id})

    critic, writer = AGENTS["critic"], AGENTS["writer"]
    draft = context[plan.final]["output"]
    for round_ in range(settings.critic_max_rounds):
        verdict = await _critic_round(task_id, round_, critic, draft,
                                      context, budget)
        await _emit_safe(task_id, "critic_verdict",
                         {"round": round_, "verdict": verdict["verdict"],
                          "issues": verdict.get("issues", [])})
        if verdict["verdict"] != "revise":
            break
        budget.check_llm()
        rw = await llm().chat(
            [{"role": "system", "content": writer.system_prompt},
             {"role": "user", "content":
              f"原稿：\n{draft}\n\nCritic 修改意见：\n"
              + "\n".join(verdict.get("issues", []))
              + f"\n\n上游结论黑板：\n{_digest({k: v for k, v in context.items() if not k.startswith('_')})}"}],
            model=writer.model)
        budget.spend_llm(rw.usage_tokens)
        draft = rw.text
        await _emit_safe(task_id, "agent_end",
                         {"agent": "writer", "node": plan.final,
                          "note": f"revise_round_{round_}"})
    context[plan.final]["output"] = draft
    context["_report"] = draft

async def _critic_round(task_id, round_, critic, draft, context, budget) -> dict:
    user = (f"上游结论黑板：\n{_digest({k: v for k, v in context.items() if not k.startswith('_')})}"
            f"\n\n报告草稿：\n{draft}")
    for attempt in range(2):
        budget.check_llm()
        r = await llm().chat(
            [{"role": "system", "content": critic.system_prompt},
             {"role": "user", "content": user}], model=critic.model)
        budget.spend_llm(r.usage_tokens)
        try:
            v = parse_json_lenient(r.text)
            assert v["verdict"] in ("pass", "revise")
            return v
        except Exception:
            if attempt == 0:
                user = ('你上次的输出不是合法JSON。只输出 '
                        f'{{"verdict":"pass|revise","issues":["..."]}}。\n{user}')
            else:
                M_CRITIC_FAILOPEN.inc()   # 独立计数：非预算事件不入M_BUDGET（v17 P2-2）
                log.warning("critic_parse_fail_failopen",
                            task_id=task_id, round=round_)
                return {"verdict": "pass",
                        "issues": ["critic_output_unparseable"]}
