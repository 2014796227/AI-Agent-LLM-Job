"""M0-§3 GLM/embedding 真实调用实测（key 从 backend/.env 读取——不入库、不入日志）。
在 backend/ 目录下执行: ./.venv/Scripts/python.exe ../scripts/m0_llm_checks.py
逐项容错：单项失败不中断，输出 pass/blocked 状态（2026-08-15 实测发现：该 key
的 glm-4.6/embedding 付费侧配额在两次成功调用后即 1113 耗尽；glm-4.7-flash
免费层持续可用——各项以当次实际结果为准记录）。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

RESULTS = []

def record(item, ok, detail):
    RESULTS.append((item, "pass" if ok else "blocked", detail))
    print(f"[{'pass' if ok else 'blocked'}] {item}: {detail}")

def _try_json(s):
    try:
        return json.loads(s)
    except Exception:
        return None

async def main():
    from app.config import settings
    from app.llm import llm, LLMClient
    assert settings.zhipu_api_key, "ZHIPU_API_KEY 未配置（backend/.env）"
    c = LLMClient()

    # ---- C1：双模型真实调用 + usage（tools=None 即生产 supervisor/critic 路径）----
    for model in ("glm-4.6", "glm-4.7-flash"):
        try:
            r = await llm().chat(
                [{"role": "user", "content": "只回复两个字：收到"}], model=model)
            record(f"C1 {model}", True,
                   f"text={r.text!r} usage_tokens={r.usage_tokens} "
                   f"（tools=None 路径，v18 项一并验证）")
        except Exception as e:
            record(f"C1 {model}", False, f"{type(e).__name__}: {str(e)[:90]}")

    # ---- C2：embedding-3(dimensions=1024) ----
    try:
        vecs = await llm().embed(["维度探针"])
        record("C2 embedding-3(dimensions=1024)", len(vecs[0]) == 1024,
               f"实测维度={len(vecs[0])}")
    except Exception as e:
        record("C2 embedding-3(dimensions=1024)", False,
               f"{type(e).__name__}: {str(e)[:90]}")

    # ---- embedding-2：不带 dimensions（生产回退路径） / 带 dimensions（观察）----
    try:
        resp2 = c.client.embeddings.create(model="embedding-2", input=["回退探针"])
        d2 = len(resp2.data[0].embedding)
        record("embedding-2 不带 dimensions", d2 == 1024, f"实测维度={d2}")
    except Exception as e:
        record("embedding-2 不带 dimensions", False,
               f"{type(e).__name__}: {str(e)[:90]}")
    try:
        resp3 = c.client.embeddings.create(model="embedding-2",
                                           input=["带参探针"], dimensions=1024)
        record("embedding-2 带 dimensions", True,
               f"未报错，维度={len(resp3.data[0].embedding)}"
               f"（API 忽略该参数——回填 ADR-0005）")
    except Exception as e:
        record("embedding-2 带 dimensions", False,
               f"{type(e).__name__}: {str(e)[:90]}（证实 v17 P1-3 判断——回填 ADR-0005）")

    # ---- 流式 tool_calls 增量拼接专项（flash 免费层）----
    try:
        tools = [{"type": "function", "function": {
            "name": "get_weather", "description": "查询城市天气",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}]
        stream = c.client.chat.completions.create(
            model="glm-4.7-flash",
            messages=[{"role": "user", "content": "查一下北京今天天气"}],
            tools=tools, stream=True, temperature=0.1)
        name, args_buf = None, ""
        for chunk in stream:
            tc = chunk.choices[0].delta.tool_calls
            if not tc:
                continue
            for part in tc:
                if part.function and part.function.name:
                    name = part.function.name
                if part.function and part.function.arguments:
                    args_buf += part.function.arguments
        ok = name == "get_weather" and _try_json(args_buf) is not None
        record("流式 tool_calls 增量拼接", ok,
               f"name={name} args={args_buf!r} 合法JSON={bool(_try_json(args_buf))}")
    except Exception as e:
        record("流式 tool_calls 增量拼接", False,
               f"{type(e).__name__}: {str(e)[:90]}")

    # ---- 真实工具调用往返（agent_loop 生产路径，flash + 工具 schema）----
    try:
        from app.tools import schemas
        r3 = await llm().chat(
            [{"role": "user",
              "content": "请获取贵州茅台600519在2024-01-02至2024-01-15的日线行情"}],
            tools=schemas(["market.price_history"]), model="glm-4.7-flash")
        tc0 = r3.tool_calls[0] if r3.tool_calls else None
        args = json.loads(tc0.arguments) if tc0 else {}
        ok = (tc0 is not None and tc0.name == "market.price_history"
              and args.get("symbol") == "600519")
        record("flash 工具调用往返", ok,
               f"name={tc0.name if tc0 else None} "
               f"args={tc0.arguments if tc0 else None}")
    except Exception as e:
        record("flash 工具调用往返", False,
               f"{type(e).__name__}: {str(e)[:90]}")

    n_pass = sum(1 for _, s, _ in RESULTS if s == "pass")
    print(f"\nM0-§3 实测：{n_pass}/{len(RESULTS)} 项 pass（blocked 项当次结果如实记录）")

if __name__ == "__main__":
    asyncio.run(main())
