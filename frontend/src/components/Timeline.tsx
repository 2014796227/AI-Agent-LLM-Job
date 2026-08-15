import type { Ev } from "../lib/api";   // 类型导入（防 verbatimModuleSyntax，v17 P3-9）

const LABEL: Record<string, string> = {
  task_started: "任务开始", plan_created: "规划完成",
  agent_start: "Agent 启动", agent_end: "Agent 完成",
  llm_response: "模型响应", tool_call: "工具调用",
  tool_result: "工具返回", artifact_created: "工件生成",
  critic_verdict: "审查裁决", task_refused: "白名单拒绝",
  budget_degraded: "预算降级", stream_overflow: "流溢出重连",
  task_done: "任务完成", task_failed: "任务失败",
  task_interrupted: "任务中断"
};

export default function Timeline({ events }: { events: Ev[] }) {
  return (
    <div style={{ margin: "16px 0" }}>
      {events.map(e => (
        <div key={e.seq}
             style={{ fontSize: 13, padding: "2px 0", opacity: .85 }}>
          <code>#{e.seq}</code> {LABEL[e.type] ?? e.type}
          {e.payload?.agent && ` · ${e.payload.agent}`}
          {e.payload?.tool && ` · ${e.payload.tool}`}
          {e.payload?.ms != null && ` · ${e.payload.ms}ms`}
          {e.payload?.verdict && ` · ${e.payload.verdict}`}
        </div>
      ))}
    </div>
  );
}
