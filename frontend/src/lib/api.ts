export interface Ev { seq: number; type: string; payload: any }

const BASE = "";   // dev: vite proxy → :8000; prod: nginx 同源

export async function createTask(input: string) {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input })
  });
  if (!r.ok) {
    // 错误体可能非 JSON（如 nginx 502 的 HTML 页）——r.json() 会抛 SyntaxError，
    // 回退 statusText，保证用户始终拿到可读信息（v17 P3-4）
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? r.statusText; } catch { /* 非 JSON */ }
    throw new Error(detail);
  }
  return r.json() as Promise<{ task_id: string; trace_id: string }>;
}

export const fetchEvents = (id: string, after = 0) =>
  fetch(`${BASE}/api/tasks/${id}/events?after=${after}`)
    .then(r => r.json() as Promise<{ events: Ev[] }>);

export const fetchTask = (id: string) =>
  fetch(`${BASE}/api/tasks/${id}`).then(r => r.json());

export const EVENT_TYPES = [
  "task_started", "plan_created", "agent_start", "agent_end",
  "llm_response", "tool_call", "tool_result", "artifact_created",
  "critic_verdict", "task_refused", "budget_degraded", "stream_overflow",
  "task_done", "task_failed", "task_interrupted"
] as const;

export function subscribe(taskId: string, after: number,
                          onEvent: (e: Ev) => void,
                          onEnd?: () => void, onFatal?: () => void) {
  const es = new EventSource(
    `${BASE}/api/tasks/${taskId}/stream?after=${after}`);
  const handler = (type: string) => (raw: MessageEvent) => {
    onEvent({ seq: Number(raw.lastEventId), type,
              payload: JSON.parse(raw.data) });
    if (["task_done", "task_failed", "task_interrupted",
         "stream_overflow"].includes(type)) {
      es.close();
      onEnd?.();
    }
  };
  // 致命错误（如 429 订阅上限）：按 EventSource 规范连接永久失败、不会自动
  // 重连——必须显式回调，否则时间线无提示静默停止（v17 P1-4③）。
  // CONNECTING 是浏览器内置自动重连（网络抖动），不动作防与其叠加。
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) onFatal?.();
  };
  for (const t of EVENT_TYPES)
    es.addEventListener(t, handler(t) as EventListener);
  return es;
}
