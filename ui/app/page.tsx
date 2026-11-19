"use client";

import Chart from "@/components/Chart";
import Status from "@/components/Status";
import { factionColor } from "@/components/WorldMap";
import { type Overview, percent, runApi, useApi } from "@/lib/api";

export default function OverviewPage() {
  const loaded = useApi<Overview>(runApi("overview"));
  return (
    <Status loaded={loaded}>
      {(run) => (
        <>
          <h1>
            {run.scenario_id} <span className="muted">{run.scenario_version}</span>
          </h1>
          <p className="lede">
            {run.event_count} events over {run.ticks} ticks, judged under the {run.profile_id} profile
            from {run.perspective}&apos;s side.
          </p>

          <div className="cards">
            <div className="card">
              <div className="label">Result</div>
              <div className="value">{run.result}</div>
            </div>
            <div className="card">
              <div className="label">Verdict</div>
              <div className={`value verdict-${run.verdict}`}>{run.verdict}</div>
              <div className="muted">confidence {percent(run.confidence)}</div>
            </div>
            <div className="card">
              <div className="label">Score</div>
              <div className="value">{run.score.toFixed(2)}</div>
              <div className="muted">0 worst, 1 best</div>
            </div>
            {run.losses.map((side) => (
              <div className="card" key={side.faction}>
                <div className="label">{side.faction} losses</div>
                <div className="value" style={{ color: factionColor(side.faction) }}>
                  {side.lost.length} of {side.units}
                </div>
              </div>
            ))}
          </div>

          <div className="two">
            <section className="panel">
              <h2>Score on each axis</h2>
              <Chart
                label="Score on each evaluation axis"
                height={Object.keys(run.scores).length * 28 + 40}
                option={{
                  grid: { left: 130, right: 30, top: 10, bottom: 20 },
                  xAxis: { type: "value", min: 0, max: 1 },
                  yAxis: {
                    type: "category",
                    inverse: true,
                    data: Object.keys(run.scores).map((axis) => axis.replaceAll("_", " ")),
                  },
                  series: [
                    {
                      type: "bar",
                      data: Object.values(run.scores),
                      itemStyle: { color: "#2d5bd7" },
                      label: { show: true, position: "right", formatter: "{c}" },
                    },
                  ],
                  tooltip: {},
                }}
              />
            </section>
            <section className="panel">
              <h2>Who was lost</h2>
              {run.losses.map((side) => (
                <p key={side.faction}>
                  <strong>{side.faction}</strong> lost {side.lost.length} of {side.units}
                  {side.lost.length > 0 && ":"}
                  {side.lost.map((unit) => (
                    <span key={unit.entity_id}>
                      <br />
                      {unit.name} at tick {unit.tick}, by {unit.by_name}
                    </span>
                  ))}
                </p>
              ))}
            </section>
          </div>

          <div className="two">
            <section>
              <h2>Findings</h2>
              <ul className="plain">
                {run.key_findings.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
            <section>
              <h2>Why it is not better</h2>
              <ul className="plain">
                {run.failure_causes.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <h2>Test next</h2>
              <ul className="plain">
                {run.recommended_next_tests.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </Status>
  );
}
