"""v37：_compose_result 降级兜底——任何路径（含 _report 赋值前熔断）都产出
可读部分结果（用户实测：critic 修订阶段预算熔断致降级任务空报告）。"""
from app.orchestrator import _compose_result

def test_compose_result_prefers_report():
    ctx = {"_report": "正式报告内容", "_plan": {},
           "n1": {"agent": "writer", "output": "草稿"}}
    r = _compose_result(ctx)
    assert r["report"] == "正式报告内容"
    assert r["nodes"] == {"n1": "草稿"}

def test_compose_result_degraded_uses_last_node_output():
    # _report 未赋值（熔断在撰写前）→ 取**末**节点产出（最完整）并带降级说明
    ctx = {"_plan": {},
           "n1": {"agent": "research", "output": "结论A"},
           "n2": {"agent": "writer", "output": "writer 草稿片段"}}
    r = _compose_result(ctx)["report"]
    assert "writer 草稿片段" in r and "降级" in r and "结论A" not in r

def test_compose_result_degraded_digest_fallback():
    # 无任何非空节点输出 → 黑板摘要 + 明示降级（而非空报告）
    ctx = {"_plan": {}, "n1": {"agent": "research", "output": ""}}
    r = _compose_result(ctx)
    assert "降级" in r["report"]
