import json, time
from app.agents import AgentSpec
from app.budget import TaskBudget, BudgetExceeded
from app.config import settings
from app.llm import llm, ChatResult

def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()

def parse_json_lenient(s: str):
    return json.loads(_strip_fence(s))

def _safe_truncate(result: dict) -> str:
    """截断后仍是合法 JSON（信封包裹预览），模型可解析。"""
    s = json.dumps(result, ensure_ascii=False, default=str)
    if len(s) <= settings.tool_result_max_chars:
        return s
    return json.dumps({"truncated": True,
                       "preview": s[:settings.tool_result_max_chars - 120],
                       "note": "结果过大已截断，可用 artifact.summary 查看摘要"},
                      ensure_ascii=False)

async def _noop_event(**_kw): ...

async def run_agent(spec: AgentSpec, instruction: str, context_digest: str,
                    budget: TaskBudget, ctx: dict | None = None,
                    on_event=_noop_event) -> tuple[str, int]:
    """返回 (最终文本, 累计tokens)。工具子集=spec.tools；步数=spec.max_steps。
    BudgetExceeded 向上传播由编排器降级；步数熔断返回明确文案+最后模型文本。"""
    # v20（M0 端到端实测发现）：tools.py 提供模块级 schemas()/execute() 与
    # REGISTRY 字典——v18 起此处误写 `from app.tools import registry`（不存在的
    # 对象），首个真实 Agent 节点即 ImportError（单测不覆盖 run_agent 故未现形）
    from app.tools import schemas as tool_schemas, execute as tool_execute
    messages = [{"role": "system", "content": spec.system_prompt},
                {"role": "user",
                 "content": f"任务背景（上游结论摘要）：\n{context_digest}\n\n你的任务：\n{instruction}"}]
    schemas = tool_schemas(spec.tools)
    total_tokens = 0
    last_text = ""
    for step in range(spec.max_steps):
        budget.check_llm()
        r: ChatResult = await llm().chat(messages, tools=schemas, model=spec.model)
        budget.spend_llm(r.usage_tokens)
        total_tokens += r.usage_tokens
        await on_event(type="llm_response", agent=spec.name, step=step)
        if not r.tool_calls:
            return r.text, total_tokens
        last_text = r.text or last_text
        messages.append({"role": "assistant", "content": r.text,
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.name,
                                                      "arguments": tc.arguments}}
                                        for tc in r.tool_calls]})
        for tc in r.tool_calls:
            budget.check_tool()
            budget.spend_tool()
            try:
                args = parse_json_lenient(tc.arguments)
                await on_event(type="tool_call", agent=spec.name, tool=tc.name,
                               args=json.dumps(args, ensure_ascii=False,
                                               default=str)[:2000])
                t0 = time.monotonic()
                result = await tool_execute(tc.name, args, ctx=ctx or {})
                ms = int((time.monotonic() - t0) * 1000)
                await on_event(type="tool_result", agent=spec.name, tool=tc.name,
                               ok=True, ms=ms,
                               artifact_id=result.get("artifact_id"),
                               kind=result.get("kind"))
                if result.get("artifact_id"):
                    # v36：行情工件事件携带溯源摘要（前端"数据溯源"条渲染依据）
                    meta = result.get("meta") or {}
                    await on_event(type="artifact_created",
                                   artifact_id=result["artifact_id"],
                                   kind=result.get("kind"),
                                   trace_meta={k: meta[k] for k in
                                               ("source", "symbol", "start",
                                                "end", "rows", "fixture")
                                               if k in meta})
            except BudgetExceeded:
                raise
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
                await on_event(type="tool_result", agent=spec.name, tool=tc.name,
                               ok=False, ms=0)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": _safe_truncate(result)})
    return (f"已达最大步数熔断（{spec.max_steps}步）。"
            f"最后模型输出片段：{last_text[:300] or '（无）'}"), total_tokens
