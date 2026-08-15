import { useEffect, useState } from "react";
import ReactECharts from "echarts-for-react";

export default function EquityChart(
  { artifactId }: { artifactId: string }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setErr(null);
    fetch(`/api/artifacts/${artifactId}/equity`)
      .then(async r => {
        // 410=工件过期(TTL 7天)、404=不存在：给出可读文案而非静默/异常
        // （与 api.ts createTask 同族处理，v17 漏了本组件，v18 P3-2）
        if (!r.ok) throw new Error(
          r.status === 410 ? "工件已过期（TTL 7 天），请重新发起任务"
                           : `HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch(e => setErr(e instanceof Error ? e.message : String(e)));
  }, [artifactId]);
  if (err) return (
    <p style={{ fontSize: 12, color: "#c00" }}>净值曲线加载失败：{err}</p>
  );
  if (!data?.equity_curve) return null;
  const dates = Object.keys(data.equity_curve);
  const vals = Object.values(data.equity_curve) as number[];
  return (
    <div>
      <ReactECharts style={{ height: 320 }} option={{
        title: {
          text: `净值曲线 · ${data.symbol ?? ""}（${data.fill}口径）`
        },
        tooltip: { trigger: "axis" },
        xAxis: { type: "category", data: dates },
        yAxis: { type: "value", scale: true },
        series: [{ type: "line", data: vals, showSymbol: false }]
      }} />
      <p style={{ fontSize: 12, color: "#888" }}>
        假设边界：{data.assumptions}
      </p>
    </div>
  );
}
