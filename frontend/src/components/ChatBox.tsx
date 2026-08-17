import { useEffect, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { fetchTask } from "../lib/api";
import { useTaskStream } from "../lib/useTaskStream";
import Timeline from "./Timeline";
import EquityChart from "./EquityChart";

// v25（M4）：报告中的 [[doc_id#页码]] 引用转为可点击链接，新标签页打开
// 服务端渲染的原 PDF 页图片（GET /api/docs/{doc_id}/page/{page}）。
const CITE_RE = /\[\[(doc_[A-Za-z0-9]+)#(\d+)\]\]/g;
function linkifyCitations(md: string): string {
  return md.replace(CITE_RE, (_m, doc: string, page: string) =>
    `[📄原文第${page}页](/api/docs/${doc}/page/${page})`);
}
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  const el = node as Element;
  if (el.tagName === "A" &&
      (el.getAttribute("href") || "").startsWith("/api/docs/")) {
    el.setAttribute("target", "_blank");
    el.setAttribute("rel", "noopener noreferrer");
  }
});

// v35（用户反馈驱动）：失败/降级在前端明示原因与应对建议——不再只有时间线上
// 一行"任务失败"。映射按错误文本特征匹配，未命中给通用建议。
const FAIL_HINT: Array<[RegExp, string]> = [
  [/1305|访问量过大|1302|速率限制|429/,
   "模型服务端限流（免费层在请求密集或高峰时段常见）——等待 2~3 分钟后重新提问即可；数据与系统本身无故障。"],
  [/1113|余额不足/,
   "模型 API 余额/资源包不足——需要为账户充值或更换 key。"],
  [/lease_expired|process_restart|interrupted/,
   "任务执行被中断（服务重启或执行超时）——重新提问即可。"],
  [/IndexError|行情|Connection/i,
   "行情数据源暂时不可用——可稍后重试，或换一个标的（6 位 A 股个股/场内 ETF）。"],
];
function failHint(err: string): string {
  for (const [re, hint] of FAIL_HINT) if (re.test(err)) return hint;
  return "偶发性失败——重新提问通常即可解决；若持续失败请把下方错误详情反馈给维护者。";
}

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
    ? DOMPurify.sanitize(
        marked.parse(linkifyCitations(taskInfo.result.report)) as string)
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
      {(() => {
        const SOURCE_LABEL: Record<string, string> = {
          eastmoney: "东方财富（AKShare 实时拉取）",
          tencent: "腾讯财经（AKShare 实时拉取）",
          cache: "24h 内缓存（原始源：东方财富/腾讯财经）",
        };
        const srcs = events
          .filter(e => e.type === "artifact_created"
            && e.payload?.trace_meta?.source)
          .map(e => e.payload.trace_meta);
        if (!srcs.length) return null;
        return (
          <div style={{ margin: "12px 0", padding: 10, border: "1px solid #ddd",
                       borderRadius: 6, fontSize: 12, color: "#444",
                       background: "#fafafa" }}>
            <strong>数据溯源</strong>（真实接口抓取，可独立核查）
            {srcs.map((m: any, i: number) => (
              <div key={i} style={{ marginTop: 4 }}>
                · {m.symbol}：{SOURCE_LABEL[m.source] || m.source} ·
                {m.rows} 行 · 区间 {m.start}~{m.end}
                {m.fixture ? " · 评测冻结快照" : ""}
              </div>
            ))}
            <div style={{ color: "#999", marginTop: 6 }}>
              核查方式：任意行情 App（东方财富/同花顺/腾讯自选股）对照同日 K 线；
              年报数字点报告中的引用直接打开原 PDF 页。
            </div>
          </div>
        );
      })()}
      {taskInfo && ["failed", "interrupted"].includes(taskInfo.status) && (
        <div style={{ margin: "12px 0", padding: 12, border: "1px solid #e3a008",
                     background: "#fff8e6", borderRadius: 6, fontSize: 13 }}>
          <strong>任务{taskInfo.status === "failed" ? "失败" : "中断"}：</strong>
          {failHint(taskInfo.error || "")}
          <div style={{ color: "#888", marginTop: 6, fontSize: 12,
                        wordBreak: "break-all" }}>
            错误详情：{taskInfo.error || "（无）"}
          </div>
        </div>
      )}
      {taskInfo?.status === "degraded" && (
        <div style={{ margin: "12px 0", padding: 10, border: "1px solid #e3a008",
                     background: "#fffdf0", borderRadius: 6, fontSize: 12,
                     color: "#7a5c00" }}>
          任务降级：触发预算/时限保护，以下为带标注的部分结果（完整数据已按引用保留）。
        </div>
      )}
      {btArt && <EquityChart artifactId={btArt} />}
      {html && <div dangerouslySetInnerHTML={{ __html: html }} />}
      <footer style={{ marginTop: 32, fontSize: 12, color: "#888" }}>
        研究演示用途，非投资建议 · 行情：东方财富/腾讯财经(AKShare 公开接口) ·
        知识库：巨潮资讯网官方年报 PDF（引用可点开原页） · 回测为向量化近似
      </footer>
    </div>
  );
}
