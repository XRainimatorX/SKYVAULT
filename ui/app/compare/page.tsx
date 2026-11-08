"use client";

import Chart from "@/components/Chart";
import Status from "@/components/Status";
import { type Comparison, percent, useApi } from "@/lib/api";

const LABELS: Record<string, string> = {
  win_rate: "Win rate",
  failure_frequency: "Judged a failure",
  mean_hp_lost: "HP lost",
  mean_risk_events: "Risk events",
  mean_score: "Score",
};

function Compare({ batch }: { batch: Comparison }) {
  const conflict = batch.conflict_package;
  return (
    <>
      <p className="lede">
        {batch.variants.length} variants × {batch.repeat_count} runs ({batch.total_runs} in all), seen from{" "}
        {batch.perspective}.
      </p>

      <div className="cards">
        {Object.entries(batch.best).map(([metric, variant]) => (
          <div className="card" key={metric}>
            <div className="label">Best {LABELS[metric] ?? metric}</div>
            <div className="value" style={{ fontSize: 17 }}>
              {variant}
            </div>
          </div>
        ))}
      </div>

      <section className="panel">
        <Chart
          label="Win rate and failure rate for each variant"
          height={batch.variants.length * 34 + 70}
          option={{
            tooltip: { trigger: "axis", valueFormatter: (v) => `${Math.round(Number(v) * 100)}%` },
            legend: { bottom: 0 },
            grid: { left: 10, right: 30, top: 10, bottom: 40, containLabel: true },
            xAxis: { type: "value", min: 0, max: 1, axisLabel: { formatter: (v: number) => percent(v) } },
            yAxis: {
              type: "category",
              inverse: true,
              data: batch.variants.map((v) => v.variant_id),
              axisLabel: { width: 150, overflow: "truncate" },
            },
            series: [
              { name: "Win rate", type: "bar", data: batch.variants.map((v) => v.win_rate), itemStyle: { color: "#23824d" } },
              {
                name: "Judged a failure",
                type: "bar",
                data: batch.variants.map((v) => v.failure_frequency),
                itemStyle: { color: "#c8423b" },
              },
            ],
          }}
        />
      </section>

      <h2>Every variant</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Variant</th>
              <th>Kind</th>
              <th className="num">Win rate (95% range)</th>
              <th className="num">Judged a failure</th>
              <th className="num">HP lost</th>
              <th className="num">Risk events</th>
              <th className="num">Score</th>
            </tr>
          </thead>
          <tbody>
            {batch.variants.map((v) => (
              <tr key={v.variant_id}>
                <td>{v.variant_id}</td>
                <td>{v.kind}</td>
                <td className="num">
                  {percent(v.win_rate)} ({percent(v.win_rate_ci[0])}–{percent(v.win_rate_ci[1])})
                </td>
                <td className="num">{percent(v.failure_frequency)}</td>
                <td className="num">{v.mean_hp_lost}</td>
                <td className="num">{v.mean_risk_events}</td>
                <td className="num">{v.mean_score.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {conflict && (
        <>
          <h2>Conflicting orders</h2>
          <ul className="plain">
            {conflict.conflicts.map((c) => (
              <li key={c.conflict_id}>
                {c.reason}{" "}
                {c.conflict_types.map((t) => (
                  <span className="badge" key={t}>
                    {t.replace("_conflict", "")}
                  </span>
                ))}
              </li>
            ))}
          </ul>
          <h2>Each branch against doing nothing</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>Orders</th>
                  <th>What happened</th>
                  <th className="num">Score vs. no orders</th>
                </tr>
              </thead>
              <tbody>
                {[...conflict.branch_runs, conflict.baseline].map((branch) => (
                  <tr key={branch.branch_id}>
                    <td>{branch.branch_id === "none" ? "no orders" : branch.branch_id}</td>
                    <td>{branch.action_set.join(", ") || "—"}</td>
                    <td>{branch.result_summary}</td>
                    <td className="num">
                      {branch.evaluation_delta.mean_score >= 0 ? "+" : ""}
                      {branch.evaluation_delta.mean_score.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="notice" style={{ marginTop: 16 }}>
            <strong>
              Decision required: {conflict.recommendation_to_nexus.required_decision ? "yes" : "no"}
            </strong>
            <p style={{ margin: "6px 0 0" }}>{conflict.recommendation_to_nexus.decision_reason}</p>
          </div>
        </>
      )}
    </>
  );
}

export default function ComparePage() {
  const loaded = useApi<Comparison>("/api/comparison");
  return (
    <>
      <h1>Compare plans</h1>
      <Status loaded={loaded}>{(batch) => <Compare batch={batch} />}</Status>
    </>
  );
}
