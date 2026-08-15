import asyncio, json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
import structlog

from app import tasks as task_repo, artifacts, rag, orchestrator, ratelimit
from app.config import settings
from app.db import pool, init_schema, close_pool
from app.events import (bus, replay_then_live, fetch_history,
                        TooManySubscribers)
from app.logging_setup import setup_logging
from app.metrics import (M_HTTP, M_EMB_DIM, M_ADMIN, generate_latest,
                         CONTENT_TYPE_LATEST)

setup_logging()
log = structlog.get_logger()

class ChatIn(BaseModel):
    input: str = Field(min_length=2, max_length=2000)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_schema()
    interrupted, repend = await task_repo.recover_on_boot()
    for tid, rsrv in repend:            # 携带行内 reserved——恢复任务仍占日预留
        orchestrator.submit(tid, reserved=rsrv)
    ok = await rag.probe()
    M_EMB_DIM.set(1 if ok else 0)
    wd = asyncio.create_task(_watchdog_loop())
    log.info("boot", interrupted=len(interrupted),
             requeued=len(repend), vector_ok=ok)
    yield
    wd.cancel()
    await close_pool()

async def _watchdog_loop():
    try:
        while True:
            await asyncio.sleep(30)
            await task_repo.watchdog_tick()
    except asyncio.CancelledError:
        pass

app = FastAPI(title="AlphaDesk", lifespan=lifespan)

@app.middleware("http")
async def _metrics_mw(req: Request, call_next):
    resp = await call_next(req)
    # 未匹配路由（404）回退固定值——原样 URL 做 label 会被随机路径撑爆基数
    route = req.scope.get("route")
    M_HTTP.labels(getattr(route, "path", None) or "/-unmatched",
                  resp.status_code).inc()
    return resp

@app.post("/api/chat")
async def create_task(req: ChatIn, request: Request):
    if not await ratelimit.allow(request.client.host):
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    reserve = settings.budget_max_tokens
    if not await task_repo.reserve_daily(reserve):
        raise HTTPException(429, "今日额度已用尽（每日token预算熔断）")
    try:
        task = await task_repo.create(req.input, reserved=reserve)
    except Exception:
        await task_repo.release_daily(reserve, 0)
        raise
    orchestrator.submit(str(task["id"]), reserved=reserve)
    return {"task_id": str(task["id"]), "trace_id": task["trace_id"]}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    t = await task_repo.get(task_id)
    if not t:
        raise HTTPException(404)
    # asyncpg 默认把 jsonb 返回为 str（db.py 未注册 codec）——必须显式解码：
    # 否则前端拿到 JSON 字符串，taskInfo.result.report 恒 undefined，投研
    # 报告永不渲染（v17 P0-1；events/summary/memory 各自 json.loads，唯此处曾漏）
    result = json.loads(t["result"]) if t["result"] else None
    return {"task_id": str(t["id"]), "trace_id": t["trace_id"],
            "status": t["status"], "result": result,
            "error": t["error"]}

@app.get("/api/tasks/{task_id}/events")
async def get_events(task_id: str, after: int = 0):
    return {"events": [json.loads(e.json())
                       for e in await fetch_history(task_id, after)]}

@app.get("/api/tasks/{task_id}/stream")
async def stream(task_id: str, request: Request, after: int | None = None):
    if not await task_repo.get(task_id):
        raise HTTPException(404)
    header_after = request.headers.get("Last-Event-ID")
    try:
        start = int(header_after) if header_after else (after or 0)
    except ValueError:
        start = after or 0   # 非整数 Last-Event-ID（恶意/旧客户端）→忽略，回退查询参数
    # 订阅必须在此急切执行（异步生成器体不随创建执行）——
    # TooManySubscribers 才能在此变成 429 而非流内部 500。
    try:
        q = bus.subscribe(task_id)
    except TooManySubscribers:
        raise HTTPException(429, "订阅数过多")
    agen = replay_then_live(task_id, start, q=q, poll_s=15.0)

    async def gen():
        try:
            while True:
                try:
                    # 45s 是兜底而非心跳：心跳由内层 poll(~15s)产生 keep_alive。
                    # 触发本超时=内层挂起（如 status 查库卡死）——关流，
                    # 客户端 EventSource 自动重连（携 Last-Event-ID）回放补齐。
                    # （不可把此超时设为与 poll 同长：wait_for 到期会取消并
                    #  摧毁内层生成器——静默期 >poll 的任务流必断，v16 修复）
                    ev = await asyncio.wait_for(agen.__anext__(), timeout=45)
                except asyncio.TimeoutError:
                    return
                except StopAsyncIteration:
                    return
                if ev.type == "keep_alive":
                    yield ": keep-alive\n\n"
                    continue
                yield (f"id: {ev.seq}\nevent: {ev.type}\n"
                       f"data: {ev.json()}\n\n")
                if ev.type == "stream_overflow":
                    return
        finally:
            await agen.aclose()

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache",
                 "X-Accel-Buffering": "no"})

@app.get("/api/artifacts/{art_id}/equity")
async def get_equity(art_id: str):
    try:
        data = await artifacts.load_json(art_id)
    except artifacts.ArtifactNotFound:
        raise HTTPException(404)
    except artifacts.ArtifactGone:
        raise HTTPException(410, "工件已过期，请重新发起任务")
    if "equity_curve" not in data:
        raise HTTPException(400, "该工件不是回测结果")
    return data

@app.get("/api/docs/{doc_id}/page/{page}")
async def doc_page(doc_id: str, page: int):
    """知识库为公开披露文件（产品决策：页级图片无鉴权，ADR-005 记录）。"""
    p = await pool()
    d = await p.fetchrow("SELECT file_path FROM docs WHERE id=$1", doc_id)
    if not d or not d["file_path"]:
        raise HTTPException(404)
    cache = f"{settings.data_dir}/pagecache/{doc_id}_{page}.png"
    if os.path.exists(cache):
        data = await asyncio.to_thread(lambda: open(cache, "rb").read())
        return Response(data, media_type="image/png")

    def render():
        import fitz
        # with 显式管理（v18 P3-3）：fitz doc 与缓存读不依赖解释器 GC 时机，
        # 与全项目资源管理风格一致；Pixmap 在 doc 关闭后仍可用（get_pixmap
        # 时光栅已生成，不引用文档内存）
        with fitz.open(os.path.join(settings.data_dir, d["file_path"])) as doc:
            if not (1 <= page <= doc.page_count):
                return None
            pix = doc[page - 1].get_pixmap(dpi=110)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        tmp = cache + ".tmp"
        pix.save(tmp)
        os.replace(tmp, cache)   # 原子替换：并发渲染同页时读端不会拿到半张PNG（v17 P3-5）
        with open(cache, "rb") as f:
            return f.read()

    data = await asyncio.to_thread(render)
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type="image/png")

@app.post("/api/admin/ttl")
async def admin_ttl(request: Request,
                    x_admin_token: str | None = Header(default=None)):
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(403)
    M_ADMIN.labels("ttl", request.client.host).inc()
    log.info("admin_ttl", ip=request.client.host)
    return {"deleted": await artifacts.ttl_cleanup()}

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/healthz")
async def healthz():
    return {"ok": True, "vector_ok": rag.VECTOR_OK}
