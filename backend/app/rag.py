import os, re, json, hashlib, asyncio
import fitz
import structlog
from app.config import settings
from app.db import pool
from app import llm as llm_mod
from app.metrics import M_RAG_FALLBACK

log = structlog.get_logger()

VECTOR_OK: bool | None = None
_bm25 = None

def _dim_ok(vec) -> bool:
    return len(vec) == llm_mod.EMBED_DIM

async def probe() -> bool:
    """embedding-3(dimensions) 失败→回退 embedding-2(1024)→再回退
    SiliconFlow bge-m3(1024, OpenAI 兼容, 免费; key 为空跳过该层)。
    维度异常仅标记向量检索不可用，不阻止应用启动。"""
    global VECTOR_OK
    VECTOR_OK = False
    chain = [("zhipu", settings.embedding_model, settings.embedding_dim),
             ("zhipu", settings.embedding_model_fallback, 1024)]
    if settings.siliconflow_api_key:
        chain.append(("siliconflow",
                      settings.siliconflow_embedding_model, 1024))
    for provider, model, dim in chain:
        try:
            llm_mod.EMBED_PROVIDER, llm_mod.EMBED_MODEL, llm_mod.EMBED_DIM = \
                provider, model, dim
            vecs = await llm_mod.llm().embed(["探针"])
            if vecs and len(vecs[0]) == dim:
                VECTOR_OK = True
                log.info("embedding_probe_ok", provider=provider,
                         model=model, dim=dim)
                return True
            log.warning("embedding_probe_dim_mismatch", provider=provider,
                        model=model, expect=dim,
                        got=len(vecs[0]) if vecs else 0)
        except Exception as e:
            log.warning("embedding_probe_fail", provider=provider,
                        model=model, err=str(e))
    return False

def chunk_pdf(path: str, size: int = 600, overlap: int = 80) -> list[dict]:
    """不跨页切块——chunk 的 page 永远准确（引用页级定位的前提）。
    overlap 仅在同页内保留；短页分块可能小于 size（引用精确性优先）。
    size 为目标值非硬上限：无换行符的单行长文本（如整页表格被提取为一行）
    可能超出——对嵌入/BM25/页级引用均无影响，不为此加强切（v18 P3-4）。"""
    chunks: list[dict] = []
    with fitz.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if len(text.strip()) < 20:
                raise ValueError(f"第{pno}页无文本层（扫描件，本期不支持OCR）")
            buf = ""
            for para in text.split("\n"):
                if buf and len(buf) + len(para) > size:
                    chunks.append({"chunk": buf, "page": pno})
                    buf = buf[-overlap:]
                buf += para + "\n"
            if buf.strip():
                chunks.append({"chunk": buf, "page": pno})
    return [{"seq": i, **c} for i, c in enumerate(chunks)]

async def ingest_pdf(path: str, title: str, source_url: str | None,
                     source_type: str) -> str:
    assert source_type in ("official", "curated")
    chunks = await asyncio.to_thread(chunk_pdf, path)
    with open(path, "rb") as f:
        checksum = hashlib.sha1(f.read()).hexdigest()
    doc_id = "doc_" + hashlib.sha1(
        f"{title}|{checksum}".encode()).hexdigest()[:10]
    vecs: list[list[float]] = []
    for i in range(0, len(chunks), 64):
        v = await llm_mod.llm().embed(
            [c["chunk"] for c in chunks[i:i + 64]])
        if not all(_dim_ok(x) for x in v):
            raise RuntimeError(
                f"embedding维度异常(期望{llm_mod.EMBED_DIM})，整批拒写")
        vecs.extend(v)
    with fitz.open(path) as d:
        pages = d.page_count
    p = await pool()
    async with p.acquire() as c:
        async with c.transaction():
            await c.execute(
                "INSERT INTO docs(id, title, source_url, source_type, "
                "pages, file_path, checksum) VALUES($1,$2,$3,$4,$5,$6,$7) "
                "ON CONFLICT(id) DO NOTHING",
                doc_id, title, source_url, source_type, pages,
                os.path.relpath(path, settings.data_dir), checksum)
            await c.execute("DELETE FROM chunks WHERE doc_id=$1", doc_id)
            await c.executemany(
                "INSERT INTO chunks(doc_id, chunk, page, seq, embedding) "
                "VALUES($1,$2,$3,$4,$5::vector)",
                [(doc_id, c_["chunk"], c_["page"], c_["seq"], json.dumps(v))
                 for c_, v in zip(chunks, vecs)])
    global _bm25
    _bm25 = None
    return doc_id

def _tokens(text: str) -> list[str]:
    s = re.sub(r"\s+", "", text)
    return [s[i:i + 2] for i in range(max(len(s) - 1, 1))]

async def _ensure_bm25():
    global _bm25
    if _bm25 is not None:
        return _bm25
    from rank_bm25 import BM25Okapi
    p = await pool()
    rows = await p.fetch("SELECT id, doc_id, chunk, page, seq FROM chunks")
    corpus = [_tokens(r["chunk"]) for r in rows]
    _bm25 = (BM25Okapi(corpus) if corpus else None, rows)
    return _bm25

async def search(query: str, top_k: int = 5) -> dict:
    if VECTOR_OK:
        try:
            qv = (await llm_mod.llm().embed([query]))[0]
            assert _dim_ok(qv)
            p = await pool()
            rows = await p.fetch(
                "SELECT id, doc_id, chunk, page, seq, "
                "1 - (embedding <=> $1::vector) AS sim "
                "FROM chunks ORDER BY embedding <=> $1::vector LIMIT $2",
                json.dumps(qv), top_k)
            return {"mode": "vector", "results": [
                {"doc_id": r["doc_id"], "page": r["page"],
                 "seq": r["seq"], "text": r["chunk"],
                 "score": float(r["sim"])} for r in rows]}
        except Exception:
            # 查询级降级（探针OK但本次embed/查询失败）不可静默——与探针级
            # embedding_dim_ok 区分，计数+日志（v17 P3-8）
            M_RAG_FALLBACK.inc()
            log.warning("rag_vector_fallback_bm25")
    bm, rows = await _ensure_bm25()
    if bm is None:
        return {"mode": "none", "results": [], "note": "知识库为空"}
    scores = bm.get_scores(_tokens(query))
    idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
    return {"mode": "bm25_degraded",
            "note": "向量检索暂不可用，已降级为关键词检索",
            "results": [{"doc_id": rows[i]["doc_id"],
                         "page": rows[i]["page"], "seq": rows[i]["seq"],
                         "text": rows[i]["chunk"],
                         "score": float(scores[i])} for i in idx]}
