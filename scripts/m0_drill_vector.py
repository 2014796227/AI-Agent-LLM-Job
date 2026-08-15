"""M0-C2 等价验证（v22）：真实向量检索 drill——bge-m3 嵌入入库 → 向量近邻检索。
在 api 容器内执行：
  docker compose cp scripts/m0_drill_vector.py api:/tmp/
  docker compose exec -e PYTHONPATH=/app api python /tmp/m0_drill_vector.py"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

TEXT = "贵州茅台2025年年报摘要：营业收入与净利润保持稳定增长，现金流充沛。"

async def main():
    from app.db import pool
    from app import rag, llm as llm_mod
    # 本脚本是独立进程——VECTOR_OK 仅在 uvicorn 启动探针里设置，这里自跑一次
    ok = await rag.probe()
    assert ok and rag.VECTOR_OK, "探针未通过，向量层不可用"
    vec = (await llm_mod.llm().embed([TEXT]))[0]
    assert len(vec) == 1024, f"维度异常 {len(vec)}"
    p = await pool()
    await p.execute(
        "INSERT INTO docs(id, title, source_type, pages) "
        "VALUES('doc_drill_vec','向量演练文档','curated',1) "
        "ON CONFLICT(id) DO NOTHING")
    await p.execute("DELETE FROM chunks WHERE doc_id='doc_drill_vec'")
    await p.execute(
        "INSERT INTO chunks(doc_id, chunk, page, seq, embedding) "
        "VALUES('doc_drill_vec',$1,1,0,$2::vector)", TEXT, json.dumps(vec))
    rag._bm25 = None
    out = await rag.search("茅台 年报 净利润", top_k=3)
    hits = [(r["doc_id"], r["page"], round(r["score"], 4))
            for r in out["results"]]
    print(f"mode={out['mode']} hits={hits}")
    assert out["mode"] == "vector"
    assert any(r["doc_id"] == "doc_drill_vec" for r in out["results"])
    idx = await p.fetch("SELECT indexname FROM pg_indexes "
                        "WHERE indexname='idx_chunks_emb'")
    print(f"HNSW idx_chunks_emb 存在={bool(idx)}")
    await p.execute("DELETE FROM chunks WHERE doc_id='doc_drill_vec'")
    await p.execute("DELETE FROM docs WHERE id='doc_drill_vec'")
    rag._bm25 = None
    print("向量检索 drill 通过（1024 维 bge-m3，近邻命中演练 chunk）")

if __name__ == "__main__":
    asyncio.run(main())
