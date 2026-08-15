import { useEffect, useRef, useState } from "react";
import { createTask, fetchEvents, subscribe, type Ev } from "./api";

export function useTaskStream() {
  const [events, setEvents] = useState<Ev[]>([]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastSeq = useRef(0);
  const esRef = useRef<EventSource | null>(null);
  const eventsRef = useRef<Ev[]>([]);

  useEffect(() => { eventsRef.current = events; }, [events]);

  const append = (e: Ev) => {
    if (e.seq <= lastSeq.current) return;   // 按 seq 单调去重
    lastSeq.current = e.seq;
    setEvents(prev => [...prev, e]);
  };

  async function start(input: string) {
    setEvents([]);
    setError(null);
    lastSeq.current = 0;
    try {
      const { task_id } = await createTask(input);
      setTaskId(task_id);
      localStorage.setItem("alphadesk:task", task_id);
    } catch (e) {                  // 429 日预算熔断 / 网络错误——必须给用户反馈
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (!taskId) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let fatalTries = 0;           // 连续致命失败计数（v18 P3-1）
    const open = () => {          // 递归重连：onEnd/onFatal 永不丢失
      if (closed) return;
      esRef.current?.close();
      esRef.current = subscribe(
        taskId, lastSeq.current,
        e => { fatalTries = 0; append(e); },  // 事件到达=连接健康，清零计数
        () => {
          const last = eventsRef.current[eventsRef.current.length - 1];
          if (last?.type === "stream_overflow") {
            open();               // 溢出→立即重订阅回放补齐
          }
          // 终态事件：无需重连（任务已结束）
        },
        () => {                   // 致命错误(429等)→3s退避后重订阅（v17 P1-4③）
          if (closed) return;
          // 陈旧 taskId（如重建过DB后 localStorage 残留）的 /stream 恒 404→
          // EventSource 永久失败：无界重试既无意义也无提示——连续 5 次致命
          // 失败后停止并向用户明示（v18 P3-1）
          if (++fatalTries >= 5) {
            setError("事件流订阅失败（任务可能不存在或已过期），请重新发起任务");
            return;
          }
          retry = setTimeout(open, 3000);
        });
    };
    (async () => {
      try {
        // 先拉历史再订阅没有丢失窗口：订阅携带 after=lastSeq，服务端三段式
        // "先急切订阅→回放 after 之后的全部落库事件→实时按 seq 去重"
        // 恰好覆盖两步之间新产生的事件（服务端有单测固化此契约）
        const { events: hist } = await fetchEvents(taskId, 0);
        if (closed) return;   // 竞态守卫（v17 P1-4①）：taskId 已切换时弃用
                              // 过期响应——否则旧任务 events 覆盖新任务、
                              // lastSeq 被全局 seq 污染而吞掉新任务事件
        if (hist.length) lastSeq.current = hist[hist.length - 1].seq;
        setEvents(hist);
        open();
      } catch (e) {           // 网络错误不再静默（v17 P1-4②）
        if (!closed) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      esRef.current?.close();
    };
  }, [taskId]);

  useEffect(() => {
    const saved = localStorage.getItem("alphadesk:task");
    if (saved && !taskId) setTaskId(saved);
  }, []);

  return { events, taskId, error, start };
}
