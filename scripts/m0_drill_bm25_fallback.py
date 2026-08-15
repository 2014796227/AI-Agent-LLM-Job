"""M0-C3 代码级演练：向量→BM25 查询级降级（探针 OK 但本次 embed 失败）。
在 api 容器内执行：
  docker compose cp scripts/m0_drill_bm25_fallback.py api:/tmp/
  docker compose exec -e PYTHONPATH=/app api python /tmp/m0_drill_bm25_fallback.py
模拟：VECTOR_OK=True（探针通过）+ 无 key（embed 必败）→ search 落入 BM25、
M_RAG_FALLBACK+1、结果带明示 note。前端展示该 note 需真实任务报告（待 key）。"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

async def main():
    from app.db import pool
    from app import rag
    from app.metrics import M_RAG_FALLBACK
    p = await pool()
    await p.execute(
        "INSERT INTO docs(id, title, source_type, pages) "
        "VALUES('doc_drill_c3','C3演练文档','curated',1) "
        "ON CONFLICT(id) DO NOTHING")
    await p.execute("DELETE FROM chunks WHERE doc_id='doc_drill_c3'")
    await p.execute(
        "INSERT INTO chunks(doc_id, chunk, page, seq, embedding) "
        "VALUES('doc_drill_c3',"
        "'贵州茅台2025年年报摘要：营业收入与净利润保持稳定增长。',1,0,$1::vector)",
        json.dumps([0.01] * 1024))
    rag._bm25 = None          # 强制重建 BM25 索引（含演练 chunk）
    rag.VECTOR_OK = True      # 模拟探针 OK——embed 无 key 必失败→查询级降级
    before = M_RAG_FALLBACK._value.get()
    out = await rag.search("茅台 年报 净利润", top_k=3)
    after = M_RAG_FALLBACK._value.get()
    print(f"mode={out['mode']} note={out.get('note')} "
          f"hits={[(r['doc_id'], r['page']) for r in out['results']]} "
          f"M_RAG_FALLBACK {before}->{after}")
    assert out["mode"] == "bm25_degraded"
    assert any(r["doc_id"] == "doc_drill_c3" for r in out["results"])
    assert after == before + 1
    # 还原现场
    rag.VECTOR_OK = None
    rag._bm25 = None
    await p.execute("DELETE FROM chunks WHERE doc_id='doc_drill_c3'")
    await p.execute("DELETE FROM docs WHERE id='doc_drill_c3'")
    print("C3 代码级演练通过（前端降级标注随真实任务报告验证，待 API key）")

if __name__ == "__main__":
    asyncio.run(main())
