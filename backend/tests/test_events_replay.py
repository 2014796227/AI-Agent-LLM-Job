import asyncio, pytest
from app.events import Event, EventBus, replay_then_live
from app.metrics import M_BUS_DROP

def _ev(seq, type_="x", task_id="t1"):
    return Event(seq=seq, task_id=task_id, type=type_, payload={})

@pytest.mark.asyncio
async def test_replay_race_no_gap_no_dup():
    """订阅后、回放查询前，新事件(seq=3)已落库且已在队列——1,2,3各一次。
    （fake 协程无真挂起点会让 consume 在插入前同步跑完并 unsubscribe——
    故用 inserted 事件门控把"订阅→回放查询"窗口确定性拉宽。）"""
    store = [_ev(1), _ev(2)]
    bus = EventBus()
    inserted = asyncio.Event()

    async def fake_fetch(task_id, after=0):
        if not inserted.is_set():
            await inserted.wait()
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        return {"status": "done"}

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=0.05):
            got.append(ev.seq)

    c = asyncio.create_task(consume())
    await asyncio.sleep(0.01)            # consume 已 subscribe，fetch 阻塞在门控
    e3 = _ev(3)
    bus.subs["t1"][0].put_nowait(e3)     # 先入队
    store.append(e3)                     # 再落库
    inserted.set()                       # 放行回放查询
    await asyncio.wait_for(c, timeout=2)
    assert got == [1, 2, 3]

@pytest.mark.asyncio
async def test_replay_dedupe_overlap():
    """回放与队列重叠（e3 既落库又入队）：实时段按 seq 去重，仅出现一次。
    （status 返回 running 使生成器真正阻塞在实时段 q.get——
    否则同步跑完后测试再 put 会 KeyError。）"""
    e3 = _ev(3)
    store = [_ev(1), _ev(2), e3]
    bus = EventBus()

    async def fake_fetch(task_id, after=0):
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        return {"status": "running"}

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=0.05):
            got.append(ev.seq)

    c = asyncio.create_task(consume())
    await asyncio.sleep(0.01)            # consume 已进入实时段阻塞在 q.get()
    q = bus.subs["t1"][0]
    q.put_nowait(e3)                     # 重复 seq=3（回放段已见）
    q.put_nowait(_ev(4, type_="task_done"))
    await asyncio.wait_for(c, timeout=2)
    assert got == [1, 2, 3, 4]

@pytest.mark.asyncio
async def test_live_terminal_event_closes_stream():
    store = [_ev(1)]
    bus = EventBus()

    async def fake_fetch(task_id, after=0):
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        return {"status": "running"}

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=0.05):
            # 过滤心跳：极端调度抖动下先于推送触发的 poll 超时会 yield keep_alive
            if ev.type != "keep_alive":
                got.append(ev.seq)

    c = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    for q in bus.subs["t1"]:
        q.put_nowait(_ev(2, type_="task_done"))
    await asyncio.wait_for(c, timeout=2)
    assert got == [1, 2]

@pytest.mark.asyncio
async def test_replay_terminal_seen_returns_immediately():
    """回放段已含终态事件→生成器立即结束（不再等 poll）。"""
    store = [_ev(1), _ev(2, type_="task_done")]
    bus = EventBus()
    status_called = [False]

    async def fake_fetch(task_id, after=0):
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        status_called[0] = True
        return {"status": "running"}   # 故意：状态未更新也不该挂起

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=5.0):
            got.append(ev.seq)

    await asyncio.wait_for(consume(), timeout=1)
    assert got == [1, 2]
    assert not status_called[0]

@pytest.mark.asyncio
async def test_overflow_notifies_and_closes():
    bus = EventBus(maxsize=2)
    store = []

    async def fake_fetch(task_id, after=0):
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        return {"status": "running"}

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=0.05):
            got.append(ev.type)

    c = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    for i in range(5):
        q = bus.subs["t1"][0]
        ev = _ev(i + 1, type_="tool_call")
        store.append(ev)
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            M_BUS_DROP.inc()
            bus._overflow.add(id(q))
    await asyncio.wait_for(c, timeout=2)
    assert got[-1] == "stream_overflow"

@pytest.mark.asyncio
async def test_keepalive_yielded_when_running():
    """实时段 poll 超时且任务仍在运行→yield keep_alive 心跳且流不终止
    （v16：心跳由内层产生，外层不再以同长超时摧毁生成器）。"""
    store = [_ev(1)]
    bus = EventBus()

    async def fake_fetch(task_id, after=0):
        return [e for e in store if e.seq > after]

    async def fake_status(task_id):
        return {"status": "running"}

    got = []

    async def consume():
        async for ev in replay_then_live(
                "t1", 0, bus_=bus, fetch=fake_fetch,
                status=fake_status, poll_s=0.02):
            got.append(ev.type)

    c = asyncio.create_task(consume())
    await asyncio.sleep(0.09)          # ≥3 个 poll 周期，无真实事件
    c.cancel()
    with pytest.raises(asyncio.CancelledError):
        await c
    ka = [t for t in got if t == "keep_alive"]
    assert got[0] == "x"               # 回放段的 seq=1 事件仍首先送达
    assert len(ka) >= 2                # 心跳持续产生、流未被终止
