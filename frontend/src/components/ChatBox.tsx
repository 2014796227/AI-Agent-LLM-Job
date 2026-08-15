import { useEffect, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { fetchTask } from "../lib/api";
import { useTaskStream } from "../lib/useTaskStream";
import Timeline from "./Timeline";
import EquityChart from "./EquityChart";

export default function ChatBox() {
  const { events, taskId, error, start } = useTaskStream();
  const [input, setInput] = useState("");
  const [taskInfo, setTaskInfo] = useState<any>(null);

  useEffect(() => { setTaskInfo(null); }, [taskId]);
  // ^ 任务切换即清空上一任务报告——否则新任务运行期间持续显示旧报告（v17 P2-3）

  useEffect(() => {
    const done = events.some(e =>
      e.type === "task_done" || e.type === "task_failed"
      || e.type === "task_interrupted");
    if (done && taskId) fetchTask(taskId).then(setTaskInfo);
  }, [events, taskId]);

  const btEvents = events.filter(
    e => e.type === "artifact_created"
      && e.payload?.kind === "backtest_result"
  );
  const btArt = btEvents.length
    ? btEvents[btEvents.length - 1].payload?.artifact_id
    : undefined;   // 不用 .at(-1)：ES2022 API，tsconfig lib<ES2022 时 tsc -b 失败（v17 P3-9）

  const html = taskInfo?.result?.report
    ? DOMPurify.sanitize(marked.parse(taskInfo.result.report) as string)
    : "";

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 16 }}>
      <form onSubmit={e => {
        e.preventDefault();
        if (input.trim()) { start(input.trim()); setInput(""); }
      }}>
        <input value={input} onChange={e => setInput(e.target.value)}
               placeholder="例如：分析贵州茅台近三年走势，并回测20日均线金叉60日策略（2023-06-01至2026-05-31）"
               style={{ width: "100%", padding: 10 }} />
      </form>
      {error && <div style={{ color: "#c00", padding: 8 }}>
        {/* error 多来源（提交失败/历史拉取失败，v17 P1-4②）——措辞中性化 */}
        出错了：{error}
      </div>}
      <Timeline events={events} />
      {btArt && <EquityChart artifactId={btArt} />}
      {html && <div dangerouslySetInnerHTML={{ __html: html }} />}
      <footer style={{ marginTop: 32, fontSize: 12, color: "#888" }}>
        研究演示用途，非投资建议 · 数据来自公开免费源(AKShare) ·
        回测为向量化近似
      </footer>
    </div>
  );
}
