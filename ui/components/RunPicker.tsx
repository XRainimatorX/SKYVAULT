"use client";

import { useEffect, useState } from "react";
import { currentRun, type RunEntry, withRun } from "@/lib/api";

/** Which run the screens show: the service's runs, newest first (Phase 21). */
export default function RunPicker() {
  const [runs, setRuns] = useState<RunEntry[] | null>(null);
  const [run, setRun] = useState("latest");

  useEffect(() => {
    setRun(currentRun());
    fetch("/api/runs")
      .then((response) => (response.ok ? response.json() : []))
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  if (runs === null) return null;
  if (runs.length === 0) {
    return <p className="runs muted">No run yet — submit one: skyvault run &lt;scenario&gt;</p>;
  }
  const shown = run === "latest" ? runs[0].run : run;
  return (
    <label className="runs">
      Run{" "}
      <select
        aria-label="Run"
        value={shown}
        onChange={(event) => {
          window.location.search = withRun("", event.target.value).replace(/^\?/, "?");
        }}
      >
        {runs.map((entry) => (
          <option key={entry.run} value={entry.run}>
            {entry.run} · {entry.scenario_id} {entry.scenario_version} · {entry.result}
          </option>
        ))}
      </select>
    </label>
  );
}
