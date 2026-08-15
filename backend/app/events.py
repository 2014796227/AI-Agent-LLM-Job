import asyncio, json
from dataclasses import dataclass
from app.db import pool
from app.metrics import M_BUS_DROP

TERMINAL_EVENTS = {"task_done", "task_failed", "task_interrupted"}
TERMINAL_STATUS = {"done", "failed", "degraded", "interrupted"}
MAX_SUBS_PER_TASK = 5

class TooManySubscribers(Exception): ...

@dataclass
class Event:
    seq: int
    task_id: str
    type: str
    payload: dict
    def json(self) -> str:
        return json.dumps({"seq": self.seq, "type": self.type,
                           "payload": self.payload}, ensure_ascii=False)

class EventBus:
    """不变式：先 INSERT task_events → 再推订阅队列。
    溢出闭环：队列满→标记该订阅→replay 发送 stream_overflow→关流→
    客户端携带 after 重连回放补齐（事件已落库，最终不丢）。"""
    def __init__(self, maxsize: int = 2000):
        self.subs: dict[str, list[asyncio.Queue]] = {}
        self._overflow: set[int] = set()
        self.maxsize = maxsize

    async def emit(self, task_id: str, type_: str,
                   payload: dict | None = None) -> Event:
        p = await pool()
        async with p.acquire() as c:
            row = await c.fetchrow(
                "INSERT INTO task_events(task_id, type, payload) VALUES($1,$2,$3) "
                "RETURNING id", task_id, type_,
                json.dumps(payload or {}, ensure_ascii=False))
        ev = Event(seq=row["id"], task_id=task_id, type=type_, payload=payload or {})
        for q in self.subs.get(task_id, []):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                M_BUS_DROP.inc()
                self._overflow.add(id(q))
        return ev

    def subscribe(self, task_id: str) -> asyncio.Queue:
        lst = self.subs.setdefault(task_id, [])
        if len(lst) >= MAX_SUBS_PER_TASK:
            raise TooManySubscribers(task_id)
        q = asyncio.Queue(maxsize=self.maxsize)
        lst.append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue):
        lst = self.subs.get(task_id, [])
        if q in lst:
            lst.remove(q)
        self._overflow.discard(id(q))
        if not lst:
            self.subs.pop(task_id, None)

    def overflowed(self, q: asyncio.Queue) -> bool:
        return id(q) in self._overflow

bus = EventBus()

async def fetch_history(task_id: str, after: int = 0) -> list[Event]:
    p = await pool()
    rows = await p.fetch(
        "SELECT id, type, payload FROM task_events "
        "WHERE task_id=$1 AND id>$2 ORDER BY id", task_id, after)
    return [Event(seq=r["id"], task_id=task_id, type=r["type"],
                  payload=json.loads(r["payload"])) for r in rows]

async def replay_then_live(task_id: str, after: int = 0, *,
                           q: "asyncio.Queue | None" = None,
                           bus_: "EventBus | None" = None,
                           fetch=None, status=None, poll_s: float = 15.0):
    """三段式：①订阅(可由调用方急切完成后注入q) ②回放 ③实时按 seq 去重。
    终止保证：回放段已见终态事件→立即返回；实时段收到终态事件→返回；
    poll 超时→查状态，终态→补漏后返回；溢出→stream_overflow→返回；
    仍在运行→yield keep_alive 心跳（SSE 层转 `: keep-alive` 注释——
    不入 task_events 表，EventSource 原生忽略注释故客户端不可见）。"""
    b = bus_ or bus
    fetch = fetch or fetch_history
    if status is None:
        from app import tasks as task_repo
        status = task_repo.get
    if q is None:
        q = b.subscribe(task_id)
    try:
        last = after
        terminal_seen = False
        for ev in await fetch(task_id, after=last):
            last = ev.seq
            if ev.type in TERMINAL_EVENTS:
                terminal_seen = True
            yield ev
        if terminal_seen:
            return
        if b.overflowed(q):
            yield Event(seq=last, task_id=task_id,
                        type="stream_overflow", payload={})
            return
        t = await status(task_id)
        if t is None:
            return
        if t["status"] in TERMINAL_STATUS:
            for ev in await fetch(task_id, after=last):
                last = ev.seq
                yield ev
            return
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=poll_s)
            except asyncio.TimeoutError:
                if b.overflowed(q):
                    yield Event(seq=last, task_id=task_id,
                                type="stream_overflow", payload={})
                    return
                t = await status(task_id)
                if t is None:          # 与回放段对称（任务行实际不可删，防御）
                    return
                if t["status"] in TERMINAL_STATUS:
                    for ev2 in await fetch(task_id, after=last):
                        last = ev2.seq
                        yield ev2
                    return
                yield Event(seq=last, task_id=task_id,
                            type="keep_alive", payload={})
                continue
            if ev.seq <= last:
                continue
            last = ev.seq
            yield ev
            if ev.type in TERMINAL_EVENTS:
                return
    finally:
        b.unsubscribe(task_id, q)
