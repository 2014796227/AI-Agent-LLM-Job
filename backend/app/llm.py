import asyncio
from dataclasses import dataclass, field
from zhipuai import ZhipuAI
from app.config import settings
from app.metrics import M_LLM_TOKEN

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage_tokens: int = 0

# 探针解析出的实际生效嵌入模型与维度（rag.probe() 设置）
EMBED_MODEL: str = settings.embedding_model
EMBED_DIM: int = settings.embedding_dim
# embed 批次串行（SDK线程安全未承诺）。必须 asyncio.Lock 而非 threading.Lock：
# 后者的 acquire 是同步调用——跨 await 持锁时，争用方会在事件循环线程上原地
# 阻塞，持锁方 API 往返期间整个服务（心跳/SSE/请求）停摆（v17 P1-2）。
# chat() 并发不加锁是刻意不对称：chat 走 httpx，请求级线程安全可支撑（D-4）。
_embed_lock = asyncio.Lock()

class LLMClient:
    def __init__(self):
        self.client = ZhipuAI(api_key=settings.zhipu_api_key)

    def _chat_sync(self, messages, tools, model, temperature):
        return self.client.chat.completions.create(
            model=model, messages=messages, tools=tools,
            temperature=temperature, timeout=60, max_tokens=4096)

    async def chat(self, messages, tools=None, model=None,
                   temperature=0.3) -> ChatResult:
        """async + asyncio.sleep 重试（可中断）。fallback 链如实声明：付费模型
        入口（model≠fallback）失败回落 fallback_model；flash 入口（model 即
        fallback）经去重退化为单模型链——回落 GLM-4.6 违背 ADR-002 的成本
        结构（免费层职责），flash 全挂时让任务失败是既定取舍（v17 D-1）。"""
        if model and model != settings.fallback_model:
            queue = [model, settings.fallback_model]
        else:
            queue = [model or settings.planner_model, settings.fallback_model]
        queue = list(dict.fromkeys(queue))
        last_err = None
        for m in queue:
            for attempt in range(3):
                try:
                    resp = await asyncio.to_thread(
                        self._chat_sync, messages, tools, m, temperature)
                    msg = resp.choices[0].message
                    usage = getattr(resp, "usage", None)
                    tokens = usage.total_tokens if usage else 0
                    M_LLM_TOKEN.labels(m).inc(tokens)
                    tcs = [ToolCall(id=tc.id, name=tc.function.name,
                                    arguments=tc.function.arguments or "{}")
                           for tc in (msg.tool_calls or [])]
                    return ChatResult(text=msg.content or "", tool_calls=tcs,
                                      usage_tokens=tokens)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"LLM 全部重试失败: {last_err}")

    def _embed_sync(self, texts, model, dim):
        # dimensions 是 embedding-3 的能力（默认2048，须显式1024匹配DDL
        # vector(1024)）；embedding-2 固定1024维、无该参数——携带可能被API
        # 拒绝而使回退探针失败→向量检索永久降级BM25，fallback不传（v17 P1-3）
        if model == settings.embedding_model_fallback:
            return self.client.embeddings.create(model=model, input=texts)
        return self.client.embeddings.create(
            model=model, input=texts, dimensions=dim)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量≤64；串行锁；使用探针解析的 (EMBED_MODEL, EMBED_DIM)。"""
        assert len(texts) <= 64
        global EMBED_MODEL, EMBED_DIM
        out: list[list[float]] = []
        for attempt in range(3):
            try:
                async with _embed_lock:
                    resp = await asyncio.to_thread(
                        self._embed_sync, texts, EMBED_MODEL, EMBED_DIM)
                out = [list(d.embedding) for d in resp.data]
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
        return out

_client: LLMClient | None = None
def llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
