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

// v24：工具参数摘要（只取 symbol/query/artifact_id 一类可读键，不整串解析）
const ARGS_KEY = /"(?:symbol|query|artifact_id)"\s*:\s*"([^"]{0,24})"/;
function argBrief(args?: string): string {
  if (!args) return "";
  const m = ARGS_KEY.exec(args);
  return m ? `（${m[1]}…）` : "";
}

export default function Timeline({ events }: { events: Ev[] }) {
  return (
    <div style={{ margin: "16px 0" }}>
      {events.map(e => (
        <div key={e.seq}
             style={{ fontSize: 13, padding: "2px 0", opacity: .85 }}>
          <code>#{e.seq}</code> {LABEL[e.type] ?? e.type}
          {(e.type === "agent_start" || e.type === "agent_end")
            && e.payload?.agent && ` · ${e.payload.agent}`}
          {e.type === "tool_call" && e.payload?.tool
            && ` · ${e.payload.tool}${argBrief(e.payload.args)}`}
          {e.type === "tool_result" && e.payload?.tool
            && ` · ${e.payload.tool} ${e.payload.ok ? "✓" : "✗"}`
              + (e.payload?.ms != null ? ` ${e.payload.ms}ms` : "")}
          {e.type === "critic_verdict" && e.payload?.verdict
            && ` · ${e.payload.verdict}`
              + (e.payload?.issues?.length
                   ? `（${String(e.payload.issues[0]).slice(0, 30)}）` : "")}
          {e.type === "plan_created"
            && Array.isArray(e.payload?.nodes)
            && ` · ${e.payload.nodes.length} 个节点`}
          {e.type === "task_refused" && e.payload?.reason
            && ` · ${String(e.payload.reason).slice(0, 40)}`}
          {e.type === "budget_degraded" && e.payload?.reason
            && ` · ${e.payload.reason}`}
        </div>
      ))}
    </div>
  );
}
