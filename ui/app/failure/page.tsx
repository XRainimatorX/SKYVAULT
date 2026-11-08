"use client";

import Chart from "@/components/Chart";
import Markdown from "@/components/Markdown";
import Status from "@/components/Status";
import { type Failure, percent, useApi } from "@/lib/api";

/** Survival 1 → green, at the threshold → amber, 0 → red. */
function heat(rate: number, threshold: number): string {
  if (rate >= threshold) return `color-mix(in srgb, var(--good) ${Math.round(rate * 45)}%, transparent)`;
  return `color-mix(in srgb, var(--bad) ${Math.round((1 - rate) * 45)}%, transparent)`;
}

function FailureMap({ map }: { map: Failure }) {
  const rows = map.rows.filter((row) => row.applicable);
  return (
    <>
      <div className="cards">
        <div className="card">
          <div className="label">Survives without stress</div>
          <div className="value">{percent(map.baseline_survival)}</div>
        </div>
        <div className="card">
          <div className="label">Crushed by</div>
          <div className="value">{map.crushing_variable ?? "nothing"}</div>
          {map.crushing_assumption && <div className="muted">breaks the {map.crushing_assumption} assumption</div>}
        </div>
        <div className="card">
          <div className="label">Best alternative</div>
          <div className="value">{map.best_alternative ?? "none"}</div>
        </div>
        <div className="card">
          <div className="label">First loss, on average</div>
          <div className="value">
            {map.how_fast.mean_first_loss_tick ? `tick ${map.how_fast.mean_first_loss_tick.toFixed(1)}` : "—"}
          </div>
        </div>
      </div>

      <h2>Survival under each stress</h2>
      <p className="muted">
        Share of {map.repeat_count} runs per level not judged a failure; a level breaks below{" "}
        {percent(map.survival_threshold)}.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Stress</th>
              {map.levels.map((level) => (
                <th key={level} className="heat">
                  {level}
                </th>
              ))}
              <th>Breaks at</th>
              <th className="num">Sensitivity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.variable}>
                <td>
                  {row.variable.replaceAll("_", " ")}
                  {row.variable === map.crushing_variable && <span className="badge">crushing</span>}
                </td>
                {row.survival.map((rate, n) => (
                  <td
                    key={n}
                    className="heat"
                    style={rate === null ? undefined : { background: heat(rate, map.survival_threshold) }}
                  >
                    {rate === null ? "—" : percent(rate)}
                  </td>
                ))}
                <td>{row.breaking_level ?? "never"}</td>
                <td className="num">{row.sensitivity.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <Chart
          label="Survival rate by stress level for each variable"
          option={{
            tooltip: { trigger: "axis", valueFormatter: (v) => `${Math.round(Number(v) * 100)}%` },
            legend: { type: "scroll", bottom: 0 },
            grid: { left: 50, right: 20, top: 20, bottom: 60 },
            xAxis: { type: "category", data: ["none", ...map.levels] },
            yAxis: { type: "value", min: 0, max: 1, axisLabel: { formatter: (v: number) => percent(v) } },
            series: rows.map((row) => ({
              name: row.variable.replaceAll("_", " "),
              type: "line" as const,
              data: [map.baseline_survival, ...row.survival],
            })),
          }}
        />
      </section>

      <div className="two">
        <section>
          <h2>Where it holds</h2>
          <ul className="plain">
            {map.conditions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <h2>Where it fails</h2>
          <ul className="plain">
            {map.failure_points.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
        <section>
          <h2>Alternatives</h2>
          <ul className="plain">
            {map.alternatives.map((alt) => (
              <li key={alt.scenario_version}>
                <strong>{alt.scenario_version}</strong>: {alt.verdict.replaceAll("_", " ")} (survives{" "}
                {percent(alt.baseline_survival_rate)} without stress)
              </li>
            ))}
          </ul>
        </section>
      </div>

      {map.recommendations && (
        <section className="panel" style={{ marginTop: 16 }}>
          <Markdown text={map.recommendations} />
        </section>
      )}
    </>
  );
}

export default function FailurePage() {
  const loaded = useApi<Failure>("/api/failure");
  return (
    <>
      <h1>Failure map</h1>
      <p className="lede">The plan made worse on purpose: where, why and how fast it breaks.</p>
      <Status loaded={loaded}>{(map) => <FailureMap map={map} />}</Status>
    </>
  );
}
